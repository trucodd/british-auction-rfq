from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from . import auction, models
from .database import SessionLocal

_scheduler = BackgroundScheduler()


def tick():
    """Runs every N seconds: closes auctions whose current/forced close has passed."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        active = (
            db.query(models.RFQ)
            .filter(models.RFQ.status == models.RFQStatus.ACTIVE)
            .all()
        )
        for rfq in active:
            if now >= rfq.forced_close:
                rfq.status = models.RFQStatus.FORCE_CLOSED
                auction._log(db, rfq.id, "FORCE_CLOSE",
                             reason="forced close time reached",
                             old_close=rfq.current_close,
                             new_close=rfq.current_close)
            elif now >= rfq.current_close:
                rfq.status = models.RFQStatus.CLOSED
                auction._log(db, rfq.id, "CLOSE",
                             reason="bid close time reached",
                             old_close=rfq.current_close,
                             new_close=rfq.current_close)
        db.commit()
    finally:
        db.close()


def start():
    _scheduler.add_job(tick, "interval", seconds=15,
                       id="auction_tick", replace_existing=True)
    _scheduler.start()