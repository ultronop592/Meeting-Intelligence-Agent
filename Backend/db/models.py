import uuid 
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector

def _now() -> datetime:
    """Returns current UTC time. Used as default for created_at columns."""
    return datetime.now(timezone.utc)
 
 
def _uuid() -> str:
    """Generates a new UUID4 string. Used as default for primary keys."""
    return str(uuid.uuid4())
 
 
# All ORM models inherit from Base — SQLAlchemy uses this to track tables
class Base(DeclarativeBase):
    pass
 
 

# TABLE 0 — users


class User(Base):
    __tablename__ = "users"

    id              = Column(String, primary_key=True, default=_uuid)
    email           = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name       = Column(String, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=_now, nullable=False)

    meetings         = relationship("Meeting", back_populates="user", cascade="all, delete-orphan")
    processing_jobs  = relationship("ProcessingJob", back_populates="user")
    chat_sessions    = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    tool_credentials = relationship("UserToolCredential", back_populates="user", cascade="all, delete-orphan")


# TABLE 1 — meetings


class Meeting(Base):
    __tablename__ = "meetings"

    id               = Column(String,  primary_key=True, default=_uuid)
    user_id          = Column(String,  ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    title            = Column(String,  nullable=False)
    audio_filename   = Column(String,  nullable=False)
    audio_storage_key= Column(String(512), nullable=True)
    duration_minutes = Column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_meetings_user_created", "user_id", "created_at"),
    )
    short_summary    = Column(Text,    nullable=False)
    detailed_summary = Column(Text,    nullable=False)
    transcript          = Column(Text, nullable=True)
    diarized_transcript = Column(Text, nullable=True)
    transcript_words    = Column(JSON, nullable=True)

    # Public sharing fields
    share_token            = Column(String(64), unique=True, index=True, nullable=True)
    share_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    is_publicly_shared     = Column(Boolean, default=False, nullable=False)

    # EmbeddingStatus — tracks RAG pipeline: pending → completed/failed
    embedding_status = Column(
        SAEnum("pending", "completed", "failed", name="embeddingstatus"),
        nullable=False,
        default="pending",
    )

    # Vector column for semantic search (1536 dims = OpenAI, 768 = sentence-transformers)
    transcript_embedding = Column(Vector(768), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    # Relationships — SQLAlchemy loads related rows automatically
    user              = relationship("User",            back_populates="meetings")
    action_items      = relationship("ActionItem",      back_populates="meeting", cascade="all, delete-orphan")
    decisions         = relationship("Decision",         back_populates="meeting", cascade="all, delete-orphan")
    participants      = relationship("Participant",      back_populates="meeting", cascade="all, delete-orphan")
    notifications_log = relationship("NotificationLog", back_populates="meeting", cascade="all, delete-orphan")
    chat_sessions     = relationship("ChatSession",     back_populates="meeting", cascade="all, delete-orphan")
    outbox_dispatches = relationship("OutboxDispatch", back_populates="meeting", cascade="all, delete-orphan")
    transcript_chunks = relationship("TranscriptChunk", back_populates="meeting", cascade="all, delete-orphan")

    # Phase 7: The Differentiator relationships
    commitment_links_as_source = relationship(
        "CommitmentLink",
        foreign_keys="CommitmentLink.source_meeting_id",
        back_populates="source_meeting",
        cascade="all, delete-orphan",
    )
    commitment_links_as_target = relationship(
        "CommitmentLink",
        foreign_keys="CommitmentLink.target_meeting_id",
        back_populates="target_meeting",
        cascade="all, delete-orphan",
    )
    decision_contradictions_as_new = relationship(
        "DecisionContradiction",
        foreign_keys="DecisionContradiction.new_meeting_id",
        back_populates="new_meeting",
        cascade="all, delete-orphan",
    )
    decision_contradictions_as_prior = relationship(
        "DecisionContradiction",
        foreign_keys="DecisionContradiction.prior_meeting_id",
        back_populates="prior_meeting",
        cascade="all, delete-orphan",
    )


# TABLE 2 — action_items
 
class ActionItem(Base):
    __tablename__ = "action_items"
 
    id          = Column(String,  primary_key=True, default=_uuid)
    meeting_id  = Column(String,  ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text,    nullable=False)
    owner       = Column(String,  nullable=False)
    due_date    = Column(String,  nullable=False)   # Stored as "YYYY-MM-DD" string
 
    priority = Column(
        SAEnum("high", "medium", "low", name="priority"),
        nullable=False,
        default="medium",
    )
 
    jira_ticket_id = Column(String, nullable=True)   # Filled by Node 5
 
    status = Column(
        SAEnum("open", "in_progress", "done", name="actionitemstatus"),
        nullable=False,
        default="open",
    )

    # Phase 2: Evidence, Verification & Confidence fields
    evidence_quote         = Column(Text, nullable=True)
    evidence_timestamp     = Column(String(32), nullable=True)
    confidence             = Column(Float, nullable=False, default=1.0)
    needs_review           = Column(Boolean, nullable=False, default=False)
    owner_status           = Column(String(32), nullable=False, default="stated")
    verification_reasoning = Column(Text, nullable=True)

    # Phase 7: Cross-Meeting Commitment Tracking
    is_repeated_commitment    = Column(Boolean, nullable=False, default=False)
    repeated_from_meeting_id  = Column(String, nullable=True)
    days_unresolved           = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        Index("ix_action_items_meeting_status", "meeting_id", "status"),
        Index("ix_action_items_due_date", "due_date"),
        Index("ix_action_items_needs_review", "meeting_id", "needs_review"),
        Index("ix_action_items_repeated", "is_repeated_commitment"),
    )

    meeting = relationship("Meeting", back_populates="action_items")
    outgoing_commitment_links = relationship(
        "CommitmentLink",
        foreign_keys="CommitmentLink.source_action_item_id",
        back_populates="source_action_item",
        cascade="all, delete-orphan",
    )
    incoming_commitment_links = relationship(
        "CommitmentLink",
        foreign_keys="CommitmentLink.target_action_item_id",
        back_populates="target_action_item",
        cascade="all, delete-orphan",
    )
 

