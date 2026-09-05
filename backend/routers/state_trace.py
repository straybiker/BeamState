"""
Trace Router - Endpoints for state change event streaming
"""
import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from trace_manager import trace_manager

logger = logging.getLogger("BeamState.TraceRouter")

router = APIRouter(prefix="/trace", tags=["trace"])


@router.get("/events")
async def get_recent_events(
    limit: int = Query(100, ge=1, le=5000),
    node_id: Optional[str] = None,
    hours: Optional[float] = Query(None, gt=0, description="Only events from the last N hours"),
):
    """Get state change events from history, oldest first."""
    events = await asyncio.to_thread(trace_manager.query, limit, node_id, hours)
    return {"events": events}


@router.get("/availability")
async def get_availability(request: Request, windows: str = Query("24,720", description="Comma-separated window sizes in hours")):
    """Availability, downtime and DOWN count per node for each requested window."""
    from availability import compute_availability
    try:
        hours_list = [float(h) for h in windows.split(",") if h.strip()]
    except ValueError:
        hours_list = [24.0, 720.0]
    hours_list = [h for h in hours_list if 0 < h <= 24 * 365][:4]

    current = {}
    pinger = getattr(request.app.state, "pinger", None)
    if pinger:
        current = {r["node_id"]: r["status"] for r in pinger.latest_results.values()}

    out = {}
    for h in hours_list:
        out[str(int(h) if h.is_integer() else h)] = await asyncio.to_thread(compute_availability, h, current)
    return {"windows": out}


@router.get("/stream")
async def stream_events(request: Request):
    """SSE endpoint for real-time event streaming"""
    
    async def event_generator():
        queue = await trace_manager.subscribe()
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                try:
                    # Wait for event with timeout to check connection periodically
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = json.dumps(event.to_dict())
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
        finally:
            await trace_manager.unsubscribe(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
