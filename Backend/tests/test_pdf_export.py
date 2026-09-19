"""Tests for PDF export service and endpoint."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from core.pdf_service import generate_meeting_pdf
from db.models import ActionItem, Decision, Meeting, Participant


def test_generate_meeting_pdf_direct():
    """Test generating a PDF directly with mock objects."""
    meeting = MagicMock()
    meeting.id = "test-meet-123"
    meeting.title = "Q4 Product Strategy & Architecture Alignment"
    meeting.short_summary = "Discussed Q4 roadmap, backend refactoring, and AI model latency."
    meeting.detailed_summary = (
        "The team met to review the deliverables for Q4. Primary focus was placed on optimizing "
        "transcription latency with Groq and implementing vector embeddings in Postgres.\n\n"
        "Security compliance and credential management were also highlighted as prerequisites."
    )
    meeting.duration_minutes = 45
    meeting.audio_filename = "q4_strategy_sync.mp3"
    meeting.created_at = datetime(2026, 9, 19, 10, 0, 0, tzinfo=timezone.utc)

    action_items = [
        MagicMock(
            description="Migrate auth credentials to user-level encryption",
            owner="Alice",
            due_date="2026-09-25",
            priority="high",
            status="in_progress",
        ),
        MagicMock(
            description="Benchmark Groq Whisper vs local Whisper",
            owner="Bob",
            due_date="2026-09-30",
            priority="medium",
            status="open",
        ),
    ]

    decisions = [
        MagicMock(
            description="Adopt ReportLab for server-side PDF generation",
            context="Lightweight, fast, no headless browser needed in container.",
        ),
    ]

    participants = [
        MagicMock(name="Alice Chen", email="alice@example.com"),
        MagicMock(name="Bob Smith", email="bob@example.com"),
    ]

    pdf_bytes = generate_meeting_pdf(
        meeting=meeting,
        action_items=action_items,
        decisions=decisions,
        participants=participants,
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000


def test_generate_meeting_pdf_minimal():
    """Test generating a PDF with empty action items and decisions."""
    meeting = MagicMock()
    meeting.id = "empty-meet-456"
    meeting.title = "Quick Standup"
    meeting.short_summary = "Brief checkin."
    meeting.detailed_summary = ""
    meeting.duration_minutes = 10
    meeting.audio_filename = "standup.wav"
    meeting.created_at = None

    pdf_bytes = generate_meeting_pdf(
        meeting=meeting,
        action_items=[],
        decisions=[],
        participants=[],
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


@pytest.mark.asyncio
async def test_export_pdf_unauthorized(async_client):
    """PDF export endpoint must return 401 when accessed without authorization."""
    resp = await async_client.get("/meetings/any-id/export/pdf")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_pdf_not_found(authenticated_client):
    """PDF export returns 404 for non-existent meeting."""
    resp = await authenticated_client.get("/meetings/non-existent-id/export/pdf")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_pdf_success(authenticated_client, seeded_meeting, db_session):
    """Authorized user can export meeting as PDF with proper content-type and disposition."""
    item = ActionItem(
        id="test-item-001",
        meeting_id=seeded_meeting.id,
        description="Verify PDF binary stream",
        owner="Test Engineer",
        due_date="2026-09-22",
        priority="high",
        status="open",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(item)

    decision = Decision(
        id="test-dec-001",
        meeting_id=seeded_meeting.id,
        description="Approve Phase 7 stretch feature",
        context="User requested 3 stretch features.",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(decision)

    participant = Participant(
        id="test-part-001",
        meeting_id=seeded_meeting.id,
        name="Developer",
        email="dev@example.com",
    )
    db_session.add(participant)
    await db_session.commit()

    resp = await authenticated_client.get(f"/meetings/{seeded_meeting.id}/export/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF-")
    assert len(resp.content) > 2000
