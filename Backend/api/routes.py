import logging
import os
import time
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.database import (
    AsyncSessionLocal,
    create_processing_job,
    get_db,
    get_processing_job,
    update_processing_job,
)
from db.models import ActionItem as DBActionItem
from db.models import Decision, Meeting, NotificationLog, Participant
from graph.agent_graph import run_meeting_agent
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


# =============================================================================
# UPLOAD
# =============================================================================

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

async def _process_job(job_id: str, payload: ProcessMeetingRequest):
    """Background task: run the full LangGraph pipeline and persist status in DB."""
    job_started_at = datetime.now(timezone.utc)

    # Create the job record in DB so it's visible even before completion.
    await create_processing_job(job_id)

    try:
        phase_start = time.perf_counter()

        # Run the sync graph in a worker thread to keep the event loop free.
        state = await asyncio.to_thread(
            run_meeting_agent,
            payload.audio_file_path,
            payload.audio_filename,
        )

        if not state.meeting_id:
            raise RuntimeError("Pipeline finished without persisting a meeting_id")

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
        notifications_sent = len([n for n in state.notification_results if n.get("status") == "sent"])

        await update_processing_job(
            job_id,
            status="completed",
            completed_nodes=["upload"] + state.completed_nodes,
            errors=state.errors,
            meeting_id=meeting.id,
            completed_at=completed_at,
            duration_ms=total_duration_ms,
            title=meeting.title,
            short_summary=meeting.short_summary,
            action_items_count=int(action_items_count or 0),
            decisions_count=int(decisions_count or 0),
            participants_count=int(participants_count or 0),
            jira_tickets_created=len(state.jira_ticket_ids),
            calendar_event_id=state.calendar_event_id,
            notifications_sent=notifications_sent,
        )
    except Exception as exc:
        logger.exception("Processing job failed")
        await update_processing_job(
            job_id,
            status="failed",
            completed_nodes=[],
            errors=[str(exc)],
            completed_at=datetime.now(timezone.utc),
        )
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
    background_tasks.add_task(_process_job, job_id, request)
    return {"job_id": job_id, "message": "Meeting processing started.", "status": "processing"}


@router.get("/meetings/status/{job_id}", tags=["meetings"])
async def get_processing_status(job_id: str):
    """Return the current processing job status from the database."""
    job = await get_processing_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
    return job


# =============================================================================
# MEETINGS
# =============================================================================

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


# =============================================================================
# MANUAL SEND — live tool integrations
# =============================================================================

@router.post("/meetings/{meeting_id}/send/email", tags=["meetings"])
async def send_email(meeting_id: str, db: AsyncSession = Depends(get_db)):
    """Send personalised emails to all participants who have email addresses stored."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

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
async def send_slack(meeting_id: str, db: AsyncSession = Depends(get_db)):
    """Post meeting summary and action items to the configured Slack channel."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

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
async def send_jira(meeting_id: str, db: AsyncSession = Depends(get_db)):
    """Create Jira tickets for all action items in this meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

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
):
    """Book a follow-up Google Calendar event for all participants."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

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


