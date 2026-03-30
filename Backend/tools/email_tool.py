"""
File: backend/tools/email_tool.py
Part of Node 7 of the LangGraph pipeline.

WHAT IT DOES
------------
Sends each meeting participant a PERSONALISED email containing
ONLY their own action items. Not a group email — each person
gets a targeted message showing exactly what they need to do.

USED IN TWO WAYS
----------------
1. AUTO (LangGraph Node 7 via send_notifications):
   Called automatically after book_calendar.
   Sends emails to all participants who have email addresses.

2. MANUAL (FastAPI endpoint):
   POST /api/meetings/{id}/send/email
   Called when user clicks "Email Participants" button.
   User can select which participants to email from the frontend.

EMAIL PERSONALISATION
---------------------
If Alice has 2 action items and Bob has 1:
  - Alice receives: her 2 items + full summary
  - Bob receives:   his 1 item + full summary
  - Neither sees the other person's tasks

This is far more useful than one group email with all 6 tasks mixed together.

SENDGRID
---------
SendGrid is a transactional email API. We use it instead of sending
directly from Gmail because:
  - Gmail blocks programmatic sending after ~500 emails/day
  - Emails from Gmail APIs often go to spam
  - SendGrid handles deliverability, bounces, and unsubscribes
  - Free tier: 100 emails/day (enough for testing + light production)

FASTAPI CONTEXT
---------------
Uses sendgrid Python SDK which is synchronous.
Called from FastAPI via asyncio.run_in_executor().
"""

import logging
from typing import Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To, Content
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from backend.core.config import settings
from backend.db.database import log_notification
from backend.models.schemas import AgentState, ActionItem
import asyncio

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email template builders
# ---------------------------------------------------------------------------

def _build_email_subject(meeting_title: str) -> str:
    return f"Your action items — {meeting_title}"


def _build_email_html(
    recipient_name:  str,
    meeting_title:   str,
    short_summary:   str,
    my_action_items: list[ActionItem],
    all_action_items: list[ActionItem],
) -> str:
    """
    Builds a clean HTML email body.

    Structure:
    - Greeting with recipient's name
    - Short meeting summary
    - YOUR action items (personalised — only this person's tasks)
    - All action items (for full context)

    Inline CSS only — email clients strip <style> blocks.
    """

    # Build "your tasks" section
    if my_action_items:
        my_items_html = "".join([
            f"""
            <tr>
              <td style="padding:10px 16px;border-bottom:1px solid #f0f0f0">
                <div style="font-weight:600;color:#1a1a1a;font-size:14px">
                  {item.description}
                </div>
                <div style="color:#666;font-size:12px;margin-top:4px">
                  Due: {item.due_date} &nbsp;|&nbsp;
                  Priority: <span style="color:{'#dc3545' if item.priority.value == 'high' else '#fd7e14' if item.priority.value == 'medium' else '#198754'};font-weight:600">
                    {item.priority.value.capitalize()}
                  </span>
                </div>
              </td>
            </tr>
            """
            for item in my_action_items
        ])
    else:
        my_items_html = """
        <tr>
          <td style="padding:10px 16px;color:#666;font-size:14px">
            No action items assigned to you for this meeting.
          </td>
        </tr>
        """

    # Build "all tasks" section for full context
    all_items_html = "".join([
        f"""
        <tr>
          <td style="padding:6px 16px;font-size:13px;color:#444;border-bottom:1px solid #f5f5f5">
            <strong>{item.owner}</strong> — {item.description}
            <span style="color:#999;font-size:12px"> ({item.due_date})</span>
          </td>
        </tr>
        """
        for item in all_action_items
    ])

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:0;background:#f8f9fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
      <div style="max-width:600px;margin:32px auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e9ecef">

        <!-- Header -->
        <div style="background:#1a1a2e;padding:24px 32px">
          <div style="color:#ffffff;font-size:18px;font-weight:600">Meeting Intelligence Agent</div>
          <div style="color:#a0a0b0;font-size:13px;margin-top:4px">Meeting summary & your action items</div>
        </div>

        <!-- Body -->
        <div style="padding:28px 32px">

          <!-- Greeting -->
          <p style="font-size:16px;color:#1a1a1a;margin:0 0 8px">
            Hi {recipient_name.split()[0]},
          </p>
          <p style="font-size:14px;color:#555;margin:0 0 24px;line-height:1.6">
            Here's a summary of <strong>{meeting_title}</strong> and your action items.
          </p>

          <!-- Summary -->
          <div style="background:#f8f9fa;border-radius:8px;padding:16px;margin-bottom:24px;border-left:4px solid #6c5ce7">
            <div style="font-size:12px;font-weight:600;color:#6c5ce7;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">Meeting summary</div>
            <div style="font-size:14px;color:#333;line-height:1.6">{short_summary}</div>
          </div>

          <!-- Your action items -->
          <div style="margin-bottom:24px">
            <div style="font-size:12px;font-weight:600;color:#1a1a1a;text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
              Your action items
            </div>
            <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e9ecef;border-radius:8px;overflow:hidden">
              {my_items_html}
            </table>
          </div>

          <!-- All action items -->
          <div style="margin-bottom:24px">
            <div style="font-size:12px;font-weight:600;color:#999;text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
              All team action items
            </div>
            <table style="width:100%;border-collapse:collapse;border:1px solid #f0f0f0;border-radius:8px;overflow:hidden">
              {all_items_html}
            </table>
          </div>

        </div>

        <!-- Footer -->
        <div style="background:#f8f9fa;padding:16px 32px;border-top:1px solid #e9ecef">
          <div style="font-size:12px;color:#999;text-align:center">
            Sent by Meeting Intelligence Agent &nbsp;|&nbsp; Powered by Groq + LangGraph
          </div>
        </div>

      </div>
    </body>
    </html>
    """


def _build_email_text(
    recipient_name:  str,
    meeting_title:   str,
    short_summary:   str,
    my_action_items: list[ActionItem],
) -> str:
    """Plain text fallback for email clients that don't render HTML."""
    items_text = "\n".join([
        f"  - {item.description} (Due: {item.due_date}, Priority: {item.priority.value})"
        for item in my_action_items
    ]) or "  No action items assigned to you."

    return f"""Hi {recipient_name.split()[0]},

Here's a summary of {meeting_title} and your action items.

SUMMARY:
{short_summary}

YOUR ACTION ITEMS:
{items_text}

Sent by Meeting Intelligence Agent
"""


