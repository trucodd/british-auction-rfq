"""Thread-safe in-process pub/sub that pushes auction updates over SSE.

Events carry the updated state itself, not just a "refetch" hint:
`submit_bid` publishes the new bid, ranking and (possibly extended) closing
time; the scheduler publishes the closed/force-closed status. Clients apply
these payloads directly, so N connected viewers of one RFQ no longer fire N
identical GETs at the backend on every event (thundering herd on /api/rfqs).
REST remains the resync path for reconnects, missed events and
payload-less clients.

Every event is stamped with `ts` (server epoch ms) so clients can align their
countdown with the server clock — close/extension validation happens
server-side only, and the browser's own clock never participates.

Threading note: FastAPI runs sync routes in a worker threadpool and the
auction-close scheduler runs in its own APScheduler thread, so publishing
happens off the main event loop. `set_main_loop()` memorises that loop at
startup and `publish()` then crosses threads with `call_soon_threadsafe`.
"""
import asyncio
import time
from collections import defaultdict
from typing import Optional

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def subscribe(topic: str) -> asyncio.Queue:
    """Register a queue for a topic ("rfq:<id>" or "rfqs")."""
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers[topic].add(q)
    return q


def unsubscribe(topic: str, q: asyncio.Queue) -> None:
    _subscribers[topic].discard(q)


def _enqueue(q: asyncio.Queue, event: dict) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass  # slow client: it resyncs from REST on its next poll/basic event


def publish(event: dict) -> None:
    """Deliver one update (with payload) to the RFQ's topic and the global list topic."""
    event.setdefault("ts", int(time.time() * 1000))  # server epoch ms, for clock sync
    topics = [f"rfq:{event.get('rfq_id')}", "rfqs"]
    for topic in topics:
        for q in list(_subscribers.get(topic, ())):
            if _main_loop is not None:
                _main_loop.call_soon_threadsafe(_enqueue, q, event)
            else:
                _enqueue(q, event)
