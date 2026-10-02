"""Domain router: Global Multi-Entity Search.

Endpoints:
- GET /search: Search across meetings (title, summaries, transcript), action items, and decisions.
"""

import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from db.database import get_db
from db.models import ActionItem as DBActionItem, Decision, Meeting, User

logger = logging.getLogger(__name__)

search_router = APIRouter(tags=["search"])


@search_router.get("/search")
async def global_search(
    q: str = Query(..., min_length=1, description="Search query term"),
    mode: str = Query("fulltext", description="Search mode: 'fulltext' or 'semantic'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Global search across meetings, action items, and decisions."""
    search_term = f"%{q.strip()}%"
    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))

    # 1. Search Meetings (Title, Summaries, Transcript)
    stmt_meetings = select(Meeting).where(
        user_filter & (
            Meeting.title.ilike(search_term) |
            Meeting.short_summary.ilike(search_term) |
            Meeting.detailed_summary.ilike(search_term) |
            Meeting.transcript.ilike(search_term)
        )
    ).limit(20)
    matching_meetings = (await db.execute(stmt_meetings)).scalars().all()

    meeting_results = []
    for m in matching_meetings:
        full_text = f"{m.short_summary or ''} {m.detailed_summary or ''} {m.transcript or ''}"
        idx = full_text.lower().find(q.lower())
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(full_text), idx + len(q) + 60)
            snippet = f"...{full_text[start:end]}..."
        else:
            snippet = (m.short_summary or "")[:120]

        meeting_results.append({
            "id": m.id,
            "title": m.title,
            "short_summary": m.short_summary,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "snippet": snippet,
        })

    # 2. Search Action Items
    meeting_ids_stmt = select(Meeting.id).where(user_filter)
    user_meeting_ids = (await db.execute(meeting_ids_stmt)).scalars().all()

    action_results = []
    if user_meeting_ids:
        stmt_actions = select(DBActionItem).where(
            DBActionItem.meeting_id.in_(user_meeting_ids) & (
                DBActionItem.description.ilike(search_term) |
                DBActionItem.owner.ilike(search_term)
            )
        ).limit(20)
        matching_actions = (await db.execute(stmt_actions)).scalars().all()

        for a in matching_actions:
            action_results.append({
                "id": a.id,
                "meeting_id": a.meeting_id,
                "description": a.description,
                "owner": a.owner,
                "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                "priority": a.priority.value if hasattr(a.priority, "value") else str(a.priority),
                "due_date": a.due_date,
            })

    # 3. Search Decisions
    decision_results = []
    if user_meeting_ids:
        stmt_decisions = select(Decision).where(
            Decision.meeting_id.in_(user_meeting_ids) & (
                Decision.description.ilike(search_term) |
                Decision.context.ilike(search_term)
            )
        ).limit(20)
        matching_decisions = (await db.execute(stmt_decisions)).scalars().all()

        for d in matching_decisions:
            decision_results.append({
                "id": d.id,
                "meeting_id": d.meeting_id,
                "description": d.description,
                "context": d.context,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            })

    total = len(meeting_results) + len(action_results) + len(decision_results)
    return {
        "query": q,
        "mode": mode,
        "meetings": meeting_results,
        "action_items": action_results,
        "decisions": decision_results,
        "total_results": total,
    }
