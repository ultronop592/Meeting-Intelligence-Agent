"""Domain router: Meetings lifecycle, audio processing, status tracking, and dispatch tools.

Endpoints:
- POST   /meeting/upload: Upload recorded meeting audio.
- POST   /meetings/process: Trigger background multi-agent processing pipeline.
- GET    /meetings/status/{job_id}: Poll processing job status.
- WS     /meetings/ws/{job_id}: Real-time WebSocket pipeline events.
- GET    /meetings: List paginated meetings for current user.
- GET    /meetings/{meeting_id}: Retrieve meeting details (summary, actions, decisions, participants).
- GET    /meetings/{meeting_id}/export/pdf: Download formatted meeting summary PDF.
- PATCH  /meetings/{meeting_id}/action-items/{item_id}: Update action item status.
- PATCH  /meetings/{meeting_id}/participants/{participant_id}: Update participant email.
- DELETE /meetings/{meeting_id}: Delete meeting and all child records.
- POST   /meetings/{meeting_id}/send/email: Dispatch personalized emails to participants.
- POST   /meetings/{meeting_id}/send/slack: Dispatch summary and action items to Slack.
- POST   /meetings/{meeting_id}/send/jira: Create Jira issue tickets for action items.
- POST   /meetings/{meeting_id}/send/calendar: Book Google Calendar follow-up event.
- POST   /meetings/{meeting_id}/dispatch: Human-in-the-loop multi-channel dispatch.
- GET    /meetings/{meeting_id}/audio: Stream meeting audio (S3 redirect or local file).
- POST   /meetings/{meeting_id}/speakers: Map diarization speaker labels to human names.
- GET    /health/detailed: Detailed health diagnostics.
"""

import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import time
from typing import Any
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import verify_meeting_ownership
from core.auth import get_current_user
from core.cache import (
    TTL_MEETING_LIST,
    cache_get,
    cache_set,
    invalidate_meetings_list,
    invalidate_user_analytics,
    key_meetings_list,
)
from core.config import settings
from core.limiter import limiter
from core.pdf_service import generate_meeting_pdf
from core.storage import storage_service
from core.ws_manager import ws_manager
from db.database import (
    AsyncSessionLocal,
    create_processing_job,
    get_db,
    get_processing_job,
    update_processing_job,
)
from db.models import ActionItem as DBActionItem, Decision, Meeting, NotificationLog, Participant, User
from graph.agent_graph import arun_meeting_agent
from models.schemas import (
    ActionItem as ActionItemSchema,
    ActionItemRow,
    ActionItemStatus,
    DecisionRow,
    DispatchMeetingRequest,
    DispatchMeetingResponse,
    MeetingDetailResponse,
    MeetingListItem,
    MeetingRow,
    NotificationLogRow,
    ParticipantRow,
    Priority,
    ProcessMeetingRequest,
    UpdateActionItemRequest,
)
from tools.calender_tool import send_calendar_for_meeting
from tools.email_tool import send_email_for_meeting
from tools.jira_tool import send_jira_for_meeting
from tools.slack_tool import send_slack_for_meeting

logger = logging.getLogger(__name__)

meetings_router = APIRouter(tags=["meetings"])

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


@meetings_router.post("/meeting/upload")
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


async def _process_job(job_id: str, payload: ProcessMeetingRequest, user_id: str | None = None):
    """Background task: run the multi-agent pipeline and persist status in DB."""
    await create_processing_job(job_id, user_id=user_id)

    try:
        phase_start = time.perf_counter()
        state = await arun_meeting_agent(
            payload.audio_file_path,
            payload.audio_filename,
            user_id=user_id,
            job_id=job_id,
        )

        completed_nodes = ["upload"] + (state.completed_nodes or [])

        if not state.meeting_id:
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
        if user_id:
            await invalidate_meetings_list(user_id)
            await invalidate_user_analytics(user_id)
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


@meetings_router.post("/meetings/process")
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


@meetings_router.get("/meetings/status/{job_id}")
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