# TABLE 3 — decisions

 
class Decision(Base):
    __tablename__ = "decisions"
 
    id          = Column(String, primary_key=True, default=_uuid)
    meeting_id  = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(Text,   nullable=False)
    context     = Column(Text,   nullable=False)

    # Phase 2: Evidence, Verification & Confidence fields
    evidence_quote         = Column(Text, nullable=True)
    evidence_timestamp     = Column(String(32), nullable=True)
    confidence             = Column(Float, nullable=False, default=1.0)
    needs_review           = Column(Boolean, nullable=False, default=False)
    verification_reasoning = Column(Text, nullable=True)

    # Phase 7: Decision Contradiction Detection
    has_contradiction         = Column(Boolean, nullable=False, default=False)
    contradiction_count       = Column(Integer, nullable=False, default=0)

    created_at  = Column(DateTime(timezone=True), default=_now, nullable=False)
 
    meeting = relationship("Meeting", back_populates="decisions")
    outgoing_contradictions   = relationship(
        "DecisionContradiction",
        foreign_keys="DecisionContradiction.new_decision_id",
        back_populates="new_decision",
        cascade="all, delete-orphan",
    )
    incoming_contradictions   = relationship(
        "DecisionContradiction",
        foreign_keys="DecisionContradiction.prior_decision_id",
        back_populates="prior_decision",
        cascade="all, delete-orphan",
    )
 


# TABLE 4 — participants

 
class Participant(Base):
    __tablename__ = "participants"
 
    id            = Column(String, primary_key=True, default=_uuid)
    meeting_id    = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    name          = Column(String, nullable=False)
    email         = Column(String, nullable=True)   # Optional — may be resolved later
    speaker_label = Column(String, nullable=True)   # e.g. "SPEAKER_00" for diarization mapping
    created_at    = Column(DateTime(timezone=True), default=_now, nullable=False)
 
    meeting = relationship("Meeting", back_populates="participants")
 
 
# TABLE 5 — notifications_log

 
class NotificationLog(Base):
    __tablename__ = "notifications_log"
 
    id         = Column(String, primary_key=True, default=_uuid)
    meeting_id = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
 
    type = Column(
        SAEnum("slack", "email", "jira", "calendar", name="notificationtype"),
        nullable=False,
    )
    status = Column(
        SAEnum("pending", "sent", "failed", name="notificationstatus"),
        nullable=False,
        default="pending",
    )
 
    detail     = Column(Text,   nullable=True)   # e.g. Jira ticket URL, error message
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
 
    meeting = relationship("Meeting", back_populates="notifications_log")


# TABLE 6 — processing_jobs


