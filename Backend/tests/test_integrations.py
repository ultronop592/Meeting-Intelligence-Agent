import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_get_integrations_unauthenticated(async_client):
    resp = await async_client.get("/integrations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_integrations_initial(authenticated_client):
    resp = await authenticated_client.get("/integrations")
    assert resp.status_code == 200
    data = resp.json()
    assert "jira" in data
    assert "slack" in data
    assert "email" in data
    assert "calendar" in data
    for tool in ("jira", "slack", "email", "calendar"):
        assert "connected" in data[tool]
        assert "is_custom" in data[tool]
        assert "details" in data[tool]


@pytest.mark.asyncio
async def test_save_and_get_jira_credentials(authenticated_client):
    payload = {
        "url": "https://myorg.atlassian.net",
        "email": "agent@myorg.com",
        "api_token": "secret-token-12345",
        "project_key": "PROJ",
    }
    save_resp = await authenticated_client.post("/integrations/jira", json=payload)
    assert save_resp.status_code == 200
    assert save_resp.json()["tool_name"] == "jira"
    assert save_resp.json()["is_active"] is True

    get_resp = await authenticated_client.get("/integrations")
    assert get_resp.status_code == 200
    jira_info = get_resp.json()["jira"]
    assert jira_info["connected"] is True
    assert jira_info["is_custom"] is True
    assert jira_info["details"]["url"] == "https://myorg.atlassian.net"
    assert jira_info["details"]["email"] == "agent@myorg.com"
    assert jira_info["details"]["project_key"] == "PROJ"
    assert jira_info["details"]["has_api_token"] is True
    # Secret must be masked and never returned in cleartext
    assert "secret-token-12345" not in str(jira_info)
    assert "2345" in jira_info["details"]["api_token_masked"]


@pytest.mark.asyncio
async def test_save_and_get_slack_credentials(authenticated_client):
    payload = {
        "webhook_url": "https://hooks.slack.com/services/T00/B00/X12345678",
        "channel": "#product-team",
    }
    save_resp = await authenticated_client.post("/integrations/slack", json=payload)
    assert save_resp.status_code == 200

    get_resp = await authenticated_client.get("/integrations")
    assert get_resp.status_code == 200
    slack_info = get_resp.json()["slack"]
    assert slack_info["connected"] is True
    assert slack_info["is_custom"] is True
    assert slack_info["details"]["channel"] == "#product-team"
    assert slack_info["details"]["has_webhook_url"] is True
    assert "X12345678" not in slack_info["details"]["webhook_url_masked"]


@pytest.mark.asyncio
async def test_save_and_get_email_credentials(authenticated_client):
    payload = {
        "api_key": "SG.secret-sendgrid-api-key-9999",
        "sender_email": "notifications@mycompany.com",
        "sender_name": "Executive Meeting Assistant",
    }
    save_resp = await authenticated_client.post("/integrations/email", json=payload)
    assert save_resp.status_code == 200

    get_resp = await authenticated_client.get("/integrations")
    assert get_resp.status_code == 200
    email_info = get_resp.json()["email"]
    assert email_info["connected"] is True
    assert email_info["is_custom"] is True
    assert email_info["details"]["sender_email"] == "notifications@mycompany.com"
    assert email_info["details"]["sender_name"] == "Executive Meeting Assistant"
    assert email_info["details"]["has_api_key"] is True
    assert "SG.secret-sendgrid-api-key-9999" not in str(email_info)


@pytest.mark.asyncio
async def test_save_and_get_calendar_credentials(authenticated_client):
    payload = {
        "calendar_id": "c_12345678@group.calendar.google.com",
        "credentials_json": '{"type": "service_account", "project_id": "test-cal"}',
    }
    save_resp = await authenticated_client.post("/integrations/calendar", json=payload)
    assert save_resp.status_code == 200

    get_resp = await authenticated_client.get("/integrations")
    assert get_resp.status_code == 200
    cal_info = get_resp.json()["calendar"]
    assert cal_info["connected"] is True
    assert cal_info["is_custom"] is True
    assert cal_info["details"]["calendar_id"] == "c_12345678@group.calendar.google.com"
    assert cal_info["details"]["has_credentials_json"] is True


@pytest.mark.asyncio
async def test_disconnect_integration(authenticated_client):
    # 1. Save credentials
    await authenticated_client.post(
        "/integrations/jira",
        json={
            "url": "https://delete-me.atlassian.net",
            "email": "del@test.com",
            "api_token": "token",
            "project_key": "DEL",
        },
    )

    # 2. Disconnect
    del_resp = await authenticated_client.delete("/integrations/jira")
    assert del_resp.status_code == 200
    assert "disconnected successfully" in del_resp.json()["message"]

    # 3. Status should no longer be custom
    get_resp = await authenticated_client.get("/integrations")
    assert get_resp.json()["jira"]["is_custom"] is False

    # 4. Deleting non-existent credentials returns 404
    del_again = await authenticated_client.delete("/integrations/jira")
    assert del_again.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_integrations(async_client, db_session, authenticated_client):
    """User B cannot see or overwrite User A's custom tool credentials."""
    import uuid
    from db.models import User
    from core.auth import hash_password, create_access_token

    # 1. User A sets custom Slack channel and webhook
    await authenticated_client.post(
        "/integrations/slack",
        json={
            "webhook_url": "https://hooks.slack.com/services/USER_A_WEBHOOK_1234",
            "channel": "#user-a-private",
        },
    )

    # 2. Create User B
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

    # 3. User B queries integrations
    resp_b = await async_client.get("/integrations", headers=headers_b)
    assert resp_b.status_code == 200
    slack_b = resp_b.json()["slack"]

    # User B should NOT see User A's custom integration
    assert slack_b["is_custom"] is False
    assert slack_b.get("details", {}).get("channel") != "#user-a-private"


@pytest.mark.asyncio
async def test_test_connection_jira_mock(authenticated_client):
    with patch("atlassian.Jira") as MockJira:
        mock_instance = MagicMock()
        mock_instance.myself.return_value = {"displayName": "Test Engineer"}
        MockJira.return_value = mock_instance

        resp = await authenticated_client.post(
            "/integrations/jira/test",
            json={
                "url": "https://test.atlassian.net",
                "email": "test@test.com",
                "api_token": "valid-token",
                "project_key": "PROJ",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Test Engineer" in data["message"]


@pytest.mark.asyncio
async def test_test_connection_slack_mock(authenticated_client):
    with patch("slack_sdk.webhook.WebhookClient") as MockSlack:
        mock_instance = MagicMock()
        mock_instance.send.return_value = MagicMock(status_code=200, body="ok")
        MockSlack.return_value = mock_instance

        resp = await authenticated_client.post(
            "/integrations/slack/test",
            json={
                "webhook_url": "https://hooks.slack.com/services/T00/B00/X00",
                "channel": "#test-channel",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Slack ping sent successfully" in data["message"]