@router.get("/meetings/{meeting_id}/audio", tags=["meetings"])
async def stream_meeting_audio(meeting_id: str, db: AsyncSession = Depends(get_db)):
    """Stream the audio file associated with a meeting for playback in the frontend audio player."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

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

    # Try Groq LLM for intelligent Q&A — model is chosen by the LLM router
    if settings.groq_api_key:
        try:
            from groq import Groq
            from core.llm_router import llm_router

            client = Groq(api_key=settings.groq_api_key, timeout=20)

            context_blocks = [
                f"MEETING TITLE: {target_meeting.title}",
                f"SHORT SUMMARY: {target_meeting.short_summary}",
                f"DETAILED SUMMARY: {target_meeting.detailed_summary}",
                "PARTICIPANTS: " + (", ".join(p.name for p in participants) if participants else "None identified"),
                "ACTION ITEMS:\n" + ("\n".join(f"- {item.description} (Owner: {item.owner}, Priority: {item.priority}, Status: {item.status})" for item in action_items) if action_items else "None"),
                "DECISIONS:\n" + ("\n".join(f"- {d.description} (Context: {d.context})" for d in decisions) if decisions else "None"),
            ]
            if getattr(target_meeting, "diarized_transcript", None):
                context_blocks.append("SPEAKER TRANSCRIPT:\n" + str(target_meeting.diarized_transcript)[:4000])
            elif getattr(target_meeting, "transcript", None):
                context_blocks.append("TRANSCRIPT:\n" + str(target_meeting.transcript)[:4000])

            system_prompt = (
                "You are an AI assistant answering questions about a meeting recording. "
                "Use the provided meeting context to answer the user's question accurately, concisely, and naturally. "
                "If the answer is not in the context, state that clearly based on the meeting record."
            )
            user_content = "CONTEXT:\n\n" + "\n\n".join(context_blocks) + f"\n\nQUESTION: {question}"

            # --- Multi-LLM Routing -------------------------------------------
            # Route based on question complexity and context size.
            # Simple keyword lookups (participants, action items, decisions)
            # use llama-3.1-8b-instant for lower latency and cost.
            # Complex / analytical questions use llama-3.3-70b-versatile.
            routing = llm_router.select_model(
                "query",
                question=question,
                context_length=len(user_content),
            )
            selected_model = routing.model
            logger.info(
                "Q&A routing: model=%s | reason=%s | question_preview=%.60s",
                selected_model,
                routing.reason,
                question,
            )
            # -----------------------------------------------------------------

            completion = await asyncio.to_thread(
                client.chat.completions.create,
                model=selected_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
                max_tokens=500,
            )
            answer = completion.choices[0].message.content.strip()
            if answer:
                return AgentQueryResponse(answer=answer, sources=[f"meeting:{target_meeting.id}"])
        except Exception as exc:
            logger.warning("Groq Llama 3.3 query failed, falling back to keyword matcher: %s", exc)

    # Fallback to rule-based keyword matcher if Groq API key is missing or fails
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


@router.post("/query/stream", tags=["agent"])
async def query_agent_stream(payload: AgentQueryRequest, db: AsyncSession = Depends(get_db)):
    """Streaming LLM Q&A endpoint using Server-Sent Events (SSE).

    Streams tokens real-time as they are generated by Groq (or fallback).
    Emits SSE events in format `data: {"chunk": "token"}\n\n` and a final `data: {"done": true, ...}\n\n`.
    """
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
        import json
        async def empty_stream():
            msg = "No meetings are available yet. Upload a recording and process it first."
            yield f"data: {json.dumps({'chunk': msg})}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"

        return StreamingResponse(empty_stream(), media_type="text/event-stream")

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

    context_blocks = [
        f"MEETING TITLE: {target_meeting.title}",
        f"SHORT SUMMARY: {target_meeting.short_summary}",
        f"DETAILED SUMMARY: {target_meeting.detailed_summary}",
        "PARTICIPANTS: " + (", ".join(p.name for p in participants) if participants else "None identified"),
        "ACTION ITEMS:\n" + ("\n".join(f"- {item.description} (Owner: {item.owner}, Priority: {item.priority}, Status: {item.status})" for item in action_items) if action_items else "None"),
        "DECISIONS:\n" + ("\n".join(f"- {d.description} (Context: {d.context})" for d in decisions) if decisions else "None"),
    ]
    if getattr(target_meeting, "diarized_transcript", None):
        context_blocks.append("SPEAKER TRANSCRIPT:\n" + str(target_meeting.diarized_transcript)[:4000])
    elif getattr(target_meeting, "transcript", None):
        context_blocks.append("TRANSCRIPT:\n" + str(target_meeting.transcript)[:4000])

    system_prompt = (
        "You are an AI assistant answering questions about a meeting recording. "
        "Use the provided meeting context to answer the user's question accurately, concisely, and naturally. "
        "If the answer is not in the context, state that clearly based on the meeting record."
    )
    user_content = "CONTEXT:\n\n" + "\n\n".join(context_blocks) + f"\n\nQUESTION: {question}"

    def get_fallback_answer() -> str:
        lower_question = question.lower()
        if (
            "how many people" in lower_question
            or "how many participants" in lower_question
            or "who attended" in lower_question
            or "participants" in lower_question
            or "people in" in lower_question
        ):
            if not participants:
                return "I could not identify any participants for this meeting yet."
            participant_names = ", ".join(p.name for p in participants[:10])
            return f"There were {len(participants)} participant(s) in this meeting: {participant_names}."
        elif "action" in lower_question or "task" in lower_question or "todo" in lower_question:
            if not action_items:
                return "No action items were extracted for this meeting yet."
            tasks = "; ".join(f"{item.description} (owner: {item.owner})" for item in action_items[:5])
            return f"Here are the key action items: {tasks}."
        elif "decision" in lower_question:
            if not decisions:
                return "No explicit decisions were captured for this meeting yet."
            decision_text = "; ".join(dec.description for dec in decisions[:5])
            return f"Captured decisions: {decision_text}."
        else:
            return (
                f"Meeting: {target_meeting.title}. "
                f"Summary: {target_meeting.short_summary}. "
                f"I found {len(action_items)} action item(s) and {len(decisions)} decision(s)."
            )

    import json

    async def sse_generator():
        stream_succeeded = False
        if settings.groq_api_key:
            try:
                from groq import Groq
                from core.llm_router import llm_router

                routing = llm_router.select_model(
                    "query",
                    question=question,
                    context_length=len(user_content),
                )
                selected_model = routing.model

                client = Groq(api_key=settings.groq_api_key, timeout=20)

                def create_stream():
                    return client.chat.completions.create(
                        model=selected_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        temperature=0.2,
                        max_tokens=500,
                        stream=True,
                    )

                stream = await asyncio.to_thread(create_stream)
                stream_iter = iter(stream)

                def get_next_chunk():
                    try:
                        return next(stream_iter)
                    except StopIteration:
                        return None

                has_content = False
                while True:
                    chunk = await asyncio.to_thread(get_next_chunk)
                    if chunk is None:
                        break
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta.content or ""
                        if delta:
                            has_content = True
                            yield f"data: {json.dumps({'chunk': delta})}\n\n"

                if has_content:
                    stream_succeeded = True
                    yield f"data: {json.dumps({'done': True, 'sources': [f'meeting:{target_meeting.id}'], 'model': selected_model})}\n\n"

            except Exception as exc:
                logger.warning("Groq streaming failed, falling back to keyword matcher: %s", exc)

        if not stream_succeeded:
            fallback_text = get_fallback_answer()
            words = fallback_text.split(" ")
            for i, word in enumerate(words):
                space = " " if i > 0 else ""
                yield f"data: {json.dumps({'chunk': space + word})}\n\n"
                await asyncio.sleep(0.015)
            yield f"data: {json.dumps({'done': True, 'sources': [f'meeting:{target_meeting.id}']})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

