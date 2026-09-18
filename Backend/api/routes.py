import logging
import os
import time
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.limiter import limiter
from core.config import settings
from db.database import (
    AsyncSessionLocal,
    create_processing_job,
    get_db,
    get_processing_job,
    update_processing_job,
)
from db.models import ActionItem as DBActionItem
from db.models import Decision, Meeting, NotificationLog, Participant, User
from core.openrouter_client import openrouter_client
from graph.agent_graph import arun_meeting_agent, run_meeting_agent
from models.schemas import (
    ActionItemRow,
    ActionItemStatus,
    AgentQueryRequest,
    AgentQueryResponse,
    ChatMessage,
    DecisionRow,
    DispatchMeetingRequest,
    DispatchMeetingResponse,
    MeetingDetailResponse,
    MeetingListItem,
    MeetingRow,
    NotificationLogRow,
    ParticipantRow,
    MemorySearchRequest,
    MemorySearchResponse,
    ProcessMeetingRequest,
    UpdateActionItemRequest,
    ActionItemOwnerBreakdown,
    AnalyticsActionItemsResponse,
    AnalyticsParticipantsResponse,
    AnalyticsSummaryResponse,
    AnalyticsTimelineResponse,
    AnalyticsTopicsResponse,
    ParticipantAnalyticsItem,
    PeriodStats,
    TimelineDataPoint,
    TopicKeywordItem,
)

# Tool connectors for live manual-send endpoints
from tools.calender_tool import send_calendar_for_meeting
from tools.email_tool import send_email_for_meeting
from tools.jira_tool import send_jira_for_meeting
from tools.slack_tool import send_slack_for_meeting

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".flac",
    ".aac",
    ".ogg",
    ".webm",
    ".mp4",
}
UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verify_meeting_ownership(meeting: Meeting, current_user: User) -> None:
    """Ensure that the requesting user owns the meeting.
    Allows access if meeting.user_id matches current_user.id or is None (legacy pre-auth records).
    """
    if meeting.user_id and meeting.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access or modify this meeting.",
        )


# =============================================================================
# UPLOAD
# =============================================================================

@router.post("/meeting/upload", tags=["meetings"])
@limiter.limit("30/minute")
async def upload_audio(request: Request, file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    lower_name = (file.filename or "").lower()
    suffix = ".mp4" if lower_name.endswith(".mp.4") else Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {suffix}",
        )

    os.makedirs(settings.upload_dir, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(settings.upload_dir, unique_name)

    size_bytes = 0
    try:
        with open(file_path, "wb") as out:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > settings.max_upload_size_bytes:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file exceeds max size")
                out.write(chunk)

        if size_bytes == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    except OSError as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to store uploaded file: {exc}")
    finally:
        await file.close()

    return {
        "filename": file.filename,
        "stored_filename": unique_name,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
    }


# =============================================================================
# PROCESSING JOB — DB-backed background job tracking
# =============================================================================

async def _process_job(job_id: str, payload: ProcessMeetingRequest, user_id: str | None = None):
    """Background task: run the multi-agent pipeline and persist status in DB."""
    job_started_at = datetime.now(timezone.utc)

    # Create the job record in DB so it's visible even before completion.
    await create_processing_job(job_id, user_id=user_id)

    try:
        phase_start = time.perf_counter()

        # Run the async multi-agent graph directly on the server event loop.
        # LangGraph runs sync nodes in worker threads and awaits async nodes (save_to_database)
        # on the active loop without cross-thread event loop collisions.
        state = await arun_meeting_agent(
            payload.audio_file_path,
            payload.audio_filename,
            user_id,
        )

        completed_nodes = ["upload"] + (state.completed_nodes or [])

        if not state.meeting_id:
            # Pipeline finished without persisting a meeting_id — preserve full error detail
            err_details = state.errors if state.errors else ["Pipeline finished without persisting a meeting record."]
            logger.error("Pipeline did not persist meeting for job %s. Errors: %s", job_id, err_details)
            await update_processing_job(
                job_id,
                status="failed",
                completed_nodes=completed_nodes,
                errors=err_details,
                completed_at=datetime.now(timezone.utc),
            )
            return

        async with AsyncSessionLocal() as session:
            meeting = await session.get(Meeting, state.meeting_id)
            if not meeting:
                raise RuntimeError(f"Meeting not found after pipeline run: {state.meeting_id}")

            action_items_count = (
                await session.execute(select(func.count(DBActionItem.id)).where(DBActionItem.meeting_id == meeting.id))
            ).scalar_one()
            decisions_count = (
                await session.execute(select(func.count(Decision.id)).where(Decision.meeting_id == meeting.id))
            ).scalar_one()
            participants_count = (
                await session.execute(select(func.count(Participant.id)).where(Participant.meeting_id == meeting.id))
            ).scalar_one()

        completed_at = datetime.now(timezone.utc)
        total_duration_ms = int((time.perf_counter() - phase_start) * 1000)

        # In Human-in-the-loop flow, integrations are dispatched on demand after summary inspection.
        await update_processing_job(
            job_id,
            status="completed",
            completed_nodes=completed_nodes,
            errors=state.errors,
            meeting_id=meeting.id,
            completed_at=completed_at,
            duration_ms=total_duration_ms,
            title=meeting.title,
            short_summary=meeting.short_summary,
            action_items_count=int(action_items_count or 0),
            decisions_count=int(decisions_count or 0),
            participants_count=int(participants_count or 0),
            jira_tickets_created=0,
            calendar_event_id=None,
            notifications_sent=0,
        )
    except Exception as exc:
        logger.exception("Processing job failed with unexpected error")
        await update_processing_job(
            job_id,
            status="failed",
            completed_nodes=["upload"],
            errors=[f"Pipeline processing error: {exc}"],
            completed_at=datetime.now(timezone.utc),
        )
    finally:
        try:
            if os.path.exists(payload.audio_file_path):
                os.remove(payload.audio_file_path)
        except OSError:
            pass


@router.post("/meetings/process", tags=["meetings"])
async def process_meeting(
    request: ProcessMeetingRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    if not os.path.exists(request.audio_file_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file not found")

    job_id = str(uuid.uuid4())
    user_id = current_user.id
    background_tasks.add_task(_process_job, job_id, request, user_id=user_id)
    return {"job_id": job_id, "message": "Meeting processing started.", "status": "processing"}


@router.get("/meetings/status/{job_id}", tags=["meetings"])
async def get_processing_status(job_id: str, current_user: User = Depends(get_current_user)):
    """Return the current processing job status from the database."""
    job = await get_processing_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
    if job.get("user_id") and job["user_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this job status.",
        )
    return job


# =============================================================================
# MEETINGS
# =============================================================================

@router.get("/meetings", response_model=list[MeetingListItem], tags=["meetings"])
async def list_meetings(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Meeting, func.count(DBActionItem.id).label("action_items_count"))
        .outerjoin(DBActionItem, DBActionItem.meeting_id == Meeting.id)
        .where((Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None)))
        .group_by(Meeting.id)
        .order_by(Meeting.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return [
        MeetingListItem(
            id=meeting.id,
            title=meeting.title,
            audio_filename=meeting.audio_filename,
            duration_minutes=meeting.duration_minutes,
            short_summary=meeting.short_summary,
            action_items_count=count or 0,
            created_at=meeting.created_at,
        )
        for meeting, count in rows
    ]


@router.get("/meetings/{meeting_id}", response_model=MeetingDetailResponse, tags=["meetings"])
async def get_meeting_details(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    action_items = (
        await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id).order_by(DBActionItem.created_at))
    ).scalars().all()
    decisions = (await db.execute(select(Decision).where(Decision.meeting_id == meeting_id))).scalars().all()
    participants = (await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))).scalars().all()
    notifications = (
        await db.execute(select(NotificationLog).where(NotificationLog.meeting_id == meeting_id).order_by(NotificationLog.created_at.desc()))
    ).scalars().all()

    return MeetingDetailResponse(
        meeting=MeetingRow.model_validate(meeting),
        action_items=[ActionItemRow.model_validate(item) for item in action_items],
        decisions=[DecisionRow.model_validate(decision) for decision in decisions],
        participants=[ParticipantRow.model_validate(participant) for participant in participants],
        notifications=[NotificationLogRow.model_validate(notification) for notification in notifications],
    )


