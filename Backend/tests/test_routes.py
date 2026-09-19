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
        ("DELETE", "/meetings/some-id"),
        ("GET", "/meetings/some-id/audio"),
        ("PATCH", "/meetings/some-id/action-items/some-item"),
        ("PATCH", "/meetings/some-id/participants/some-part"),
        ("POST", "/meetings/some-id/send/email"),
        ("POST", "/meetings/some-id/send/slack"),
        ("POST", "/meetings/some-id/send/jira"),
        ("POST", "/meetings/some-id/send/calendar"),
        ("POST", "/query"),
        ("POST", "/query/stream"),
        ("POST", "/memory/search"),
    ]
    for method, path in routes:
        if method == "GET":
            resp = await async_client.get(path)
        elif method == "DELETE":
            resp = await async_client.delete(path)
        elif method == "PATCH":
            resp = await async_client.patch(path, json={"status": "done"})
        else:
            resp = await async_client.post(path, json={"question": "test"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_meeting_ownership_isolation(async_client, db_session, seeded_meeting, seeded_action_item):
    """User B should not be able to access or modify User A's meeting."""
    import uuid
    from db.models import User
    from core.auth import hash_password, create_access_token

    user_b = User(
        id=f"user-b-{uuid.uuid4().hex[:8]}",
        email=f"userb_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="User B",
    )
    db_session.add(user_b)
    await db_session.commit()

    token_b = create_access_token({"sub": user_b.id, "email": user_b.email})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. User B tries to view User A's meeting details -> 403
    resp = await async_client.get(f"/meetings/{seeded_meeting.id}", headers=headers_b)
    assert resp.status_code == 403

    # 2. User B tries to delete User A's meeting -> 403
    resp = await async_client.delete(f"/meetings/{seeded_meeting.id}", headers=headers_b)
    assert resp.status_code == 403

    # 3. User B tries to update User A's action item -> 403
    resp = await async_client.patch(
        f"/meetings/{seeded_meeting.id}/action-items/{seeded_action_item.id}",
        json={"status": "done"},
        headers=headers_b,
    )
    assert resp.status_code == 403


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
# Human-in-the-Loop Batch Dispatch
# =============================================================================

@pytest.mark.asyncio
async def test_dispatch_meeting_not_found(authenticated_client):
    resp = await authenticated_client.post(
        "/meetings/nonexistent-id/dispatch",
        json={"channels": ["slack", "jira", "calendar"], "days_from_now": 7},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dispatch_meeting_success(authenticated_client, seeded_meeting, seeded_action_item, seeded_participant):
    with patch("api.routes.send_slack_for_meeting", new=AsyncMock(return_value={"success": True, "error": None})), \
         patch("api.routes.send_jira_for_meeting", new=AsyncMock(return_value={"created": ["PROJ-1"], "failed": []})), \
         patch("api.routes.send_calendar_for_meeting", new=AsyncMock(return_value={"event_id": "cal1", "event_url": "https://cal.com/1", "error": None})):
        resp = await authenticated_client.post(
            f"/meetings/{seeded_meeting.id}/dispatch",
            json={"channels": ["slack", "jira", "calendar"], "days_from_now": 7},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["meeting_id"] == seeded_meeting.id
    assert data["results"]["slack"]["status"] == "sent"
    assert data["results"]["jira"]["status"] == "sent"
    assert data["results"]["calendar"]["status"] == "sent"


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


# =============================================================================
# Chat Sessions & Multi-Turn Memory Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_create_and_get_chat_session(authenticated_client, seeded_meeting):
    # 1. Create chat session
    create_resp = await authenticated_client.post(
        "/chat/sessions",
        json={"title": "Q3 Planning Discussion", "meeting_id": seeded_meeting.id},
    )
    assert create_resp.status_code == 200
    session_data = create_resp.json()
    assert session_data["title"] == "Q3 Planning Discussion"
    assert session_data["meeting_id"] == seeded_meeting.id
    assert session_data["messages"] == []
    session_id = session_data["id"]

    # 2. Get chat session by ID
    get_resp = await authenticated_client.get(f"/chat/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == session_id


@pytest.mark.asyncio
async def test_list_chat_sessions(authenticated_client, seeded_meeting):
    # Create two sessions
    await authenticated_client.post(
        "/chat/sessions",
        json={"title": "Session 1", "meeting_id": seeded_meeting.id},
    )
    await authenticated_client.post(
        "/chat/sessions",
        json={"title": "Session 2", "meeting_id": seeded_meeting.id},
    )

    resp = await authenticated_client.get("/chat/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) >= 2
    titles = [s["title"] for s in sessions]
    assert "Session 1" in titles
    assert "Session 2" in titles


@pytest.mark.asyncio
async def test_delete_chat_session(authenticated_client):
    # Create session
    create_resp = await authenticated_client.post(
        "/chat/sessions",
        json={"title": "Session To Delete"},
    )
    assert create_resp.status_code == 200
    session_id = create_resp.json()["id"]

    # Delete session
    del_resp = await authenticated_client.delete(f"/chat/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    # Confirm 404
    get_resp = await authenticated_client.get(f"/chat/sessions/{session_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_session_tenant_isolation(async_client, db_session, authenticated_client):
    """User B cannot access or delete User A's chat session."""
    import uuid
    from db.models import User
    from core.auth import hash_password, create_access_token

    # 1. User A creates session
    create_resp = await authenticated_client.post(
        "/chat/sessions",
        json={"title": "User A Private Session"},
    )
    assert create_resp.status_code == 200
    session_id = create_resp.json()["id"]

    # 2. Setup User B
    user_b = User(
        id=f"user-b-{uuid.uuid4().hex[:8]}",
        email=f"userb_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="User B",
    )
    db_session.add(user_b)
    await db_session.commit()

    token_b = create_access_token({"sub": user_b.id, "email": user_b.email})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 3. User B attempts to read User A's session -> 403
    resp_get = await async_client.get(f"/chat/sessions/{session_id}", headers=headers_b)
    assert resp_get.status_code == 403

    # 4. User B attempts to delete User A's session -> 403
    resp_del = await async_client.delete(f"/chat/sessions/{session_id}", headers=headers_b)
    assert resp_del.status_code == 403


@pytest.mark.asyncio
async def test_query_persists_multiturn_chat_session(authenticated_client, seeded_meeting, seeded_participant):
    # 1. First turn: no session_id supplied -> auto-creates session
    resp1 = await authenticated_client.post(
        "/query",
        json={"question": "Who attended the meeting?", "meeting_id": seeded_meeting.id},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1.get("session_id") is not None
    session_id = data1["session_id"]
    assert "Alice Chen" in data1["answer"]

    # 2. Second turn: provide session_id
    resp2 = await authenticated_client.post(
        "/query",
        json={"question": "What is their role?", "meeting_id": seeded_meeting.id, "session_id": session_id},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2.get("session_id") == session_id

    # 3. Retrieve session from DB endpoint -> should have 4 messages (2 user + 2 assistant)
    session_resp = await authenticated_client.get(f"/chat/sessions/{session_id}")
    assert session_resp.status_code == 200
    sess = session_resp.json()
    assert len(sess["messages"]) == 4
    assert sess["messages"][0]["role"] == "user"
    assert "Who attended the meeting?" in sess["messages"][0]["content"]
    assert sess["messages"][1]["role"] == "assistant"
    assert sess["messages"][2]["role"] == "user"
    assert sess["messages"][3]["role"] == "assistant"


def test_meeting_websocket_progress():
    from starlette.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    with client.websocket_connect("/meetings/ws/test-job-websocket-123") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_text()
        assert data == "pong"


