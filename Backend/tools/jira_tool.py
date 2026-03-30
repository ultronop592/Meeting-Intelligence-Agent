"""
File: backend/tools/jira_tool.py
Node 5 of the LangGraph pipeline.

WHAT IT DOES
------------
Creates one Jira ticket per action item extracted from the meeting.
Each ticket is automatically assigned to the correct person with
the right priority, due date, and description.

USED IN TWO WAYS
----------------
1. AUTO (LangGraph Node 5):
   Called automatically after save_to_database succeeds.
   Creates tickets for ALL action items in one go.

2. MANUAL (FastAPI endpoint):
   POST /api/meetings/{id}/send/jira
   Called when user clicks "Create Jira Tickets" button on the frontend.
   Can re-create tickets even if auto-send already ran.

HOW JIRA REST API WORKS
------------------------
We use the atlassian-python-api SDK which wraps the Jira REST API.
Each ticket creation is one POST request to:
  POST https://yourname.atlassian.net/rest/api/3/issue

The ticket body must follow Jira's Atlassian Document Format (ADF)
for the description field — plain strings are not accepted in v3.

FASTAPI CONTEXT
---------------
Sync function — atlassian-python-api is synchronous.
Called from FastAPI via asyncio.run_in_executor() so it doesn't
block the async event loop.
"""

import logging
from typing import Optional

from atlassian import Jira
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from backend.core.config import settings
from backend.db.database import log_notification
from backend.models.schemas import AgentState, ActionItem, Priority
import asyncio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Priority mapping — our values → Jira priority names
# ---------------------------------------------------------------------------

PRIORITY_MAP: dict[str, str] = {
    Priority.HIGH.value:   "High",
    Priority.MEDIUM.value: "Medium",
    Priority.LOW.value:    "Low",
}


# ---------------------------------------------------------------------------
# Helper — build Jira ticket payload
# ---------------------------------------------------------------------------

def _build_ticket_payload(
    item:        ActionItem,
    project_key: str,
) -> dict:
    """
    Builds the Jira issue creation payload for one action item.

    Uses Atlassian Document Format (ADF) for the description.
    ADF is required by Jira REST API v3 — plain strings are rejected.

    ADF structure for a simple paragraph:
    {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "your text here"}]
            }
        ]
    }
    """
    description_adf = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Action item extracted from meeting recording.\n\n"
                            f"Owner: {item.owner}\n"
                            f"Due date: {item.due_date}\n"
                            f"Priority: {item.priority.value.capitalize()}\n\n"
                            f"Task: {item.description}"
                        ),
                    }
                ],
            }
        ],
    }

    return {
        "project":     {"key": project_key},
        "summary":     item.description,
        "description": description_adf,
        "issuetype":   {"name": "Task"},
        "priority":    {"name": PRIORITY_MAP.get(item.priority.value, "Medium")},
        # Due date format: YYYY-MM-DD (matches our stored format)
        "duedate":     item.due_date,
    }


# ---------------------------------------------------------------------------
# Single ticket creation with retry
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _create_single_ticket(
    jira_client: Jira,
    payload:     dict,
) -> str:
    """
    Creates one Jira ticket and returns the ticket key (e.g. 'PROJ-101').
    Retries up to 3 times on any failure.
    """
    response = jira_client.issue_create(fields=payload)
    return response.get("key", "")


# ---------------------------------------------------------------------------
# LangGraph Node 5 + Manual re-send function
# ---------------------------------------------------------------------------

