from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from . import models, schemas


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


def _log(db, rfq_id, event_type, *, reason=None, old_close=None,
         new_close=None, extra=None):
    db.add(models.ActivityLog(
        rfq_id=rfq_id,
        event_type=event_type,
        reason=reason,
        old_close=old_close,
        new_close=new_close,
        extra=extra or {},
    ))


# ---------- the bid submission + extension engine ----------

def submit_bid(db: Session, rfq: models.RFQ, payload: schemas.BidCreate) -> models.Bid:
    now = datetime.utcnow()

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

    _log(db, rfq.id, "BID",
         reason=f"{payload.supplier_name} bid {total:.2f}",
         extra={"bid_id": bid.id, "total_price": total,
                "rank_after": new_ranks[bid.id]})

    # ---------- extension check ----------
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

    if reasons and rfq.current_close < rfq.forced_close:
        old_close = rfq.current_close
        proposed = rfq.current_close + timedelta(minutes=cfg.extension_minutes)
        new_close = min(proposed, rfq.forced_close)   # never past forced_close
        rfq.current_close = new_close

        _log(db, rfq.id, "EXTENSION",
             reason="; ".join(reasons),
             old_close=old_close,
             new_close=new_close,
             extra={
                 "trigger_window_minutes": cfg.trigger_window_minutes,
                 "extension_minutes": cfg.extension_minutes,
                 "capped_by_forced_close": new_close == rfq.forced_close,
             })

    db.commit()
    db.refresh(bid)
    return bid