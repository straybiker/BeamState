from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from models import Base, GroupDB, NodeDB, MetricDefinitionDB, NodeMetricDB
import os

# SQLite Database in the data volume
# Use local path for dev, /app/data for docker (set via env var)
import pathlib
DEFAULT_DB_PATH = pathlib.Path(__file__).parent / "data" / "beamstate.db"
DB_PATH = os.getenv("DB_PATH", str(DEFAULT_DB_PATH))

# Ensure directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)





if os.getenv("TESTING"):
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
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
