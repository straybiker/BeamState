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

# Setup Logging
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("data/system.log"),
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
    
    # Run database migrations for new columns
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), 'data', 'beamstate.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Check if notification_priority column exists, add if not
        cursor.execute("PRAGMA table_info(nodes)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'notification_priority' not in columns:
            cursor.execute('ALTER TABLE nodes ADD COLUMN notification_priority INTEGER')
            logger.info("Migration: Added notification_priority column to nodes table")
        # Check if is_default column exists in groups, add if not
        cursor.execute("PRAGMA table_info(groups)")
        group_columns = [col[1] for col in cursor.fetchall()]
        if 'is_default' not in group_columns:
            cursor.execute('ALTER TABLE groups ADD COLUMN is_default BOOLEAN DEFAULT 0')
            logger.info("Migration: Added is_default column to groups table")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Database migration check failed (may be first run): {e}")
    
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

from routers import config, metrics, discovery

# Include Routers (prefixes are defined in the router modules themselves)
app.include_router(config.router)
app.include_router(metrics.router)
app.include_router(discovery.router)




@app.get("/")
def read_root():
    return {"status": "online", "service": "BeamState"}

@app.get("/status")
def get_pinger_status():
    return pinger.get_status()
