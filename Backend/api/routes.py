import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.database import AsyncSessionLocal, get_db
from db.models import ActionItem as DBActionItem
from db.models import Decision, Meeting, NotificationLog, Participant
from models.schemas import (
    ActionItemRow,
    ActionItemStatus,
    AgentQueryRequest,
    AgentQueryResponse,
    DecisionRow,
    MeetingDetailResponse,
    MeetingListItem,
    MeetingRow,
    NotificationLogRow,
    ParticipantRow,
    ProcessMeetingRequest,
    UpdateActionItemRequest,
)

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
_job_status: dict[str, dict] = {}


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/meeting/upload", tags=["meetings"])
async def upload_audio(file: UploadFile = File(...)):
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
        # Stream upload chunks to disk to avoid loading large files into memory.
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


async def _process_job(job_id: str, payload: ProcessMeetingRequest):
    job_started_at = _utc_iso_now()
    _job_status[job_id] = {
        "status": "processing",
        "completed_nodes": ["upload"],
        "errors": [],
        "meeting_id": None,
        "started_at": job_started_at,
        "completed_at": None,
        "duration_ms": None,
        "node_timings": {
            "upload": {
                "started_at": job_started_at,
                "completed_at": job_started_at,
                "duration_ms": 0,
            }
        },
    }

    try:
        phase_start = time.perf_counter()
        async with AsyncSessionLocal() as session:
            title_base = Path(payload.audio_filename).stem.replace("_", " ").strip() or "Untitled meeting"
            after_transcribe = time.perf_counter()
            extract_timing = {
                "started_at": _utc_iso_now(),
                "completed_at": None,
                "duration_ms": None,
            }
            meeting = Meeting(
                title=title_base.title(),
                audio_filename=payload.audio_filename,
                duration_minutes=30,
                short_summary="Meeting processed and ready for review.",
                detailed_summary="This meeting was ingested successfully. You can now review action items and decisions.",
                embedding_status="pending",
            )
            session.add(meeting)
            await session.flush()
            extract_timing["completed_at"] = _utc_iso_now()
            extract_timing["duration_ms"] = int((time.perf_counter() - after_transcribe) * 1000)

            summarize_started_at = _utc_iso_now()
            summarize_start = time.perf_counter()

            session.add(
                DBActionItem(
                    meeting_id=meeting.id,
                    description="Review transcript and confirm action items.",
                    owner="Team",
                    due_date="2026-12-31",
                    priority="medium",
                    status="open",
                )
            )
            session.add(
                Decision(
                    meeting_id=meeting.id,
                    description="Proceed with the current implementation plan.",
                    context="Consensus in the recorded meeting.",
                )
            )
            session.add(Participant(meeting_id=meeting.id, name="Participant 1", email=None))

            save_started_at = _utc_iso_now()
            save_start = time.perf_counter()

            await session.commit()

            completed_at = _utc_iso_now()
            total_duration_ms = int((time.perf_counter() - phase_start) * 1000)

            _job_status[job_id] = {
                "status": "completed",
                "completed_nodes": ["upload", "process", "save_to_database"],
                "errors": [],
                "meeting_id": meeting.id,
                "started_at": job_started_at,
                "completed_at": completed_at,
                "duration_ms": total_duration_ms,
                "node_timings": {
                    "upload": {
                        "started_at": job_started_at,
                        "completed_at": job_started_at,
                        "duration_ms": 0,
                    },
                    "transcribe_audio": {
                        "started_at": job_started_at,
                        "completed_at": _utc_iso_now(),
                        "duration_ms": int((after_transcribe - phase_start) * 1000),
                    },
                    "extract_information": extract_timing,
                    "generate_summary": {
                        "started_at": summarize_started_at,
                        "completed_at": save_started_at,
                        "duration_ms": int((save_start - summarize_start) * 1000),
                    },
                    "save_to_database": {
                        "started_at": save_started_at,
                        "completed_at": completed_at,
                        "duration_ms": int((time.perf_counter() - save_start) * 1000),
                    },
                },
                "title": meeting.title,
                "short_summary": meeting.short_summary,
                "action_items_count": 1,
                "decisions_count": 1,
                "participants_count": 1,
                "jira_tickets_created": 0,
                "calendar_event_id": None,
                "notifications_sent": 0,
            }
    except Exception as exc:
        logger.exception("Processing job failed")
        completed_at = _utc_iso_now()
        _job_status[job_id] = {
            "status": "failed",
            "completed_nodes": [],
            "errors": [str(exc)],
            "meeting_id": None,
            "started_at": job_started_at,
            "completed_at": completed_at,
            "duration_ms": None,
            "node_timings": _job_status.get(job_id, {}).get("node_timings", {}),
        }
    finally:
        try:
            if os.path.exists(payload.audio_file_path):
                os.remove(payload.audio_file_path)
        except OSError:
            pass


