import asyncio
import logging 
import os 
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from numpy import select
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from Backend.core.config import settings
from Backend.db.database import get_db, log_notifications
from Backend.db.models import (
    Meeting, ActionItem as DBActionItem, 
    Decision, Participant, NotificationLog,
)

from Backend.graph.agent_graph import run_meeting_agent
from Backend.models.schemas import (
    ActionItemStatus,
    MeetingDetailResponse,
    MeetingListItem,
    MeetingRow,
    ActionItemRow,
    DecisionRow,
    ParticipantRow,
    NotificationLogRow,
    ProcessMeetingRequest,
    ProcessMeetingResponse,
    UpdateActionItemRequest,
    Priority,
)

from Backend.tools.jira_tool import send_jira_for_meeting
from Backend.tools.calender_tool import send_calendar_for_meeting
from Backend.tools.email_tool import send_email_for_meeting
from Backend.tools.slack_tool import send_slack_for_meeting


logger =  logging.getLogger(__name__)
router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=4)

__job_status: dict[str, dict] ={}
ALLOWED_AUDIO_EXTENSIONS={ ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg","webm"}


#AUDIO UPLOAD 


@router.post("/meeting/upload", tags =["meetings"])
async def upload_audio(file: UploadFile = File(...)):
    """
 
    WHY SEPARATE UPLOAD AND PROCESS?
    Separating upload from processing gives the user a progress bar
    for the upload itself (large files take time to upload), and lets
    us validate the file before starting the expensive agent pipeline.
    """ 

#Validate file extension

suffix = Path(file.filename or "").suffix.lower()
if suffix not in ALLOWED_AUDIO_EXTENSIONS:
    raise HTTPException(
        status_code = status.HTTP_400_BAD_REQUEST,
        detail= F"Unsupported file type: {suffix}. Allowed types: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
        
    )

#Read file content 

content = await file.read()
size_bytes = len(content)

# validate file size 

if size_bytes > settings.max_upload_size_bytes:
    size_mb= size_bytes/(1024*1024)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=F"File too large: {size_mb:.2f} MB. Max allowed size is {settings.max_upload_size_bytes/(1024*1024):.2f} MB."
    )

if size_bytes == 0:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Uploaded file is empty."
    )
    
# save to disk 

unique_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
file_path = os.path.join(settings.upload_dir, unique_name)

os.makedirs(settings.upload_dir, exist_ok=True)

with open(file_path, "wb") as f:
    f.write(content)
    
    
size_mb = round(size_bytes/ (1024*1024), 2)
logger.info("File Uploaded | name: %s | size: %.2f MB | path: %s", file.filename, size_mb, file_path)

return {
    "filename": file.filename,
    "stored_filename": unique_name,
    "size_bytes": size_bytes,
    "size_mb": size_mb,
}


#PROCESS MEETING

def _run_agent_background(
    job_id; str,
    audio_file_path:str,
    audio_filename:str,
    
) ->None:
    
    try:
        __job_status[job_id] = {
            "status":          "processing",
            "completed_nodes": [],
            "errors":          [],
            "meeting_id":      None,
        }
        
        
        logger.info("Background Agent Started | job_id: %s", job_id)
        
        final_state =run_meeting_agent(
            audio_file_path = audio_file_path,
            audio_filename=audio_filename,
            
        )
        
        
        __job_status[job_id] ={
            "status":          "completed" if not final_state.errors else "completed_with_errors",
            "completed_nodes": final_state.completed_nodes,
            "errors":          final_state.errors,
            "meeting_id":      final_state.meeting_id,
            "title":           final_state.summary.title if final_state.summary else None,
            "short_summary":   final_state.summary.short_summary if final_state.summary else None,
            "action_items_count": len(final_state.extraction.action_items) if final_state.extraction else 0,
            "decisions_count":    len(final_state.extraction.decisions) if final_state.extraction else 0,
            "participants_count": len(final_state.extraction.participants) if final_state.extraction else 0,
            "jira_tickets_created": len(final_state.jira_ticket_ids),
            "calendar_event_id":    final_state.calendar_event_id,
            "notifications_sent":   len(final_state.notification_results)
        }
        
        logger.info(
            "Background agent complete | job_id: %s | meeting_id: %s | status: %s | errors: %d | action_items: %d | decisions: %d | participants: %d | jira_tickets: %d | notifications_sent: %d",
            job_id,
            final_state.meeting_id,
            final-state.completed_nodes,
            
        )
        
        try:
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
                logger.info("Temporary audio file removed | path: %s", audio_file_path)
        except OSError:
            pass
        
        except Exception as e:
            logger.error("Error in background agent for job_id %s: %s", job_id, str(e))
            __job_status[job_id] ={
                "status": "failed",
                "completed_nodes": [],
                "errors": [str(e)],
                "meeting_id": None,
            }
            
