import pytest

from app.database import SessionLocal
from app.sources.source_health_manager import reset_all


@pytest.fixture(autouse=True)
def _reset_source_health_manager() -> None:
    reset_all()
    yield
    reset_all()


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
