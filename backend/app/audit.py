"""Asynchronous activity-log writer.

Problem solved (write amplification): every accepted bid used to write the BID
(and maybe EXTENSION) activity rows inside the same locked transaction that
computes the new ranking. Under a final-second burst across many RFQs those
inserts extended the hot path: extra WAL churn, row contention on
activity_logs, and a slower 201 response for the supplier.

Instead, submit_bid commits only rfqs + bids (the rows that must be consistent
with the RFQ row lock), then hands log rows to this module: a single daemon
thread drains the queue and batches inserts in its own connection every ~0.5s.

Trade-off: an unflushed log row can be lost on a hard crash — bids themselves
are never lost, only their audit lines. Activity rows also land a few hundred
milliseconds after the related SSE event; the REST endpoints remain the
source of truth for a full, consistent detail view.
"""
import threading
import time
from collections import deque
from datetime import datetime

from . import models
from .database import SessionLocal

_queue: deque = deque()
_lock = threading.Lock()
_thread: threading.Thread | None = None


def log(rfq_id: int, event_type: str, *, reason: str | None = None,
        old_close: datetime | None = None, new_close: datetime | None = None,
        extra: dict | None = None) -> None:
    """Queue one activity row for the batched background writer.

    Signature mirrors the old synchronous `_log`; callers don't need a session
    and nothing DB-related happens on the caller's critical path.
    """
    global _thread
    if _thread is None:
        with _lock:
            if _thread is None:
                _thread = threading.Thread(
                    target=_writer, daemon=True, name="activity-log-writer")
                _thread.start()
    _queue.append({
        "rfq_id": rfq_id,
        "event_type": event_type,
        "reason": reason,
        "old_close": old_close,
        "new_close": new_close,
        "extra": extra or {},
        "created_at": datetime.utcnow(),  # real event time, not flush time
    })


def _writer() -> None:
    while True:
        if not _queue:
            time.sleep(0.5)
            continue
        batch = list(_queue)
        _queue.clear()
        db = SessionLocal()
        try:
            db.add_all([models.ActivityLog(**row) for row in batch])
            db.commit()
        except Exception:
            # Push the batch back and retry on the next cycle (DB down, deadlock...).
            db.rollback()
            for row in reversed(batch):
                _queue.appendleft(row)
            time.sleep(1.0)
        finally:
            db.close()