@router.post("/meetings/process", tags=["meetings"])
async def process_meeting(
    request: ProessMeetingRequest,
    background_tasks: BackgroundTasks,
):
    
# validate the fill exists 

if not os.path.exists(request.audio_file_path):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=F"Audio file not found at path: {request.audio_file_path}"
    )
    
    
    job_id  str(uuid.uuid4())
    
    background_tasks.add_task(
        _run_agent_background,
        job_id=job_id,
        audio_file_path=request.audio_file_path,
        audio_filename=request.audio_filename,
    )
    
    
    logger.info("Meeting processing started | job_id: %s | audio_file: %s", job_id, request.audio_file_path)
    
    return {
        "job_id": job_id,
        "message": "Meeting processing started. Use the job_id to check status."
        "status": "processing",
    }
    
    
# POLL PROCESSING STATUS

@router.get("/meetings/status/{job_id}", tags=["meetings"])
async def get_processing_status(job_id: str):
     """
    GET /api/meetings/status/{job_id}
 
    Poll this endpoint every 3 seconds while processing.
    Frontend shows a progress bar based on completed_nodes.
 
    Returns:
        {
            "status": "processing" | "completed" | "completed_with_errors" | "failed",
            "completed_nodes": ["transcribe_audio", "extract_information", ...],
            "meeting_id": "uuid-when-done",
            "errors": []
        }
 
    When status = "completed", redirect frontend to /meetings/{meeting_id}
    """
    if job_id not in _job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found. It may have expired.",
        )
 
    return _job_status[job_id]

#LIST MEETINGS 

@router.get("/meetings", response_model=list[MeetingListItem], tags=["meetings"])
async def list_meetings(
    limit: int = 20,
    offset: int =0,
    db: AsyncSession = Depends(get_db),
    
):
    
    
 # Query meetings with action item count using a subquery
  stmt = (
      select(
          Meetings,
          func.count(DBActionItem.id).label("action_items_count")   
          
      )
      .outerjoin(DBActionItem, DBActionItem.meeting_id == Meeting.id)
        .group_by(Meeting.id)
        .order_by(Meeting.created_at.desc())
        .limit(limit)
        .offset(offset)
  )
  
  result =  await db.execute(stmt)
  rows = reasult.all()
  
  meetings = []
  for meeting, count in rows:
       meetings.append(MeetingListItem(
            id=meeting.id,
            title=meeting.title,
            audio_filename=meeting.audio_filename,
            duration_minutes=meeting.duration_minutes,
            short_summary=meeting.short_summary,
            action_items_count=count or 0,
            created_at=meeting.created_at,
        ))
       
    return meetings


# GET MEETING DETAILS

@router.get("/meetings/{meeting_id}", response_model=MeetingDetailResponse, tags=["meetings"])
async def get_meeting_details(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
):
    meeting await db.get(Meeting, meeting_id)   
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting with id {meeting_id} not found.",
        )
        
        # fetch all related data in parallel
        action_item-result = await db.execue(
              select(DBActionItem)
        .where(DBActionItem.meeting_id == meeting_id)
        .order_by(DBActionItem.created_at)
    )
    decisions_result = await db.execute(
        select(Decision).where(Decision.meeting_id == meeting_id)
    )
    participants_result = await db.execute(
        select(Participant).where(Participant.meeting_id == meeting_id)
    )
    notifications_result = await db.execute(
        select(NotificationLog)
        .where(NotificationLog.meeting_id == meeting_id)
        .order_by(NotificationLog.created_at.desc())
    )
 
    action_items  = action_items_result.scalars().all()
    decisions     = decisions_result.scalars().all()
    participants  = participants_result.scalars().all()
    notifications = notifications_result.scalars().all()
 
    return MeetingDetailResponse(
        meeting=MeetingRow.model_validate(meeting),
        action_items=[ActionItemRow.model_validate(i) for i in action_items],
        decisions=[DecisionRow.model_validate(d) for d in decisions],
        participants=[ParticipantRow.model_validate(p) for p in participants],
        notifications=[NotificationLogRow.model_validate(n) for n in notifications],
        

    )
    
    # UPDATE ACTION ITEM STATUS
    
    @router.patch(
        "/meetings/{meeting_id}/action-items/{item_id}",
    response_model=ActionItemRow,
    tags=["meetings"],
)
async def update_action_item(
    meeting_id: str,
    item_id:    str,
    body:       UpdateActionItemRequest,
    db:         AsyncSession = Depends(get_db),
):
    item = await db.get(DBActionItem, item_id)
 
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action item {item_id} not found.",
        )
 
    if item.meeting_id != meeting_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action item does not belong to this meeting.",
        )
 
    item.status = body.status.value
    await db.flush()
 
    logger.info(
        "Action item updated | id: %s | status: %s",
        item_id,
        body.status.value,
    )
 
    return ActionItemRow.model_validate(item)
 
 
