import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import init_db, SessionLocal
from node_pinger import Pinger
from routers import nc as config
from cleanup import sync_with_config

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NetSentry")

# Initialize Pinger
pinger = Pinger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("NetSentry Backend Starting...")
    init_db()
    
    # Run Startup Cleanup & Sync
    try:
        db = SessionLocal()
        sync_with_config(db)
        db.close()
    except Exception as e:
        logger.error(f"Startup sync failed: {e}")
    
    # Start the pinger background task
    ping_task = asyncio.create_task(pinger.run_loop())
    
    yield
    
    # Shutdown
    logger.info("NetSentry Backend Stopping...")
    pinger.stop()
    await ping_task

app = FastAPI(title="NetSentry API", lifespan=lifespan)
app.state.pinger = pinger

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, set to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
logger.warning(f"DEBUG: IMPORTED CONFIG FROM {config.__file__}")
app.include_router(config.router)


@app.on_event("startup")
async def startup_event():
    for route in app.routes:
        logger.warning(f"ROUTE: {route.path} -> {route.name} ({route.endpoint})")

@app.get("/")
def read_root():
    return {"status": "online", "service": "NetSentry"}

@app.get("/status")
def get_pinger_status():
    return pinger.get_status()