@router.patch("/meetings/{meeting_id}/action-items/{item_id}", response_model=ActionItemRow, tags=["meetings"])
async def update_action_item(
    meeting_id: str,
    item_id: str,
    payload: UpdateActionItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    item = await db.get(DBActionItem, item_id)
    if not item or item.meeting_id != meeting_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")
    item.status = payload.status.value if isinstance(payload.status, ActionItemStatus) else str(payload.status)
    await db.flush()
    return ActionItemRow.model_validate(item)


@router.patch("/meetings/{meeting_id}/participants/{participant_id}", response_model=ParticipantRow, tags=["meetings"])
async def update_participant_email(
    meeting_id: str,
    participant_id: str,
    email: str = Query(..., min_length=3),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    participant = await db.get(Participant, participant_id)
    if not participant or participant.meeting_id != meeting_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    participant.email = email
    await db.flush()
    return ParticipantRow.model_validate(participant)


@router.delete("/meetings/{meeting_id}", tags=["meetings"])
async def delete_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)
    await db.delete(meeting)
    await db.flush()
    return {"deleted": True, "meeting_id": meeting_id}


# =============================================================================
# MANUAL SEND — live tool integrations
# =============================================================================

@router.post("/meetings/{meeting_id}/send/email", tags=["meetings"])
async def send_email(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send personalised emails to all participants who have email addresses stored."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    action_items_rows = (
        await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
    ).scalars().all()
    participants = (
        await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))
    ).scalars().all()

    # Build {name: email} map — only participants with stored email addresses.
    participant_emails: dict[str, str] = {
        p.name: p.email
        for p in participants
        if p.email
    }

    if not participant_emails:
        return {
            "message": "No participant emails configured. Update participant emails first.",
            "sent": 0,
            "failed": 0,
        }

    # Convert ORM rows → Pydantic ActionItem models expected by the tool.
    from models.schemas import ActionItem as ActionItemSchema, Priority
    action_items = [
        ActionItemSchema(
            description=i.description,
            owner=i.owner,
            due_date=i.due_date,
            priority=Priority(i.priority),
        )
        for i in action_items_rows
    ]

    result = await send_email_for_meeting(
        meeting_id=meeting_id,
        meeting_title=meeting.title,
        short_summary=meeting.short_summary,
        all_action_items=action_items,
        participant_emails=participant_emails,
    )
    return {
        "message": f"Email dispatch complete — sent: {result['sent']}, failed: {result['failed']}",
        "sent": result["sent"],
        "failed": result["failed"],
    }


@router.post("/meetings/{meeting_id}/send/slack", tags=["meetings"])
async def send_slack(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post meeting summary and action items to the configured Slack channel."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    action_items_rows = (
        await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
    ).scalars().all()
    decisions_count = (
        await db.execute(select(func.count(Decision.id)).where(Decision.meeting_id == meeting_id))
    ).scalar_one()
    participants = (
        await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))
    ).scalars().all()

    from models.schemas import ActionItem as ActionItemSchema, Priority
    action_items = [
        ActionItemSchema(
            description=i.description,
            owner=i.owner,
            due_date=i.due_date,
            priority=Priority(i.priority),
        )
        for i in action_items_rows
    ]

    result = await send_slack_for_meeting(
        meeting_id=meeting_id,
        meeting_title=meeting.title,
        short_summary=meeting.short_summary,
        action_items=action_items,
        participants=[p.name for p in participants],
        decisions_count=int(decisions_count or 0),
        duration_minutes=meeting.duration_minutes,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Slack dispatch failed: {result['error']}",
        )
    return {"message": "Slack notification sent successfully.", "sent": 1, "failed": 0}