# =============================================================================
# DELETE MEETING
# =============================================================================
 
@router.delete("/meetings/{meeting_id}", tags=["meetings"])
async def delete_meeting(
    meeting_id: str,
    db:         AsyncSession = Depends(get_db),
):
    """
    DELETE /api/meetings/{meeting_id}
 
    Deletes a meeting and ALL related data:
    - action_items, decisions, participants, notifications_log
 
    The cascade="all, delete-orphan" on SQLAlchemy relationships
    handles deleting all child rows automatically.
    """
    meeting = await db.get(Meeting, meeting_id)
 
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meeting_id} not found.",
        )
 
    await db.delete(meeting)
    await db.flush()
 
    logger.info("Meeting deleted | id: %s", meeting_id)
 
    return {"deleted": True, "meeting_id": meeting_id}
 
 
# =============================================================================
# MANUAL SEND — EMAIL
# =============================================================================
 
@router.post("/meetings/{meeting_id}/send/email", tags=["send"])
async def manual_send_email(
    meeting_id: str,
    db:         AsyncSession = Depends(get_db),
):
    """
    POST /api/meetings/{meeting_id}/send/email
 
    Sends personalised emails to all participants who have email addresses.
    Called when user clicks "Email Participants" button on the frontend.
 
    Reads participant emails from the database.
    Only participants with a non-null email field receive an email.
    """
    # Fetch meeting + related data
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")
 
    action_items_result = await db.execute(
        select(DBActionItem).where(DBActionItem.meeting_id == meeting_id)
    )
    participants_result = await db.execute(
        select(Participant).where(Participant.meeting_id == meeting_id)
    )
 
    action_items = action_items_result.scalars().all()
    participants = participants_result.scalars().all()
 
    # Build email map — only participants with emails
    participant_emails = {
        p.name: p.email
        for p in participants
        if p.email
    }
 
    if not participant_emails:
        return JSONResponse(
            status_code=200,
            content={
                "sent":    0,
                "failed":  0,
                "message": "No participants have email addresses configured. "
                           "Add emails in the participants settings.",
            },
        )
 
    # Convert DB models to Pydantic for email_tool
    from backend.models.schemas import ActionItem as SchemaActionItem
    schema_items = [
        SchemaActionItem(
            description=i.description,
            owner=i.owner,
            due_date=i.due_date,
            priority=Priority(i.priority),
        )
        for i in action_items
    ]
 
    result = await send_email_for_meeting(
        meeting_id=meeting_id,
        meeting_title=meeting.title,
        short_summary=meeting.short_summary,
        all_action_items=schema_items,
        participant_emails=participant_emails,
    )
 
    return result
 
 
# =============================================================================
# MANUAL SEND — SLACK
# =============================================================================
 
