import uuid 
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
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
 
 

# TABLE 1 — meetings

 
class Meeting(Base):
    __tablename__ = "meetings"
 
    id               = Column(String,  primary_key=True, default=_uuid)
    title            = Column(String,  nullable=False)
    audio_filename   = Column(String,  nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    short_summary    = Column(Text,    nullable=False)
    detailed_summary = Column(Text,    nullable=False)
 
    # EmbeddingStatus — tracks RAG pipeline: pending → completed/failed
    # SAEnum maps the Python string values directly to a Postgres ENUM type
    embedding_status = Column(
        SAEnum("pending", "completed", "failed", name="embeddingstatus"),
        nullable=False,
        default="pending",
    )
 
    # Vector column for semantic search (1536 dims = OpenAI, 768 = sentence-transformers)
    # Stored here so you can search across all meetings: "what did we decide about auth?"
    transcript_embedding = Column(Vector(768), nullable=True)
 
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
 
    # Relationships — SQLAlchemy loads related rows automatically
    # cascade="all, delete-orphan" means: deleting a meeting deletes all its children
    action_items      = relationship("ActionItem",      back_populates="meeting", cascade="all, delete-orphan")
    decisions         = relationship("Decision",         back_populates="meeting", cascade="all, delete-orphan")
    participants      = relationship("Participant",      back_populates="meeting", cascade="all, delete-orphan")
    notifications_log = relationship("NotificationLog", back_populates="meeting", cascade="all, delete-orphan")
 
 

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
 
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
 
    meeting = relationship("Meeting", back_populates="action_items")
 

# TABLE 3 — decisions

 
class Decision(Base):
    __tablename__ = "decisions"
 
    id          = Column(String, primary_key=True, default=_uuid)
    meeting_id  = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text,   nullable=False)
    context     = Column(Text,   nullable=False)
    created_at  = Column(DateTime(timezone=True), default=_now, nullable=False)
 
    meeting = relationship("Meeting", back_populates="decisions")
 
 

# TABLE 4 — participants

 
class Participant(Base):
    __tablename__ = "participants"
 
    id         = Column(String, primary_key=True, default=_uuid)
    meeting_id = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String, nullable=False)
    email      = Column(String, nullable=True)   # Optional — may be resolved later
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
 
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