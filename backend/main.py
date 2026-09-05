import asyncio
import os
import sys
import logging
import json
import pathlib

# Load log level from config
CONFIG_FILE = pathlib.Path(__file__).parent / "config.json"
log_level = logging.INFO  # Default
try:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            if "app_config" in data and "logging" in data["app_config"]:
                level_str = data["app_config"]["logging"].get("log_level", "INFO")
                log_level = getattr(logging, level_str.upper(), logging.INFO)
except Exception:
    pass  # Fall back to default

# Setup Logging: rotate at 5 MB, keep 3 archives
from logging.handlers import RotatingFileHandler
LOG_DIR = pathlib.Path(__file__).parent / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(LOG_DIR / "system.log", maxBytes=5 * 1024 * 1024, backupCount=3),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("BeamState")

# Fix for Windows: "ValueError: too many file descriptors in select()"
# Use ProactorEventLoopPolicy which supports I/O Completion Ports (IOCP) and has no 512 limit.
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    logger.info("Using WindowsProactorEventLoopPolicy for IOCP support")
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from database import init_db, SessionLocal
from monitor_manager import MonitorManager
from routers import config
from cleanup import sync_with_config
from storage import storage
from trace_manager import trace_manager


# Initialize Monitor Manager
pinger = MonitorManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("BeamState Backend Starting...")
    init_db()
    
    # Run database migrations for new columns
    try:
        from migrations.schema_update import run_migrations
        run_migrations()
        from migrations.schema_update_v2 import run_migrations as run_migrations_v2
        run_migrations_v2()
        from migrations.schema_update_v3 import run_migrations as run_migrations_v3
        run_migrations_v3()
    except Exception as e:
        logger.warning(f"Database migration failed: {e}")

    # History: load the ring buffer and apply retention
    trace_manager.load_history()
    _apply_retention()
    
    # Seed metric definitions first so an import can resolve metric names
    try:
        from seed_metrics import seed_metric_definitions
        seed_metric_definitions()
    except Exception as e:
        logger.error(f"Metric seeding failed: {e}")

    # Reconcile database and config.json (database is authoritative)
    try:
        db = SessionLocal()
        sync_with_config(db)
        db.close()
    except Exception as e:
        logger.error(f"Startup sync failed: {e}")
    
    # Start the pinger background task and the daily history pruner
    if not os.getenv("TESTING"):
        ping_task = asyncio.create_task(pinger.run_loop())
        prune_task = asyncio.create_task(_prune_loop())

    yield

    # Shutdown
    logger.info("BeamState Backend Stopping...")
    pinger.stop()
    if not os.getenv("TESTING"):
        prune_task.cancel()
        await ping_task


def _apply_retention():
    """Prune state events and metric samples according to the history config."""
    from metrics_processor import MetricProcessor
    hist = storage.config.get("history", {})
    try:
        trace_manager.prune(int(hist.get("retention_days", 90) or 0))
        MetricProcessor.prune_samples(int(hist.get("metric_retention_days", 3) or 0))
    except Exception as e:
        logger.warning(f"History prune failed: {e}")


async def _prune_loop():
    """Apply history retention every 6 hours."""
    while True:
        await asyncio.sleep(6 * 3600)
        await asyncio.to_thread(_apply_retention)

app = FastAPI(title="BeamState API", lifespan=lifespan)
app.state.pinger = pinger

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, set to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import config, metrics, discovery, state_trace

# Include Routers (prefixes are defined in the router modules themselves)
app.include_router(config.router)
app.include_router(metrics.router)
app.include_router(discovery.router)
app.include_router(state_trace.router)




@app.get("/")
def read_root():
    return {"status": "online", "service": "BeamState"}

@app.get("/status")
def get_pinger_status():
    return pinger.get_status()


@app.get("/status/stream")
async def stream_status(request: Request):
    """
    SSE stream for the dashboard.
    Messages: {"type": "node", "data": <latest result>} on every check,
              {"type": "config"} when groups, nodes or app settings change.
    """
    from broadcast import status_stream
    from fastapi.responses import StreamingResponse

    async def generator():
        queue = status_stream.subscribe()
        try:
            # Snapshot first so a reconnecting client is complete immediately
            yield f"data: {json.dumps({'type': 'snapshot', 'data': list(pinger.latest_results.values())})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            status_stream.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

if __name__ == "__main__":
    import uvicorn
    # Allow direct running with python main.py
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
