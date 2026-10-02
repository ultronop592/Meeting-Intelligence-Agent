"""Domain router: Meeting Analytics & Intelligence Insights.

Endpoints:
- GET /analytics/summary: High-level meeting counts, avg duration, action completion rates.
- GET /analytics/participants: Active participants leaderboard and workload distribution.
- GET /analytics/timeline: Time-series velocity of meetings and task completions (weekly/monthly).
- GET /analytics/action-items: Breakdown of open, in-progress, done, and overdue items by owner.
- GET /analytics/topics: Recurring topic frequencies and keywords across meetings.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import logging
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.cache import (
    TTL_ANALYTICS,
    cache_get,
    cache_set,
    key_analytics_action_items,
    key_analytics_participants,
    key_analytics_summary,
    key_analytics_timeline,
    key_analytics_topics,
)
from db.database import get_db
from db.models import ActionItem as DBActionItem, Meeting, Participant, User
from models.schemas import (
    ActionItemOwnerBreakdown,
    AnalyticsActionItemsResponse,
    AnalyticsParticipantsResponse,
    AnalyticsSummaryResponse,
    AnalyticsTimelineResponse,
    AnalyticsTopicsResponse,
    ParticipantAnalyticsItem,
    PeriodStats,
    TimelineDataPoint,
    TopicKeywordItem,
)

logger = logging.getLogger(__name__)

analytics_router = APIRouter(tags=["analytics"])


@analytics_router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return high-level analytics summary: meeting counts, average duration, action item completion rate."""
    _ck = key_analytics_summary(current_user.id)
    cached = await cache_get(_ck)
    if cached is not None:
        return AnalyticsSummaryResponse(**cached)

    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))

    stmt_meetings = select(Meeting).where(user_filter)
    meetings_res = (await db.execute(stmt_meetings)).scalars().all()

    total_meetings = len(meetings_res)
    avg_duration = (
        round(sum(m.duration_minutes for m in meetings_res) / total_meetings, 1)
        if total_meetings > 0
        else 0.0
    )

    meeting_ids = [m.id for m in meetings_res]
    if meeting_ids:
        stmt_actions = select(DBActionItem).where(DBActionItem.meeting_id.in_(meeting_ids))
        action_items = (await db.execute(stmt_actions)).scalars().all()
    else:
        action_items = []

    total_action_items = len(action_items)
    completed_action_items = sum(
        1 for a in action_items
        if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "done"
    )
    completion_rate = (
        round((completed_action_items / total_action_items) * 100, 1)
        if total_action_items > 0
        else 0.0
    )

    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    # 7-day stats
    meetings_7d = [m for m in meetings_res if m.created_at and m.created_at >= cutoff_7d]
    meeting_ids_7d = set(m.id for m in meetings_7d)
    actions_7d = [a for a in action_items if a.meeting_id in meeting_ids_7d]
    completed_7d = sum(
        1 for a in actions_7d
        if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "done"
    )
    rate_7d = round((completed_7d / len(actions_7d)) * 100, 1) if actions_7d else 0.0

    stats_7d = PeriodStats(
        meetings_count=len(meetings_7d),
        action_items_count=len(actions_7d),
        completed_action_items=completed_7d,
        completion_rate=rate_7d,
    )

    # 30-day stats
    meetings_30d = [m for m in meetings_res if m.created_at and m.created_at >= cutoff_30d]
    meeting_ids_30d = set(m.id for m in meetings_30d)
    actions_30d = [a for a in action_items if a.meeting_id in meeting_ids_30d]
    completed_30d = sum(
        1 for a in actions_30d
        if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "done"
    )
    rate_30d = round((completed_30d / len(actions_30d)) * 100, 1) if actions_30d else 0.0

    stats_30d = PeriodStats(
        meetings_count=len(meetings_30d),
        action_items_count=len(actions_30d),
        completed_action_items=completed_30d,
        completion_rate=rate_30d,
    )

    result = AnalyticsSummaryResponse(
        total_meetings=total_meetings,
        avg_duration_minutes=avg_duration,
        total_action_items=total_action_items,
        completed_action_items=completed_action_items,
        completion_rate=completion_rate,
        last_7_days=stats_7d,
        last_30_days=stats_30d,
    )
    await cache_set(_ck, result.model_dump(), ttl=TTL_ANALYTICS)
    return result


