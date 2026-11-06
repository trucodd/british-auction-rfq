"""Tiny in-process pub/sub used to push "state changed" hints over SSE.

Events carry no payload beyond a type + rfq_id on purpose: they mean
"something about this RFQ changed — refetch it". Clients always read the
authoritative state from the REST endpoints, so a dropped event only costs
one missed notification, never consistency.

Threading note: FastAPI runs sync routes in a worker threadpool and the
auction-close scheduler runs in its own APScheduler thread, so publishing
happens off the main event loop. `set_main_loop()` memorises that loop at
startup and `publish()` then crosses threads with `call_soon_threadsafe`.
"""
import asyncio
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
        pass  # slow client: drop the hint, its fallback poll will catch up


def publish(event: dict) -> None:
    """Deliver a change hint to the RFQ's topic and the global list topic."""
    topics = [f"rfq:{event.get('rfq_id')}", "rfqs"]
    for topic in topics:
        for q in list(_subscribers.get(topic, ())):
            if _main_loop is not None:
                _main_loop.call_soon_threadsafe(_enqueue, q, event)
            else:
                _enqueue(q, event)
