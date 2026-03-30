"""
File: backend/tools/slack_tool.py
Part of Node 7 of the LangGraph pipeline.

WHAT IT DOES
------------
Posts the meeting summary and action items to a Slack channel
using Slack Incoming Webhooks. Also contains the send_notifications()
function which is the actual LangGraph Node 7 — it calls BOTH
email_tool.py and this file in one node.

USED IN TWO WAYS
----------------
1. AUTO (LangGraph Node 7 via send_notifications):
   Called automatically as the final node in the pipeline.

2. MANUAL (FastAPI endpoint):
   POST /api/meetings/{id}/send/slack
   Called when user clicks "Post to Slack" button.

HOW SLACK WEBHOOKS WORK
------------------------
A Slack Incoming Webhook is a URL you POST JSON to.
Slack immediately shows the message in the configured channel.

Format: {"text": "...", "blocks": [...]}

We use Slack Block Kit (blocks) for rich formatting:
  - Header block    → meeting title
  - Section block   → short summary
  - Divider block   → visual separator
  - Section block   → action items list
  - Context block   → metadata (duration, participant count)

No OAuth, no bot token, no complex setup — just one URL in .env.

FASTAPI CONTEXT
---------------
Uses the slack-sdk which is sync.
FastAPI calls this via run_in_executor().
"""

import logging
from slack_sdk.webhook import WebhookClient
from slack_sdk.errors import SlackApiError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from backend.core.config import settings
from backend.db.database import log_notification
from backend.models.schemas import AgentState, ActionItem
from backend.tools.email_tool import send_emails
import asyncio

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Build Slack Block Kit message
# ---------------------------------------------------------------------------

def _build_slack_blocks(
    meeting_title:   str,
    short_summary:   str,
    action_items:    list[ActionItem],
    decisions_count: int,
    participants:    list[str],
    duration_minutes: int,
) -> list[dict]:
    """
    Builds a rich Slack Block Kit message.

    Block Kit gives us formatted text, dividers, and structured layout.
    Much more readable than a plain text message.

    Slack has a 3000-char limit per text block — we truncate if needed.
    """

    # Format action items as bullet list
    if action_items:
        items_text = "\n".join([
            f"• *{item.owner}* — {item.description} "
            f"_(due {item.due_date}, {item.priority.value} priority)_"
            for item in action_items[:10]  # Max 10 to stay under char limit
        ])
        if len(action_items) > 10:
            items_text += f"\n_...and {len(action_items) - 10} more_"
    else:
        items_text = "_No action items identified._"

    # Truncate summary if too long for Slack
    summary_text = short_summary[:500] + "..." if len(short_summary) > 500 else short_summary

    blocks = [
        # Header — meeting title
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Meeting Summary: {meeting_title}"[:150],
            },
        },

        # Summary section
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary*\n{summary_text}",
            },
        },

        {"type": "divider"},

        # Action items
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Action Items ({len(action_items)})*\n{items_text}",
            },
        },

        {"type": "divider"},

        # Metadata footer
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Duration: *{duration_minutes} min* &nbsp;|&nbsp; "
                        f"Participants: *{len(participants)}* &nbsp;|&nbsp; "
                        f"Decisions: *{decisions_count}* &nbsp;|&nbsp; "
                        f"Processed by Meeting Intelligence Agent"
                    ),
                }
            ],
        },
    ]

    return blocks


# ---------------------------------------------------------------------------
# Slack webhook send with retry
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _post_to_slack(webhook_url: str, text: str, blocks: list[dict]) -> bool:
    """
    Posts a message to Slack via Incoming Webhook.
    text is the fallback for clients that don't support Block Kit.
    Returns True on success, raises on failure.
    """
    client   = WebhookClient(url=webhook_url)
    response = client.send(text=text, blocks=blocks)

    if response.status_code != 200:
        raise SlackApiError(
            message=f"Slack webhook returned {response.status_code}: {response.body}",
            response=response,
        )

    return True


# ---------------------------------------------------------------------------
# LangGraph Node 7 — send_notifications
# This is the ACTUAL node registered in agent_graph.py.
# It calls BOTH email_tool.py (emails) and this file (Slack).
# ---------------------------------------------------------------------------

