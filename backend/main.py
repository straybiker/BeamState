import asyncio
import os
import sys
import logging

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("system.log"),
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
from fastapi import FastAPI
from database import init_db, SessionLocal
from monitor_manager import MonitorManager
from routers import config
from cleanup import sync_with_config


# Initialize Monitor Manager
pinger = MonitorManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("BeamState Backend Starting...")
    init_db()
    
    # Run Startup Cleanup & Sync
    try:
        db = SessionLocal()
        sync_with_config(db)
        db.close()
    except Exception as e:
        logger.error(f"Startup sync failed: {e}")
    
    # Seed metric definitions
    try:
        from seed_metrics import seed_metric_definitions
        seed_metric_definitions()
    except Exception as e:
        logger.error(f"Metric seeding failed: {e}")
    
    # Start the pinger background task
    # Start the pinger background task
    if not os.getenv("TESTING"):
        ping_task = asyncio.create_task(pinger.run_loop())
    
    yield
    
    # Shutdown
    logger.info("BeamState Backend Stopping...")
    pinger.stop()
    if not os.getenv("TESTING"):
        await ping_task

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

from routers import config, metrics

# Include Routers (prefixes are defined in the router modules themselves)
app.include_router(config.router)
app.include_router(metrics.router)




@app.get("/")
def read_root():
    return {"status": "online", "service": "BeamState"}

@app.get("/status")
def get_pinger_status():
    return pinger.get_status()