@meetings_router.websocket("/meetings/ws/{job_id}")
async def meeting_ws_progress(websocket: WebSocket, job_id: str):
    """Real-time pipeline progress events over WebSocket with fallback keepalive."""
    await ws_manager.connect(job_id, websocket)
    try:
        current_job = await get_processing_job(job_id)
        if current_job:
            await websocket.send_json({
                "event": "initial_state",
                "job_id": job_id,
                **current_job,
            })

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=25.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_json({"event": "ping", "job_id": job_id})
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected for job %s", job_id)
    except Exception as exc:
        logger.debug("WebSocket error for job %s: %s", job_id, exc)
    finally:
        await ws_manager.disconnect(job_id, websocket)


@meetings_router.get("/meetings", response_model=list[MeetingListItem])
async def list_meetings(
    response: Response,
    limit: int = Query(default=20, ge=1, le=100, description="Max meetings to return per page"),
    offset: int = Query(default=0, ge=0, description="Offset cursor for pagination"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))

    _ck = key_meetings_list(current_user.id, limit, offset)
    cached = await cache_get(_ck)
    if cached is not None:
        response.headers["X-Total-Count"] = str(cached.get("total", 0))
        response.headers["X-Page-Limit"]  = str(limit)
        response.headers["X-Page-Offset"] = str(offset)
        response.headers["X-Cache"] = "HIT"
        return [MeetingListItem(**m) for m in cached["items"]]

    total_count = (
        await db.execute(select(func.count(Meeting.id)).where(user_filter))
    ).scalar_one()

    stmt = (
        select(Meeting, func.count(DBActionItem.id).label("action_items_count"))
        .outerjoin(DBActionItem, DBActionItem.meeting_id == Meeting.id)
        .where(user_filter)
        .group_by(Meeting.id)
        .order_by(Meeting.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()

    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page-Limit"] = str(limit)
    response.headers["X-Page-Offset"] = str(offset)
    response.headers["X-Cache"] = "MISS"

    items = [
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
    await cache_set(_ck, {"total": total_count, "items": [i.model_dump() for i in items]}, ttl=TTL_MEETING_LIST)
    return items


@meetings_router.get("/meetings/{meeting_id}", response_model=MeetingDetailResponse)
async def get_meeting_details(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)

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


@meetings_router.get("/meetings/{meeting_id}/export/pdf")
async def export_meeting_pdf(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a meeting's intelligence summary, action items, and decisions as a formatted PDF."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)

    action_items = (
        await db.execute(
            select(DBActionItem).where(DBActionItem.meeting_id == meeting_id).order_by(DBActionItem.created_at)
        )
    ).scalars().all()
    decisions = (
        await db.execute(
            select(Decision).where(Decision.meeting_id == meeting_id).order_by(Decision.created_at)
        )
    ).scalars().all()
    participants = (
        await db.execute(
            select(Participant).where(Participant.meeting_id == meeting_id).order_by(Participant.name)
        )
    ).scalars().all()

    pdf_bytes = generate_meeting_pdf(
        meeting=meeting,
        action_items=action_items,
        decisions=decisions,
        participants=participants,
    )

    safe_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (meeting.title or "meeting")).strip("_")
    filename = f"{safe_title[:40]}_{meeting.id[:8]}_summary.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@meetings_router.patch("/meetings/{meeting_id}/action-items/{item_id}", response_model=ActionItemRow)
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
    verify_meeting_ownership(meeting, current_user)

    item = await db.get(DBActionItem, item_id)
    if not item or item.meeting_id != meeting_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")
    item.status = payload.status.value if isinstance(payload.status, ActionItemStatus) else str(payload.status)
    await db.flush()
    await invalidate_user_analytics(current_user.id)
    return ActionItemRow.model_validate(item)


@meetings_router.patch("/meetings/{meeting_id}/participants/{participant_id}", response_model=ParticipantRow)
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
    verify_meeting_ownership(meeting, current_user)

    participant = await db.get(Participant, participant_id)
    if not participant or participant.meeting_id != meeting_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    participant.email = email
    await db.flush()
    return ParticipantRow.model_validate(participant)


@meetings_router.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)
    await db.delete(meeting)
    await db.flush()
    await invalidate_meetings_list(current_user.id)
    await invalidate_user_analytics(current_user.id)
    return {"deleted": True, "meeting_id": meeting_id}


@meetings_router.post("/meetings/{meeting_id}/send/email")
async def send_email(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send personalised emails to all participants who have email addresses stored."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)

    action_items_rows = (
        await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
    ).scalars().all()
    participants = (
        await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))
    ).scalars().all()

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
        user_id=current_user.id,
    )
    return {
        "message": f"Email dispatch complete — sent: {result['sent']}, failed: {result['failed']}",
        "sent": result["sent"],
        "failed": result["failed"],
    }


