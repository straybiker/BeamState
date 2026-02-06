"""
Trace Manager - In-memory circular buffer for state change events.
Provides real-time streaming via SSE.
"""
import asyncio
import time
import logging
from collections import deque
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger("BeamState.TraceManager")


@dataclass
class TraceEvent:
    """A single state change event"""
    timestamp: float
    node_id: int
    node_name: str
    ip: str
    group_name: str
    old_status: str
    new_status: str
    reason: str
    
    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))
        }


class TraceManager:
    """
    Manages state change events in memory.
    Supports SSE streaming to multiple clients.
    """
    
    def __init__(self, max_events: int = 500):
        self.max_events = max_events
        self.events: deque[TraceEvent] = deque(maxlen=max_events)
        self.subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()
    
    async def emit(self, event: TraceEvent):
        """Add a new event and notify all subscribers"""
        async with self._lock:
            self.events.append(event)
            logger.debug(f"Trace event: {event.node_name} {event.old_status} -> {event.new_status} ({event.reason})")
            
            # Notify all subscribers
            dead_queues = []
            for queue in self.subscribers:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Queue is full, subscriber is too slow - mark for removal
                    dead_queues.append(queue)
            
            # Remove dead queues
            for q in dead_queues:
                self.subscribers.remove(q)
    
    def get_recent_events(self, limit: int = 100) -> List[dict]:
        """Get recent events as list of dicts"""
        events = list(self.events)[-limit:]
        return [e.to_dict() for e in events]
    
    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to new events, returns a queue that receives events"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self.subscribers.append(queue)
        logger.info(f"New trace subscriber. Total: {len(self.subscribers)}")
        return queue
    
    async def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from events"""
        async with self._lock:
            if queue in self.subscribers:
                self.subscribers.remove(queue)
        logger.info(f"Trace subscriber removed. Total: {len(self.subscribers)}")


# Global singleton
trace_manager = TraceManager()
