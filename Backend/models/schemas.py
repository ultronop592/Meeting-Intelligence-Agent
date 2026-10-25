from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional 
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


class OutboxChannel(str, Enum):
    JIRA     = "jira"
    SLACK    = "slack"
    EMAIL    = "email"
    CALENDAR = "calendar"


class OutboxStatus(str, Enum):
    PENDING = "pending"
    SENT    = "sent"
    FAILED  = "failed"
 
 
# =============================================================================
# 2. LLM OUTPUT MODELS (structured output demanded from Groq)
# =============================================================================
 
class ActionItem(BaseModel):
    """A single task extracted from the meeting transcript."""
    description: str           = Field(..., min_length=5, description="Actionable task starting with a verb.")
    owner:       str           = Field(..., description="Full name of the responsible person or 'Unassigned'.")
    due_date:    Optional[str] = Field(default="unspecified", description="ISO-8601 date YYYY-MM-DD or 'unspecified'.")
    priority:    Priority      = Field(default=Priority.medium)

    # Phase 2 Verification & Grounding fields
    evidence_quote:         Optional[str] = Field(default=None, description="Exact verbatim quote from the transcript supporting this task.")
    evidence_timestamp:     Optional[str] = Field(default=None, description="Timestamp or time span of the evidence in the meeting.")
    confidence:             float         = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")
    needs_review:           bool          = Field(default=False, description="Flagged for human review if ambiguous or unverified.")
    owner_status:           str           = Field(default="stated", description="Status of owner: 'stated', 'inferred', or 'unassigned'.")
    verification_reasoning: Optional[str] = Field(default=None, description="Explanation for verification or ambiguity decision.")

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

    # Phase 2 Verification & Grounding fields
    evidence_quote:         Optional[str] = Field(default=None, description="Exact verbatim quote from the transcript supporting this decision.")
    evidence_timestamp:     Optional[str] = Field(default=None, description="Timestamp or time span of the evidence.")
    confidence:             float         = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")
    needs_review:           bool          = Field(default=False, description="Flagged for human review if ambiguous or unverified.")
    verification_reasoning: Optional[str] = Field(default=None, description="Explanation for verification decision.")
 
 
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
    audio_file_path:   Optional[str] = None
    audio_filename:    Optional[str] = None
    audio_storage_key: Optional[str] = None
    user_id:           Optional[str] = None
    job_id:            Optional[str] = None

    # --- Node outputs --------------------------------------------------------
    transcript:           Optional[str]              = None
    # Speaker-labelled version of the transcript, e.g.:
    #   "SPEAKER_00: Hello everyone.\nSPEAKER_01: Let's start with updates."
    # Only populated when diarization is enabled and HF_TOKEN is configured.
    diarized_transcript:  Optional[str]              = None
    # Raw diarization segments: [{"speaker": "SPEAKER_00", "start": 0.0, "end": 5.2}, ...]
    speaker_segments:     list[dict]                 = Field(default_factory=list)
    # Word-level Whisper timestamps: [{"word": "Hello", "start": 0.24, "end": 0.68, "speaker": "SPEAKER_00"}, ...]
    transcript_words:     list[dict]                 = Field(default_factory=list)
    extraction:           Optional[ExtractionOutput] = None
    summary:              Optional[MeetingSummary]   = None
    meeting_id:           Optional[str]              = None
    jira_ticket_ids:      list[str]                  = Field(default_factory=list)
    calendar_event_id:    Optional[str]              = None
    notification_results: list[dict]                 = Field(default_factory=list)
 
    # --- RAG pipeline --------------------------------------------------------
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
 
    # --- Runtime metadata ----------------------------------------------------
    errors:          list[str]        = Field(default_factory=list)
    completed_nodes: list[str]        = Field(default_factory=list)
    # Per-node wall-clock timings in milliseconds, e.g. {"transcribe_audio": 12340}
    node_timings:    dict[str, float] = Field(default_factory=dict)
    # Tracks the last Groq model selected by LLMRouter (e.g. "llama-3.1-8b-instant").
    # Updated by extraction and summary nodes on each run.
    llm_model_used:  Optional[str] = None

    # --- Phase 2 Verification Metadata ---------------------------------------
    verification_summary:     Optional[dict] = Field(default=None, description="Summary stats from the verification node.")
    verification_retry_count: int            = Field(default=0, description="Number of feedback retry attempts.")

    # --- Phase 3 Durable Runtime Checkpoints ---------------------------------
    checkpoint_state:         Optional[dict[str, Any]] = Field(default=None, description="Persisted intermediate state for recovery.")
    resumed_from_checkpoint:  bool                     = Field(default=False, description="Flag indicating pipeline resumed from saved checkpoint.")

    class Config:
        arbitrary_types_allowed = True
 
 
# =============================================================================
# 4. DATABASE ROW MODELS (mirror SQLAlchemy ORM columns in db/models.py)
# =============================================================================