def send_notifications(state: AgentState) -> dict:
    """
    LangGraph Node 7 — Send Notifications.

    This is the final node in the LangGraph pipeline.
    It handles BOTH email sending AND Slack posting.

    Called by:  graph/agent_graph.py (auto only)
    Manual sends use send_slack_for_meeting() + send_email_for_meeting()
    directly from FastAPI routes.

    INPUT  (reads from AgentState): summary, extraction, meeting_id
    OUTPUT (writes to AgentState):  notification_results, completed_nodes

    Non-fatal: failures are logged but do not stop node completion.
    """
    logger.info("Node 7 — send_notifications | meeting_id: %s", state.meeting_id)

    if not state.summary or not state.extraction:
        error = "send_notifications: missing summary or extraction — skipping."
        logger.warning(error)
        return {
            "errors":          state.errors + [error],
            "completed_nodes": state.completed_nodes + ["send_notifications"],
        }

    notification_results: list[dict] = list(state.notification_results)
    errors: list[str]                = list(state.errors)

    # --- 1. Send Slack notification ------------------------------------------
    if settings.slack_webhook_url:
        try:
            blocks = _build_slack_blocks(
                meeting_title=state.summary.title,
                short_summary=state.summary.short_summary,
                action_items=state.extraction.action_items,
                decisions_count=len(state.extraction.decisions),
                participants=state.extraction.participants,
                duration_minutes=state.summary.duration_minutes,
            )

            _post_to_slack(
                webhook_url=settings.slack_webhook_url,
                text=f"Meeting Summary: {state.summary.title}",
                blocks=blocks,
            )

            logger.info("Slack notification sent to %s", settings.slack_channel)
            notification_results.append({"type": "slack", "status": "sent"})

            if state.meeting_id:
                asyncio.run(log_notification(
                    meeting_id=state.meeting_id,
                    notification_type="slack",
                    status="sent",
                    detail=settings.slack_channel,
                ))

        except Exception as e:
            error_msg = f"Slack notification failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            notification_results.append({"type": "slack", "status": "failed", "error": str(e)})

            if state.meeting_id:
                asyncio.run(log_notification(
                    meeting_id=state.meeting_id,
                    notification_type="slack",
                    status="failed",
                    detail=str(e)[:200],
                ))
    else:
        logger.warning("SLACK_WEBHOOK_URL not configured — skipping Slack notification.")

    # --- 2. Send personalised emails ----------------------------------------
    # For auto-send: we don't have emails stored yet in the pipeline
    # (emails are added later via frontend settings page).
    # So we attempt email sending but it will only work if participants
    # have emails stored from a previous session or settings page.
    # The manual send (POST /api/meetings/{id}/send/email) is the
    # proper way to send emails with full email addresses.
    if settings.sendgrid_api_key:
        try:
            # Build participant_emails from extraction
            # In auto-send, emails are empty — this is expected
            # Users add emails via the settings/participants page
            participant_emails: dict[str, str] = {}

            email_result = send_emails(
                state=state,
                participant_emails=participant_emails,
            )

            notification_results.append({
                "type":   "email",
                "status": "sent",
                "sent":   email_result["sent"],
                "failed": email_result["failed"],
            })

        except Exception as e:
            error_msg = f"Email sending failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
    else:
        logger.warning("SENDGRID_API_KEY not configured — skipping emails.")

    logger.info(
        "Node 7 complete | notifications: %d",
        len(notification_results),
    )

    return {
        "notification_results": notification_results,
        "errors":               errors,
        "completed_nodes":      state.completed_nodes + ["send_notifications"],
    }


# ---------------------------------------------------------------------------
# Standalone async function for FastAPI manual send route
# ---------------------------------------------------------------------------

async def send_slack_for_meeting(
    meeting_id:      str,
    meeting_title:   str,
    short_summary:   str,
    action_items:    list[ActionItem],
    participants:    list[str],
    decisions_count: int,
    duration_minutes: int,
) -> dict:
    """
    Called by FastAPI POST /api/meetings/{id}/send/slack
    when user clicks "Post to Slack" button.

    RETURNS:
        {"success": True, "error": None}
    """
    logger.info("Manual Slack send | meeting_id: %s", meeting_id)

    if not settings.slack_webhook_url:
        return {"success": False, "error": "SLACK_WEBHOOK_URL not configured"}

    try:
        blocks = _build_slack_blocks(
            meeting_title=meeting_title,
            short_summary=short_summary,
            action_items=action_items,
            decisions_count=decisions_count,
            participants=participants,
            duration_minutes=duration_minutes,
        )

        _post_to_slack(
            webhook_url=settings.slack_webhook_url,
            text=f"Meeting Summary: {meeting_title}",
            blocks=blocks,
        )

        await log_notification(
            meeting_id=meeting_id,
            notification_type="slack",
            status="sent",
            detail=settings.slack_channel,
        )

        return {"success": True, "error": None}

    except Exception as e:
        await log_notification(
            meeting_id=meeting_id,
            notification_type="slack",
            status="failed",
            detail=str(e)[:200],
        )
        return {"success": False, "error": str(e)}