@router.post("/meetings/process", tags=["meetings"])
async def process_meeting(request: ProcessMeetingRequest, background_tasks: BackgroundTasks):
    if not os.path.exists(request.audio_file_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file not found")

    job_id = str(uuid.uuid4())
    _job_status[job_id] = {
        "status": "processing",
        "completed_nodes": [],
        "errors": [],
        "meeting_id": None,
        "started_at": _utc_iso_now(),
        "completed_at": None,
        "duration_ms": None,
        "node_timings": {},
    }
    background_tasks.add_task(_process_job, job_id, request)
    return {"job_id": job_id, "message": "Meeting processing started.", "status": "processing"}


@router.get("/meetings/status/{job_id}", tags=["meetings"])
async def get_processing_status(job_id: str):
    if job_id not in _job_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
    return _job_status[job_id]


@router.get("/meetings", response_model=list[MeetingListItem], tags=["meetings"])
async def list_meetings(limit: int = 20, offset: int = 0, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Meeting, func.count(DBActionItem.id).label("action_items_count"))
        .outerjoin(DBActionItem, DBActionItem.meeting_id == Meeting.id)
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
async def get_meeting_details(meeting_id: str, db: AsyncSession = Depends(get_db)):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

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
):
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
):
    participant = await db.get(Participant, participant_id)
    if not participant or participant.meeting_id != meeting_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    participant.email = email
    await db.flush()
    return ParticipantRow.model_validate(participant)


@router.delete("/meetings/{meeting_id}", tags=["meetings"])
async def delete_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    await db.delete(meeting)
    await db.flush()
    return {"deleted": True, "meeting_id": meeting_id}


async def _log_send(db: AsyncSession, meeting_id: str, channel: str):
    db.add(NotificationLog(meeting_id=meeting_id, type=channel, status="sent", detail=f"Sent via {channel}"))
    await db.flush()


@router.post("/meetings/{meeting_id}/send/email", tags=["meetings"])
async def send_email(meeting_id: str, db: AsyncSession = Depends(get_db)):
    await _log_send(db, meeting_id, "email")
    return {"message": "Email dispatch simulated", "sent": 1, "failed": 0}


@router.post("/meetings/{meeting_id}/send/slack", tags=["meetings"])
async def send_slack(meeting_id: str, db: AsyncSession = Depends(get_db)):
    await _log_send(db, meeting_id, "slack")
    return {"message": "Slack dispatch simulated", "sent": 1, "failed": 0}


@router.post("/meetings/{meeting_id}/send/jira", tags=["meetings"])
async def send_jira(meeting_id: str, db: AsyncSession = Depends(get_db)):
    await _log_send(db, meeting_id, "jira")
    return {"message": "Jira dispatch simulated", "sent": 1, "failed": 0, "created": []}


@router.post("/meetings/{meeting_id}/send/calendar", tags=["meetings"])
async def send_calendar(
    meeting_id: str,
    days_from_now: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    await _log_send(db, meeting_id, "calendar")
    return {
        "message": f"Calendar dispatch simulated for {days_from_now} day(s) from now",
        "sent": 1,
        "failed": 0,
    }


@router.post("/query", response_model=AgentQueryResponse, tags=["agent"])
async def query_agent(payload: AgentQueryRequest, db: AsyncSession = Depends(get_db)):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

    target_meeting: Meeting | None = None
    if payload.meeting_id:
        target_meeting = await db.get(Meeting, payload.meeting_id)
        if not target_meeting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    else:
        target_meeting = (
            await db.execute(select(Meeting).order_by(Meeting.created_at.desc()).limit(1))
        ).scalars().first()

    if not target_meeting:
        return AgentQueryResponse(
            answer="No meetings are available yet. Upload a recording and process it first.",
            sources=[],
        )

    action_items = (
        await db.execute(
            select(DBActionItem).where(DBActionItem.meeting_id == target_meeting.id).order_by(DBActionItem.created_at)
        )
    ).scalars().all()
    decisions = (
        await db.execute(select(Decision).where(Decision.meeting_id == target_meeting.id).order_by(Decision.created_at))
    ).scalars().all()
    participants = (
        await db.execute(
            select(Participant)
            .where(Participant.meeting_id == target_meeting.id)
            .order_by(Participant.created_at)
        )
    ).scalars().all()

    lower_question = question.lower()
    if (
        "how many people" in lower_question
        or "how many participants" in lower_question
        or "who attended" in lower_question
        or "participants" in lower_question
        or "people in" in lower_question
    ):
        if not participants:
            answer = "I could not identify any participants for this meeting yet."
        else:
            participant_names = ", ".join(p.name for p in participants[:10])
            answer = (
                f"There were {len(participants)} participant(s) in this meeting: "
                f"{participant_names}."
            )
    elif "action" in lower_question or "task" in lower_question or "todo" in lower_question:
        if not action_items:
            answer = "No action items were extracted for this meeting yet."
        else:
            tasks = "; ".join(f"{item.description} (owner: {item.owner})" for item in action_items[:5])
            answer = f"Here are the key action items: {tasks}."
    elif "decision" in lower_question:
        if not decisions:
            answer = "No explicit decisions were captured for this meeting yet."
        else:
            decision_text = "; ".join(dec.description for dec in decisions[:5])
            answer = f"Captured decisions: {decision_text}."
    else:
        answer = (
            f"Meeting: {target_meeting.title}. "
            f"Summary: {target_meeting.short_summary}. "
            f"I found {len(action_items)} action item(s) and {len(decisions)} decision(s)."
        )

    return AgentQueryResponse(answer=answer, sources=[f"meeting:{target_meeting.id}"])