@router.post("/meetings/{meeting_id}/send/jira", tags=["meetings"])
async def send_jira(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create Jira tickets for all action items in this meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    action_items_rows = (
        await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
    ).scalars().all()

    if not action_items_rows:
        return {"message": "No action items found for this meeting.", "sent": 0, "failed": 0, "created": []}

    from models.schemas import ActionItem as ActionItemSchema, Priority
    action_items = [
        ActionItemSchema(
            description=i.description,
            owner=i.owner,
            due_date=i.due_date,
            priority=Priority(i.priority),
        )
        for i in action_items_rows
    ]

    try:
        result = await send_jira_for_meeting(
            meeting_id=meeting_id,
            action_items=action_items,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    return {
        "message": f"Jira dispatch complete — created: {len(result['created'])}, failed: {len(result['failed'])}",
        "sent": len(result["created"]),
        "failed": len(result["failed"]),
        "created": result["created"],
    }


@router.post("/meetings/{meeting_id}/send/calendar", tags=["meetings"])
async def send_calendar(
    meeting_id: str,
    days_from_now: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Book a follow-up Google Calendar event for all participants."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    participants = (
        await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))
    ).scalars().all()

    participant_names = [p.name for p in participants]
    participant_emails = [p.email for p in participants if p.email]

    result = await send_calendar_for_meeting(
        meeting_id=meeting_id,
        meeting_title=meeting.title,
        participants=participant_names,
        emails=participant_emails,
        days_from_now=days_from_now,
    )

    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Calendar dispatch failed: {result['error']}",
        )

    return {
        "message": f"Calendar follow-up booked for {days_from_now} day(s) from now.",
        "sent": 1,
        "failed": 0,
        "event_id": result.get("event_id"),
        "event_url": result.get("event_url"),
    }


@router.post("/meetings/{meeting_id}/dispatch", response_model=DispatchMeetingResponse, tags=["meetings"])
async def dispatch_meeting(
    meeting_id: str,
    payload: DispatchMeetingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Human-in-the-Loop Batch Dispatch: Send meeting intelligence to approved external tools."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    results: dict[str, Any] = {}
    requested_channels = set(payload.channels or [])

    # 1. Slack
    if "slack" in requested_channels:
        try:
            action_items_rows = (
                await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
            ).scalars().all()
            decisions_count = (
                await db.execute(select(func.count(Decision.id)).where(Decision.meeting_id == meeting_id))
            ).scalar_one()
            participants = (
                await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))
            ).scalars().all()

            from models.schemas import ActionItem as ActionItemSchema, Priority
            action_items = [
                ActionItemSchema(
                    description=i.description,
                    owner=i.owner,
                    due_date=i.due_date,
                    priority=Priority(i.priority),
                )
                for i in action_items_rows
            ]

            slack_res = await send_slack_for_meeting(
                meeting_id=meeting_id,
                meeting_title=meeting.title,
                short_summary=meeting.short_summary,
                action_items=action_items,
                participants=[p.name for p in participants],
                decisions_count=int(decisions_count or 0),
                duration_minutes=meeting.duration_minutes,
            )
            results["slack"] = {
                "status": "sent" if slack_res["success"] else "failed",
                "message": "Slack notification sent successfully." if slack_res["success"] else slack_res.get("error", "Slack dispatch failed"),
            }
        except Exception as exc:
            results["slack"] = {"status": "failed", "message": str(exc)}

    # 2. Jira
    if "jira" in requested_channels:
        try:
            action_items_rows = (
                await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
            ).scalars().all()

            if not action_items_rows:
                results["jira"] = {
                    "status": "skipped",
                    "created_count": 0,
                    "failed_count": 0,
                    "message": "No action items found for Jira ticket creation.",
                    "created": [],
                }
            else:
                from models.schemas import ActionItem as ActionItemSchema, Priority
                action_items = [
                    ActionItemSchema(
                        description=i.description,
                        owner=i.owner,
                        due_date=i.due_date,
                        priority=Priority(i.priority),
                    )
                    for i in action_items_rows
                ]
                jira_res = await send_jira_for_meeting(
                    meeting_id=meeting_id,
                    action_items=action_items,
                )
                results["jira"] = {
                    "status": "sent" if jira_res["created"] else ("failed" if jira_res["failed"] else "skipped"),
                    "created_count": len(jira_res.get("created", [])),
                    "failed_count": len(jira_res.get("failed", [])),
                    "message": f"Created {len(jira_res.get('created', []))} Jira tickets.",
                    "created": jira_res.get("created", []),
                }
        except Exception as exc:
            results["jira"] = {"status": "failed", "message": str(exc)}

    # 3. Calendar
    if "calendar" in requested_channels:
        try:
            participants = (
                await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))
            ).scalars().all()
            cal_res = await send_calendar_for_meeting(
                meeting_id=meeting_id,
                meeting_title=meeting.title,
                participants=[p.name for p in participants],
                emails=[p.email for p in participants if p.email],
                days_from_now=payload.days_from_now,
            )
            results["calendar"] = {
                "status": "sent" if not cal_res.get("error") else "failed",
                "event_id": cal_res.get("event_id"),
                "event_url": cal_res.get("event_url"),
                "message": f"Calendar follow-up booked for {payload.days_from_now} day(s) from now." if not cal_res.get("error") else cal_res.get("error"),
            }
        except Exception as exc:
            results["calendar"] = {"status": "failed", "message": str(exc)}

    # 4. Email
    if "email" in requested_channels:
        try:
            action_items_rows = (
                await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
            ).scalars().all()
            participants = (
                await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))
            ).scalars().all()
            participant_emails = {p.name: p.email for p in participants if p.email}
            if not participant_emails:
                results["email"] = {
                    "status": "skipped",
                    "sent_count": 0,
                    "failed_count": 0,
                    "message": "No participant email addresses configured.",
                }
            else:
                from models.schemas import ActionItem as ActionItemSchema, Priority
                action_items = [
                    ActionItemSchema(
                        description=i.description,
                        owner=i.owner,
                        due_date=i.due_date,
                        priority=Priority(i.priority),
                    )
                    for i in action_items_rows
                ]
                email_res = await send_email_for_meeting(
                    meeting_id=meeting_id,
                    meeting_title=meeting.title,
                    short_summary=meeting.short_summary,
                    all_action_items=action_items,
                    participant_emails=participant_emails,
                )
                results["email"] = {
                    "status": "sent" if email_res["sent"] > 0 else "failed",
                    "sent_count": email_res["sent"],
                    "failed_count": email_res["failed"],
                    "message": f"Email dispatch complete — sent: {email_res['sent']}, failed: {email_res['failed']}",
                }
        except Exception as exc:
            results["email"] = {"status": "failed", "message": str(exc)}

    return DispatchMeetingResponse(
        meeting_id=meeting_id,
        results=results,
    )


