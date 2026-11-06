"""Auction lifecycle enforcement (close / force-close transitions).

Mechanism: for every active RFQ we schedule an APScheduler *date* job at
exactly its current_close and forced_close times, and reinstall those jobs
whenever a bid extends the deadline (scheduler.reschedule, called from the
bid path). A coarse interval tick can't close auctions to the exact second or
track soft-close extensions precisely; exact jobs can. The 15s tick below
stays on purely as a reconciliation safety net (restarts, missed jobs) — with
the exact jobs in place it normally finds nothing to do.

Every transition takes the same SELECT ... FOR UPDATE lock on the RFQ row as
submit_bid, so closing never races an in-flight bid: if a bid just extended
current_close, a close job that fires a moment later re-locks the row, sees
the extended deadline and does nothing.
"""
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import or_

from . import audit, auction, events, models
from .database import SessionLocal

_scheduler = BackgroundScheduler(timezone="UTC")
_jobs_lock = threading.Lock()

_EVENT_BY_STATUS = {
    models.RFQStatus.CLOSED: "closed",
    models.RFQStatus.FORCE_CLOSED: "force_closed",
}


def _transition(rfq_id: int) -> str | None:
    """Close an RFQ if its deadline has passed; serialized against bids by
    the row lock. Returns the transition name if one happened."""
    db = SessionLocal()
    try:
        rfq = (
            db.query(models.RFQ)
            .filter(models.RFQ.id == rfq_id)
            .with_for_update()
            .one_or_none()
        )
        if not rfq or rfq.status != models.RFQStatus.ACTIVE:
            return None
        now = datetime.utcnow()
        if now >= rfq.forced_close:
            rfq.status = models.RFQStatus.FORCE_CLOSED
        elif now >= rfq.current_close:
            rfq.status = models.RFQStatus.CLOSED
        else:
            return None  # a concurrent bid extended the deadline — nothing to do
        db.commit()
        db.refresh(rfq)
        # Notify + log after the lock is released / commit is done.
        events.publish({
            "type": _EVENT_BY_STATUS[rfq.status],
            "rfq_id": rfq.id,
            "summary": auction.rfq_summary(rfq).model_dump(mode="json"),
        })
        event_type = ("FORCE_CLOSE" if rfq.status == models.RFQStatus.FORCE_CLOSED
                      else "CLOSE")
        reason = ("forced close time reached"
                  if event_type == "FORCE_CLOSE" else "bid close time reached")
        audit.log(rfq.id, event_type, reason=reason,
                  old_close=rfq.current_close, new_close=rfq.current_close)
        return _EVENT_BY_STATUS[rfq.status]
    finally:
        db.close()


def _schedule_exact(rfq: models.RFQ) -> None:
    """Install exact one-shot close jobs for one RFQ (replaces existing ones)."""
    with _jobs_lock:
        _scheduler.add_job(
            _transition, "date", run_date=rfq.current_close.replace(tzinfo=timezone.utc),
            id=f"close:{rfq.id}", kwargs={"rfq_id": rfq.id}, replace_existing=True)
        _scheduler.add_job(
            _transition, "date", run_date=rfq.forced_close.replace(tzinfo=timezone.utc),
            id=f"force:{rfq.id}", kwargs={"rfq_id": rfq.id}, replace_existing=True)


def reschedule(rfq_id: int) -> None:
    """(Re)install the exact close jobs for one RFQ — called after RFQ creation
    and after every accepted bid, because an extension moves current_close
    forward and the exact job must move with it."""
    db = SessionLocal()
    try:
        rfq = db.query(models.RFQ).get(rfq_id)
        if rfq and rfq.status == models.RFQStatus.ACTIVE:
            _schedule_exact(rfq)
    finally:
        db.close()


def tick() -> None:
    """Reconciliation safety net run every 15s: closes anything whose exact
    job was missed. Normally a no-op."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due = (
            db.query(models.RFQ.id)
            .filter(models.RFQ.status == models.RFQStatus.ACTIVE,
                    or_(models.RFQ.current_close <= now,
                        models.RFQ.forced_close <= now))
            .all()
        )
    finally:
        db.close()
    for (rfq_id,) in due:
        _transition(rfq_id)


def start() -> None:
    _scheduler.start()
    db = SessionLocal()
    try:
        for rfq in (db.query(models.RFQ)
                    .filter(models.RFQ.status == models.RFQStatus.ACTIVE)
                    .all()):
            _schedule_exact(rfq)
    finally:
        db.close()
    _scheduler.add_job(tick, "interval", seconds=15,
                       id="auction_tick", replace_existing=True)
