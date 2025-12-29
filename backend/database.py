from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base, GroupDB, NodeDB
import os

# SQLite Database in the data volume
# Use local path for dev, /app/data for docker (set via env var)
DB_PATH = os.getenv("DB_PATH", "backend/data/netsentry.db")
# Ensure directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    # Default seeding removed in favor of config.json sync

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
