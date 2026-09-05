"""
Broadcaster - fan-out of JSON-serialisable messages to SSE subscribers.

Safe to call from the event loop and from threadpool workers (sync routes).
"""
import asyncio
import logging
from typing import List, Tuple

logger = logging.getLogger("BeamState.Broadcast")


class Broadcaster:
    def __init__(self, queue_size: int = 200):
        self.queue_size = queue_size
        # (queue, loop) pairs; the loop is needed for thread-safe publishing
        self.subscribers: List[Tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        self.subscribers.append((queue, asyncio.get_running_loop()))
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        self.subscribers = [(q, l) for (q, l) in self.subscribers if q is not queue]

    def publish(self, message: dict):
        """Deliver to every subscriber. Slow subscribers are dropped."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        dead = []
        for queue, loop in self.subscribers:
            try:
                if loop is current_loop:
                    queue.put_nowait(message)
                else:
                    loop.call_soon_threadsafe(self._put, queue, message, dead)
            except asyncio.QueueFull:
                dead.append(queue)
            except RuntimeError:
                dead.append(queue)  # loop closed
        for q in dead:
            self.unsubscribe(q)

    def _put(self, queue: asyncio.Queue, message: dict, dead: list):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            self.unsubscribe(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self.subscribers)


# Live node status and configuration-change notifications for the dashboard
status_stream = Broadcaster()