def create_jira_tickets(state: AgentState) -> dict:
    """
    LangGraph Node 5 — Create Jira Tickets.

    Called by:  graph/agent_graph.py (auto) + FastAPI route (manual)

    INPUT  (reads from AgentState): extraction, meeting_id
    OUTPUT (writes to AgentState):  jira_ticket_ids, completed_nodes

    Creates one Jira ticket per action item.
    Non-fatal: if one ticket fails, logs the error and continues
    creating the remaining tickets.
    """
    logger.info("Node 5 — create_jira_tickets | meeting_id: %s", state.meeting_id)

    # --- Guard: need action items to create tickets --------------------------
    if not state.extraction or not state.extraction.action_items:
        logger.warning("create_jira_tickets: no action items found — skipping.")
        return {
            "completed_nodes": state.completed_nodes + ["create_jira_tickets"],
        }

    # --- Guard: check Jira config is set ------------------------------------
    if not all([
        settings.jira_url,
        settings.jira_email,
        settings.jira_api_token,
        settings.jira_project_key,
    ]):
        error = "Jira credentials not configured in .env — skipping ticket creation."
        logger.warning(error)
        return {
            "errors":          state.errors + [error],
            "completed_nodes": state.completed_nodes + ["create_jira_tickets"],
        }

    # --- Initialise Jira client ---------------------------------------------
    jira_client = Jira(
        url=settings.jira_url,
        username=settings.jira_email,
        password=settings.jira_api_token,   # API token used as password
        cloud=True,                          # Must be True for Jira Cloud
    )

    ticket_ids: list[str] = []
    errors:     list[str] = list(state.errors)

    # --- Create one ticket per action item -----------------------------------
    for i, item in enumerate(state.extraction.action_items):
        try:
            payload    = _build_ticket_payload(item, settings.jira_project_key)
            ticket_key = _create_single_ticket(jira_client, payload)

            if ticket_key:
                ticket_ids.append(ticket_key)
                logger.info(
                    "Jira ticket created: %s | owner: %s | task: %s",
                    ticket_key,
                    item.owner,
                    item.description[:50],
                )

                # Log success to notifications_log table
                if state.meeting_id:
                    asyncio.run(log_notification(
                        meeting_id=state.meeting_id,
                        notification_type="jira",
                        status="sent",
                        detail=f"{ticket_key}: {item.description[:80]}",
                    ))

        except Exception as e:
            error_msg = f"Failed to create Jira ticket for '{item.description[:50]}': {e}"
            logger.error(error_msg)
            errors.append(error_msg)

            # Log failure to notifications_log table
            if state.meeting_id:
                asyncio.run(log_notification(
                    meeting_id=state.meeting_id,
                    notification_type="jira",
                    status="failed",
                    detail=str(e)[:200],
                ))

    logger.info(
        "Jira complete | created: %d | failed: %d",
        len(ticket_ids),
        len(state.extraction.action_items) - len(ticket_ids),
    )

    return {
        "jira_ticket_ids": ticket_ids,
        "errors":          errors,
        "completed_nodes": state.completed_nodes + ["create_jira_tickets"],
    }


# ---------------------------------------------------------------------------
# Standalone function for manual re-send from FastAPI route
# ---------------------------------------------------------------------------

async def send_jira_for_meeting(
    meeting_id:   str,
    action_items: list[ActionItem],
) -> dict:
    """
    Called by FastAPI POST /api/meetings/{id}/send/jira
    when the user manually clicks "Create Jira Tickets".

    This is the async wrapper around the same logic above,
    designed for direct FastAPI route usage without a full AgentState.

    RETURNS:
        {"created": [...ticket_keys], "failed": [...error_msgs]}
    """
    logger.info("Manual Jira send | meeting_id: %s | items: %d", meeting_id, len(action_items))

    if not all([
        settings.jira_url,
        settings.jira_email,
        settings.jira_api_token,
        settings.jira_project_key,
    ]):
        raise ValueError("Jira credentials not configured in .env")

    jira_client = Jira(
        url=settings.jira_url,
        username=settings.jira_email,
        password=settings.jira_api_token,
        cloud=True,
    )

    created: list[str] = []
    failed:  list[str] = []

    for item in action_items:
        try:
            payload    = _build_ticket_payload(item, settings.jira_project_key)
            ticket_key = _create_single_ticket(jira_client, payload)

            if ticket_key:
                created.append(ticket_key)
                await log_notification(
                    meeting_id=meeting_id,
                    notification_type="jira",
                    status="sent",
                    detail=f"{ticket_key}: {item.description[:80]}",
                )
        except Exception as e:
            failed.append(str(e))
            await log_notification(
                meeting_id=meeting_id,
                notification_type="jira",
                status="failed",
                detail=str(e)[:200],
            )

    return {"created": created, "failed": failed}