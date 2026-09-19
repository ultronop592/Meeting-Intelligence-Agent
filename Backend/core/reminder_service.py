"""Reminder Service for Action Items.

Detects due and overdue action items across meetings and delivers automated
reminders via Email (SendGrid) and/or Slack webhook.
Includes an async background scheduler to periodically check for due tasks.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import settings
from db.database import AsyncSessionLocal, get_user_tool_credentials, log_notification
from db.models import ActionItem, Meeting, NotificationLog, Participant
from tools.email_tool import _send_single_email, resolve_email_credentials
from tools.slack_tool import _post_to_slack, resolve_slack_credentials

logger = logging.getLogger(__name__)


def parse_due_date(due_date_str: str | None) -> date | None:
    """Safely parse a due date string (YYYY-MM-DD or ISO format) into a date object."""
    if not due_date_str:
        return None
    cleaned = due_date_str.strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def evaluate_due_urgency(due: date, today: date, window_days: int = 1) -> tuple[bool, str]:
    """Determine whether an action item is due/overdue and return its urgency label.

    Returns:
        (is_due, urgency):
          urgency is one of: "overdue", "due_today", "due_soon", or "upcoming"
    """
    diff = (due - today).days
    if diff < 0:
        return True, "overdue"
    if diff == 0:
        return True, "due_today"
    if diff <= window_days:
        return True, "due_soon"
    return False, "upcoming"


def _build_reminder_email_html(
    owner_name: str,
    meeting_title: str,
    task_description: str,
    due_date_str: str,
    priority: str,
    urgency: str,
) -> str:
    urgency_badge_color = "#DC2626" if urgency == "overdue" else ("#D97706" if urgency == "due_today" else "#4F46E5")
    urgency_label = "OVERDUE" if urgency == "overdue" else ("DUE TODAY" if urgency == "due_today" else "DUE SOON")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.6;color:#1e293b;background-color:#f8fafc;margin:0;padding:24px;">
  <div style="max-width:580px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
    <div style="background:#0f172a;padding:20px 28px;">
      <div style="font-size:11px;font-weight:700;letter-spacing:0.1em;color:#818cf8;text-transform:uppercase;">Meeting Intelligence Reminder</div>
      <h1 style="color:#ffffff;font-size:18px;margin:6px 0 0 0;font-weight:600;">Action Item Due Reminder</h1>
    </div>
    <div style="padding:28px;">
      <div style="display:inline-block;padding:4px 10px;border-radius:9999px;font-size:11px;font-weight:700;color:#ffffff;background-color:{urgency_badge_color};margin-bottom:16px;">
        {urgency_label}
      </div>
      <p style="margin:0 0 16px 0;font-size:14px;color:#334155;">
        Hi <strong>{owner_name}</strong>, this is an automated reminder regarding an action item assigned to you from <em>{meeting_title}</em>.
      </p>
      <div style="background:#f1f5f9;border-left:4px solid {urgency_badge_color};padding:14px 18px;border-radius:6px;margin-bottom:20px;">
        <div style="font-size:14px;font-weight:600;color:#0f172a;margin-bottom:6px;">{task_description}</div>
        <div style="font-size:12px;color:#64748b;">
          <strong>Due Date:</strong> {due_date_str} &nbsp;|&nbsp; <strong>Priority:</strong> {priority.capitalize()}
        </div>
      </div>
      <p style="font-size:13px;color:#64748b;margin:0;">
        Please update the task status in Meeting Intelligence Agent once completed.
      </p>
    </div>
    <div style="background:#f8fafc;padding:14px 28px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;text-align:center;">
      Sent automatically by Meeting Intelligence Agent
    </div>
  </div>
</body>
</html>"""


def _build_reminder_email_text(
    owner_name: str,
    meeting_title: str,
    task_description: str,
    due_date_str: str,
    priority: str,
    urgency: str,
) -> str:
    status_tag = urgency.upper().replace("_", " ")
    return f"""[{status_tag}] Action Item Reminder: {task_description}

Hi {owner_name},

This is an automated reminder for an action item from "{meeting_title}":

Task: {task_description}
Due Date: {due_date_str}
Priority: {priority.capitalize()}

Please update the status in Meeting Intelligence Agent when completed.

Sent by Meeting Intelligence Agent.
"""


