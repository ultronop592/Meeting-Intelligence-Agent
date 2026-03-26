import logging 
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import(
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from Backend.core.config import settings
from Backend.db.models import(
    Base, Meeting, ActionItem, Decision, Participant, NotificationLog
)
from Backend.models.schemas  import AgentState, EmbedddingStatus

logger = logging.getLogger(__name__)
 
 
# =============================================================================
# DATABASE ENGINE
# =============================================================================
 
# create_async_engine builds the connection pool to Neon.
# pool_size=5    — keep 5 connections open (reuse across requests)
# max_overflow=10 — allow up to 10 extra connections under load
# pool_pre_ping=True — test connections before use (handles Neon idle timeouts)
engine = create_async_engine(
    settings.database_url,
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
        await conn.run_sync(Base.metadata.create_all)
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
                title=state.summary.title,
                audio_filename=state.audio_filename or "unknown.mp3",
                duration_minutes=state.summary.duration_minutes,
                short_summary=state.summary.short_summary,
                detailed_summary=state.summary.detailed_summary,
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
 