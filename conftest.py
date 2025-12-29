import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Ensure backend modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from main import app
from database import Base, get_db
from models import NodeDB, GroupDB

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session(engine):
    """Returns a sqlalchemy session, and handles rollback after test."""
    connection = engine.connect()
    transaction = connection.begin()
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    """
    Fixture for TestClient with dependency override.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass # Session is closed by fixture
            
    app.dependency_overrides[get_db] = override_get_db
    
    # Disable pinger for tests via state
    if hasattr(app.state, "pinger"):
        app.state.pinger.stop()
        
    with TestClient(app) as c:
        yield c
        
    app.dependency_overrides.clear()
