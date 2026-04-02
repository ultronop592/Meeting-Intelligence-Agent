"""
File: backend/tools/calendar_tool.py
Node 6 of the LangGraph pipeline.

WHAT IT DOES
------------
Books a follow-up Google Calendar meeting for all participants
identified in the meeting transcript. The event is created via
the Google Calendar API using a Service Account.

USED IN TWO WAYS
----------------
1. AUTO (LangGraph Node 6):
   Called automatically after create_jira_tickets.
   Books a follow-up meeting 7 days after the original recording.

2. MANUAL (FastAPI endpoint):
   POST /api/meetings/{id}/send/calendar
   Called when user clicks "Book Follow-up" button on the frontend.

HOW GOOGLE CALENDAR API WORKS
------------------------------
We use a Service Account — a special Google account your code
logs in as programmatically, without any human clicking "Allow".

Setup:
1. Create a Service Account in Google Cloud Console
2. Download the JSON credentials file
3. Share your calendar with the service account email address
4. Paste the JSON contents into GOOGLE_CALENDAR_CREDENTIALS_JSON in .env

The service account then creates events on your calendar as if it were you.

FASTAPI CONTEXT
---------------
Sync function — google-api-python-client is synchronous.
FastAPI calls this via asyncio.run_in_executor().
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from backend.core.config import settings
from backend.db.database import log_notification
from backend.models.schemas import AgentState
import asyncio

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


# ---------------------------------------------------------------------------
# Build Google Calendar service client
# ---------------------------------------------------------------------------

def _get_calendar_service():
    """
    Creates and returns an authenticated Google Calendar API client.
    Reads service account credentials from GOOGLE_CALENDAR_CREDENTIALS_JSON.
    Raises ValueError if credentials are not configured.
    """
    if not settings.google_calendar_credentials_json:
        raise ValueError("GOOGLE_CALENDAR_CREDENTIALS_JSON not set in .env")

    try:
        # Parse the JSON credentials string from .env
        credentials_info = json.loads(settings.google_calendar_credentials_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in GOOGLE_CALENDAR_CREDENTIALS_JSON: {e}")

    # Create service account credentials with Calendar scope
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=SCOPES,
    )

    # Build the Calendar API client
    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
    return service


# ---------------------------------------------------------------------------
# Build the calendar event payload
# ---------------------------------------------------------------------------

def _build_event_payload(
    meeting_title: str,
    participants:  list[str],
    emails:        list[str],
    follow_up_date: datetime,
) -> dict:
    """
    Builds the Google Calendar event creation payload.

    The event is scheduled 7 days after the meeting was processed,
    at 10:00 AM for 1 hour — a sensible default for a follow-up.

    Attendees list uses emails if available, otherwise skipped.
    """
    # Event start: follow_up_date at 10:00 AM UTC
    start_dt = follow_up_date.replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    # Event end: 1 hour later
    end_dt = start_dt + timedelta(hours=1)

    # Format as RFC3339 strings (Google Calendar requirement)
    start_str = start_dt.isoformat()
    end_str   = end_dt.isoformat()

    # Build attendees list — only include participants with known emails
    attendees = [{"email": email} for email in emails if email]

    return {
        "summary":     f"Follow-up: {meeting_title}",
        "description": (
            f"Follow-up meeting for: {meeting_title}\n\n"
            f"Participants: {', '.join(participants)}\n\n"
            "Agenda: Review action items and decisions from the previous meeting."
        ),
        "start": {
            "dateTime": start_str,
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end_str,
            "timeZone": "UTC",
        },
        "attendees":  attendees,
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email",  "minutes": 24 * 60},  # 1 day before
                {"method": "popup",  "minutes": 15},         # 15 min before
            ],
        },
        # Send email invites to all attendees automatically
        "guestsCanModifyEvent": False,
    }


# ---------------------------------------------------------------------------
# API call with retry
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(HttpError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _create_calendar_event(service, calendar_id: str, event_payload: dict) -> dict:
    """
    Creates a Google Calendar event and returns the full event resource.
    sendUpdates="all" sends email invitations to all attendees.
    """
    return (
        service.events()
        .insert(
            calendarId=calendar_id,
            body=event_payload,
            sendUpdates="all",
        )
        .execute()
    )


# ---------------------------------------------------------------------------
# LangGraph Node 6 + Manual re-send function
# ---------------------------------------------------------------------------

def book_calendar(state: AgentState) -> dict:
    """
    LangGraph Node 6 — Book Google Calendar Follow-up.

    Called by:  graph/agent_graph.py (auto) + FastAPI route (manual)

    INPUT  (reads from AgentState): summary, extraction, meeting_id
    OUTPUT (writes to AgentState):  calendar_event_id, completed_nodes

    Non-fatal: if booking fails, logs error and continues to Node 7.
    """
    logger.info("Node 6 — book_calendar | meeting_id: %s", state.meeting_id)

    # --- Guard: need a summary for the meeting title -------------------------
    if not state.summary:
        error = "book_calendar: no summary — cannot determine meeting title."
        logger.warning(error)
        return {
            "errors":          state.errors + [error],
            "completed_nodes": state.completed_nodes + ["book_calendar"],
        }

    # --- Guard: check Calendar config is set --------------------------------
    if not settings.google_calendar_credentials_json or not settings.google_calendar_id:
        error = "Google Calendar credentials not configured in .env — skipping."
        logger.warning(error)
        return {
            "errors":          state.errors + [error],
            "completed_nodes": state.completed_nodes + ["book_calendar"],
        }

    try:
        service = _get_calendar_service()

        # Participants list — use names from extraction if available
        participants = (
            state.extraction.participants
            if state.extraction and state.extraction.participants
            else ["Meeting participants"]
        )

        # For auto-booking we don't have emails yet (they're optional in DB)
        # The user can add emails later in settings and re-book manually
        emails: list[str] = []

        # Schedule follow-up 7 days from now
        follow_up_date = datetime.now(timezone.utc) + timedelta(days=7)

        event_payload = _build_event_payload(
            meeting_title=state.summary.title,
            participants=participants,
            emails=emails,
            follow_up_date=follow_up_date,
        )

        event = _create_calendar_event(
            service,
            settings.google_calendar_id,
            event_payload,
        )

        event_id  = event.get("id", "")
        event_url = event.get("htmlLink", "")

        logger.info(
            "Calendar event created | id: %s | url: %s",
            event_id,
            event_url,
        )

        # Log to notifications_log
        if state.meeting_id:
            asyncio.run(log_notification(
                meeting_id=state.meeting_id,
                notification_type="calendar",
                status="sent",
                detail=event_url,
            ))

        return {
            "calendar_event_id": event_id,
            "completed_nodes":   state.completed_nodes + ["book_calendar"],
        }

    except ValueError as e:
        error = f"Calendar configuration error: {e}"
        logger.error(error)
        if state.meeting_id:
            asyncio.run(log_notification(
                meeting_id=state.meeting_id,
                notification_type="calendar",
                status="failed",
                detail=str(e)[:200],
            ))
        return {
            "errors":          state.errors + [error],
            "completed_nodes": state.completed_nodes + ["book_calendar"],
        }

    except HttpError as e:
        error = f"Google Calendar API error: {e.status_code} — {e.reason}"
        logger.error(error)
        if state.meeting_id:
            asyncio.run(log_notification(
                meeting_id=state.meeting_id,
                notification_type="calendar",
                status="failed",
                detail=error,
            ))
        return {
            "errors":          state.errors + [error],
            "completed_nodes": state.completed_nodes + ["book_calendar"],
        }

    except Exception as e:
        error = f"Unexpected Calendar error: {e}"
        logger.exception(error)
        return {
            "errors":          state.errors + [error],
            "completed_nodes": state.completed_nodes + ["book_calendar"],
        }


# ---------------------------------------------------------------------------
# Standalone function for manual send from FastAPI route
# ---------------------------------------------------------------------------

async def send_calendar_for_meeting(
    meeting_id:    str,
    meeting_title: str,
    participants:  list[str],
    emails:        list[str],
    days_from_now: int = 7,
) -> dict:
    """
    Called by FastAPI POST /api/meetings/{id}/send/calendar
    when user manually clicks "Book Follow-up".

    emails — participant email addresses from the frontend form
    days_from_now — how many days ahead to schedule (default 7)

    RETURNS:
        {"event_id": "...", "event_url": "...", "error": None}
    """
    logger.info(
        "Manual calendar send | meeting_id: %s | participants: %d",
        meeting_id,
        len(participants),
    )

    try:
        service = _get_calendar_service()

        follow_up_date = datetime.now(timezone.utc) + timedelta(days=days_from_now)

        event_payload = _build_event_payload(
            meeting_title=meeting_title,
            participants=participants,
            emails=emails,
            follow_up_date=follow_up_date,
        )

        event = _create_calendar_event(
            service,
            settings.google_calendar_id,
            event_payload,
        )

        event_id  = event.get("id", "")
        event_url = event.get("htmlLink", "")

        await log_notification(
            meeting_id=meeting_id,
            notification_type="calendar",
            status="sent",
            detail=event_url,
        )

        return {"event_id": event_id, "event_url": event_url, "error": None}

    except Exception as e:
        await log_notification(
            meeting_id=meeting_id,
            notification_type="calendar",
            status="failed",
            detail=str(e)[:200],
        )
        return {"event_id": None, "event_url": None, "error": str(e)}