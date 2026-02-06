"""
Trace Router - Endpoints for state change event streaming
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from trace_manager import trace_manager

logger = logging.getLogger("BeamState.TraceRouter")

router = APIRouter(prefix="/trace", tags=["trace"])


@router.get("/events")
async def get_recent_events(limit: int = 100):
    """Get recent state change events"""
    events = trace_manager.get_recent_events(limit)
    return {"events": events}


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
