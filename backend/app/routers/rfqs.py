import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import auction, events, models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/rfqs", tags=["rfqs"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # don't let reverse proxies buffer the stream
}


def _sse_stream(topic: str) -> StreamingResponse:
    """Server-Sent Events stream of "state changed" hints for a topic."""

    async def gen():
        q = events.subscribe(topic)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # keeps proxies and the client happy
        finally:
            events.unsubscribe(topic, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=_SSE_HEADERS)


@router.get("/stream")
async def stream_rfqs():
    """Global stream — one event whenever any RFQ changes (list page)."""
    return _sse_stream("rfqs")


@router.get("/{rfq_id}/stream")
async def stream_rfq(rfq_id: int):
    """Per-RFQ stream — one event whenever that auction changes (detail page)."""
    return _sse_stream(f"rfq:{rfq_id}")


def _to_out(rfq: models.RFQ) -> schemas.RFQOut:
    lowest = min((b.total_price for b in rfq.bids), default=None)
    return schemas.RFQOut(
        id=rfq.id,
        reference_id=rfq.reference_id,
        name=rfq.name,
        pickup_date=rfq.pickup_date,
        bid_start=rfq.bid_start,
        original_close=rfq.original_close,
        current_close=rfq.current_close,
        forced_close=rfq.forced_close,
        status=rfq.status,
        lowest_bid=lowest,
    )


@router.post("", response_model=schemas.RFQOut, status_code=201)
def create_rfq(payload: schemas.RFQCreate, db: Session = Depends(get_db)):
    if db.query(models.RFQ).filter_by(reference_id=payload.reference_id).first():
        raise HTTPException(400, "reference_id already exists")

    rfq = models.RFQ(
        reference_id=payload.reference_id,
        name=payload.name,
        pickup_date=payload.pickup_date,
        bid_start=payload.bid_start,
        original_close=payload.bid_close,
        current_close=payload.bid_close,
        forced_close=payload.forced_close,
        status=models.RFQStatus.ACTIVE,
    )
    rfq.config = models.AuctionConfig(**payload.config.model_dump())
    db.add(rfq)
    db.commit()
    db.refresh(rfq)
    events.publish({"type": "rfq_created", "rfq_id": rfq.id})
    return _to_out(rfq)


@router.get("", response_model=list[schemas.RFQOut])
def list_rfqs(db: Session = Depends(get_db)):
    rfqs = db.query(models.RFQ).order_by(models.RFQ.id.desc()).all()
    return [_to_out(r) for r in rfqs]


@router.get("/{rfq_id}", response_model=schemas.RFQDetail)
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.query(models.RFQ).get(rfq_id)
    if not rfq:
        raise HTTPException(404, "rfq not found")

    ranked = auction.compute_rankings(rfq.bids)
    bids = [schemas.BidOut(**{**b.__dict__, "rank": rank}) for b, rank in ranked]
    logs = sorted(rfq.logs, key=lambda l: l.created_at, reverse=True)

    return schemas.RFQDetail(
        **_to_out(rfq).model_dump(),
        config=schemas.AuctionConfigOut.model_validate(rfq.config),
        bids=bids,
        logs=[schemas.ActivityLogOut.model_validate(l) for l in logs],
    )


@router.post("/{rfq_id}/bids", response_model=schemas.BidOut, status_code=201)
def place_bid(rfq_id: int, payload: schemas.BidCreate, db: Session = Depends(get_db)):
    rfq = db.query(models.RFQ).get(rfq_id)
    if not rfq:
        raise HTTPException(404, "rfq not found")

    try:
        bid = auction.submit_bid(db, rfq, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))

    rank_map = {b.id: r for b, r in auction.compute_rankings(rfq.bids)}
    return schemas.BidOut(**{**bid.__dict__, "rank": rank_map.get(bid.id)})