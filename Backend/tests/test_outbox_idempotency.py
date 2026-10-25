"""Tests for Phase 3 Step 4: Transactional Outbox pattern and Idempotent Multi-Channel Dispatch."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.outbox import outbox_service, build_idempotency_key
from db.models import Meeting, OutboxDispatch
from db.database import get_outbox_dispatch, create_or_get_outbox_dispatch
from models.schemas import ActionItem, Priority
from tools.jira_tool import send_jira_for_meeting
from tools.slack_tool import send_slack_for_meeting
from tools.email_tool import send_email_for_meeting


@pytest.mark.asyncio
async def test_outbox_service_prevents_duplicate_dispatch(db_session):
    """Calling outbox_service twice with the same key must only execute dispatch_fn once."""
    meeting_id = f"m-{uuid.uuid4().hex[:8]}"
    key = build_idempotency_key(meeting_id, "jira", item_id="item_42")

    mock_dispatch = AsyncMock(return_value=("JIRA-101", {"summary": "Fix bug"}))

    # First call — must execute dispatch_fn
    res1 = await outbox_service.execute_idempotent_dispatch(
        idempotency_key=key,
        meeting_id=meeting_id,
        channel="jira",
        dispatch_fn=mock_dispatch,
        session=db_session,
    )
    assert res1["status"] == "sent"
    assert res1["external_id"] == "JIRA-101"
    assert res1["is_duplicate"] is False
    assert mock_dispatch.call_count == 1

    # Second call — must skip dispatch_fn and return duplicate
    res2 = await outbox_service.execute_idempotent_dispatch(
        idempotency_key=key,
        meeting_id=meeting_id,
        channel="jira",
        dispatch_fn=mock_dispatch,
        session=db_session,
    )
    assert res2["status"] == "sent"
    assert res2["external_id"] == "JIRA-101"
    assert res2["is_duplicate"] is True
    assert mock_dispatch.call_count == 1  # Not incremented!


@pytest.mark.asyncio
async def test_outbox_remote_reconciliation_recovers_crashed_dispatch(db_session):
    """If worker crashes after remote creates resource but before DB records it,

    check_remote_fn finds the existing remote ticket and recovers without duplicate creation.
    """
    meeting_id = f"m-{uuid.uuid4().hex[:8]}"
    key = build_idempotency_key(meeting_id, "jira", item_id="item_99")

    # Simulate worker crash: outbox row was written as 'pending'
    row, created = await create_or_get_outbox_dispatch(
        idempotency_key=key,
        meeting_id=meeting_id,
        channel="jira",
        session=db_session,
    )
    assert created is True
    assert row.status == "pending"

    # Worker restarts: mock remote check finds ticket already created on Jira
    mock_dispatch = AsyncMock(return_value=("JIRA-NEW", {}))
    mock_check_remote = AsyncMock(return_value="JIRA-RECOVERED-99")

    res = await outbox_service.execute_idempotent_dispatch(
        idempotency_key=key,
        meeting_id=meeting_id,
        channel="jira",
        dispatch_fn=mock_dispatch,
        check_remote_fn=mock_check_remote,
        session=db_session,
    )

    assert res["status"] == "sent"
    assert res["external_id"] == "JIRA-RECOVERED-99"
    assert res["is_duplicate"] is True
    assert mock_dispatch.call_count == 0  # Crucial: did not create a second ticket!

    # Verify DB outbox row was updated to 'sent' with recovered ticket ID
    db_row = await get_outbox_dispatch(key, session=db_session)
    assert db_row.status == "sent"
    assert db_row.external_id == "JIRA-RECOVERED-99"


@pytest.mark.asyncio
async def test_outbox_retry_storm_resilience(db_session):
    """Simulated retry storm / timeout: failures are tracked and final success transitions to sent."""
    meeting_id = f"m-{uuid.uuid4().hex[:8]}"
    key = build_idempotency_key(meeting_id, "email", recipient="bob@example.com")

    # Failures 1 & 2
    mock_failing_dispatch = AsyncMock(side_effect=RuntimeError("Gateway timeout 504"))

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await outbox_service.execute_idempotent_dispatch(
                idempotency_key=key,
                meeting_id=meeting_id,
                channel="email",
                dispatch_fn=mock_failing_dispatch,
                session=db_session,
            )

    row = await get_outbox_dispatch(key, session=db_session)
    assert row.status == "failed"
    assert row.retry_count == 2
    assert "Gateway timeout 504" in row.last_error

    # Attempt 3 succeeds
    mock_success_dispatch = AsyncMock(return_value=("email_msg_123", {"recipient": "bob@example.com"}))
    res = await outbox_service.execute_idempotent_dispatch(
        idempotency_key=key,
        meeting_id=meeting_id,
        channel="email",
        dispatch_fn=mock_success_dispatch,
        session=db_session,
    )
    assert res["status"] == "sent"
    assert res["external_id"] == "email_msg_123"

    row_after = await get_outbox_dispatch(key, session=db_session)
    assert row_after.status == "sent"


@pytest.mark.asyncio
async def test_send_jira_for_meeting_idempotency(db_session):
    """Verify send_jira_for_meeting produces no duplicate tickets when called multiple times."""
    meeting_id = f"m-{uuid.uuid4().hex[:8]}"
    action_items = [
        ActionItem(description="Setup Redis queue", owner="Alice", due_date="2026-11-01", priority=Priority.high),
        ActionItem(description="Write unit tests", owner="Bob", due_date="2026-11-02", priority=Priority.medium),
    ]

    mock_jira = MagicMock()
    mock_jira.issue_create.side_effect = [{"key": "PROJ-1"}, {"key": "PROJ-2"}]
    mock_jira.jql.return_value = {"issues": []}

    fake_creds = {
        "jira_url": "https://company.atlassian.net",
        "jira_email": "ci@example.com",
        "jira_api_token": "secret_token",
        "jira_project_key": "PROJ",
    }

    with patch("tools.jira_tool.Jira", return_value=mock_jira):
        # 1st send: creates 2 tickets
        res1 = await send_jira_for_meeting(
            meeting_id=meeting_id,
            action_items=action_items,
            credentials=fake_creds,
            session=db_session,
        )
        assert res1["created"] == ["PROJ-1", "PROJ-2"]
        assert len(res1["skipped"]) == 0
        assert mock_jira.issue_create.call_count == 2

        # 2nd send (e.g. retry / double-click): skips both, creates 0 new tickets!
        res2 = await send_jira_for_meeting(
            meeting_id=meeting_id,
            action_items=action_items,
            credentials=fake_creds,
            session=db_session,
        )
        assert len(res2["created"]) == 0
        assert res2["skipped"] == ["PROJ-1", "PROJ-2"]
        assert mock_jira.issue_create.call_count == 2  # No new Jira calls made!


@pytest.mark.asyncio
async def test_send_slack_and_email_idempotency(db_session):
    """Verify Slack and Email dispatches do not duplicate on retry."""
    meeting_id = f"m-{uuid.uuid4().hex[:8]}"

    # --- Test Slack Idempotency ---
    mock_post_slack = MagicMock()
    with patch("tools.slack_tool._post_to_slack", mock_post_slack):
        slack_creds = {"slack_webhook_url": "https://hooks.slack.com/services/test/123", "slack_channel": "#dev"}
        
        # First call
        res_s1 = await send_slack_for_meeting(
            meeting_id=meeting_id,
            meeting_title="Q4 Architecture Review",
            short_summary="Reviewing scalable runtime.",
            action_items=[],
            participants=["Alice"],
            decisions_count=1,
            duration_minutes=25,
            credentials=slack_creds,
            session=db_session,
        )
        assert res_s1["success"] is True
        assert res_s1["is_duplicate"] is False
        assert mock_post_slack.call_count == 1

        # Second call (retry)
        res_s2 = await send_slack_for_meeting(
            meeting_id=meeting_id,
            meeting_title="Q4 Architecture Review",
            short_summary="Reviewing scalable runtime.",
            action_items=[],
            participants=["Alice"],
            decisions_count=1,
            duration_minutes=25,
            credentials=slack_creds,
            session=db_session,
        )
        assert res_s2["success"] is True
        assert res_s2["is_duplicate"] is True
        assert mock_post_slack.call_count == 1  # Webhook not called again!

    # --- Test Email Idempotency ---
    mock_send_email = MagicMock()
    with patch("tools.email_tool._send_single_email", mock_send_email):
        email_creds = {
            "sendgrid_api_key": "SG.test12345",
            "sendgrid_sender_email": "bot@company.com",
            "sendgrid_sender_name": "Meeting Bot",
        }
        recipients = {"Alice": "alice@example.com", "Bob": "bob@example.com"}

        res_e1 = await send_email_for_meeting(
            meeting_id=meeting_id,
            meeting_title="Q4 Architecture Review",
            short_summary="Reviewing scalable runtime.",
            all_action_items=[],
            participant_emails=recipients,
            credentials=email_creds,
            session=db_session,
        )
        assert res_e1["sent"] == 2
        assert res_e1["skipped"] == 0
        assert mock_send_email.call_count == 2

        # Retry sending emails — both should be skipped
        res_e2 = await send_email_for_meeting(
            meeting_id=meeting_id,
            meeting_title="Q4 Architecture Review",
            short_summary="Reviewing scalable runtime.",
            all_action_items=[],
            participant_emails=recipients,
            credentials=email_creds,
            session=db_session,
        )
        assert res_e2["sent"] == 0
        assert res_e2["skipped"] == 2
        assert mock_send_email.call_count == 2  # No duplicate emails sent!