@meetings_router.post("/meetings/{meeting_id}/send/slack")
async def send_slack(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post meeting summary and action items to the configured Slack channel."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)

    action_items_rows = (
        await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
    ).scalars().all()
    decisions_count = (
        await db.execute(select(func.count(Decision.id)).where(Decision.meeting_id == meeting_id))
    ).scalar_one()
    participants = (
        await db.execute(select(Participant).where(Participant.meeting_id == meeting_id))
    ).scalars().all()

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
        user_id=current_user.id,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Slack dispatch failed: {result['error']}",
        )
    return {"message": "Slack notification sent successfully.", "sent": 1, "failed": 0}


@meetings_router.post("/meetings/{meeting_id}/send/jira")
async def send_jira(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create Jira tickets for all action items in this meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)

    action_items_rows = (
        await db.execute(select(DBActionItem).where(DBActionItem.meeting_id == meeting_id))
    ).scalars().all()

    if not action_items_rows:
        return {"message": "No action items found for this meeting.", "sent": 0, "failed": 0, "created": []}

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
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    return {
        "message": f"Jira dispatch complete — created: {len(result['created'])}, failed: {len(result['failed'])}",
        "sent": len(result["created"]),
        "failed": len(result["failed"]),
        "created": result["created"],
    }


@meetings_router.post("/meetings/{meeting_id}/send/calendar")
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
    verify_meeting_ownership(meeting, current_user)

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
        user_id=current_user.id,
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


@meetings_router.post("/meetings/{meeting_id}/dispatch", response_model=DispatchMeetingResponse)
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
    verify_meeting_ownership(meeting, current_user)

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
                user_id=current_user.id,
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
                    user_id=current_user.id,
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
                user_id=current_user.id,
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
                    user_id=current_user.id,
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


@meetings_router.get("/meetings/{meeting_id}/audio")
async def stream_meeting_audio(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream the audio file associated with a meeting for playback in the frontend audio player."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    verify_meeting_ownership(meeting, current_user)

    if getattr(meeting, "audio_storage_key", None):
        presigned_url = await storage_service.get_presigned_url(meeting.audio_storage_key)
        if presigned_url:
            return RedirectResponse(
                url=presigned_url,
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Cache-Control": "private, max-age=3600"},
            )

    possible_paths = []
    if getattr(meeting, "audio_storage_key", None):
        possible_paths.append(os.path.join(settings.upload_dir, meeting.audio_storage_key))

    possible_paths.append(os.path.join(settings.upload_dir, meeting.audio_filename))
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
            detail=f"Audio file for meeting '{meeting.title}' is not available on server disk or object storage.",
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


@meetings_router.post("/meetings/{meeting_id}/speakers")
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
    verify_meeting_ownership(meeting, current_user)

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

        if meeting.diarized_transcript:
            meeting.diarized_transcript = meeting.diarized_transcript.replace(
                f"{clean_key}:", f"{clean_name}:"
            )

    await db.commit()
    await db.refresh(meeting)

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


@meetings_router.get("/health/detailed", tags=["health"])
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
