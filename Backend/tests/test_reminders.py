"""Tests for Action Item Due-Date Reminders service and endpoints."""

import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from core.reminder_service import (
    check_and_send_due_reminders,
    evaluate_due_urgency,
    parse_due_date,
    reminder_scheduler,
)
from db.models import ActionItem, Meeting, NotificationLog, Participant


def test_parse_due_date():
    """Verify various due date string formats are correctly parsed."""
    assert parse_due_date("2026-09-25") == date(2026, 9, 25)
    assert parse_due_date("2026-09-25T14:30:00Z") == date(2026, 9, 25)
    assert parse_due_date("25-09-2026") == date(2026, 9, 25)
    assert parse_due_date("2026/09/25") == date(2026, 9, 25)
    assert parse_due_date("invalid-date") is None
    assert parse_due_date(None) is None
    assert parse_due_date("") is None


def test_evaluate_due_urgency():
    """Verify urgency classification for overdue, today, soon, and upcoming dates."""
    today = date(2026, 9, 19)

    # Overdue
    is_due, urgency = evaluate_due_urgency(date(2026, 9, 18), today)
    assert is_due is True
    assert urgency == "overdue"

    # Due today
    is_due, urgency = evaluate_due_urgency(date(2026, 9, 19), today)
    assert is_due is True
    assert urgency == "due_today"

    # Due soon (tomorrow)
    is_due, urgency = evaluate_due_urgency(date(2026, 9, 20), today, window_days=1)
    assert is_due is True
    assert urgency == "due_soon"

    # Upcoming (in 5 days)
    is_due, urgency = evaluate_due_urgency(date(2026, 9, 24), today, window_days=1)
    assert is_due is False
    assert urgency == "upcoming"


@pytest.mark.asyncio
async def test_check_and_send_due_reminders_service(db_session, seeded_meeting):
    """Test reminder service finds due items, logs notifications, and prevents duplicates."""
    today = date(2026, 9, 19)

    # Overdue item
    item1 = ActionItem(
        id="item-overdue-001",
        meeting_id=seeded_meeting.id,
        description="Fix production auth bug",
        owner="Alice",
        due_date="2026-09-18",
        priority="high",
        status="open",
        created_at=datetime.now(timezone.utc),
    )
    # Future item (not due)
    item2 = ActionItem(
        id="item-future-002",
        meeting_id=seeded_meeting.id,
        description="Plan next quarter offsite",
        owner="Bob",
        due_date="2026-10-15",
        priority="low",
        status="open",
        created_at=datetime.now(timezone.utc),
    )
    # Done item (should be excluded)
    item3 = ActionItem(
        id="item-done-003",
        meeting_id=seeded_meeting.id,
        description="Setup repo",
        owner="Alice",
        due_date="2026-09-17",
        priority="medium",
        status="done",
        created_at=datetime.now(timezone.utc),
    )
    # Participant with email
    participant = Participant(
        id="part-alice-001",
        meeting_id=seeded_meeting.id,
        name="Alice",
        email="alice@example.com",
    )

    db_session.add_all([item1, item2, item3, participant])
    await db_session.commit()

    with patch("core.reminder_service._send_single_email") as mock_send_email, \
         patch("core.reminder_service.resolve_email_credentials", return_value=("fake-key", "bot@example.com", "Bot")):

        mock_send_email.return_value = True

        # First run: should detect 1 due item (item1) and send reminder
        result = await check_and_send_due_reminders(
            db=db_session,
            meeting_id=seeded_meeting.id,
            today_override=today,
        )

        assert result["total_checked"] == 2  # item1 and item2 (item3 is done)
        assert result["due_items_found"] == 1
        assert result["reminders_sent"] == 1
        assert result["already_reminded"] == 0
        assert mock_send_email.called

        # Second run on same day: should detect it was already reminded today
        result_2 = await check_and_send_due_reminders(
            db=db_session,
            meeting_id=seeded_meeting.id,
            today_override=today,
        )
        assert result_2["due_items_found"] == 1
        assert result_2["already_reminded"] == 1
        assert result_2["reminders_sent"] == 0


@pytest.mark.asyncio
async def test_reminder_endpoints(authenticated_client, seeded_meeting, db_session):
    """Test triggering and checking reminder status via API routes."""
    # Add an overdue action item
    item = ActionItem(
        id="item-api-001",
        meeting_id=seeded_meeting.id,
        description="Update security documentation",
        owner="Charlie",
        due_date="2026-09-15",
        priority="high",
        status="in_progress",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(item)
    await db_session.commit()

    # 1. Check reminder status
    status_resp = await authenticated_client.get(f"/meetings/{seeded_meeting.id}/reminders/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["meeting_id"] == seeded_meeting.id
    assert len(status_data["items"]) >= 1
    found_item = next(i for i in status_data["items"] if i["id"] == item.id)
    assert found_item["is_due"] is True
    assert found_item["urgency"] == "overdue"

    # 2. Trigger reminders for meeting
    trigger_resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/reminders/trigger")
    assert trigger_resp.status_code == 200
    trigger_data = trigger_resp.json()
    assert trigger_data["success"] is True
    assert "summary" in trigger_data

    # 3. Trigger global reminders
    global_resp = await authenticated_client.post("/reminders/trigger")
    assert global_resp.status_code == 200
    assert global_resp.json()["success"] is True
