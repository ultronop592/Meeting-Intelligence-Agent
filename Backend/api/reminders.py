"""Domain router: Meeting Action Item Reminders.

Endpoints:
- POST /meetings/{meeting_id}/reminders/trigger: Trigger due/overdue reminders for a meeting.
- GET  /meetings/{meeting_id}/reminders/status: Inspect current reminder status for a meeting.
- POST /reminders/trigger: Trigger due-date reminders across all meetings owned by user.
"""

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import verify_meeting_ownership
from core.auth import get_current_user
from core.reminder_service import check_and_send_due_reminders, evaluate_due_urgency, parse_due_date
from db.database import get_db
from db.models import ActionItem as DBActionItem, Meeting, NotificationLog, User

logger = logging.getLogger(__name__)

reminders_router = APIRouter(tags=["reminders"])


@reminders_router.post("/meetings/{meeting_id}/reminders/trigger")
async def trigger_meeting_reminders(
    meeting_id: str,
    window_days: int = Query(1, ge=0, le=14),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger due-date and overdue reminders for action items in a specific meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)

    summary = await check_and_send_due_reminders(
        db=db,
        meeting_id=meeting_id,
        user_id=current_user.id,
        window_days=window_days,
    )
    return {"success": True, "meeting_id": meeting_id, "summary": summary}


@reminders_router.get("/meetings/{meeting_id}/reminders/status")
async def get_meeting_reminder_status(
    meeting_id: str,
    window_days: int = Query(1, ge=0, le=14),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current due-date reminder status for all active action items in a meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)

    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()

    action_items = (
        await db.execute(
            select(DBActionItem).where(DBActionItem.meeting_id == meeting_id, DBActionItem.status != "done")
        )
    ).scalars().all()

    due_items = []
    for item in action_items:
        parsed_due = parse_due_date(item.due_date)
        if not parsed_due:
            continue
        is_due, urgency = evaluate_due_urgency(parsed_due, today, window_days=window_days)

        reminded_log = (
            await db.execute(
                select(NotificationLog).where(
                    NotificationLog.meeting_id == meeting_id,
                    NotificationLog.detail.like(f"reminder:item:{item.id}:{today_str}:%"),
                )
            )
        ).scalars().first()

        due_items.append({
            "id": item.id,
            "description": item.description,
            "owner": item.owner,
            "due_date": item.due_date,
            "priority": item.priority,
            "status": item.status,
            "is_due": is_due,
            "urgency": urgency,
            "reminded_today": reminded_log is not None,
            "last_reminded_at": reminded_log.created_at if reminded_log else None,
        })

    return {"meeting_id": meeting_id, "items": due_items}


@reminders_router.post("/reminders/trigger")
async def trigger_global_reminders(
    window_days: int = Query(1, ge=0, le=14),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger due-date reminders across all meetings owned by the current user."""
    summary = await check_and_send_due_reminders(
        db=db,
        user_id=current_user.id,
        window_days=window_days,
    )
    return {"success": True, "summary": summary}
