"""Auction engine: bid submission, ranking and soft-close extensions.

Concurrency model: every attempt re-acquires the RFQ row with
SELECT ... FOR UPDATE inside its own transaction, so two simultaneous bids on
the same RFQ are fully serialized at the database level — the second one sees
the first one's extended current_close and ranking, and extension calculations
can never run twice on the same deadline. On a serialization failure /
deadlock (heavy final-second load, hot row) the whole transaction is retried.

Clock rule: "now" is always the server clock (UTC). Client clocks never
participate in close/extension decisions; the SSE event carries `ts` (server
epoch ms) so clients can align their countdown with the server.
"""
import time as _time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

from . import audit, models, schemas

_MAX_ATTEMPTS = 4  # first try + up to 3 retries on transient DB errors
_RETRYABLE_PGCODES = ("40001", "40P01")  # serialization_failure, deadlock_detected


# ---------- helpers ----------

def _ranked(bids):
    """Return [(bid, rank)] ordered by lowest total_price, then earliest bid."""
    ordered = sorted(bids, key=lambda b: (b.total_price, b.created_at))
    return [(b, i + 1) for i, b in enumerate(ordered)]


def _l1(bids) -> Optional[models.Bid]:
    if not bids:
        return None
    return sorted(bids, key=lambda b: (b.total_price, b.created_at))[0]


def compute_rankings(bids):
    return _ranked(bids)


def rfq_summary(rfq: models.RFQ) -> schemas.RFQOut:
    """Summary projection shared by the REST list endpoint and SSE payloads."""
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


def detail_out(rfq: models.RFQ) -> schemas.RFQDetail:
    """Full detail projection (bids + ranks + logs + config) shared by the REST
    detail endpoint and the SSE bid payload."""
    ranked = compute_rankings(rfq.bids)
    bids = [schemas.BidOut(**{**b.__dict__, "rank": rank}) for b, rank in ranked]
    logs = sorted(rfq.logs, key=lambda l: l.created_at, reverse=True)
    return schemas.RFQDetail(
        **rfq_summary(rfq).model_dump(),
        config=schemas.AuctionConfigOut.model_validate(rfq.config),
        bids=bids,
        logs=[schemas.ActivityLogOut.model_validate(l) for l in logs],
    )


# ---------- the bid submission + extension engine ----------

def submit_bid(db: Session, rfq_id: int, payload: schemas.BidCreate) -> models.Bid:
    """Validate + insert one bid and maybe extend current_close.

    Loads and locks the RFQ row itself (SELECT ... FOR UPDATE): only one
    transaction may evaluate/extend current_close at a time. The critical
    transaction touches rfqs + bids only; activity-log rows are written
    asynchronously (see audit.py) so they don't prolong the lock or the
    supplier's response time.
    """
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return _submit_locked(db, rfq_id, payload)
        except sa_exc.DBAPIError as e:
            db.rollback()  # discard the aborted transaction before retrying
            pgcode = getattr(getattr(e, "orig", None), "pgcode", None)
            if pgcode not in _RETRYABLE_PGCODES or attempt == _MAX_ATTEMPTS - 1:
                raise
            _time.sleep(0.05 * (2 ** attempt))  # brief backoff: 50/100/200ms
    raise RuntimeError("unreachable")


def _submit_locked(db: Session, rfq_id: int, payload: schemas.BidCreate) -> models.Bid:
    now = datetime.utcnow()

    # Row-level lock: serialize concurrent bids/extensions on this RFQ.
    try:
        rfq = (
            db.query(models.RFQ)
            .filter(models.RFQ.id == rfq_id)
            .with_for_update()
            .one()
        )
    except sa_exc.NoResultFound:
        raise LookupError("rfq not found") from None

    if rfq.status != models.RFQStatus.ACTIVE:
        raise ValueError("auction is not active")
    if now < rfq.bid_start:
        raise ValueError("bidding has not started yet")
    if now >= rfq.forced_close:
        raise ValueError("forced close time reached")
    if now >= rfq.current_close:
        raise ValueError("bid close time reached")

    total = payload.freight_charge + payload.origin_charge + payload.destination_charge

    # Snapshot BEFORE inserting the new bid
    old_bids = db.query(models.Bid).filter(models.Bid.rfq_id == rfq.id).all()
    old_l1 = _l1(old_bids)
    old_ranks = {b.id: r for b, r in _ranked(old_bids)}

    # Insert bid
    bid = models.Bid(
        rfq_id=rfq.id,
        supplier_name=payload.supplier_name,
        freight_charge=payload.freight_charge,
        origin_charge=payload.origin_charge,
        destination_charge=payload.destination_charge,
        total_price=total,
        transit_days=payload.transit_days,
        quote_valid_until=payload.quote_valid_until,
        created_at=now,
    )
    db.add(bid)
    db.flush()

    new_bids = old_bids + [bid]
    new_l1 = _l1(new_bids)
    new_ranks = {b.id: r for b, r in _ranked(new_bids)}

    # ---------- extension check (serialized by the row lock above) ----------
    cfg = rfq.config
    window_start = rfq.current_close - timedelta(minutes=cfg.trigger_window_minutes)
    in_window = window_start <= now < rfq.current_close

    reasons: list[str] = []
    if in_window:
        if cfg.trigger_on_bid:
            reasons.append("bid received inside trigger window")

        if cfg.trigger_on_any_rank_change:
            # Only existing suppliers' rank shifts count. A new bid at the bottom
            # does not shift anyone → not a trigger.
            shifted = any(
                old_ranks.get(bid_id) != new_ranks.get(bid_id)
                for bid_id in old_ranks
            )
            if shifted:
                reasons.append("existing supplier rank changed inside trigger window")

        if cfg.trigger_on_l1_change:
            if old_l1 is None or (new_l1 and old_l1.id != new_l1.id):
                reasons.append("L1 (lowest bidder) changed inside trigger window")

    extended = False
    old_close = rfq.current_close
    new_close = old_close
    if reasons and rfq.current_close < rfq.forced_close:
        proposed = rfq.current_close + timedelta(minutes=cfg.extension_minutes)
        new_close = min(proposed, rfq.forced_close)  # never past forced_close
        rfq.current_close = new_close
        extended = True

    # Critical commit — rfqs + bids only; activity rows go through audit.py.
    db.commit()
    db.refresh(bid)

    audit.log(rfq.id, "BID",
              reason=f"{payload.supplier_name} bid {total:.2f}",
              extra={"bid_id": bid.id, "total_price": total,
                     "rank_after": new_ranks[bid.id]})
    if extended:
        audit.log(rfq.id, "EXTENSION",
                  reason="; ".join(reasons),
                  old_close=old_close,
                  new_close=new_close,
                  extra={
                      "trigger_window_minutes": cfg.trigger_window_minutes,
                      "extension_minutes": cfg.extension_minutes,
                      "capped_by_forced_close": new_close == rfq.forced_close,
                  })

    return bid