@router.post("/meetings/{meeting_id}/send/slack", tags=["send"])
async def manual_send_slack(
    meeting_id: str,
    db:         AsyncSession = Depends(get_db),
):
    """
    POST /api/meetings/{meeting_id}/send/slack
 
    Posts the meeting summary to the configured Slack channel.
    Called when user clicks "Post to Slack" button.
    """
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")
 
    action_items_result = await db.execute(
        select(DBActionItem).where(DBActionItem.meeting_id == meeting_id)
    )
    participants_result = await db.execute(
        select(Participant).where(Participant.meeting_id == meeting_id)
    )
    decisions_result = await db.execute(
        select(Decision).where(Decision.meeting_id == meeting_id)
    )
 
    action_items = action_items_result.scalars().all()
    participants = participants_result.scalars().all()
    decisions    = decisions_result.scalars().all()
 
    from backend.models.schemas import ActionItem as SchemaActionItem
    schema_items = [
        SchemaActionItem(
            description=i.description,
            owner=i.owner,
            due_date=i.due_date,
            priority=Priority(i.priority),
        )
        for i in action_items
    ]
 
    result = await send_slack_for_meeting(
        meeting_id=meeting_id,
        meeting_title=meeting.title,
        short_summary=meeting.short_summary,
        action_items=schema_items,
        participants=[p.name for p in participants],
        decisions_count=len(decisions),
        duration_minutes=meeting.duration_minutes,
    )
 
    return result
 
 
# =============================================================================
# MANUAL SEND — JIRA
# =============================================================================
 
@router.post("/meetings/{meeting_id}/send/jira", tags=["send"])
async def manual_send_jira(
    meeting_id: str,
    db:         AsyncSession = Depends(get_db),
):
    """
    POST /api/meetings/{meeting_id}/send/jira
 
    Creates Jira tickets for all action items in this meeting.
    Called when user clicks "Create Jira Tickets" button.
    Can be called multiple times — creates new tickets each time.
    """
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")
 
    action_items_result = await db.execute(
        select(DBActionItem).where(DBActionItem.meeting_id == meeting_id)
    )
    action_items = action_items_result.scalars().all()
 
    if not action_items:
        return {"created": [], "failed": [], "message": "No action items found for this meeting."}
 
    from backend.models.schemas import ActionItem as SchemaActionItem
    schema_items = [
        SchemaActionItem(
            description=i.description,
            owner=i.owner,
            due_date=i.due_date,
            priority=Priority(i.priority),
        )
        for i in action_items
    ]
 
    # Run sync Jira tool in thread executor (Jira SDK is synchronous)
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        lambda: asyncio.run(send_jira_for_meeting(meeting_id, schema_items)),
    )
 
    return result
 
 
# =============================================================================
# MANUAL SEND — CALENDAR
# =============================================================================
 
@router.post("/meetings/{meeting_id}/send/calendar", tags=["send"])
async def manual_send_calendar(
    meeting_id:    str,
    days_from_now: int = 7,
    db:            AsyncSession = Depends(get_db),
):
    """
    POST /api/meetings/{meeting_id}/send/calendar?days_from_now=7
 
    Books a Google Calendar follow-up meeting.
    Called when user clicks "Book Follow-up" button.
 
    days_from_now — how many days ahead to schedule (default 7)
    """
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")
 
    participants_result = await db.execute(
        select(Participant).where(Participant.meeting_id == meeting_id)
    )
    participants = participants_result.scalars().all()
 
    participant_names  = [p.name for p in participants]
    participant_emails = [p.email for p in participants if p.email]
 
    result = await send_calendar_for_meeting(
        meeting_id=meeting_id,
        meeting_title=meeting.title,
        participants=participant_names,
        emails=participant_emails,
        days_from_now=days_from_now,
    )
 
    return result
 
 
# =============================================================================
# UPDATE PARTICIPANT EMAIL
# =============================================================================
 
@router.patch("/meetings/{meeting_id}/participants/{participant_id}", tags=["meetings"])
async def update_participant_email(
    meeting_id:     str,
    participant_id: str,
    email:          str,
    db:             AsyncSession = Depends(get_db),
):
    """
    PATCH /api/meetings/{meeting_id}/participants/{participant_id}?email=alice@co.com
 
    Adds or updates the email address for a participant.
    Called from the frontend "Add email" input on the meeting detail page.
 
    This is how participants get email addresses — the AI extracts names
    from the transcript, and the user manually adds the email addresses here.
    """
    participant = await db.get(Participant, participant_id)
 
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found.")
 
    if participant.meeting_id != meeting_id:
        raise HTTPException(status_code=403, detail="Participant does not belong to this meeting.")
 
    participant.email = email
    await db.flush()
 
    logger.info("Participant email updated | id: %s | email: %s", participant_id, email)
 
    return ParticipantRow.model_validate(participant)