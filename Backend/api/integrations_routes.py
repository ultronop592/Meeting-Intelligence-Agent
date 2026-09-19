import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.config import settings
from db.database import (
    delete_user_tool_credentials,
    get_db,
    get_user_tool_credentials,
    list_user_tool_credentials,
    save_user_tool_credentials,
)
from db.models import User

logger = logging.getLogger(__name__)

integrations_router = APIRouter(prefix="/integrations", tags=["integrations"])


def _mask_secret(secret: Optional[str]) -> Optional[str]:
    """Masks secrets showing only last 4 characters if long enough."""
    if not secret:
        return None
    s = str(secret).strip()
    if len(s) <= 6:
        return "••••••"
    return f"••••••••{s[-4:]}"


# =============================================================================
# Schemas
# =============================================================================

class JiraCredentialPayload(BaseModel):
    url: str = Field(..., description="Atlassian Jira URL e.g. https://company.atlassian.net")
    email: str = Field(..., description="Atlassian account email")
    api_token: Optional[str] = Field(None, description="Jira API Token from id.atlassian.com")
    project_key: str = Field(..., description="Jira Project Key e.g. PROJ")


class SlackCredentialPayload(BaseModel):
    webhook_url: Optional[str] = Field(None, description="Slack Incoming Webhook URL")
    channel: Optional[str] = Field("#general", description="Default notification channel")


class EmailCredentialPayload(BaseModel):
    api_key: Optional[str] = Field(None, description="SendGrid API Key (SG....)")
    sender_email: str = Field(..., description="Verified sender email address")
    sender_name: Optional[str] = Field("Meeting Intelligence Agent", description="Display name")


class CalendarCredentialPayload(BaseModel):
    calendar_id: str = Field(..., description="Target Google Calendar ID or email")
    credentials_json: Optional[str] = Field(None, description="Google Service Account JSON string")


class ToolStatusResponse(BaseModel):
    tool_name: str
    connected: bool
    is_custom: bool
    details: dict[str, Any]


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    error: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================

@integrations_router.get("", response_model=dict[str, ToolStatusResponse])
async def get_integrations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve integration connection statuses and masked configurations for current user."""
    user_creds = await list_user_tool_credentials(current_user.id, db=db)
    results = {}

    # 1. Jira
    jira_custom = user_creds.get("jira")
    if jira_custom and jira_custom.get("url") and jira_custom.get("email"):
        results["jira"] = ToolStatusResponse(
            tool_name="jira",
            connected=True,
            is_custom=True,
            details={
                "url": jira_custom.get("url"),
                "email": jira_custom.get("email"),
                "project_key": jira_custom.get("project_key"),
                "has_api_token": bool(jira_custom.get("api_token")),
                "api_token_masked": _mask_secret(jira_custom.get("api_token")),
            },
        )
    elif settings.jira_url and settings.jira_email and settings.jira_api_token:
        results["jira"] = ToolStatusResponse(
            tool_name="jira",
            connected=True,
            is_custom=False,
            details={
                "url": settings.jira_url,
                "email": settings.jira_email,
                "project_key": settings.jira_project_key,
                "has_api_token": True,
                "api_token_masked": _mask_secret(settings.jira_api_token),
                "is_system_default": True,
            },
        )
    else:
        results["jira"] = ToolStatusResponse(
            tool_name="jira",
            connected=False,
            is_custom=False,
            details={},
        )

    # 2. Slack
    slack_custom = user_creds.get("slack")
    if slack_custom and slack_custom.get("webhook_url"):
        results["slack"] = ToolStatusResponse(
            tool_name="slack",
            connected=True,
            is_custom=True,
            details={
                "channel": slack_custom.get("channel", "#general"),
                "has_webhook_url": True,
                "webhook_url_masked": _mask_secret(slack_custom.get("webhook_url")),
            },
        )
    elif settings.slack_webhook_url:
        results["slack"] = ToolStatusResponse(
            tool_name="slack",
            connected=True,
            is_custom=False,
            details={
                "channel": settings.slack_channel,
                "has_webhook_url": True,
                "webhook_url_masked": _mask_secret(settings.slack_webhook_url),
                "is_system_default": True,
            },
        )
    else:
        results["slack"] = ToolStatusResponse(
            tool_name="slack",
            connected=False,
            is_custom=False,
            details={},
        )

    # 3. Email (SendGrid)
    email_custom = user_creds.get("email")
    if email_custom and email_custom.get("sender_email") and email_custom.get("api_key"):
        results["email"] = ToolStatusResponse(
            tool_name="email",
            connected=True,
            is_custom=True,
            details={
                "sender_email": email_custom.get("sender_email"),
                "sender_name": email_custom.get("sender_name", "Meeting Intelligence Agent"),
                "has_api_key": True,
                "api_key_masked": _mask_secret(email_custom.get("api_key")),
            },
        )
    elif settings.sendgrid_api_key and settings.sender_email:
        results["email"] = ToolStatusResponse(
            tool_name="email",
            connected=True,
            is_custom=False,
            details={
                "sender_email": settings.sender_email,
                "sender_name": settings.sender_name,
                "has_api_key": True,
                "api_key_masked": _mask_secret(settings.sendgrid_api_key),
                "is_system_default": True,
            },
        )
    else:
        results["email"] = ToolStatusResponse(
            tool_name="email",
            connected=False,
            is_custom=False,
            details={},
        )

    # 4. Google Calendar
    cal_custom = user_creds.get("calendar")
    if cal_custom and cal_custom.get("calendar_id") and cal_custom.get("credentials_json"):
        results["calendar"] = ToolStatusResponse(
            tool_name="calendar",
            connected=True,
            is_custom=True,
            details={
                "calendar_id": cal_custom.get("calendar_id"),
                "has_credentials_json": True,
            },
        )
    elif settings.google_calendar_id and settings.google_calendar_credentials_json:
        results["calendar"] = ToolStatusResponse(
            tool_name="calendar",
            connected=True,
            is_custom=False,
            details={
                "calendar_id": settings.google_calendar_id,
                "has_credentials_json": True,
                "is_system_default": True,
            },
        )
    else:
        results["calendar"] = ToolStatusResponse(
            tool_name="calendar",
            connected=False,
            is_custom=False,
            details={},
        )

    return results


@integrations_router.post("/{tool_name}", response_model=dict[str, Any])
async def update_integration(
    tool_name: str,
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save or update custom credentials for a specific tool."""
    tool_key = tool_name.strip().lower()
    if tool_key not in ("jira", "slack", "email", "calendar"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported tool '{tool_name}'. Allowed: jira, slack, email, calendar",
        )

    result = await save_user_tool_credentials(
        user_id=current_user.id,
        tool_name=tool_key,
        credentials=payload,
        db=db,
    )
    return {
        "message": f"{tool_key.title()} credentials saved successfully.",
        "tool_name": tool_key,
        "is_active": result["is_active"],
    }