@analytics_router.get("/analytics/participants", response_model=AnalyticsParticipantsResponse)
async def get_analytics_participants(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Leaderboard of active participants and action item load."""
    _ck = key_analytics_participants(current_user.id)
    cached = await cache_get(_ck)
    if cached is not None:
        return AnalyticsParticipantsResponse(**cached)

    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    stmt_meetings = select(Meeting.id).where(user_filter)
    meeting_ids = (await db.execute(stmt_meetings)).scalars().all()

    if not meeting_ids:
        return AnalyticsParticipantsResponse(participants=[])

    stmt_participants = select(Participant).where(Participant.meeting_id.in_(meeting_ids))
    participants = (await db.execute(stmt_participants)).scalars().all()

    stmt_actions = select(DBActionItem).where(DBActionItem.meeting_id.in_(meeting_ids))
    action_items = (await db.execute(stmt_actions)).scalars().all()

    part_stats: dict[str, dict] = {}
    for p in participants:
        name = (p.name or "").strip()
        if not name:
            continue
        if name not in part_stats:
            part_stats[name] = {"meetings": set(), "actions_count": 0, "actions_completed": 0}
        part_stats[name]["meetings"].add(p.meeting_id)

    for a in action_items:
        owner = (a.owner or "").strip()
        if not owner:
            continue
        if owner not in part_stats:
            part_stats[owner] = {"meetings": set(), "actions_count": 0, "actions_completed": 0}
        part_stats[owner]["actions_count"] += 1
        st = a.status.value if hasattr(a.status, "value") else str(a.status)
        if st == "done":
            part_stats[owner]["actions_completed"] += 1

    result = [
        ParticipantAnalyticsItem(
            name=name,
            meetings_count=len(info["meetings"]),
            action_items_count=info["actions_count"],
            completed_action_items=info["actions_completed"],
        )
        for name, info in part_stats.items()
    ]
    result.sort(key=lambda x: (x.meetings_count, x.action_items_count), reverse=True)
    participants_result = AnalyticsParticipantsResponse(participants=result)
    await cache_set(_ck, participants_result.model_dump(), ttl=TTL_ANALYTICS)
    return participants_result


@analytics_router.get("/analytics/timeline", response_model=AnalyticsTimelineResponse)
async def get_analytics_timeline(
    period: str = Query("monthly", pattern="^(weekly|monthly)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Meeting frequency and action item completion trend over time (weekly/monthly)."""
    _ck = key_analytics_timeline(current_user.id) + f":{period}"
    cached = await cache_get(_ck)
    if cached is not None:
        return AnalyticsTimelineResponse(**cached)

    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    stmt_meetings = select(Meeting).where(user_filter).order_by(Meeting.created_at.asc())
    meetings = (await db.execute(stmt_meetings)).scalars().all()

    meeting_ids = [m.id for m in meetings]
    if meeting_ids:
        stmt_actions = select(DBActionItem).where(DBActionItem.meeting_id.in_(meeting_ids))
        action_items = (await db.execute(stmt_actions)).scalars().all()
    else:
        action_items = []

    grouped: dict[str, dict] = {}

    for m in meetings:
        dt = m.created_at or datetime.now(timezone.utc)
        if period == "weekly":
            year, week, _ = dt.isocalendar()
            key = f"{year}-W{week:02d}"
            label = f"W{week} ({dt.strftime('%b %d')})"
        else:
            key = dt.strftime("%Y-%m")
            label = dt.strftime("%b %Y")

        if key not in grouped:
            grouped[key] = {
                "label": label,
                "meetings": [],
                "meeting_ids": set(),
            }
        grouped[key]["meetings"].append(m)
        grouped[key]["meeting_ids"].add(m.id)

    timeline_points = []
    for key, data in grouped.items():
        m_list = data["meetings"]
        m_ids = data["meeting_ids"]
        actions = [a for a in action_items if a.meeting_id in m_ids]
        done_cnt = sum(
            1 for a in actions
            if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "done"
        )
        avg_dur = round(sum(m.duration_minutes for m in m_list) / len(m_list), 1) if m_list else 0.0

        timeline_points.append(
            TimelineDataPoint(
                period=key,
                label=data["label"],
                meetings_count=len(m_list),
                action_items_count=len(actions),
                completed_action_items=done_cnt,
                avg_duration_minutes=avg_dur,
            )
        )

    timeline_result = AnalyticsTimelineResponse(period_type=period, timeline=timeline_points)
    await cache_set(_ck, timeline_result.model_dump(), ttl=TTL_ANALYTICS)
    return timeline_result


@analytics_router.get("/analytics/action-items", response_model=AnalyticsActionItemsResponse)
async def get_analytics_action_items(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Breakdown of open, in-progress, done, and overdue action items across all meetings and per owner."""
    _ck = key_analytics_action_items(current_user.id)
    cached = await cache_get(_ck)
    if cached is not None:
        return AnalyticsActionItemsResponse(**cached)

    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    stmt_meetings = select(Meeting.id).where(user_filter)
    meeting_ids = (await db.execute(stmt_meetings)).scalars().all()

    if not meeting_ids:
        return AnalyticsActionItemsResponse()

    stmt_actions = select(DBActionItem).where(DBActionItem.meeting_id.in_(meeting_ids))
    action_items = (await db.execute(stmt_actions)).scalars().all()

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_open = 0
    total_in_progress = 0
    total_done = 0
    total_overdue = 0

    by_owner_dict: dict[str, dict] = {}

    for a in action_items:
        st = a.status.value if hasattr(a.status, "value") else str(a.status)
        is_overdue = (st != "done") and bool(a.due_date and a.due_date < today_str)

        if st == "open":
            total_open += 1
        elif st == "in_progress":
            total_in_progress += 1
        elif st == "done":
            total_done += 1

        if is_overdue:
            total_overdue += 1

        owner = (a.owner or "").strip() or "Unassigned"
        if owner not in by_owner_dict:
            by_owner_dict[owner] = {"open": 0, "in_progress": 0, "done": 0, "overdue": 0, "total": 0}

        by_owner_dict[owner]["total"] += 1
        if st == "open":
            by_owner_dict[owner]["open"] += 1
        elif st == "in_progress":
            by_owner_dict[owner]["in_progress"] += 1
        elif st == "done":
            by_owner_dict[owner]["done"] += 1

        if is_overdue:
            by_owner_dict[owner]["overdue"] += 1

    by_owner = [
        ActionItemOwnerBreakdown(
            owner=owner,
            open=stats["open"],
            in_progress=stats["in_progress"],
            done=stats["done"],
            overdue=stats["overdue"],
            total=stats["total"],
        )
        for owner, stats in by_owner_dict.items()
    ]
    by_owner.sort(key=lambda x: x.total, reverse=True)

    action_items_result = AnalyticsActionItemsResponse(
        total_open=total_open,
        total_in_progress=total_in_progress,
        total_done=total_done,
        total_overdue=total_overdue,
        by_owner=by_owner,
    )
    await cache_set(_ck, action_items_result.model_dump(), ttl=TTL_ANALYTICS)
    return action_items_result


@analytics_router.get("/analytics/topics", response_model=AnalyticsTopicsResponse)
async def get_analytics_topics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top recurring topics and keywords extracted across all meetings."""
    _ck = key_analytics_topics(current_user.id)
    cached = await cache_get(_ck)
    if cached is not None:
        return AnalyticsTopicsResponse(**cached)

    user_filter = (Meeting.user_id == current_user.id) | (Meeting.user_id.is_(None))
    stmt_meetings = select(Meeting).where(user_filter)
    meetings = (await db.execute(stmt_meetings)).scalars().all()

    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "about",
        "against", "between", "into", "through", "during", "before", "after", "above", "below",
        "from", "up", "down", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "any", "both", "each",
        "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same",
        "so", "than", "too", "very", "can", "will", "just", "should", "now", "meeting", "sync",
        "discussion", "update", "notes", "agenda", "call", "project", "team", "this", "that", "was",
        "were", "have", "has", "had", "been", "being", "they", "them", "their", "what", "which", "who"
    }

    counter = Counter()
    for m in meetings:
        text = f"{m.title} {m.short_summary or ''}"
        words = re.findall(r"\b[A-Za-z]{3,}\b", text)
        for w in words:
            wl = w.lower()
            if wl not in stopwords:
                counter[wl.capitalize()] += 1

    top_topics = [
        TopicKeywordItem(topic=topic, count=cnt)
        for topic, cnt in counter.most_common(15)
    ]
    topics_result = AnalyticsTopicsResponse(topics=top_topics)
    await cache_set(_ck, topics_result.model_dump(), ttl=TTL_ANALYTICS)
    return topics_result
