import logging 
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import(
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings
from db.models import(
    Base, Meeting, ActionItem, Decision, Participant, NotificationLog, ProcessingJob, ChatSession, UserToolCredential
)
from models.schemas import AgentState, EmbeddingStatus

logger = logging.getLogger(__name__)


def _normalized_async_database_url(url: str) -> str:
    """Strips query parameters from asyncpg URLs so connect_args can handle SSL cleanly."""
    if url.startswith("postgresql+asyncpg://"):
        return url.split("?")[0]
    return url


# =============================================================================
# DATABASE ENGINE
# =============================================================================

# create_async_engine builds the connection pool to Neon.
# pool_size=5    — keep 5 connections open (reuse across requests)
# max_overflow=10 — allow up to 10 extra connections under load
# pool_pre_ping=True — test connections before use (handles Neon idle timeouts)
if settings.database_url.startswith("sqlite+"):
    engine = create_async_engine(
        settings.database_url,
        echo=not settings.is_production,
    )
else:
    engine = create_async_engine(
        _normalized_async_database_url(settings.database_url),
        connect_args={
            "ssl": "require",
            "statement_cache_size": 0,  # Required for Neon PgBouncer transaction pooler
        },
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=not settings.is_production,  # Log SQL queries in development only
    )
 
# async_sessionmaker creates a factory for DB sessions
# expire_on_commit=False — keep ORM objects usable after commit (important for async)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
 
 
# =============================================================================
# DATABASE INITIALISATION
# =============================================================================
 
async def init_db() -> None:
    """
    Creates all tables in Neon if they don't exist yet.
    Called once at FastAPI startup (in main.py lifespan).
 
    In production you'd use Alembic migrations instead.
    This is a convenience for development / first run.
    """
    async with engine.begin() as conn:
        # Neon/Postgres needs pgvector extension for Vector columns.
        if settings.database_url.startswith("postgresql+"):
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

        # === Safe column migrations (idempotent ALTER TABLE) ===
        # These handle the case where the table already exists without new columns.
        if settings.database_url.startswith("postgresql+"):

            # --- meetings table ---
            # user_id: added for per-user meeting isolation
            await conn.execute(text("""
                ALTER TABLE meetings
                ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE SET NULL
            """))

            # transcript: plain text transcript from Whisper
            await conn.execute(text("""
                ALTER TABLE meetings
                ADD COLUMN IF NOT EXISTS transcript TEXT
            """))

            # diarized_transcript: speaker-labelled version (SPEAKER_00: ...)
            await conn.execute(text("""
                ALTER TABLE meetings
                ADD COLUMN IF NOT EXISTS diarized_transcript TEXT
            """))

            # embedding_status: tracks RAG pipeline state
            await conn.execute(text("""
                ALTER TABLE meetings
                ADD COLUMN IF NOT EXISTS embedding_status VARCHAR NOT NULL DEFAULT 'pending'
            """))

            # transcript_embedding: 768-dim pgvector embedding for semantic search
            await conn.execute(text("""
                ALTER TABLE meetings
                ADD COLUMN IF NOT EXISTS transcript_embedding vector(768)
            """))

            # --- participants table ---
            # speaker_label: diarization label mapping e.g. SPEAKER_00
            await conn.execute(text("""
                ALTER TABLE participants
                ADD COLUMN IF NOT EXISTS speaker_label VARCHAR
            """))

            # --- chat_sessions table ---
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id VARCHAR PRIMARY KEY,
                    user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE,
                    meeting_id VARCHAR REFERENCES meetings(id) ON DELETE SET NULL,
                    title VARCHAR NOT NULL DEFAULT 'New Conversation',
                    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))

            # --- user_tool_credentials table ---
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_tool_credentials (
                    id VARCHAR PRIMARY KEY,
                    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    tool_name VARCHAR NOT NULL,
                    credentials JSONB NOT NULL DEFAULT '{}'::jsonb,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_user_tool UNIQUE (user_id, tool_name)
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_user_tool_credentials_user ON user_tool_credentials(user_id)
            """))

    logger.info("Database tables verified / created.")
 
 
# =============================================================================
# SESSION DEPENDENCY (used by FastAPI routes)
# =============================================================================
 
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields a DB session for each request.
 
    Usage in a route:
        @router.get("/meetings")
        async def list_meetings(db: AsyncSession = Depends(get_db)):
            ...
 
    The session is automatically closed after the request finishes,
    even if an exception occurs (the finally block handles it).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
 
 
# =============================================================================
# NODE 4 — save_to_database (LangGraph node)
# =============================================================================
 
async def save_to_database(state: AgentState) -> dict:
    """
    LangGraph Node 4 — Save to Database.
 
    Saves all data produced by Nodes 1-3 into Neon Postgres:
      - One Meeting row
      - One ActionItem row per action item
      - One Decision row per decision
      - One Participant row per participant
 
    INPUT  (reads from state): summary, extraction, audio_filename
    OUTPUT (writes to state):  meeting_id
    """
    logger.info("Node 4 — save_to_database: starting")
 
    # Guard — need at minimum a summary to save
    if not state.summary:
        error = "save_to_database: summary is missing — Node 3 may have failed."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    async with AsyncSessionLocal() as session:
        try:
            # --- 1. Create the Meeting row -----------------------------------
            meeting = Meeting(
                user_id=getattr(state, "user_id", None),
                title=state.summary.title,
                audio_filename=state.audio_filename or "unknown.mp3",
                duration_minutes=state.summary.duration_minutes,
                short_summary=state.summary.short_summary,
                detailed_summary=state.summary.detailed_summary,
                transcript=state.transcript,
                diarized_transcript=state.diarized_transcript,
                embedding_status=EmbeddingStatus.PENDING.value,
            )
            session.add(meeting)
 
            # Flush to get the auto-generated meeting.id before inserting children
            # (flush sends SQL to DB but doesn't commit yet — it's still in transaction)
            await session.flush()
            meeting_id: str = meeting.id
            logger.info("Meeting row created — id: %s", meeting_id)
 
            # --- 2. Save Action Items ----------------------------------------
            if state.extraction and state.extraction.action_items:
                for item in state.extraction.action_items:
                    db_item = ActionItem(
                        meeting_id=meeting_id,
                        description=item.description,
                        owner=item.owner,
                        due_date=item.due_date,
                        priority=item.priority.value,
                    )
                    session.add(db_item)
                logger.info("Saved %d action items.", len(state.extraction.action_items))
 
            # --- 3. Save Decisions -------------------------------------------
            if state.extraction and state.extraction.decisions:
                for decision in state.extraction.decisions:
                    db_decision = Decision(
                        meeting_id=meeting_id,
                        description=decision.description,
                        context=decision.context,
                    )
                    session.add(db_decision)
                logger.info("Saved %d decisions.", len(state.extraction.decisions))
 
            # --- 4. Save Participants ----------------------------------------
            if state.extraction and state.extraction.participants:
                for name in state.extraction.participants:
                    db_participant = Participant(
                        meeting_id=meeting_id,
                        name=name,
                        email=None,  # Email resolved later via settings page
                    )
                    session.add(db_participant)
                logger.info("Saved %d participants.", len(state.extraction.participants))
 
            # --- 5. Commit everything in one transaction ----------------------
            # If ANY insert fails, ALL inserts are rolled back — data stays clean
            await session.commit()
            logger.info("All data committed to Neon successfully.")

            # --- 6. Index Meeting into Vector Memory Layer (RAG) --------------
            try:
                from core.memory_service import memory_service
                await memory_service.index_meeting(session, meeting_id)
            except Exception as mem_err:
                logger.warning("Memory indexing warning for meeting %s: %s", meeting_id, mem_err)

            return {
                "meeting_id":      meeting_id,
                "completed_nodes": state.completed_nodes + ["save_to_database"],
            }
 
        except Exception as e:
            await session.rollback()
            error = f"Database save failed: {e}"
            logger.exception(error)
            return {"errors": state.errors + [error]}
 
 
# =============================================================================
# HELPER — log a notification result (called by tools in Nodes 5-7)
# =============================================================================
 
async def log_notification(
    meeting_id:        str,
    notification_type: str,
    status:            str,
    detail:            str | None = None,
) -> None:
    """
    Saves one row to notifications_log.
    Called by jira_tool, calendar_tool, email_tool, slack_tool
    to record whether their integration succeeded or failed.
    """
    async with AsyncSessionLocal() as session:
        try:
            log = NotificationLog(
                meeting_id=meeting_id,
                type=notification_type,
                status=status,
                detail=detail,
            )
            session.add(log)
            await session.commit()
        except Exception as e:
            logger.error("Failed to log notification: %s", e)
            await session.rollback()


# =============================================================================
# HELPERS — persistent job state (ProcessingJob table)
# =============================================================================

async def create_processing_job(job_id: str, user_id: str | None = None) -> None:
    """Insert a new ProcessingJob row in 'processing' state."""
    async with AsyncSessionLocal() as session:
        try:
            job = ProcessingJob(
                id=job_id,
                user_id=user_id,
                status="processing",
                completed_nodes=[],
                errors=[],
                node_timings={},
            )
            session.add(job)
            await session.commit()
        except Exception as e:
            logger.error("Failed to create processing job %s: %s", job_id, e)
            await session.rollback()


async def update_processing_job(job_id: str, **kwargs) -> None:
    """Merge a partial update into an existing ProcessingJob row."""
    async with AsyncSessionLocal() as session:
        try:
            job = await session.get(ProcessingJob, job_id)
            if not job:
                logger.warning("update_processing_job: job %s not found", job_id)
                return
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            await session.commit()

            # Broadcast update to connected WebSocket clients
            try:
                from core.ws_manager import ws_manager
                await ws_manager.broadcast(job_id, {
                    "event": "job_status_updated",
                    "job_id": job_id,
                    "status": job.status,
                    "completed_nodes": job.completed_nodes or [],
                    "errors": job.errors or [],
                    "meeting_id": job.meeting_id,
                    "duration_ms": job.duration_ms,
                    "title": job.title,
                    "short_summary": job.short_summary,
                })
            except Exception as ws_err:
                logger.debug("WebSocket broadcast failed for job %s: %s", job_id, ws_err)
        except Exception as e:
            logger.error("Failed to update processing job %s: %s", job_id, e)
            await session.rollback()


async def get_processing_job(job_id: str) -> dict | None:
    """Return a ProcessingJob as a plain dict, or None if not found."""
    async with AsyncSessionLocal() as session:
        try:
            job = await session.get(ProcessingJob, job_id)
            if not job:
                return None
            return {
                "status":              job.status,
                "user_id":             job.user_id,
                "completed_nodes":     job.completed_nodes or [],
                "errors":              job.errors or [],
                "meeting_id":          job.meeting_id,
                "started_at":          job.started_at.isoformat() if job.started_at else None,
                "completed_at":        job.completed_at.isoformat() if job.completed_at else None,
                "duration_ms":         job.duration_ms,
                "node_timings":        job.node_timings or {},
                "title":               job.title,
                "short_summary":       job.short_summary,
                "action_items_count":  job.action_items_count,
                "decisions_count":     job.decisions_count,
                "participants_count":  job.participants_count,
                "jira_tickets_created":job.jira_tickets_created,
                "calendar_event_id":   job.calendar_event_id,
                "notifications_sent":  job.notifications_sent,
            }
        except Exception as e:
            logger.error("Failed to get processing job %s: %s", job_id, e)
            return None


async def recover_stale_jobs() -> int:
    """
    Called once at startup — marks any job still in 'processing' state as 'failed'.

    When uvicorn restarts (e.g. due to --reload or a crash), any in-flight
    BackgroundTasks are killed instantly. Without this, those jobs stay stuck
    in 'processing' forever and the frontend spinner never stops.

    Returns the number of jobs recovered.
    """
    from datetime import datetime, timezone
    from sqlalchemy import update as sa_update

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                sa_update(ProcessingJob)
                .where(ProcessingJob.status == "processing")
                .values(
                    status="failed",
                    errors=["Server restarted while job was in progress. Please resubmit."],
                    completed_at=datetime.now(timezone.utc),
                )
                .returning(ProcessingJob.id)
            )
            recovered = result.fetchall()
            await session.commit()
            if recovered:
                logger.warning(
                    "Recovered %d orphaned job(s) on startup: %s",
                    len(recovered),
                    [r[0] for r in recovered],
                )
            return len(recovered)
        except Exception as exc:
            logger.error("Failed to recover stale jobs: %s", exc)
            await session.rollback()
            return 0


# =============================================================================
# CHAT SESSIONS — Multi-Turn Conversational Memory Persistence
# =============================================================================

from contextlib import asynccontextmanager

@asynccontextmanager
async def _get_context_session(db: AsyncSession | None = None):
    if db is not None:
        yield db
    else:
        async with AsyncSessionLocal() as session:
            yield session


async def create_chat_session(
    user_id: str,
    meeting_id: str | None = None,
    title: str | None = None,
    db: AsyncSession | None = None,
) -> dict:
    """Create a new ChatSession record in the DB and return its dict."""
    async with _get_context_session(db) as session:
        new_session = ChatSession(
            user_id=user_id,
            meeting_id=meeting_id,
            title=title or "New Conversation",
            messages=[],
        )
        session.add(new_session)
        await session.commit()
        await session.refresh(new_session)
        return {
            "id": new_session.id,
            "title": new_session.title,
            "meeting_id": new_session.meeting_id,
            "messages": new_session.messages or [],
            "created_at": new_session.created_at,
            "updated_at": new_session.updated_at,
        }


async def get_chat_session(
    session_id: str,
    user_id: str | None = None,
    db: AsyncSession | None = None,
) -> dict | None:
    """Get a ChatSession record by id (with optional user ownership verification)."""
    async with _get_context_session(db) as session:
        chat_sess = await session.get(ChatSession, session_id)
        if not chat_sess:
            return None
        if user_id and chat_sess.user_id and chat_sess.user_id != user_id:
            return None
        return {
            "id": chat_sess.id,
            "user_id": chat_sess.user_id,
            "title": chat_sess.title,
            "meeting_id": chat_sess.meeting_id,
            "messages": chat_sess.messages or [],
            "created_at": chat_sess.created_at,
            "updated_at": chat_sess.updated_at,
        }


async def list_chat_sessions(
    user_id: str,
    limit: int = 30,
    offset: int = 0,
    db: AsyncSession | None = None,
) -> list[dict]:
    """List chat sessions for a user, sorted by updated_at descending, with meeting titles."""
    from sqlalchemy import select
    async with _get_context_session(db) as session:
        stmt = (
            select(ChatSession, Meeting.title.label("meeting_title"))
            .outerjoin(Meeting, Meeting.id == ChatSession.meeting_id)
            .where((ChatSession.user_id == user_id) | (ChatSession.user_id.is_(None)))
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await session.execute(stmt)).all()
        results = []
        for sess, meeting_title in rows:
            msgs = sess.messages or []
            last_msg = msgs[-1]["content"] if msgs and "content" in msgs[-1] else None
            preview = (last_msg[:90] + "...") if last_msg and len(last_msg) > 90 else last_msg
            results.append({
                "id": sess.id,
                "title": sess.title,
                "meeting_id": sess.meeting_id,
                "meeting_title": meeting_title,
                "message_count": len(msgs),
                "preview": preview,
                "created_at": sess.created_at,
                "updated_at": sess.updated_at,
            })
        return results


async def append_chat_session_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    sources: list[str] | None = None,
    user_id: str | None = None,
    meeting_id: str | None = None,
    db: AsyncSession | None = None,
) -> str:
    """Appends user and assistant messages to a ChatSession. Creates session if not existing."""
    from datetime import datetime, timezone
    async with _get_context_session(db) as session:
        chat_sess = await session.get(ChatSession, session_id)
        now_str = datetime.now(timezone.utc).isoformat()

        if not chat_sess:
            title = user_message.strip()[:40]
            if len(user_message.strip()) > 40:
                title += "..."
            chat_sess = ChatSession(
                id=session_id,
                user_id=user_id,
                meeting_id=meeting_id,
                title=title or "New Conversation",
                messages=[],
            )
            session.add(chat_sess)

        current_messages = list(chat_sess.messages or [])
        current_messages.append({
            "role": "user",
            "content": user_message,
            "timestamp": now_str,
        })
        current_messages.append({
            "role": "assistant",
            "content": assistant_message,
            "timestamp": now_str,
            "sources": sources or [],
        })
        chat_sess.messages = current_messages
        if chat_sess.title == "New Conversation" and user_message:
            title = user_message.strip()[:40]
            if len(user_message.strip()) > 40:
                title += "..."
            chat_sess.title = title
        if meeting_id and not chat_sess.meeting_id:
            chat_sess.meeting_id = meeting_id

        chat_sess.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return chat_sess.id


async def delete_chat_session(
    session_id: str,
    user_id: str,
    db: AsyncSession | None = None,
) -> bool:
    """Delete a chat session, verifying user ownership."""
    async with _get_context_session(db) as session:
        chat_sess = await session.get(ChatSession, session_id)
        if not chat_sess:
            return False
        if chat_sess.user_id and chat_sess.user_id != user_id:
            return False
        await session.delete(chat_sess)
        await session.commit()
        return True


# =============================================================================
# USER TOOL CREDENTIALS — Per-User Integration Settings
# =============================================================================

async def get_user_tool_credentials(
    user_id: str,
    tool_name: str,
    db: AsyncSession | None = None,
) -> dict | None:
    """Retrieve decrypted/stored credentials dict for a specific tool for a user."""
    from sqlalchemy import select
    async with _get_context_session(db) as session:
        stmt = select(UserToolCredential).where(
            UserToolCredential.user_id == user_id,
            UserToolCredential.tool_name == tool_name,
            UserToolCredential.is_active.is_(True),
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if not row or not row.credentials:
            return None
        return dict(row.credentials)


async def save_user_tool_credentials(
    user_id: str,
    tool_name: str,
    credentials: dict,
    db: AsyncSession | None = None,
) -> dict:
    """Create or update credentials for a user and tool."""
    from sqlalchemy import select
    from datetime import datetime, timezone
    async with _get_context_session(db) as session:
        stmt = select(UserToolCredential).where(
            UserToolCredential.user_id == user_id,
            UserToolCredential.tool_name == tool_name,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row:
            # Merge with existing credentials so omitted secret fields aren't cleared
            current = dict(row.credentials or {})
            for k, v in credentials.items():
                if v is not None and v != "":
                    current[k] = v
            row.credentials = current
            row.is_active = True
            row.updated_at = datetime.now(timezone.utc)
        else:
            row = UserToolCredential(
                user_id=user_id,
                tool_name=tool_name,
                credentials=credentials,
                is_active=True,
            )
            session.add(row)

        await session.commit()
        await session.refresh(row)
        return {
            "tool_name": row.tool_name,
            "is_active": row.is_active,
            "updated_at": row.updated_at,
        }


async def delete_user_tool_credentials(
    user_id: str,
    tool_name: str,
    db: AsyncSession | None = None,
) -> bool:
    """Remove/disconnect credentials for a tool."""
    from sqlalchemy import select
    async with _get_context_session(db) as session:
        stmt = select(UserToolCredential).where(
            UserToolCredential.user_id == user_id,
            UserToolCredential.tool_name == tool_name,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if not row:
            return False
        await session.delete(row)
        await session.commit()
        return True


async def list_user_tool_credentials(
    user_id: str,
    db: AsyncSession | None = None,
) -> dict[str, dict]:
    """List all stored credentials for a user mapped by tool_name."""
    from sqlalchemy import select
    async with _get_context_session(db) as session:
        stmt = select(UserToolCredential).where(UserToolCredential.user_id == user_id)
        rows = (await session.execute(stmt)).scalars().all()
        return {r.tool_name: dict(r.credentials or {}) for r in rows if r.is_active}



