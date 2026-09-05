"""
Trace Manager - node state change events.

Events are kept in an in-memory ring buffer for the live SSE stream and
persisted to the state_events table so history survives restarts.
"""
import asyncio
import time
import logging
from collections import deque
from typing import List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger("BeamState.TraceManager")


@dataclass
class TraceEvent:
    """A single state change event"""
    timestamp: float
    node_id: str
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
    Manages state change events. Supports SSE streaming to multiple clients
    and persistence to SQLite.
    """

    def __init__(self, max_events: int = 500):
        self.max_events = max_events
        self.events: deque = deque(maxlen=max_events)
        self.subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self.persist = True

    # --- Persistence ----------------------------------------------------

    def _persist(self, event: TraceEvent):
        if not self.persist:
            return
        try:
            from database import SessionLocal
            from models import StateEventDB
            db = SessionLocal()
            try:
                db.add(StateEventDB(**asdict(event)))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to persist trace event: {e}")

    def load_history(self):
        """Fill the ring buffer from the database (call once after init_db)."""
        try:
            from database import SessionLocal
            from models import StateEventDB
            db = SessionLocal()
            try:
                rows = (db.query(StateEventDB)
                          .order_by(StateEventDB.timestamp.desc())
                          .limit(self.max_events).all())
            finally:
                db.close()
            for row in reversed(rows):
                self.events.append(TraceEvent(
                    timestamp=row.timestamp, node_id=row.node_id, node_name=row.node_name,
                    ip=row.ip, group_name=row.group_name, old_status=row.old_status,
                    new_status=row.new_status, reason=row.reason))
            logger.info(f"Loaded {len(rows)} state events from history")
        except Exception as e:
            logger.error(f"Failed to load trace history: {e}")

    def prune(self, retention_days: int) -> int:
        """Delete persisted events older than retention_days. Returns rows removed."""
        if not retention_days or retention_days <= 0:
            return 0
        try:
            from database import SessionLocal
            from models import StateEventDB
            cutoff = time.time() - retention_days * 86400
            db = SessionLocal()
            try:
                removed = db.query(StateEventDB).filter(StateEventDB.timestamp < cutoff).delete()
                db.commit()
            finally:
                db.close()
            if removed:
                logger.info(f"Pruned {removed} state events older than {retention_days} days")
            return removed
        except Exception as e:
            logger.error(f"Failed to prune trace history: {e}")
            return 0

    def query(self, limit: int = 100, node_id: Optional[str] = None, hours: Optional[float] = None) -> List[dict]:
        """Read events from the database, oldest first within the selected window."""
        try:
            from database import SessionLocal
            from models import StateEventDB
            db = SessionLocal()
            try:
                q = db.query(StateEventDB)
                if node_id:
                    q = q.filter(StateEventDB.node_id == node_id)
                if hours:
                    q = q.filter(StateEventDB.timestamp >= time.time() - hours * 3600)
                rows = q.order_by(StateEventDB.timestamp.desc()).limit(limit).all()
            finally:
                db.close()
            out = []
            for row in reversed(rows):
                out.append(TraceEvent(
                    timestamp=row.timestamp, node_id=row.node_id, node_name=row.node_name,
                    ip=row.ip, group_name=row.group_name, old_status=row.old_status,
                    new_status=row.new_status, reason=row.reason).to_dict())
            return out
        except Exception as e:
            logger.error(f"Failed to query trace history: {e}")
            return self.get_recent_events(limit)

    # --- Live stream ----------------------------------------------------

    async def emit(self, event: TraceEvent):
        """Add a new event, persist it and notify all subscribers"""
        async with self._lock:
            self.events.append(event)
            logger.debug(f"Trace event: {event.node_name} {event.old_status} -> {event.new_status} ({event.reason})")

            dead_queues = []
            for queue in self.subscribers:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead_queues.append(queue)

            for q in dead_queues:
                self.subscribers.remove(q)

        await asyncio.to_thread(self._persist, event)

    def get_recent_events(self, limit: int = 100) -> List[dict]:
        """Get recent events from the in-memory buffer as list of dicts"""
        events = list(self.events)[-limit:]
        return [e.to_dict() for e in events]

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self.subscribers.append(queue)
        logger.info(f"New trace subscriber. Total: {len(self.subscribers)}")
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        async with self._lock:
            if queue in self.subscribers:
                self.subscribers.remove(queue)
        logger.info(f"Trace subscriber removed. Total: {len(self.subscribers)}")


# Global singleton
trace_manager = TraceManager()