@router.get("/meetings/{meeting_id}/audio", tags=["meetings"])
async def stream_meeting_audio(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream the audio file associated with a meeting for playback in the frontend audio player."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    possible_paths = [
        os.path.join(settings.upload_dir, meeting.audio_filename),
    ]
    if os.path.exists(settings.upload_dir):
        for fname in os.listdir(settings.upload_dir):
            if fname.endswith(meeting.audio_filename) or meeting.audio_filename in fname:
                possible_paths.insert(0, os.path.join(settings.upload_dir, fname))

    found_path = None
    for path in possible_paths:
        if os.path.exists(path) and os.path.isfile(path):
            found_path = path
            break

    if not found_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio file for meeting '{meeting.title}' is not available on server disk.",
        )

    ext = Path(found_path).suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".mp4": "video/mp4",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=found_path,
        media_type=media_type,
        filename=meeting.audio_filename,
        headers={"Accept-Ranges": "bytes"},
    )


# =============================================================================
# AGENT QUERY (conversational)
# =============================================================================

# =============================================================================
# AGENT QUERY (conversational) — Powered by OpenRouter with Full Meeting Context
# =============================================================================

SYSTEM_CHAT_PROMPT = (
    "You are an elite Meeting Intelligence AI Agent powered by advanced LLM reasoning. "
    "You have comprehensive access to all details of the user's meeting discussions, including "
    "executive summaries, detailed minutes, assigned action items with owners and deadlines, "
    "architectural and business decisions, attendees with speaker labels, and the complete verbatim dialogue transcript.\n\n"
    "INSTRUCTIONS:\n"
    "1. Answer questions thoroughly, accurately, and naturally based strictly on the provided meeting context.\n"
    "2. When asked about action items, explicitly detail who owns them, the urgency/priority, status, and due dates.\n"
    "3. When asked about decisions, opinions, or debates, cite specific quotes or speaker turns from the transcript.\n"
    "4. Format your responses with clean, readable GitHub-flavored Markdown (bolding, structured bullet points, numbered lists, or tables).\n"
    "5. If a question cannot be answered from the meeting record, state that clearly and mention what related topics were covered.\n"
    "6. Maintain a helpful, confident, executive pair-programmer and chief-of-staff tone."
)


async def _build_full_meeting_context(
    db: AsyncSession,
    question: str,
    meeting_id: str | None = None,
    current_user: User | None = None,
) -> tuple[str, list[str]]:
    """Build comprehensive context from the meeting record, full transcript, actions, decisions, and memory."""
    target_meeting: Meeting | None = None
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None)) if current_user else True

    if meeting_id:
        target_meeting = await db.get(Meeting, meeting_id)
        if target_meeting and current_user and target_meeting.user_id and target_meeting.user_id != current_user.id:
            target_meeting = None
    else:
        stmt = select(Meeting).where(user_filter).order_by(Meeting.created_at.desc()).limit(1)
        target_meeting = (await db.execute(stmt)).scalars().first()

    if not target_meeting:
        return "", []

    action_items = (
        await db.execute(
            select(DBActionItem).where(DBActionItem.meeting_id == target_meeting.id).order_by(DBActionItem.created_at)
        )
    ).scalars().all()

    decisions = (
        await db.execute(
            select(Decision).where(Decision.meeting_id == target_meeting.id).order_by(Decision.created_at)
        )
    ).scalars().all()

    participants = (
        await db.execute(
            select(Participant).where(Participant.meeting_id == target_meeting.id).order_by(Participant.created_at)
        )
    ).scalars().all()

    context_sections: list[str] = [
        f"MEETING TITLE: {target_meeting.title}",
        f"MEETING DURATION: {target_meeting.duration_minutes} minutes" if target_meeting.duration_minutes else "MEETING DURATION: Not recorded",
        f"RECORDED AT: {target_meeting.created_at.isoformat() if target_meeting.created_at else 'Unknown'}",
    ]

    if target_meeting.short_summary:
        context_sections.append(f"EXECUTIVE SUMMARY:\n{target_meeting.short_summary}")

    if target_meeting.detailed_summary:
        context_sections.append(f"DETAILED MINUTES & TOPICS:\n{target_meeting.detailed_summary}")

    if participants:
        part_lines = []
        for p in participants:
            label = f" ({p.speaker_label})" if p.speaker_label else ""
            email = f" <{p.email}>" if p.email else ""
            part_lines.append(f"- {p.name}{label}{email}")
        context_sections.append("PARTICIPANTS & SPEAKERS:\n" + "\n".join(part_lines))
    else:
        context_sections.append("PARTICIPANTS: None identified")

    if action_items:
        items_lines = [
            f"- [Status: {item.status.value if hasattr(item.status, 'value') else item.status}] {item.description} | Owner: {item.owner or 'Unassigned'} | Priority: {item.priority.value if hasattr(item.priority, 'value') else item.priority} | Due: {item.due_date or 'No deadline'}"
            for item in action_items
        ]
        context_sections.append("ACTION ITEMS & ASSIGNMENTS:\n" + "\n".join(items_lines))
    else:
        context_sections.append("ACTION ITEMS: None extracted")

    if decisions:
        dec_lines = [
            f"- {d.description} (Rationale/Context: {d.context})" if d.context else f"- {d.description}"
            for d in decisions
        ]
        context_sections.append("KEY DECISIONS MADE:\n" + "\n".join(dec_lines))
    else:
        context_sections.append("KEY DECISIONS: None recorded")

    # Complete Transcript (diarized speaker transcript preferred)
    transcript_text = getattr(target_meeting, "diarized_transcript", None) or getattr(target_meeting, "transcript", None)
    if transcript_text:
        # Full transcript provided to model (up to 60,000 characters, easily accommodated by 128k context)
        context_sections.append(f"VERBATIM MEETING DIALOGUE TRANSCRIPT:\n{transcript_text[:60000]}")

    # Cross-Meeting RAG Search for workspace-wide contextual intelligence
    try:
        from core.memory_service import memory_service
        mem_matches = await memory_service.search_memory(
            db,
            question,
            top_k=2,
            exclude_meeting_id=target_meeting.id,
            user_id=current_user.id if current_user else None,
        )
        if mem_matches:
            mem_block = ["HISTORICAL CROSS-MEETING INTELLIGENCE:"]
            for m_match in mem_matches:
                mem_block.append(f"- Past Meeting: \"{m_match['title']}\" ({m_match['date']}) | Summary: {m_match['short_summary']}")
                if m_match.get("action_items"):
                    items_str = "; ".join(f"{i['description']} (owner: {i['owner']})" for i in m_match["action_items"][:3])
                    mem_block.append(f"  Related Action Items: {items_str}")
            context_sections.append("\n".join(mem_block))
    except Exception as mem_exc:
        logger.debug("Memory RAG lookup: %s", mem_exc)

    full_context = "\n\n".join(context_sections)
    sources = [f"meeting:{target_meeting.id}"]
    return full_context, sources