class ProcessingJob(Base):
    """Persists background meeting-processing job state so it survives
    server restarts and is visible across multiple worker processes."""

    __tablename__ = "processing_jobs"

    id = Column(String, primary_key=True, default=_uuid)

    status = Column(
        SAEnum("processing", "completed", "failed", name="jobstatus"),
        nullable=False,
        default="processing",
    )

    user_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    meeting_id = Column(
        String, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True
    )

    user = relationship("User", back_populates="processing_jobs")

    # Lists stored as JSON arrays
    completed_nodes = Column(JSON, nullable=False, default=list)
    errors          = Column(JSON, nullable=False, default=list)
    node_timings    = Column(JSON, nullable=False, default=dict)

    # Summary fields populated on completion
    title               = Column(String,  nullable=True)
    short_summary       = Column(Text,    nullable=True)
    action_items_count  = Column(Integer, nullable=True)
    decisions_count     = Column(Integer, nullable=True)
    participants_count  = Column(Integer, nullable=True)
    jira_tickets_created= Column(Integer, nullable=True)
    calendar_event_id   = Column(String,  nullable=True)
    notifications_sent  = Column(Integer, nullable=True)
    duration_ms         = Column(Integer, nullable=True)

    # Phase 3 Durable Runtime fields
    checkpoint_state = Column(JSON, nullable=True)
    last_heartbeat   = Column(DateTime(timezone=True), nullable=True)
    worker_id        = Column(String(128), nullable=True)
    retry_count      = Column(Integer, nullable=False, default=0)

    started_at   = Column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


# TABLE 7 — chat_sessions


class ChatSession(Base):
    """Persists multi-turn conversation sessions between user and the Meeting Intelligence Agent."""

    __tablename__ = "chat_sessions"

    id         = Column(String, primary_key=True, default=_uuid)
    user_id    = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    meeting_id = Column(String, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True)
    title      = Column(String, nullable=False, default="New Conversation")
    messages   = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    user    = relationship("User",    back_populates="chat_sessions")
    meeting = relationship("Meeting", back_populates="chat_sessions")


# TABLE 8 — user_tool_credentials


class UserToolCredential(Base):
    """Stores user-specific external tool credentials (Jira, Slack, Email, Calendar)."""

    __tablename__ = "user_tool_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "tool_name", name="uq_user_tool"),
    )

    id          = Column(String, primary_key=True, default=_uuid)
    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name   = Column(String, nullable=False, index=True)  # "jira", "slack", "email", "calendar"
    credentials = Column(JSON, nullable=False, default=dict)
    is_active   = Column(Boolean, nullable=False, default=True)

    created_at  = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at  = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    user        = relationship("User", back_populates="tool_credentials")


# TABLE 9 — outbox_dispatches


class OutboxDispatch(Base):
    """Guarantees effectively exactly-once delivery to external channels
    (Jira, Slack, Email, Calendar) via idempotency keys and transactional outbox.
    """

    __tablename__ = "outbox_dispatches"
    __table_args__ = (
        Index("ix_outbox_dispatches_meeting_status", "meeting_id", "status"),
    )

    id              = Column(String, primary_key=True, default=_uuid)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    meeting_id      = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id         = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    channel         = Column(String(32), nullable=False, index=True)  # "jira", "slack", "email", "calendar"
    status          = Column(
        SAEnum("pending", "sent", "failed", name="outboxstatus"),
        nullable=False,
        default="pending",
        index=True,
    )
    payload         = Column(JSON, nullable=True)
    external_id     = Column(String(255), nullable=True)
    retry_count     = Column(Integer, nullable=False, default=0)
    last_error      = Column(Text, nullable=True)

    created_at      = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at      = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    meeting = relationship("Meeting", back_populates="outbox_dispatches")
    user    = relationship("User")


# TABLE — audit_logs (Phase 4: Security & Safety)

class AuditLog(Base):
    """Append-only record of every external write attempt.

    Records who approved what dispatch, on which channel, with what outcome.
    Policy-blocked events are captured with the violated rule name so operators
    can correlate injection attempts with pipeline runs.
    """
    __tablename__ = "audit_logs"

    id             = Column(String, primary_key=True, default=_uuid)
    user_id        = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    job_id         = Column(String, nullable=True, index=True)   # processing job that triggered the dispatch
    channel        = Column(String(32),  nullable=False, index=True)  # "jira" | "slack" | "email" | "calendar" | "system"
    outcome        = Column(String(32),  nullable=False, index=True)  # "success" | "policy_blocked" | "error" | "skipped"
    entity_summary = Column(String(1024), nullable=False)             # human-readable description of what was dispatched
    policy_rule    = Column(String(128), nullable=True)               # policy rule name when outcome == "policy_blocked"
    extra          = Column(JSON, nullable=True)                      # arbitrary metadata (recipients, ticket key, etc.)
    created_at     = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)

    __table_args__ = (
        Index("ix_audit_logs_user_created",    "user_id",  "created_at"),
        Index("ix_audit_logs_job_channel",     "job_id",   "channel"),
        Index("ix_audit_logs_outcome_created", "outcome",  "created_at"),
    )

    user = relationship("User")