class UserRegister(BaseModel):
    email:     str = Field(..., description="User email address")
    password:  str = Field(..., min_length=6, description="Raw password (at least 6 chars)")
    full_name: Optional[str] = Field(None, description="User full name")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v:
            raise ValueError("Invalid email format.")
        return v


class UserLogin(BaseModel):
    email:    str
    password: str


class UserResponse(BaseModel):
    id:         str
    email:      str
    full_name:  Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserResponse
 
class MeetingRow(BaseModel):
    id:               Optional[str]       = None
    user_id:          Optional[str]       = None
    title:            str
    audio_filename:   str
    audio_storage_key:Optional[str]       = None
    duration_minutes: int
    short_summary:    str
    detailed_summary: str
    transcript:          Optional[str]       = None
    diarized_transcript: Optional[str]       = None
    transcript_words:    Optional[list[dict]]= None
    share_token:            Optional[str]       = None
    share_token_expires_at: Optional[datetime]  = None
    is_publicly_shared:     bool                = False
    embedding_status: EmbeddingStatus     = EmbeddingStatus.PENDING
    created_at:       Optional[datetime]  = None
 
    class Config:
        from_attributes = True   # Allows building from SQLAlchemy ORM objects
 
 
class ActionItemRow(BaseModel):
    id:                     Optional[str]    = None
    meeting_id:             str
    description:            str
    owner:                  str
    due_date:               str
    priority:               Priority
    jira_ticket_id:         Optional[str]    = None
    status:                 ActionItemStatus = ActionItemStatus.OPEN
    evidence_quote:         Optional[str]    = None
    evidence_timestamp:     Optional[str]    = None
    confidence:             float            = 1.0
    needs_review:           bool             = False
    owner_status:           str              = "stated"
    verification_reasoning: Optional[str]    = None
 
    class Config:
        from_attributes = True
 
 
class DecisionRow(BaseModel):
    id:                     Optional[str] = None
    meeting_id:             str
    description:            str
    context:                str
    evidence_quote:         Optional[str] = None
    evidence_timestamp:     Optional[str] = None
    confidence:             float         = 1.0
    needs_review:           bool          = False
    verification_reasoning: Optional[str] = None
 
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


class OutboxDispatchRow(BaseModel):
    id:              Optional[str]             = None
    idempotency_key: str
    meeting_id:      str
    user_id:         Optional[str]             = None
    channel:         str
    status:          OutboxStatus              = OutboxStatus.PENDING
    payload:         Optional[dict[str, Any]]  = None
    external_id:     Optional[str]             = None
    retry_count:     int                       = 0
    last_error:      Optional[str]             = None
    created_at:      Optional[datetime]        = None
    updated_at:      Optional[datetime]        = None

    class Config:
        from_attributes = True
 
 
# =============================================================================
# 5. API REQUEST / RESPONSE MODELS
# =============================================================================
 
class PresignedUploadRequest(BaseModel):
    """POST /meeting/presigned-upload-url"""
    filename: str = Field(..., examples=["standup.mp3"])
    content_type: Optional[str] = Field(default=None, examples=["audio/mpeg"])


class PresignedUploadResponse(BaseModel):
    """Response from POST /meeting/presigned-upload-url"""
    direct_upload_available: bool
    presigned_url: Optional[str] = None
    storage_key: Optional[str] = None
    content_type: Optional[str] = None


class ResumableUploadTokenRequest(BaseModel):
    """POST /meeting/resumable-upload-token"""
    filename: str = Field(..., examples=["standup.mp3"])
    content_type: Optional[str] = Field(default=None, examples=["audio/mpeg"])


class ResumableUploadTokenResponse(BaseModel):
    """Response from POST /meeting/resumable-upload-token.

    Allows the browser to upload directly to Supabase Storage using the
    TUS resumable-upload protocol (tus-js-client).  The client uses:
      - tus_endpoint: POST target for starting/resuming a TUS upload
      - auth_token: Bearer token for the Authorization header
      - storage_key: the object path inside the bucket (pass to /meetings/process)
      - bucket_name: Supabase bucket name (for x-upsert / metadata)
    """
    resumable_upload_available: bool
    tus_endpoint: Optional[str] = None
    auth_token: Optional[str] = None
    storage_key: Optional[str] = None
    bucket_name: Optional[str] = None
    content_type: Optional[str] = None


class ProcessMeetingRequest(BaseModel):
    """POST /api/meetings/process"""
    audio_file_path: Optional[str] = Field(default=None, examples=["/tmp/uploads/standup.mp3"])
    audio_filename:  str = Field(..., examples=["standup.mp3"])
    storage_key:     Optional[str] = Field(default=None, examples=["audio/user1/standup.mp3"])
 
 
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


