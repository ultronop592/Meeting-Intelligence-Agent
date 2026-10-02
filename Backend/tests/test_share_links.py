"""test_share_links.py — Integration tests for unauthenticated public share links.

Tests cover:
- Authenticated owner creating, querying, and revoking a share link.
- Unauthenticated public stakeholder access to meeting details via share token.
- Expiration and revocation enforcement (404/410 errors).
- Public audio stream access without credentials.
"""
from datetime import datetime, timedelta, timezone
import pytest
from db.models import ActionItem, Decision, Meeting, Participant


@pytest.mark.asyncio
async def test_create_share_link_authenticated(authenticated_client, seeded_meeting):
    """Owner can generate a public share link for their meeting."""
    resp = await authenticated_client.post(
        f"/meetings/{seeded_meeting.id}/share",
        json={"expires_in_days": 7},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["meeting_id"] == seeded_meeting.id
    assert data["is_publicly_shared"] is True
    assert data["share_token"] is not None
    assert data["share_token"].startswith("sh_")
    assert f"/share/{data['share_token']}" in data["share_url"]
    assert data["expires_at"] is not None


@pytest.mark.asyncio
async def test_create_share_link_unauthorized(async_client, seeded_meeting):
    """Anonymous requests cannot create or configure share links."""
    resp = await async_client.post(
        f"/meetings/{seeded_meeting.id}/share",
        json={"expires_in_days": 7},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_and_revoke_share_link(authenticated_client, seeded_meeting):
    """Owner can check share status and revoke an active share link."""
    # 1. Create link
    create_resp = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/share")
    assert create_resp.status_code == 200
    token = create_resp.json()["share_token"]

    # 2. Get status
    status_resp = await authenticated_client.get(f"/meetings/{seeded_meeting.id}/share")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_publicly_shared"] is True
    assert status_resp.json()["share_token"] == token

    # 3. Revoke link
    del_resp = await authenticated_client.delete(f"/meetings/{seeded_meeting.id}/share")
    assert del_resp.status_code == 200
    assert del_resp.json()["is_publicly_shared"] is False

    # 4. Confirm revoked
    status_after = await authenticated_client.get(f"/meetings/{seeded_meeting.id}/share")
    assert status_after.json()["is_publicly_shared"] is False


@pytest.mark.asyncio
async def test_public_meeting_access_unauthenticated(
    authenticated_client,
    async_client,
    seeded_meeting,
    db_session,
):
    """Stakeholders can view meeting details and action items via token without auth."""
    # Add an action item and decision
    action = ActionItem(
        meeting_id=seeded_meeting.id,
        description="Ship the share link feature",
        owner="Engineering",
        due_date="2026-10-15",
        priority="high",
    )
    decision = Decision(
        meeting_id=seeded_meeting.id,
        description="Adopt unauthenticated public links for stakeholders",
        context="Approved by consensus",
    )
    db_session.add_all([action, decision])
    await db_session.commit()

    # Generate public share link
    share_res = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/share")
    assert share_res.status_code == 200
    token = share_res.json()["share_token"]

    # Access via unauthenticated client (no Authorization header!)
    pub_res = await async_client.get(f"/public/share/{token}")
    assert pub_res.status_code == 200
    data = pub_res.json()

    assert data["title"] == seeded_meeting.title
    assert data["short_summary"] == seeded_meeting.short_summary
    assert len(data["action_items"]) == 1
    assert data["action_items"][0]["description"] == "Ship the share link feature"
    assert len(data["decisions"]) == 1
    assert data["decisions"][0]["description"] == "Adopt unauthenticated public links for stakeholders"
    assert f"/api/public/share/{token}/audio" in data["audio_stream_url"]


@pytest.mark.asyncio
async def test_public_meeting_revoked_returns_404(
    authenticated_client,
    async_client,
    seeded_meeting,
):
    """Revoked share links return 404 to public stakeholders."""
    create_res = await authenticated_client.post(f"/meetings/{seeded_meeting.id}/share")
    token = create_res.json()["share_token"]

    # Revoke link
    await authenticated_client.delete(f"/meetings/{seeded_meeting.id}/share")

    # Access attempt should fail
    resp = await async_client.get(f"/public/share/{token}")
    assert resp.status_code == 404
    assert "inactive or invalid" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_public_meeting_expired_returns_410(
    async_client,
    seeded_meeting,
    db_session,
):
    """Expired share links return 410 Gone."""
    seeded_meeting.share_token = "sh_test_expired_token_123"
    seeded_meeting.is_publicly_shared = True
    seeded_meeting.share_token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    resp = await async_client.get(f"/public/share/{seeded_meeting.share_token}")
    assert resp.status_code == 410
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_public_meeting_invalid_token_returns_404(async_client):
    """Non-existent token returns 404."""
    resp = await async_client.get("/public/share/sh_non_existent_token_99999")
    assert resp.status_code == 404