def _get_fallback_rule_answer(meeting_context: str, question: str) -> str:
    lower_question = question.lower()
    if any(term in lower_question for term in ("how many people", "participants", "who attended", "attendees")):
        return "Please refer to the participants section extracted for this meeting."
    elif any(term in lower_question for term in ("action", "task", "todo", "assigned")):
        return "Action items and owners are listed in the meeting details."
    elif "decision" in lower_question:
        return "Decisions made during this meeting are summarized in the decision log."
    return "The meeting record and summary have been loaded. Please ask a specific question regarding topics discussed."


@router.post("/query", response_model=AgentQueryResponse, tags=["agent"])
async def query_agent(
    payload: AgentQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Conversational Q&A endpoint powered by OpenRouter with full meeting context."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

    meeting_context, sources = await _build_full_meeting_context(
        db=db,
        question=question,
        meeting_id=payload.meeting_id,
        current_user=current_user,
    )

    if not meeting_context:
        return AgentQueryResponse(
            answer="No meetings are available yet in this workspace. Upload and process a recording first.",
            sources=[],
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": f"{SYSTEM_CHAT_PROMPT}\n\n=== FULL MEETING CONTEXT ===\n{meeting_context}"}
    ]
    if payload.history:
        for h in payload.history[-10:]:
            if h.role in ("user", "assistant"):
                messages.append({"role": h.role, "content": h.content})

    messages.append({"role": "user", "content": question})

    # 1. Primary: OpenRouter LLM
    if openrouter_client.is_configured:
        try:
            answer = await openrouter_client.chat_completion(messages)
            if answer:
                return AgentQueryResponse(answer=answer, sources=sources)
        except Exception as exc:
            logger.warning("OpenRouter chat completion failed: %s", exc)

    # 2. Secondary fallback: Groq
    if settings.groq_api_key:
        try:
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key, timeout=20)
            completion = await asyncio.to_thread(
                client.chat.completions.create,
                model=settings.llm_fast_model,
                messages=messages,
                temperature=0.2,
                max_tokens=800,
            )
            answer = completion.choices[0].message.content.strip()
            if answer:
                return AgentQueryResponse(answer=answer, sources=sources)
        except Exception as exc:
            logger.warning("Groq fallback query failed: %s", exc)

    # 3. Tertiary fallback: Rule-based matcher
    fallback_ans = _get_fallback_rule_answer(meeting_context, question)
    return AgentQueryResponse(answer=fallback_ans, sources=sources)


@router.post("/query/stream", tags=["agent"])
async def query_agent_stream(
    payload: AgentQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Streaming LLM Q&A endpoint using Server-Sent Events (SSE) powered by OpenRouter."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

    meeting_context, sources = await _build_full_meeting_context(
        db=db,
        question=question,
        meeting_id=payload.meeting_id,
        current_user=current_user,
    )

    import json

    if not meeting_context:
        async def empty_stream():
            msg = "No meetings are available yet in this workspace. Upload and process a recording first."
            yield f"data: {json.dumps({'chunk': msg})}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": f"{SYSTEM_CHAT_PROMPT}\n\n=== FULL MEETING CONTEXT ===\n{meeting_context}"}
    ]
    if payload.history:
        for h in payload.history[-10:]:
            if h.role in ("user", "assistant"):
                messages.append({"role": h.role, "content": h.content})

    messages.append({"role": "user", "content": question})

    async def sse_generator():
        stream_succeeded = False

        # 1. Primary: OpenRouter Streaming
        if openrouter_client.is_configured:
            try:
                has_tokens = False
                async for token in openrouter_client.stream_chat_completion(messages):
                    has_tokens = True
                    yield f"data: {json.dumps({'chunk': token})}\n\n"

                if has_tokens:
                    stream_succeeded = True
                    yield f"data: {json.dumps({'done': True, 'sources': sources, 'model': openrouter_client.default_model})}\n\n"
                    return
            except Exception as exc:
                logger.warning("OpenRouter stream failed, attempting fallback: %s", exc)

        # 2. Secondary fallback: Groq Streaming
        if not stream_succeeded and settings.groq_api_key:
            try:
                from groq import Groq
                client = Groq(api_key=settings.groq_api_key, timeout=20)
                def create_groq_stream():
                    return client.chat.completions.create(
                        model=settings.llm_fast_model,
                        messages=messages,
                        temperature=0.2,
                        max_tokens=800,
                        stream=True,
                    )
                stream = await asyncio.to_thread(create_groq_stream)
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        stream_succeeded = True
                        yield f"data: {json.dumps({'chunk': delta})}\n\n"

                if stream_succeeded:
                    yield f"data: {json.dumps({'done': True, 'sources': sources, 'model': settings.llm_fast_model})}\n\n"
                    return
            except Exception as exc:
                logger.warning("Groq stream fallback failed: %s", exc)

        # 3. Tertiary fallback: rule-based word-by-word emission
        fallback_text = _get_fallback_rule_answer(meeting_context, question)
        words = fallback_text.split(" ")
        for i, word in enumerate(words):
            space = " " if i > 0 else ""
            yield f"data: {json.dumps({'chunk': space + word})}\n\n"
            await asyncio.sleep(0.015)
        yield f"data: {json.dumps({'done': True, 'sources': sources, 'fallback': True})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")