# TABLE — transcript_chunks (Phase 6: Retrieval Upgrade)

class TranscriptChunk(Base):
    """A 30-60 second window of a meeting transcript for chunk-level RAG retrieval.

    Each chunk stores speaker metadata, start/end timestamps, plain text, and a
    768-dim pgvector embedding. Enables timestamp-cited answers instead of 60k
    full-transcript stuffing.
    """
    __tablename__ = "transcript_chunks"

    id          = Column(String,  primary_key=True, default=_uuid)
    meeting_id  = Column(String,  ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)       # 0-based position within the meeting
    start_sec   = Column(Float,   nullable=False)       # seconds from audio start
    end_sec     = Column(Float,   nullable=False)       # seconds from audio start
    speaker     = Column(String(128), nullable=True)   # dominant speaker label e.g. "SPEAKER_01"
    text        = Column(Text,    nullable=False)       # verbatim transcript text of this window
    embedding   = Column(Vector(768), nullable=True)   # dense semantic vector

    created_at  = Column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        Index("ix_transcript_chunks_meeting_idx",   "meeting_id", "chunk_index"),
        Index("ix_transcript_chunks_meeting_time",  "meeting_id", "start_sec"),
    )

    meeting = relationship("Meeting", back_populates="transcript_chunks")


# TABLE 10 — commitment_links (Phase 7: The Differentiator)

class CommitmentLink(Base):
    """Tracks commitments across meetings.
    
    Detects when an action item raised in meeting B is the same task promised in
    meeting A, tracks aging/stale commitments, and flags 'Promised X weeks ago,
    raised again, still not done.'
    """
    __tablename__ = "commitment_links"

    id                    = Column(String, primary_key=True, default=_uuid)
    source_action_item_id = Column(String, ForeignKey("action_items.id", ondelete="CASCADE"), nullable=False, index=True)
    target_action_item_id = Column(String, ForeignKey("action_items.id", ondelete="CASCADE"), nullable=False, index=True)
    source_meeting_id     = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    target_meeting_id     = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    
    link_type             = Column(String(64), nullable=False, default="repeated_commitment")
    confidence            = Column(Float, nullable=False, default=1.0)
    similarity_score      = Column(Float, nullable=False, default=0.0)
    days_unresolved       = Column(Integer, nullable=False, default=0)
    status                = Column(String(32), nullable=False, default="open")  # open, in_progress, overdue, resolved
    explanation           = Column(Text, nullable=False)

    created_at            = Column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        Index("ix_commitment_links_pair", "source_action_item_id", "target_action_item_id"),
        Index("ix_commitment_links_meetings", "source_meeting_id", "target_meeting_id"),
        Index("ix_commitment_links_status", "status"),
    )

    source_action_item = relationship("ActionItem", foreign_keys=[source_action_item_id], back_populates="outgoing_commitment_links")
    target_action_item = relationship("ActionItem", foreign_keys=[target_action_item_id], back_populates="incoming_commitment_links")
    source_meeting     = relationship("Meeting", foreign_keys=[source_meeting_id], back_populates="commitment_links_as_source")
    target_meeting     = relationship("Meeting", foreign_keys=[target_meeting_id], back_populates="commitment_links_as_target")


# TABLE 11 — decision_contradictions (Phase 7: The Differentiator)

class DecisionContradiction(Base):
    """Tracks contradictions and conflicts between decisions across meetings.

    Detects when a new architectural or business decision conflicts with an earlier
    decision and provides conflict rationale and resolution tracking.
    """
    __tablename__ = "decision_contradictions"

    id                  = Column(String, primary_key=True, default=_uuid)
    new_decision_id     = Column(String, ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False, index=True)
    prior_decision_id   = Column(String, ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False, index=True)
    new_meeting_id      = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    prior_meeting_id    = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)

    contradiction_score = Column(Float, nullable=False, default=0.0)
    summary             = Column(Text, nullable=False)
    resolution_status   = Column(String(32), nullable=False, default="detected")  # detected, acknowledged, overruled, dismissed

    created_at          = Column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        Index("ix_decision_contradictions_pair", "new_decision_id", "prior_decision_id"),
        Index("ix_decision_contradictions_status", "resolution_status"),
    )

    new_decision   = relationship("Decision", foreign_keys=[new_decision_id], back_populates="outgoing_contradictions")
    prior_decision = relationship("Decision", foreign_keys=[prior_decision_id], back_populates="incoming_contradictions")
    new_meeting    = relationship("Meeting", foreign_keys=[new_meeting_id], back_populates="decision_contradictions_as_new")
    prior_meeting  = relationship("Meeting", foreign_keys=[prior_meeting_id], back_populates="decision_contradictions_as_prior")