class ShareLinkCreateRequest(BaseModel):
    """POST /meetings/{id}/share"""
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class ShareLinkResponse(BaseModel):
    """Response for share link generation/retrieval"""
    meeting_id: str
    share_token: Optional[str] = None
    share_url: Optional[str] = None
    is_publicly_shared: bool = False
    expires_at: Optional[datetime] = None


class PublicMeetingResponse(BaseModel):
    """GET /public/share/{token} - Sanitized unauthenticated view"""
    title:               str
    audio_filename:      str
    duration_minutes:    int
    short_summary:       str
    detailed_summary:    str
    transcript:          Optional[str]        = None
    diarized_transcript: Optional[str]        = None
    transcript_words:    Optional[list[dict]] = None
    action_items:        list[ActionItemRow]  = Field(default_factory=list)
    decisions:           list[DecisionRow]    = Field(default_factory=list)
    participants:        list[ParticipantRow] = Field(default_factory=list)
    created_at:          Optional[datetime]   = None
    audio_stream_url:    Optional[str]        = None
    expires_at:          Optional[datetime]   = None
    is_expired:          bool                 = False
 
 
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


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text")


class AgentQueryRequest(BaseModel):
    """POST /query and POST /query/stream"""
    question: str = Field(..., min_length=1)
    meeting_id: Optional[str] = None
    session_id: Optional[str] = None
    history: Optional[list[ChatMessage]] = Field(default_factory=list)


class AgentQueryResponse(BaseModel):
    """Response from POST /query"""
    answer: str
    sources: list[str] = Field(default_factory=list)
    session_id: Optional[str] = None


class ChatMessageDetail(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    sources: Optional[list[str]] = None


class ChatSessionListItem(BaseModel):
    id: str
    title: str
    meeting_id: Optional[str] = None
    meeting_title: Optional[str] = None
    message_count: int = 0
    preview: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatSessionDetail(BaseModel):
    id: str
    title: str
    meeting_id: Optional[str] = None
    messages: list[ChatMessageDetail] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreateChatSessionRequest(BaseModel):
    meeting_id: Optional[str] = None
    title: Optional[str] = None


class MemorySearchRequest(BaseModel):
    """POST /memory/search"""
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)


class MemorySearchResponse(BaseModel):
    """Response from POST /memory/search"""
    query: str
    results_count: int
    matches: list[dict] = Field(default_factory=list)


# =============================================================================
# 6. ANALYTICS MODELS
# =============================================================================

class PeriodStats(BaseModel):
    meetings_count: int = 0
    action_items_count: int = 0
    completed_action_items: int = 0
    completion_rate: float = 0.0


class AnalyticsSummaryResponse(BaseModel):
    total_meetings: int = 0
    avg_duration_minutes: float = 0.0
    total_action_items: int = 0
    completed_action_items: int = 0
    completion_rate: float = 0.0
    last_7_days: PeriodStats = Field(default_factory=PeriodStats)
    last_30_days: PeriodStats = Field(default_factory=PeriodStats)


class ParticipantAnalyticsItem(BaseModel):
    name: str
    meetings_count: int = 0
    action_items_count: int = 0
    completed_action_items: int = 0


class AnalyticsParticipantsResponse(BaseModel):
    participants: list[ParticipantAnalyticsItem] = Field(default_factory=list)


class TimelineDataPoint(BaseModel):
    period: str
    label: str
    meetings_count: int = 0
    action_items_count: int = 0
    completed_action_items: int = 0
    avg_duration_minutes: float = 0.0


class AnalyticsTimelineResponse(BaseModel):
    period_type: str = "monthly"
    timeline: list[TimelineDataPoint] = Field(default_factory=list)


class ActionItemOwnerBreakdown(BaseModel):
    owner: str
    open: int = 0
    in_progress: int = 0
    done: int = 0
    overdue: int = 0
    total: int = 0


class AnalyticsActionItemsResponse(BaseModel):
    total_open: int = 0
    total_in_progress: int = 0
    total_done: int = 0
    total_overdue: int = 0
    by_owner: list[ActionItemOwnerBreakdown] = Field(default_factory=list)


class TopicKeywordItem(BaseModel):
    topic: str
    count: int = 1


class AnalyticsTopicsResponse(BaseModel):
    topics: list[TopicKeywordItem] = Field(default_factory=list)


class DispatchMeetingRequest(BaseModel):
    channels: list[str] = Field(default_factory=lambda: ["slack", "jira", "calendar"])
    days_from_now: int = Field(default=7, ge=1, le=365)


class DispatchMeetingResponse(BaseModel):
    meeting_id: str
    results: dict[str, Any] = Field(default_factory=dict)


class LiveTranscriptionChunkResponse(BaseModel):
    """Real-time live audio chunk transcription feedback."""
    text: str = Field(default="", description="Transcribed text for this audio chunk.")
    is_final: bool = Field(default=True, description="Whether this chunk transcription is finalized.")
    chunk_size_bytes: int = Field(default=0, description="Size of uploaded audio chunk in bytes.")