@router.post("/memory/search", response_model=MemorySearchResponse, tags=["agent"])
async def search_memory(
    payload: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search cross-meeting vector memory using semantic similarity.

    Returns relevant past meetings, action items, and decisions matching the query vector.
    """
    from core.memory_service import memory_service
    matches = await memory_service.search_memory(db, payload.query, top_k=payload.top_k, user_id=current_user.id)
    return MemorySearchResponse(
        query=payload.query,
        results_count=len(matches),
        matches=matches,
    )


# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse, tags=["analytics"])
async def get_analytics_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return high-level analytics summary: meeting counts, average duration, action item completion rate."""
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    
    stmt_meetings = select(Meeting).where(user_filter)
    meetings_res = (await db.execute(stmt_meetings)).scalars().all()
    
    total_meetings = len(meetings_res)
    avg_duration = (
        round(sum(m.duration_minutes for m in meetings_res) / total_meetings, 1)
        if total_meetings > 0
        else 0.0
    )
    
    meeting_ids = [m.id for m in meetings_res]
    if meeting_ids:
        stmt_actions = select(DBActionItem).where(DBActionItem.meeting_id.in_(meeting_ids))
        action_items = (await db.execute(stmt_actions)).scalars().all()
    else:
        action_items = []
        
    total_action_items = len(action_items)
    completed_action_items = sum(
        1 for a in action_items
        if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "done"
    )
    completion_rate = (
        round((completed_action_items / total_action_items) * 100, 1)
        if total_action_items > 0
        else 0.0
    )
    
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)
    
    # 7-day stats
    meetings_7d = [m for m in meetings_res if m.created_at and m.created_at >= cutoff_7d]
    meeting_ids_7d = set(m.id for m in meetings_7d)
    actions_7d = [a for a in action_items if a.meeting_id in meeting_ids_7d]
    completed_7d = sum(
        1 for a in actions_7d
        if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "done"
    )
    rate_7d = round((completed_7d / len(actions_7d)) * 100, 1) if actions_7d else 0.0
    
    stats_7d = PeriodStats(
        meetings_count=len(meetings_7d),
        action_items_count=len(actions_7d),
        completed_action_items=completed_7d,
        completion_rate=rate_7d,
    )
    
    # 30-day stats
    meetings_30d = [m for m in meetings_res if m.created_at and m.created_at >= cutoff_30d]
    meeting_ids_30d = set(m.id for m in meetings_30d)
    actions_30d = [a for a in action_items if a.meeting_id in meeting_ids_30d]
    completed_30d = sum(
        1 for a in actions_30d
        if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "done"
    )
    rate_30d = round((completed_30d / len(actions_30d)) * 100, 1) if actions_30d else 0.0
    
    stats_30d = PeriodStats(
        meetings_count=len(meetings_30d),
        action_items_count=len(actions_30d),
        completed_action_items=completed_30d,
        completion_rate=rate_30d,
    )
    
    return AnalyticsSummaryResponse(
        total_meetings=total_meetings,
        avg_duration_minutes=avg_duration,
        total_action_items=total_action_items,
        completed_action_items=completed_action_items,
        completion_rate=completion_rate,
        last_7_days=stats_7d,
        last_30_days=stats_30d,
    )