@integrations_router.delete("/{tool_name}")
async def disconnect_integration(
    tool_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect/remove custom credentials for a specific tool."""
    tool_key = tool_name.strip().lower()
    deleted = await delete_user_tool_credentials(current_user.id, tool_key, db=db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No custom credentials found for {tool_key}.",
        )
    return {"message": f"{tool_key.title()} disconnected successfully."}


@integrations_router.post("/{tool_name}/test", response_model=TestConnectionResponse)
async def test_integration_connection(
    tool_name: str,
    payload: Optional[dict[str, Any]] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test connection with the provided or stored credentials for a tool."""
    tool_key = tool_name.strip().lower()

    # Load stored credentials if not provided in request body
    creds = payload or {}
    if not creds:
        stored = await get_user_tool_credentials(current_user.id, tool_key, db=db)
        if stored:
            creds = stored

    if tool_key == "jira":
        from tools.jira_tool import resolve_jira_credentials
        resolved = resolve_jira_credentials(creds)
        if not resolved:
            return TestConnectionResponse(
                success=False,
                message="Jira credentials incomplete",
                error="Please provide URL, email, API token, and project key.",
            )
        url, email, token, project = resolved
        try:
            from atlassian import Jira
            client = Jira(url=url, username=email, password=token, cloud=True)
            myself = client.myself()
            display_name = myself.get("displayName", email)
            return TestConnectionResponse(
                success=True,
                message=f"Connected successfully as '{display_name}'! Project: {project}",
            )
        except Exception as exc:
            return TestConnectionResponse(
                success=False,
                message="Failed to connect to Jira",
                error=str(exc),
            )

    elif tool_key == "slack":
        from tools.slack_tool import resolve_slack_credentials
        resolved = resolve_slack_credentials(creds)
        if not resolved:
            return TestConnectionResponse(
                success=False,
                message="Slack webhook incomplete",
                error="Please provide a valid Incoming Webhook URL.",
            )
        webhook_url, channel = resolved
        try:
            from slack_sdk.webhook import WebhookClient
            client = WebhookClient(webhook_url)
            res = client.send(text="🧪 Meeting Intelligence Agent connection test passed successfully!")
            if res.status_code == 200:
                return TestConnectionResponse(
                    success=True,
                    message=f"Slack ping sent successfully to {channel}!",
                )
            return TestConnectionResponse(
                success=False,
                message="Slack webhook error",
                error=f"Status code {res.status_code}: {res.body}",
            )
        except Exception as exc:
            return TestConnectionResponse(
                success=False,
                message="Failed to send Slack test message",
                error=str(exc),
            )

    elif tool_key == "email":
        from tools.email_tool import resolve_email_credentials
        resolved = resolve_email_credentials(creds)
        if not resolved:
            return TestConnectionResponse(
                success=False,
                message="SendGrid credentials incomplete",
                error="Please provide SendGrid API Key and sender email.",
            )
        api_key, sender_email, sender_name = resolved
        try:
            from sendgrid import SendGridAPIClient
            sg = SendGridAPIClient(api_key)
            # Call a lightweight read endpoint to verify API key validity
            res = sg.client.api_keys.get()
            if res.status_code in (200, 202):
                return TestConnectionResponse(
                    success=True,
                    message=f"SendGrid API Key verified successfully for sender: {sender_email}",
                )
            return TestConnectionResponse(
                success=False,
                message="SendGrid verification failed",
                error=f"Status code: {res.status_code}",
            )
        except Exception as exc:
            return TestConnectionResponse(
                success=False,
                message="Failed to verify SendGrid API Key",
                error=str(exc),
            )

    elif tool_key == "calendar":
        from tools.calender_tool import _get_calendar_service, resolve_calendar_credentials
        resolved = resolve_calendar_credentials(creds)
        if not resolved:
            return TestConnectionResponse(
                success=False,
                message="Calendar credentials incomplete",
                error="Please provide Calendar ID and Service Account JSON.",
            )
        cal_id, creds_json = resolved
        try:
            service = _get_calendar_service(creds_json)
            cal = service.calendars().get(calendarId=cal_id).execute()
            cal_summary = cal.get("summary", cal_id)
            return TestConnectionResponse(
                success=True,
                message=f"Connected to Google Calendar '{cal_summary}' successfully!",
            )
        except Exception as exc:
            return TestConnectionResponse(
                success=False,
                message="Failed to access Google Calendar",
                error=str(exc),
            )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown tool '{tool_name}'",
    )
