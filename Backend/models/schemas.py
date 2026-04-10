from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional 
from pydantic import BaseModel, Field, field_validator

# ENUMS

class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    
class NotificationType(str,Enum):
    SLACK = "slack"
    EMAIL    = "email"
    JIRA     = "jira"
    CALENDAR = "calendar"
 
 
class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT    = "sent"
    FAILED  = "failed"
 
 
class ActionItemStatus(str, Enum):
    OPEN        = "open"
    IN_PROGRESS = "in_progress"
    DONE        = "done"
 
 
class EmbeddingStatus(str, Enum):
    """Tracks whether a meeting transcript has been embedded for RAG search."""
    PENDING   = "pending"
    COMPLETED = "completed"
    FAILED    = "failed"
 
 
# =============================================================================
# 2. LLM OUTPUT MODELS (structured output demanded from Groq)
# =============================================================================
 
class ActionItem(BaseModel):
    """A single task extracted from the meeting transcript."""
    description: str      = Field(..., min_length=5, description="Actionable task starting with a verb.")
    owner:       str      = Field(..., description="Full name of the responsible person.")
    due_date:    str      = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="ISO-8601 date YYYY-MM-DD.")
    priority:    Priority = Field(default=Priority.medium)
 
    @field_validator("owner")
    @classmethod
    def owner_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("owner must not be blank.")
        return v.strip()
 
 
class Decision(BaseModel):
    """A key decision reached during the meeting."""
    description: str = Field(..., min_length=5)
    context:     str = Field(..., description="Why this decision was made.")
 
 
class ExtractionOutput(BaseModel):
    """Full structured output from Node 2 — extract_information."""
    action_items: list[ActionItem] = Field(default_factory=list)
    decisions:    list[Decision]   = Field(default_factory=list)
    participants: list[str]        = Field(default_factory=list)
    key_topics:   list[str]        = Field(default_factory=list)
 
 
class MeetingSummary(BaseModel):
    """Structured summary produced by Node 3 — generate_summary."""
    title:            str = Field(..., min_length=3)
    short_summary:    str = Field(..., description="2-3 sentence executive summary.")
    detailed_summary: str = Field(..., description="Full paragraph narrative.")
    duration_minutes: int = Field(..., gt=0)
 
 
# =============================================================================
# 3. LANGGRAPH AGENT STATE
# =============================================================================
 
class AgentState(BaseModel):
    """
    Shared mutable state that flows through all 7 LangGraph nodes.
 
    Each node:
      1. Receives the full state
      2. Does its work
      3. Returns ONLY the fields it changed (dict)
    LangGraph merges those changes back into the shared state automatically.
 
    NODE → FIELD MAPPING
    ┌──────────────────────────┬───────────────────────────────┐
    │ Node                     │ Populates                     │
    ├──────────────────────────┼───────────────────────────────┤
    │ 1  transcribe_audio      │ transcript                    │
    │ 2  extract_information   │ extraction                    │
    │ 3  generate_summary      │ summary                       │
    │ 4  save_to_database      │ meeting_id                    │
    │ 5  create_jira_tickets   │ jira_ticket_ids               │
    │ 6  book_calendar         │ calendar_event_id             │
    │ 7  send_notifications    │ notification_results          │
    └──────────────────────────┴───────────────────────────────┘
    """
 
    # --- Input (set before graph starts) -------------------------------------
    audio_file_path: Optional[str] = None
    audio_filename:  Optional[str] = None
 
    # --- Node outputs --------------------------------------------------------
    transcript:           Optional[str]              = None
    extraction:           Optional[ExtractionOutput] = None
    summary:              Optional[MeetingSummary]   = None
    meeting_id:           Optional[str]              = None
    jira_ticket_ids:      list[str]                  = Field(default_factory=list)
    calendar_event_id:    Optional[str]              = None
    notification_results: list[dict]                 = Field(default_factory=list)
 
    # --- RAG pipeline --------------------------------------------------------
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
 
    # --- Runtime metadata ----------------------------------------------------
    errors:          list[str] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
 
    class Config:
        arbitrary_types_allowed = True
 
 
# =============================================================================
# 4. DATABASE ROW MODELS (mirror SQLAlchemy ORM columns in db/models.py)
# =============================================================================
 
class MeetingRow(BaseModel):
    id:               Optional[str]       = None
    title:            str
    audio_filename:   str
    duration_minutes: int
    short_summary:    str
    detailed_summary: str
    embedding_status: EmbeddingStatus     = EmbeddingStatus.PENDING
    created_at:       Optional[datetime]  = None
 
    class Config:
        from_attributes = True   # Allows building from SQLAlchemy ORM objects
 
 
class ActionItemRow(BaseModel):
    id:             Optional[str]    = None
    meeting_id:     str
    description:    str
    owner:          str
    due_date:       str
    priority:       Priority
    jira_ticket_id: Optional[str]    = None
    status:         ActionItemStatus = ActionItemStatus.OPEN
 
    class Config:
        from_attributes = True
 
 
class DecisionRow(BaseModel):
    id:          Optional[str] = None
    meeting_id:  str
    description: str
    context:     str
 
    class Config:
        from_attributes = True
 
 
class ParticipantRow(BaseModel):
    id:         Optional[str] = None
    meeting_id: str
    name:       str
    email:      Optional[str] = None
 
    class Config:
        from_attributes = True
 
 
class NotificationLogRow(BaseModel):
    id:         Optional[str]      = None
    meeting_id: str
    type:       NotificationType
    status:     NotificationStatus
    detail:     Optional[str]      = None
    created_at: Optional[datetime] = None
 
    class Config:
        from_attributes = True
 
 
# =============================================================================
# 5. API REQUEST / RESPONSE MODELS
# =============================================================================
 
class ProcessMeetingRequest(BaseModel):
    """POST /api/meetings/process"""
    audio_file_path: str = Field(..., examples=["/tmp/uploads/standup.mp3"])
    audio_filename:  str = Field(..., examples=["standup.mp3"])
 
 
class ProcessMeetingResponse(BaseModel):
    """Response from POST /api/meetings/process"""
    meeting_id:           str
    title:                str
    short_summary:        str
    action_items_count:   int
    decisions_count:      int
    participants_count:   int
    jira_tickets_created: int
    calendar_event_id:    Optional[str]
    notifications_sent:   int
    errors:               list[str] = Field(default_factory=list)
 
 
class MeetingDetailResponse(BaseModel):
    """GET /api/meetings/{id}"""
    meeting:       MeetingRow
    action_items:  list[ActionItemRow]
    decisions:     list[DecisionRow]
    participants:  list[ParticipantRow]
    notifications: list[NotificationLogRow]
 
 
class MeetingListItem(BaseModel):
    """Single item in GET /api/meetings list"""
    id:                 str
    title:              str
    audio_filename:     str
    duration_minutes:   int
    short_summary:      str
    action_items_count: int
    created_at:         Optional[datetime] = None
 
 
class UpdateActionItemRequest(BaseModel):
    """PATCH /api/meetings/{id}/action-items/{item_id}"""
    status: ActionItemStatus
 
 
class HealthResponse(BaseModel):
    """GET /health"""
    status:   str = "ok"
    version:  str = "2.0.0"
    database: str = "neon"


class AgentQueryRequest(BaseModel):
    """POST /query"""
    question: str = Field(..., min_length=1)
    meeting_id: Optional[str] = None


class AgentQueryResponse(BaseModel):
    """Response from POST /query"""
    answer: str
    sources: list[str] = Field(default_factory=list)