@router.get("/analytics/participants", response_model=AnalyticsParticipantsResponse, tags=["analytics"])
async def get_analytics_participants(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Leaderboard of active participants and action item load."""
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    stmt_meetings = select(Meeting.id).where(user_filter)
    meeting_ids = (await db.execute(stmt_meetings)).scalars().all()
    
    if not meeting_ids:
        return AnalyticsParticipantsResponse(participants=[])
        
    stmt_participants = select(Participant).where(Participant.meeting_id.in_(meeting_ids))
    participants = (await db.execute(stmt_participants)).scalars().all()
    
    stmt_actions = select(DBActionItem).where(DBActionItem.meeting_id.in_(meeting_ids))
    action_items = (await db.execute(stmt_actions)).scalars().all()
    
    part_stats: dict[str, dict] = {}
    for p in participants:
        name = (p.name or "").strip()
        if not name:
            continue
        if name not in part_stats:
            part_stats[name] = {"meetings": set(), "actions_count": 0, "actions_completed": 0}
        part_stats[name]["meetings"].add(p.meeting_id)
        
    for a in action_items:
        owner = (a.owner or "").strip()
        if not owner:
            continue
        if owner not in part_stats:
            part_stats[owner] = {"meetings": set(), "actions_count": 0, "actions_completed": 0}
        part_stats[owner]["actions_count"] += 1
        st = a.status.value if hasattr(a.status, "value") else str(a.status)
        if st == "done":
            part_stats[owner]["actions_completed"] += 1

    result = [
        ParticipantAnalyticsItem(
            name=name,
            meetings_count=len(info["meetings"]),
            action_items_count=info["actions_count"],
            completed_action_items=info["actions_completed"],
        )
        for name, info in part_stats.items()
    ]
    result.sort(key=lambda x: (x.meetings_count, x.action_items_count), reverse=True)
    return AnalyticsParticipantsResponse(participants=result)


@router.get("/analytics/timeline", response_model=AnalyticsTimelineResponse, tags=["analytics"])
async def get_analytics_timeline(
    period: str = Query("monthly", pattern="^(weekly|monthly)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Meeting frequency and action item completion trend over time (weekly/monthly)."""
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    stmt_meetings = select(Meeting).where(user_filter).order_by(Meeting.created_at.asc())
    meetings = (await db.execute(stmt_meetings)).scalars().all()
    
    meeting_ids = [m.id for m in meetings]
    if meeting_ids:
        stmt_actions = select(DBActionItem).where(DBActionItem.meeting_id.in_(meeting_ids))
        action_items = (await db.execute(stmt_actions)).scalars().all()
    else:
        action_items = []
        
    grouped: dict[str, dict] = {}
    
    for m in meetings:
        dt = m.created_at or datetime.now(timezone.utc)
        if period == "weekly":
            year, week, _ = dt.isocalendar()
            key = f"{year}-W{week:02d}"
            label = f"W{week} ({dt.strftime('%b %d')})"
        else:
            key = dt.strftime("%Y-%m")
            label = dt.strftime("%b %Y")
            
        if key not in grouped:
            grouped[key] = {
                "label": label,
                "meetings": [],
                "meeting_ids": set(),
            }
        grouped[key]["meetings"].append(m)
        grouped[key]["meeting_ids"].add(m.id)
        
    timeline_points = []
    for key, data in grouped.items():
        m_list = data["meetings"]
        m_ids = data["meeting_ids"]
        actions = [a for a in action_items if a.meeting_id in m_ids]
        done_cnt = sum(
            1 for a in actions
            if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "done"
        )
        avg_dur = round(sum(m.duration_minutes for m in m_list) / len(m_list), 1) if m_list else 0.0
        
        timeline_points.append(
            TimelineDataPoint(
                period=key,
                label=data["label"],
                meetings_count=len(m_list),
                action_items_count=len(actions),
                completed_action_items=done_cnt,
                avg_duration_minutes=avg_dur,
            )
        )
        
    return AnalyticsTimelineResponse(period_type=period, timeline=timeline_points)


@router.get("/analytics/action-items", response_model=AnalyticsActionItemsResponse, tags=["analytics"])
async def get_analytics_action_items(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Breakdown of open, in-progress, done, and overdue action items across all meetings and per owner."""
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    stmt_meetings = select(Meeting.id).where(user_filter)
    meeting_ids = (await db.execute(stmt_meetings)).scalars().all()
    
    if not meeting_ids:
        return AnalyticsActionItemsResponse()
        
    stmt_actions = select(DBActionItem).where(DBActionItem.meeting_id.in_(meeting_ids))
    action_items = (await db.execute(stmt_actions)).scalars().all()
    
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    total_open = 0
    total_in_progress = 0
    total_done = 0
    total_overdue = 0
    
    by_owner_dict: dict[str, dict] = {}
    
    for a in action_items:
        st = a.status.value if hasattr(a.status, "value") else str(a.status)
        is_overdue = (st != "done") and bool(a.due_date and a.due_date < today_str)
        
        if st == "open":
            total_open += 1
        elif st == "in_progress":
            total_in_progress += 1
        elif st == "done":
            total_done += 1
            
        if is_overdue:
            total_overdue += 1
            
        owner = (a.owner or "").strip() or "Unassigned"
        if owner not in by_owner_dict:
            by_owner_dict[owner] = {"open": 0, "in_progress": 0, "done": 0, "overdue": 0, "total": 0}
            
        by_owner_dict[owner]["total"] += 1
        if st == "open":
            by_owner_dict[owner]["open"] += 1
        elif st == "in_progress":
            by_owner_dict[owner]["in_progress"] += 1
        elif st == "done":
            by_owner_dict[owner]["done"] += 1
            
        if is_overdue:
            by_owner_dict[owner]["overdue"] += 1

    by_owner = [
        ActionItemOwnerBreakdown(
            owner=owner,
            open=stats["open"],
            in_progress=stats["in_progress"],
            done=stats["done"],
            overdue=stats["overdue"],
            total=stats["total"],
        )
        for owner, stats in by_owner_dict.items()
    ]
    by_owner.sort(key=lambda x: x.total, reverse=True)
    
    return AnalyticsActionItemsResponse(
        total_open=total_open,
        total_in_progress=total_in_progress,
        total_done=total_done,
        total_overdue=total_overdue,
        by_owner=by_owner,
    )


@router.get("/analytics/topics", response_model=AnalyticsTopicsResponse, tags=["analytics"])
async def get_analytics_topics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top recurring topics and keywords extracted across all meetings."""
    import re
    from collections import Counter
    
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    stmt_meetings = select(Meeting).where(user_filter)
    meetings = (await db.execute(stmt_meetings)).scalars().all()
    
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "about",
        "against", "between", "into", "through", "during", "before", "after", "above", "below",
        "from", "up", "down", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "any", "both", "each",
        "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same",
        "so", "than", "too", "very", "can", "will", "just", "should", "now", "meeting", "sync",
        "discussion", "update", "notes", "agenda", "call", "project", "team", "this", "that", "was",
        "were", "have", "has", "had", "been", "being", "they", "them", "their", "what", "which", "who"
    }
    
    counter = Counter()
    for m in meetings:
        text = f"{m.title} {m.short_summary or ''}"
        words = re.findall(r"\b[A-Za-z]{3,}\b", text)
        for w in words:
            wl = w.lower()
            if wl not in stopwords:
                counter[wl.capitalize()] += 1

    top_topics = [
        TopicKeywordItem(topic=topic, count=cnt)
        for topic, cnt in counter.most_common(15)
    ]
    return AnalyticsTopicsResponse(topics=top_topics)


# =============================================================================
# PHASE 5 — GLOBAL SEARCH, SPEAKER IDENTITY & DETAILED OBSERVABILITY
# =============================================================================

@router.get("/search", tags=["search"])
async def global_search(
    q: str = Query(..., min_length=1, description="Search query term"),
    mode: str = Query("fulltext", description="Search mode: 'fulltext' or 'semantic'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Global search across meetings, action items, and decisions."""
    search_term = f"%{q.strip()}%"
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))

    # 1. Search Meetings (Title, Summaries, Transcript)
    stmt_meetings = select(Meeting).where(
        user_filter & (
            Meeting.title.ilike(search_term) |
            Meeting.short_summary.ilike(search_term) |
            Meeting.detailed_summary.ilike(search_term) |
            Meeting.transcript.ilike(search_term)
        )
    ).limit(20)
    matching_meetings = (await db.execute(stmt_meetings)).scalars().all()

    meeting_results = []
    for m in matching_meetings:
        # Extract best snippet
        full_text = f"{m.short_summary or ''} {m.detailed_summary or ''} {m.transcript or ''}"
        idx = full_text.lower().find(q.lower())
        snippet = ""
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(full_text), idx + len(q) + 60)
            snippet = f"...{full_text[start:end]}..."
        else:
            snippet = (m.short_summary or "")[:120]

        meeting_results.append({
            "id": m.id,
            "title": m.title,
            "short_summary": m.short_summary,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "snippet": snippet,
        })

    # 2. Search Action Items
    meeting_ids_stmt = select(Meeting.id).where(user_filter)
    user_meeting_ids = (await db.execute(meeting_ids_stmt)).scalars().all()

    action_results = []
    if user_meeting_ids:
        stmt_actions = select(DBActionItem).where(
            DBActionItem.meeting_id.in_(user_meeting_ids) & (
                DBActionItem.description.ilike(search_term) |
                DBActionItem.owner.ilike(search_term)
            )
        ).limit(20)
        matching_actions = (await db.execute(stmt_actions)).scalars().all()

        for a in matching_actions:
            action_results.append({
                "id": a.id,
                "meeting_id": a.meeting_id,
                "description": a.description,
                "owner": a.owner,
                "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                "priority": a.priority.value if hasattr(a.priority, "value") else str(a.priority),
                "due_date": a.due_date,
            })

    # 3. Search Decisions
    decision_results = []
    if user_meeting_ids:
        stmt_decisions = select(Decision).where(
            Decision.meeting_id.in_(user_meeting_ids) & (
                Decision.description.ilike(search_term) |
                Decision.context.ilike(search_term)
            )
        ).limit(20)
        matching_decisions = (await db.execute(stmt_decisions)).scalars().all()

        for d in matching_decisions:
            decision_results.append({
                "id": d.id,
                "meeting_id": d.meeting_id,
                "description": d.description,
                "context": d.context,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            })

    total = len(meeting_results) + len(action_results) + len(decision_results)
    return {
        "query": q,
        "mode": mode,
        "meetings": meeting_results,
        "action_items": action_results,
        "decisions": decision_results,
        "total_results": total,
    }


