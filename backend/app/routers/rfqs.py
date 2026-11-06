import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

from .. import auction, events, models, schemas, scheduler
from ..database import get_db

router = APIRouter(prefix="/api/rfqs", tags=["rfqs"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # don't let reverse proxies buffer the stream
}


def _sse_stream(topic: str) -> StreamingResponse:
    """Server-Sent Events stream of auction updates for a topic.

    Events carry the updated state (summary and/or full detail), so clients
    apply the push directly instead of refetching via REST — N viewers of one
    RFQ no longer means N simultaneous GETs per event.
    """

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


def _summary_json(rfq: models.RFQ) -> dict:
    return auction.rfq_summary(rfq).model_dump(mode="json")


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
    events.publish({"type": "rfq_created", "rfq_id": rfq.id,
                    "summary": _summary_json(rfq)})
    # Install the exact close-time jobs for the new RFQ.
    scheduler.reschedule(rfq.id)
    return auction.rfq_summary(rfq)


@router.get("", response_model=list[schemas.RFQOut])
def list_rfqs(db: Session = Depends(get_db)):
    rfqs = db.query(models.RFQ).order_by(models.RFQ.id.desc()).all()
    return [auction.rfq_summary(r) for r in rfqs]


@router.get("/{rfq_id}", response_model=schemas.RFQDetail)
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.query(models.RFQ).get(rfq_id)
    if not rfq:
        raise HTTPException(404, "rfq not found")
    return auction.detail_out(rfq)


@router.post("/{rfq_id}/bids", response_model=schemas.BidOut, status_code=201)
def place_bid(rfq_id: int, payload: schemas.BidCreate, db: Session = Depends(get_db)):
    # submit_bid locks the RFQ row (SELECT ... FOR UPDATE), retries on
    # serialization failures, and commits the bid + any extension atomically.
    try:
        bid = auction.submit_bid(db, rfq_id, payload)
    except LookupError:
        db.rollback()  # release the row lock taken before the record was found
        raise HTTPException(404, "rfq not found")
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except sa_exc.DBAPIError:
        # Transient contention the retry budget couldn't absorb (hot RFQ row).
        raise HTTPException(503, "auction is busy, please retry shortly",
                            headers={"Retry-After": "1"})

    # Fresh post-commit state for the SSE payload — pushed directly so all
    # watching clients can skip the REST refetch that a hint would trigger.
    rfq = db.query(models.RFQ).get(rfq_id)
    rank_map = {b.id: r for b, r in auction.compute_rankings(rfq.bids)}
    out = schemas.BidOut(**{**bid.__dict__, "rank": rank_map.get(bid.id)})

    events.publish({
        "type": "bid",
        "rfq_id": rfq.id,
        "bid": out.model_dump(mode="json"),
        "summary": _summary_json(rfq),
        "detail": auction.detail_out(rfq).model_dump(mode="json"),
    })
    # current_close may have moved (extension) → the exact close-time jobs
    # must move with it.
    scheduler.reschedule(rfq_id)
    return out