# ---------------------------------------------------------------------------
# Single email send with retry
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _send_single_email(
    to_email:    str,
    to_name:     str,
    subject:     str,
    html_body:   str,
    plain_body:  str,
) -> bool:
    """
    Sends one email via SendGrid.
    Returns True on success, raises on failure.
    """
    message = Mail(
        from_email=(settings.sender_email, settings.sender_name),
        to_emails=To(email=to_email, name=to_name),
        subject=subject,
    )
    message.content = [
        Content("text/plain", plain_body),
        Content("text/html",  html_body),
    ]

    sg       = SendGridAPIClient(settings.sendgrid_api_key)
    response = sg.send(message)

    # SendGrid returns 202 Accepted for successful queuing
    if response.status_code not in (200, 202):
        raise Exception(f"SendGrid returned status {response.status_code}")

    return True


# ---------------------------------------------------------------------------
# LangGraph Node 7 (email part) + Manual re-send
# ---------------------------------------------------------------------------

def send_emails(
    state:             AgentState,
    participant_emails: dict[str, str],  # {"Alice Chen": "alice@co.com"}
) -> dict:
    """
    Sends personalised emails to all participants who have email addresses.

    Called by:
    - send_notifications() in this file (LangGraph auto-send)
    - FastAPI route /api/meetings/{id}/send/email (manual send)

    participant_emails — mapping of name → email for participants
    who have emails stored. Built by the FastAPI route from the DB.

    Returns dict with sent/failed counts for logging.
    """
    if not state.extraction or not state.summary:
        logger.warning("send_emails: missing extraction or summary — skipping.")
        return {"sent": 0, "failed": 0}

    if not settings.sendgrid_api_key or not settings.sender_email:
        logger.warning("SendGrid credentials not configured — skipping emails.")
        return {"sent": 0, "failed": 0}

    all_action_items = state.extraction.action_items
    subject          = _build_email_subject(state.summary.title)
    sent_count       = 0
    failed_count     = 0

    for name, email in participant_emails.items():
        if not email:
            continue

        # Filter action items that belong to this person
        # Case-insensitive name matching for robustness
        my_items = [
            item for item in all_action_items
            if item.owner.lower() == name.lower()
        ]

        html_body  = _build_email_html(
            recipient_name=name,
            meeting_title=state.summary.title,
            short_summary=state.summary.short_summary,
            my_action_items=my_items,
            all_action_items=all_action_items,
        )
        plain_body = _build_email_text(
            recipient_name=name,
            meeting_title=state.summary.title,
            short_summary=state.summary.short_summary,
            my_action_items=my_items,
        )

        try:
            _send_single_email(
                to_email=email,
                to_name=name,
                subject=subject,
                html_body=html_body,
                plain_body=plain_body,
            )

            sent_count += 1
            logger.info("Email sent | to: %s <%s> | items: %d", name, email, len(my_items))

            if state.meeting_id:
                asyncio.run(log_notification(
                    meeting_id=state.meeting_id,
                    notification_type="email",
                    status="sent",
                    detail=f"{name} <{email}>",
                ))

        except Exception as e:
            failed_count += 1
            error_msg = f"Failed to send email to {name} <{email}>: {e}"
            logger.error(error_msg)

            if state.meeting_id:
                asyncio.run(log_notification(
                    meeting_id=state.meeting_id,
                    notification_type="email",
                    status="failed",
                    detail=error_msg[:200],
                ))

    logger.info("Email complete | sent: %d | failed: %d", sent_count, failed_count)
    return {"sent": sent_count, "failed": failed_count}


# ---------------------------------------------------------------------------
# Standalone async function for FastAPI manual send route
# ---------------------------------------------------------------------------

async def send_email_for_meeting(
    meeting_id:         str,
    meeting_title:      str,
    short_summary:      str,
    all_action_items:   list[ActionItem],
    participant_emails: dict[str, str],
) -> dict:
    """
    Called by FastAPI POST /api/meetings/{id}/send/email
    when user clicks "Email Participants" button.

    participant_emails — {name: email} for selected participants only
    (user may have unchecked some on the frontend)

    RETURNS:
        {"sent": 3, "failed": 0}
    """
    sent, failed = 0, 0

    for name, email in participant_emails.items():
        my_items   = [i for i in all_action_items if i.owner.lower() == name.lower()]
        html_body  = _build_email_html(name, meeting_title, short_summary, my_items, all_action_items)
        plain_body = _build_email_text(name, meeting_title, short_summary, my_items)

        try:
            _send_single_email(email, name, _build_email_subject(meeting_title), html_body, plain_body)
            sent += 1
            await log_notification(meeting_id, "email", "sent", f"{name} <{email}>")
        except Exception as e:
            failed += 1
            await log_notification(meeting_id, "email", "failed", str(e)[:200])

    return {"sent": sent, "failed": failed}