@router.post("/meetings/{meeting_id}/speakers", tags=["meetings"])
async def update_speaker_mapping(
    meeting_id: str,
    payload: dict[str, str],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update speaker label mappings (e.g. SPEAKER_00 -> 'Alice Chen') and rewrite diarized transcript."""
    stmt = select(Meeting).where(Meeting.id == meeting_id)
    meeting = (await db.execute(stmt)).scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _verify_meeting_ownership(meeting, current_user)

    # Update or add Participant speaker_label records
    stmt_parts = select(Participant).where(Participant.meeting_id == meeting_id)
    existing_parts = (await db.execute(stmt_parts)).scalars().all()
    part_map = {p.speaker_label: p for p in existing_parts if p.speaker_label}

    for speaker_key, resolved_name in payload.items():
        clean_key = speaker_key.strip()
        clean_name = resolved_name.strip()
        if not clean_name:
            continue

        if clean_key in part_map:
            part_map[clean_key].name = clean_name
        else:
            new_p = Participant(
                meeting_id=meeting_id,
                name=clean_name,
                speaker_label=clean_key,
            )
            db.add(new_p)

        # Retroactively replace in diarized_transcript
        if meeting.diarized_transcript:
            meeting.diarized_transcript = meeting.diarized_transcript.replace(
                f"{clean_key}:", f"{clean_name}:"
            )

    await db.commit()
    await db.refresh(meeting)

    # Return updated participant list
    stmt_updated_parts = select(Participant).where(Participant.meeting_id == meeting_id)
    updated_parts = (await db.execute(stmt_updated_parts)).scalars().all()

    return {
        "meeting_id": meeting_id,
        "diarized_transcript": meeting.diarized_transcript,
        "participants": [
            {
                "id": p.id,
                "name": p.name,
                "email": p.email,
                "speaker_label": p.speaker_label,
            }
            for p in updated_parts
        ],
    }


@router.get("/health/detailed", tags=["health"])
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """Comprehensive system observability endpoint checking database & Groq connectivity."""
    db_healthy = False
    db_error = None
    try:
        await db.execute(select(1))
        db_healthy = True
    except Exception as exc:
        db_error = str(exc)

    groq_configured = bool(settings.groq_api_key and settings.groq_api_key.strip())

    overall = "healthy" if (db_healthy and groq_configured) else "degraded"

    return {
        "status": overall,
        "version": settings.app_version,
        "database": {
            "connected": db_healthy,
            "error": db_error,
        },
        "groq_api": {
            "configured": groq_configured,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }




