"""
Availability statistics derived from persisted state events.

For a window [start, now]:
- monitored seconds  = window time not spent in PAUSED
- downtime seconds   = time spent in DOWN
- availability       = 1 - downtime / monitored
- down_count         = number of transitions into DOWN inside the window

PENDING (a failed check under retry) is not counted as downtime; only a
confirmed DOWN is.
"""
import time
from typing import Dict, Optional
from sqlalchemy import func, and_
from database import SessionLocal
from models import StateEventDB


def _last_state_before(db, start: float) -> Dict[str, str]:
    """node_id -> status the node was in at 'start', from the latest event before it."""
    latest = (db.query(StateEventDB.node_id, func.max(StateEventDB.timestamp).label("ts"))
                .filter(StateEventDB.timestamp < start)
                .group_by(StateEventDB.node_id)
                .subquery())
    rows = (db.query(StateEventDB)
              .join(latest, and_(StateEventDB.node_id == latest.c.node_id,
                                 StateEventDB.timestamp == latest.c.ts))
              .all())
    return {r.node_id: r.new_status for r in rows}


def compute_availability(hours: float, current_status: Optional[Dict[str, str]] = None, now: Optional[float] = None) -> Dict[str, dict]:
    """
    Returns {node_id: {"availability": pct|None, "downtime_seconds", "down_count", "monitored_seconds"}}.
    current_status supplies the state for nodes that have no history at all.
    """
    now = now or time.time()
    start = now - hours * 3600
    current_status = current_status or {}

    db = SessionLocal()
    try:
        initial = _last_state_before(db, start)
        events = (db.query(StateEventDB)
                    .filter(StateEventDB.timestamp >= start)
                    .order_by(StateEventDB.timestamp.asc())
                    .all())
    finally:
        db.close()

    per_node: Dict[str, list] = {}
    for e in events:
        per_node.setdefault(e.node_id, []).append(e)

    node_ids = set(initial) | set(per_node) | set(current_status)
    result = {}

    for node_id in node_ids:
        evs = per_node.get(node_id, [])
        if node_id in initial:
            state = initial[node_id]
        elif evs:
            state = evs[0].old_status
        else:
            state = current_status.get(node_id, "UP")

        cursor = start
        downtime = 0.0
        paused = 0.0
        down_count = 0

        def accumulate(state_, seconds):
            nonlocal downtime, paused
            if state_ == "DOWN":
                downtime += seconds
            elif state_ == "PAUSED":
                paused += seconds

        for e in evs:
            # Ignore same-state informational events (e.g. suppressed alert notes)
            if e.old_status == e.new_status:
                continue
            accumulate(state, e.timestamp - cursor)
            cursor = e.timestamp
            state = e.new_status
            if e.new_status == "DOWN":
                down_count += 1
        accumulate(state, now - cursor)

        monitored = max(0.0, (now - start) - paused)
        availability = round(100.0 * (1.0 - downtime / monitored), 3) if monitored > 0 else None

        result[node_id] = {
            "availability": availability,
            "downtime_seconds": int(downtime),
            "down_count": down_count,
            "monitored_seconds": int(monitored),
        }

    return result