def _build_slack_reminder_blocks(
    owner_name: str,
    meeting_title: str,
    task_description: str,
    due_date_str: str,
    priority: str,
    urgency: str,
) -> list[dict]:
    emoji = "🚨" if urgency == "overdue" else ("⏰" if urgency == "due_today" else "⏳")
    tag = "OVERDUE" if urgency == "overdue" else ("DUE TODAY" if urgency == "due_today" else "DUE SOON")
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} Action Item Reminder ({tag})"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Task:*\n{task_description}"},
                {"type": "mrkdwn", "text": f"*Assignee:*\n{owner_name}"},
                {"type": "mrkdwn", "text": f"*Meeting:*\n{meeting_title}"},
                {"type": "mrkdwn", "text": f"*Due:*\n`{due_date_str}` ({priority.capitalize()})"},
            ],
        },
        {"type": "divider"},
    ]


async def check_and_send_due_reminders(
    db: AsyncSession,
    meeting_id: str | None = None,
    user_id: str | None = None,
    window_days: int = 1,
    today_override: date | None = None,
) -> dict[str, Any]:
    """Inspect action items, find due or overdue tasks, and deliver reminders."""
    today = today_override or datetime.now(timezone.utc).date()
    today_str = today.isoformat()

    # Query active items
    query = (
        select(ActionItem)
        .join(Meeting, Meeting.id == ActionItem.meeting_id)
        .options(selectinload(ActionItem.meeting).selectinload(Meeting.participants))
        .where(ActionItem.status != "done")
    )
    if meeting_id:
        query = query.where(ActionItem.meeting_id == meeting_id)
    if user_id:
        query = query.where((Meeting.user_id == user_id) | (Meeting.user_id.is_(None)))

    result = await db.execute(query)
    action_items = result.scalars().all()

    total_checked = len(action_items)
    due_items_found = 0
    reminders_sent = 0
    already_reminded = 0
    skipped_no_contact = 0
    results_detail = []

    for item in action_items:
        parsed_due = parse_due_date(item.due_date)
        if not parsed_due:
            continue

        is_due, urgency = evaluate_due_urgency(parsed_due, today, window_days=window_days)
        if not is_due:
            continue

        due_items_found += 1
        meeting = item.meeting

        # Check if already reminded today for this item
        existing_log = await db.execute(
            select(NotificationLog).where(
                NotificationLog.meeting_id == meeting.id,
                NotificationLog.detail.like(f"reminder:item:{item.id}:{today_str}:%"),
            )
        )
        if existing_log.scalars().first():
            already_reminded += 1
            results_detail.append({
                "item_id": item.id,
                "description": item.description,
                "owner": item.owner,
                "status": "already_reminded_today",
                "urgency": urgency,
            })
            continue

        # Find owner contact info
        owner_name = item.owner or "Participant"
        owner_email = None
        for p in getattr(meeting, "participants", []) or []:
            if p.name and p.name.strip().lower() == owner_name.strip().lower() and p.email:
                owner_email = p.email
                break

        # Check tool credentials
        resolved_user_id = getattr(meeting, "user_id", None) or user_id
        email_creds_dict = None
        slack_creds_dict = None
        if resolved_user_id:
            try:
                email_creds_dict = await get_user_tool_credentials(resolved_user_id, "email", db=db)
            except Exception:
                email_creds_dict = None
            try:
                slack_creds_dict = await get_user_tool_credentials(resolved_user_id, "slack", db=db)
            except Exception:
                slack_creds_dict = None

        email_creds = resolve_email_credentials(email_creds_dict)
        slack_creds = resolve_slack_credentials(slack_creds_dict)

        sent_channels = []

        # 1. Send Email if owner email is known and credentials exist
        if owner_email and email_creds:
            api_key, sender_email, sender_name = email_creds
            subject = f"[{urgency.upper().replace('_', ' ')}] Action Item Due: {item.description[:40]} — {meeting.title}"
            html_body = _build_reminder_email_html(
                owner_name=owner_name,
                meeting_title=meeting.title,
                task_description=item.description,
                due_date_str=item.due_date,
                priority=item.priority,
                urgency=urgency,
            )
            plain_body = _build_reminder_email_text(
                owner_name=owner_name,
                meeting_title=meeting.title,
                task_description=item.description,
                due_date_str=item.due_date,
                priority=item.priority,
                urgency=urgency,
            )
            try:
                _send_single_email(
                    to_email=owner_email,
                    to_name=owner_name,
                    subject=subject,
                    html_body=html_body,
                    plain_body=plain_body,
                    api_key=api_key,
                    sender_email=sender_email,
                    sender_name=sender_name,
                )
                db.add(NotificationLog(
                    meeting_id=meeting.id,
                    type="email",
                    status="sent",
                    detail=f"reminder:item:{item.id}:{today_str}:email:{owner_email}",
                ))
                sent_channels.append("email")
            except Exception as e:
                logger.error("Failed to send reminder email to %s: %s", owner_email, e)
                db.add(NotificationLog(
                    meeting_id=meeting.id,
                    type="email",
                    status="failed",
                    detail=f"reminder:item:{item.id}:{today_str}:email_error:{str(e)[:150]}",
                ))

        # 2. Send Slack reminder if configured
        if slack_creds:
            webhook_url, channel = slack_creds
            blocks = _build_slack_reminder_blocks(
                owner_name=owner_name,
                meeting_title=meeting.title,
                task_description=item.description,
                due_date_str=item.due_date,
                priority=item.priority,
                urgency=urgency,
            )
            try:
                _post_to_slack(
                    webhook_url=webhook_url,
                    text=f"Reminder: {item.description} ({urgency.replace('_', ' ')})",
                    blocks=blocks,
                )
                db.add(NotificationLog(
                    meeting_id=meeting.id,
                    type="slack",
                    status="sent",
                    detail=f"reminder:item:{item.id}:{today_str}:slack:{channel}",
                ))
                sent_channels.append("slack")
            except Exception as e:
                logger.error("Failed to post reminder to Slack: %s", e)
                db.add(NotificationLog(
                    meeting_id=meeting.id,
                    type="slack",
                    status="failed",
                    detail=f"reminder:item:{item.id}:{today_str}:slack_error:{str(e)[:150]}",
                ))

        if sent_channels:
            reminders_sent += 1
            results_detail.append({
                "item_id": item.id,
                "description": item.description,
                "owner": item.owner,
                "status": "sent",
                "channels": sent_channels,
                "urgency": urgency,
            })
        else:
            skipped_no_contact += 1
            results_detail.append({
                "item_id": item.id,
                "description": item.description,
                "owner": item.owner,
                "status": "skipped_no_channel_or_email",
                "urgency": urgency,
            })

    if reminders_sent > 0:
        await db.commit()

    return {
        "total_checked": total_checked,
        "due_items_found": due_items_found,
        "reminders_sent": reminders_sent,
        "already_reminded": already_reminded,
        "skipped_no_contact": skipped_no_contact,
        "items": results_detail,
    }


class ReminderScheduler:
    """Background scheduler that periodically checks and dispatches due date reminders."""

    def __init__(self, interval_seconds: int = 3600) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._is_running = False

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("ReminderScheduler started with interval %ds", self.interval_seconds)

    async def stop(self) -> None:
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ReminderScheduler stopped")

    async def _run_loop(self) -> None:
        while self._is_running:
            try:
                logger.info("ReminderScheduler: Running periodic due date check...")
                async with AsyncSessionLocal() as session:
                    summary = await check_and_send_due_reminders(session)
                    logger.info(
                        "ReminderScheduler run complete | due: %d | sent: %d | already_reminded: %d",
                        summary["due_items_found"],
                        summary["reminders_sent"],
                        summary["already_reminded"],
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ReminderScheduler unexpected error: %s", e)

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break


# Global singleton instance for FastAPI lifespan
reminder_scheduler = ReminderScheduler(interval_seconds=3600)
