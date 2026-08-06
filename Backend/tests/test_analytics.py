import pytest
import pytest_asyncio
from datetime import datetime, timezone
from db.models import ActionItem, Meeting, Participant, User

@pytest.mark.asyncio
async def test_analytics_unauthorized(async_client):
    """Analytics endpoints must return 401 when unauthenticated."""
    routes = [
        "/analytics/summary",
        "/analytics/participants",
        "/analytics/timeline",
        "/analytics/action-items",
        "/analytics/topics",
    ]
    for r in routes:
        resp = await async_client.get(r)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_analytics_empty_db(authenticated_client):
    """Analytics endpoints return valid empty default schemas when no data exists."""
    resp = await authenticated_client.get("/analytics/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_meetings"] == 0
    assert summary["avg_duration_minutes"] == 0.0
    assert summary["total_action_items"] == 0
    assert summary["completion_rate"] == 0.0

    resp = await authenticated_client.get("/analytics/participants")
    assert resp.status_code == 200
    assert resp.json()["participants"] == []

    resp = await authenticated_client.get("/analytics/timeline")
    assert resp.status_code == 200
    assert resp.json()["timeline"] == []

    resp = await authenticated_client.get("/analytics/action-items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_open"] == 0
    assert data["total_done"] == 0

    resp = await authenticated_client.get("/analytics/topics")
    assert resp.status_code == 200
    assert resp.json()["topics"] == []


@pytest.mark.asyncio
async def test_analytics_with_data(authenticated_client, db_session):
    """Analytics endpoints compute aggregated metrics accurately when data exists."""
    # Seed a test meeting
    m1 = Meeting(
        title="Frontend Architecture Sync",
        audio_filename="sync.mp3",
        duration_minutes=30,
        short_summary="Discussed frontend components and dashboard performance.",
        detailed_summary="Detailed summary of frontend components.",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(m1)
    await db_session.flush()

    p1 = Participant(meeting_id=m1.id, name="Alice Chen")
    p2 = Participant(meeting_id=m1.id, name="Bob Smith")
    a1 = ActionItem(meeting_id=m1.id, description="Implement charts", owner="Alice Chen", due_date="2026-08-01", status="done")
    a2 = ActionItem(meeting_id=m1.id, description="Fix CSS layout", owner="Bob Smith", due_date="2026-08-10", status="open")
    
    db_session.add_all([p1, p2, a1, a2])
    await db_session.commit()

    # Test summary
    resp = await authenticated_client.get("/analytics/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_meetings"] == 1
    assert summary["avg_duration_minutes"] == 30.0
    assert summary["total_action_items"] == 2
    assert summary["completed_action_items"] == 1
    assert summary["completion_rate"] == 50.0

    # Test participants
    resp = await authenticated_client.get("/analytics/participants")
    assert resp.status_code == 200
    parts = resp.json()["participants"]
    assert len(parts) >= 2
    names = [p["name"] for p in parts]
    assert "Alice Chen" in names
    assert "Bob Smith" in names

    # Test action items
    resp = await authenticated_client.get("/analytics/action-items")
    assert resp.status_code == 200
    ai_data = resp.json()
    assert ai_data["total_done"] == 1
    assert ai_data["total_open"] == 1
    assert len(ai_data["by_owner"]) >= 2

    # Test timeline
    resp = await authenticated_client.get("/analytics/timeline?period=monthly")
    assert resp.status_code == 200
    assert len(resp.json()["timeline"]) == 1

    # Test topics
    resp = await authenticated_client.get("/analytics/topics")
    assert resp.status_code == 200
    topics = resp.json()["topics"]
    assert len(topics) > 0
