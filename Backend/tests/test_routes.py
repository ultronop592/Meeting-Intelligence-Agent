"""
test_routes.py — Integration tests for all FastAPI API routes.

Each test:
- Uses an in-memory SQLite database (no real Postgres needed).
- Uses the AsyncClient with the DB dependency overridden.
- Mocks external tool connectors (Slack/Jira/Email/Calendar) so no live API calls are made.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# Health & root
# =============================================================================

@pytest.mark.asyncio
async def test_health_check(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_root(async_client):
    resp = await async_client.get("/")
    assert resp.status_code == 200
    assert "Meeting Intelligence Agent" in resp.json()["message"]
# =============================================================================
# Unauthorized Access Checks
# =============================================================================

@pytest.mark.asyncio
async def test_unauthorized_access(async_client):
    """Endpoints requiring authentication must return 401 when accessed without token."""
    routes = [
        ("GET", "/meetings"),
        ("GET", "/meetings/some-id"),
        ("POST", "/query"),
        ("POST", "/query/stream"),
        ("POST", "/memory/search"),
    ]
    for method, path in routes:
        if method == "GET":
            resp = await async_client.get(path)
        else:
            resp = await async_client.post(path, json={"question": "test"})
        assert resp.status_code == 401


# =============================================================================
# Meetings list / detail
# =============================================================================

@pytest.mark.asyncio
async def test_list_meetings_empty(authenticated_client):
    resp = await authenticated_client.get("/meetings")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_meetings_with_data(authenticated_client, seeded_meeting):
    resp = await authenticated_client.get("/meetings")
    assert resp.status_code == 200
    meetings = resp.json()
    assert len(meetings) >= 1
    assert meetings[0]["id"] == seeded_meeting.id
    assert meetings[0]["title"] == "Weekly Standup"


@pytest.mark.asyncio
async def test_get_meeting_detail(authenticated_client, seeded_meeting, seeded_action_item, seeded_participant):
    resp = await authenticated_client.get(f"/meetings/{seeded_meeting.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meeting"]["id"] == seeded_meeting.id
    assert len(data["action_items"]) == 1
    assert data["action_items"][0]["description"] == "Write unit tests for the API"
    assert len(data["participants"]) == 1
    assert data["participants"][0]["name"] == "Alice Chen"


@pytest.mark.asyncio
async def test_get_meeting_detail_not_found(authenticated_client):
    resp = await authenticated_client.get("/meetings/nonexistent-id")
    assert resp.status_code == 404


# =============================================================================
# Action item update
# =============================================================================

@pytest.mark.asyncio
async def test_update_action_item_status(authenticated_client, seeded_meeting, seeded_action_item):
    resp = await authenticated_client.patch(
        f"/meetings/{seeded_meeting.id}/action-items/{seeded_action_item.id}",
        json={"status": "done"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


@pytest.mark.asyncio
async def test_update_action_item_wrong_meeting(authenticated_client, seeded_meeting, seeded_action_item):
    """Item exists but belongs to a different meeting_id — should 404."""
    resp = await authenticated_client.patch(
        f"/meetings/wrong-meeting-id/action-items/{seeded_action_item.id}",
        json={"status": "done"},
    )
    assert resp.status_code == 404


# =============================================================================
# Participant email update
# =============================================================================

@pytest.mark.asyncio
async def test_update_participant_email(authenticated_client, seeded_meeting, seeded_participant):
    resp = await authenticated_client.patch(
        f"/meetings/{seeded_meeting.id}/participants/{seeded_participant.id}",
        params={"email": "new@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "new@example.com"


@pytest.mark.asyncio
async def test_update_participant_email_not_found(authenticated_client, seeded_meeting):
    resp = await authenticated_client.patch(
        f"/meetings/{seeded_meeting.id}/participants/nonexistent",
        params={"email": "x@example.com"},
    )
    assert resp.status_code == 404


# =============================================================================
# Delete meeting
# =============================================================================

@pytest.mark.asyncio
async def test_delete_meeting(authenticated_client, seeded_meeting):
    resp = await authenticated_client.delete(f"/meetings/{seeded_meeting.id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Confirm it's gone
    resp2 = await authenticated_client.get(f"/meetings/{seeded_meeting.id}")
    assert resp2.status_code == 404


# =============================================================================
# Manual send endpoints — Slack
# =============================================================================

@pytest.mark.asyncio
async def test_send_slack_success(authenticated_client, seeded_meeting, seeded_action_item, seeded_participant):
    with patch(
        "api.routes.send_slack_for_meeting",
        new=AsyncMock(return_value={"success": True, "error": None}),
    ):
        resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/send/slack")
    assert resp.status_code == 200
    assert resp.json()["sent"] == 1


@pytest.mark.asyncio
async def test_send_slack_tool_failure(authenticated_client, seeded_meeting):
    with patch(
        "api.routes.send_slack_for_meeting",
        new=AsyncMock(return_value={"success": False, "error": "Webhook URL not configured"}),
    ):
        resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/send/slack")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_send_slack_meeting_not_found(authenticated_client):
    resp = await authenticated_client.post("/meetings/bad-id/send/slack")
    assert resp.status_code == 404


# =============================================================================
# Manual send endpoints — Jira
# =============================================================================

@pytest.mark.asyncio
async def test_send_jira_success(authenticated_client, seeded_meeting, seeded_action_item):
    with patch(
        "api.routes.send_jira_for_meeting",
        new=AsyncMock(return_value={"created": ["PROJ-1"], "failed": []}),
    ):
        resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/send/jira")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] == 1
    assert "PROJ-1" in data["created"]


@pytest.mark.asyncio
async def test_send_jira_no_action_items(authenticated_client, seeded_meeting):
    """Meeting with no action items should return a friendly message, not error."""
    resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/send/jira")
    assert resp.status_code == 200
    assert resp.json()["sent"] == 0


@pytest.mark.asyncio
async def test_send_jira_credentials_missing(authenticated_client, seeded_meeting, seeded_action_item):
    with patch(
        "api.routes.send_jira_for_meeting",
        new=AsyncMock(side_effect=ValueError("Jira credentials not configured in .env")),
    ):
        resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/send/jira")
    assert resp.status_code == 503


# =============================================================================
# Manual send endpoints — Email
# =============================================================================

@pytest.mark.asyncio
async def test_send_email_no_emails_configured(authenticated_client, seeded_meeting, seeded_action_item):
    """If no participant has an email, return a helpful message (not error)."""
    resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/send/email")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_send_email_with_participant_email(authenticated_client, seeded_meeting, seeded_action_item, seeded_participant):
    with patch(
        "api.routes.send_email_for_meeting",
        new=AsyncMock(return_value={"sent": 1, "failed": 0}),
    ):
        resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/send/email")
    assert resp.status_code == 200
    assert resp.json()["sent"] == 1


# =============================================================================
# Manual send endpoints — Calendar
# =============================================================================

@pytest.mark.asyncio
async def test_send_calendar_success(authenticated_client, seeded_meeting, seeded_participant):
    with patch(
        "api.routes.send_calendar_for_meeting",
        new=AsyncMock(return_value={"event_id": "cal123", "event_url": "https://cal.google.com/event/cal123", "error": None}),
    ):
        resp = await authenticated_client.post(
            f"/meetings/{seeded_meeting.id}/send/calendar",
            params={"days_from_now": 7},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] == 1
    assert data["event_id"] == "cal123"


@pytest.mark.asyncio
async def test_send_calendar_tool_error(authenticated_client, seeded_meeting, seeded_participant):
    with patch(
        "api.routes.send_calendar_for_meeting",
        new=AsyncMock(return_value={"event_id": None, "event_url": None, "error": "Credentials not set"}),
    ):
        resp = await authenticated_client.post(
            f"/meetings/{seeded_meeting.id}/send/calendar",
            params={"days_from_now": 7},
        )
    assert resp.status_code == 502


# =============================================================================
# Job status endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_get_job_status_not_found(authenticated_client):
    resp = await authenticated_client.get("/meetings/status/nonexistent-job-id")
    assert resp.status_code == 404


# =============================================================================
# /query endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_query_no_meetings(authenticated_client):
    resp = await authenticated_client.post("/query", json={"question": "What were the decisions?"})
    assert resp.status_code == 200
    assert "No meetings are available" in resp.json()["answer"]


@pytest.mark.asyncio
async def test_query_participants(authenticated_client, seeded_meeting, seeded_participant):
    resp = await authenticated_client.post(
        "/query",
        json={"question": "Who attended the meeting?", "meeting_id": seeded_meeting.id},
    )
    assert resp.status_code == 200
    assert "Alice Chen" in resp.json()["answer"]


@pytest.mark.asyncio
async def test_query_action_items(authenticated_client, seeded_meeting, seeded_action_item):
    resp = await authenticated_client.post(
        "/query",
        json={"question": "What are the action items?", "meeting_id": seeded_meeting.id},
    )
    assert resp.status_code == 200
    assert "Write unit tests" in resp.json()["answer"]


@pytest.mark.asyncio
async def test_query_stream_endpoint(authenticated_client, seeded_meeting, seeded_participant):
    resp = await authenticated_client.post(
        "/query/stream",
        json={"question": "Who attended the meeting?", "meeting_id": seeded_meeting.id},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


# =============================================================================
# Upload endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_upload_unsupported_file_type(authenticated_client):
    import io
    resp = await authenticated_client.post(
        "/meeting/upload",
        files={"file": ("report.pdf", io.BytesIO(b"fake-content"), "application/pdf")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file(authenticated_client):
    import io
    resp = await authenticated_client.post(
        "/meeting/upload",
        files={"file": ("audio.mp3", io.BytesIO(b""), "audio/mpeg")},
    )
    assert resp.status_code == 400
    assert "Uploaded file is empty" in resp.json()["detail"]
