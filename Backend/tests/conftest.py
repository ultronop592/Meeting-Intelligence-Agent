"""
conftest.py — shared Pytest fixtures for the Meeting Intelligence Agent backend.

Uses:
- SQLite in-memory via asyncpg-compatible aiosqlite for fast, isolated DB tests
- FastAPI TestClient (sync ASGI) for route tests
- Monkeypatching of tool connectors to avoid real API calls
"""
import asyncio
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import AsyncMock, MagicMock, patch

# --- Point settings at an in-memory SQLite DB before importing app modules ---
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///:memory:"
)
os.environ.setdefault(
    "DATABASE_URL_SYNC", "sqlite:///:memory:"
)

from db.models import Base
from api.main import app
from db.database import get_db


# =============================================================================
# Event-loop fixture (module-scoped so all async tests share one loop)
# =============================================================================

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# In-memory SQLite async engine + session
# =============================================================================

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="module")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(test_engine):
    """Provide a fresh transactional AsyncSession for each test, rolled back after."""
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


# =============================================================================
# FastAPI async test client with DB override
# =============================================================================

@pytest_asyncio.fixture()
async def async_client(db_session: AsyncSession):
    """AsyncClient with the app DB dependency overridden to use in-memory SQLite."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# =============================================================================
# Pre-seeded meeting helper
# =============================================================================

@pytest_asyncio.fixture()
async def seeded_meeting(db_session: AsyncSession):
    """Insert a minimal Meeting row and return its id."""
    from db.models import Meeting
    from datetime import datetime, timezone

    meeting = Meeting(
        id="test-meeting-id",
        title="Weekly Standup",
        audio_filename="standup.mp3",
        duration_minutes=30,
        short_summary="Discussed sprint goals and blockers.",
        detailed_summary="Long form text goes here.",
        embedding_status="pending",
    )
    db_session.add(meeting)
    await db_session.commit()
    return meeting


@pytest_asyncio.fixture()
async def seeded_action_item(db_session: AsyncSession, seeded_meeting):
    """Insert one ActionItem for the seeded meeting."""
    from db.models import ActionItem

    item = ActionItem(
        id="test-item-id",
        meeting_id=seeded_meeting.id,
        description="Write unit tests for the API",
        owner="Alice Chen",
        due_date="2026-08-01",
        priority="high",
        status="open",
    )
    db_session.add(item)
    await db_session.commit()
    return item


@pytest_asyncio.fixture()
async def seeded_participant(db_session: AsyncSession, seeded_meeting):
    """Insert one Participant for the seeded meeting."""
    from db.models import Participant

    p = Participant(
        id="test-participant-id",
        meeting_id=seeded_meeting.id,
        name="Alice Chen",
        email="alice@example.com",
    )
    db_session.add(p)
    await db_session.commit()
    return p
