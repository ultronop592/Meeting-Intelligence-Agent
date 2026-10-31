"""
core/commitment_tracker.py — Phase 7: Cross-Meeting Commitment & Contradiction Engine

WHAT IT DOES
------------
1. Tracks commitments across multiple meetings:
   - Detects when an action item raised in meeting B is the same task promised in
     meeting A ("Promised 3 weeks ago in 'Sprint 40 Planning' by Alice, raised again, still not done").
   - Computes semantic similarity + lexical overlap + owner alignment.
   - Calculates exact aging (days_unresolved) and categorizes links:
     `repeated_commitment`, `status_update`, `blocker_escalation`, `scope_change`.
   - Flags items with `is_repeated_commitment=True` and populates the `commitment_links` table.

2. Detects decision contradictions across meetings:
   - Compares new architectural/business decisions against prior decisions.
   - Flags conflicting directions (e.g. database choices, policy shifts, cancellations).
   - Populates the `decision_contradictions` table with human-readable rationale.

3. Builds cross-meeting commitment audit timelines and aging buckets:
   - Fresh (< 7 days)
   - Aging (7–21 days)
   - Stale / Critical (> 21 days overdue)
"""

import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory_service import cosine_similarity, generate_embedding
from db.models import ActionItem, CommitmentLink, Decision, DecisionContradiction, Meeting

logger = logging.getLogger(__name__)

# Similarity thresholds
COMMITMENT_SIMILARITY_THRESHOLD = 0.60
COMMITMENT_OWNER_BOOST_THRESHOLD = 0.50
CONTRADICTION_TOPIC_THRESHOLD   = 0.55

# Contrasting / conflicting semantic markers
CONTRADICTION_MARKERS = [
    ("replace", "keep"),
    ("migrate from", "migrate to"),
    ("postgresql", "mongodb"),
    ("postgres", "mysql"),
    ("microservices", "monolith"),
    ("monolith", "microservice"),
    ("approve", "reject"),
    ("approved", "rejected"),
    ("cancel", "proceed"),
    ("cancelled", "scheduled"),
    ("stripe", "adyen"),
    ("aws", "gcp"),
    ("rest", "graphql"),
    ("celery", "temporal"),
    ("self-hosted", "cloud"),
]


def _clean_tokens(text: str) -> set[str]:
    """Extract lowercased alphanumeric word tokens."""
    return set(re.findall(r"\b[a-z0-9_-]{3,}\b", text.lower()))


def _lexical_jaccard(s1: str, s2: str) -> float:
    """Compute token Jaccard similarity between two strings."""
    t1 = _clean_tokens(s1)
    t2 = _clean_tokens(s2)
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def _compute_days_between(dt_earlier: Optional[datetime], dt_later: Optional[datetime]) -> int:
    """Calculate day difference between two datetimes (minimum 0)."""
    if not dt_earlier or not dt_later:
        return 0
    delta = dt_later - dt_earlier
    return max(0, delta.days)


def _format_weeks_or_days(days: int) -> str:
    """Format duration into friendly English, e.g. '3 weeks ago' or '5 days ago'."""
    if days >= 14:
        weeks = days // 7
        return f"{weeks} weeks ago"
    elif days >= 7:
        return "1 week ago"
    elif days == 1:
        return "yesterday"
    elif days == 0:
        return "earlier today"
    else:
        return f"{days} days ago"


# ---------------------------------------------------------------------------
# Cross-Meeting Commitment Linking
# ---------------------------------------------------------------------------

async def track_and_link_commitments(
    db: AsyncSession,
    meeting_id: str,
) -> List[CommitmentLink]:
    """Scan current meeting action items against past meetings to link repeated commitments.

    Persists CommitmentLink rows and updates ActionItem metadata.
    """
    current_meeting = await db.get(Meeting, meeting_id)
    if not current_meeting:
        logger.warning("commitment_tracker: meeting %s not found", meeting_id)
        return []

    # 1. Fetch current action items
    curr_items = (
        await db.execute(
            select(ActionItem).where(ActionItem.meeting_id == meeting_id)
        )
    ).scalars().all()

    if not curr_items:
        return []

    # 2. Fetch past meetings and their unresolved / historical action items
    past_meetings_stmt = (
        select(Meeting)
        .where(Meeting.id != meeting_id)
    )
    if current_meeting.user_id:
        past_meetings_stmt = past_meetings_stmt.where(
            (Meeting.user_id == current_meeting.user_id) | (Meeting.user_id.is_(None))
        )
    if current_meeting.created_at:
        past_meetings_stmt = past_meetings_stmt.where(
            Meeting.created_at < current_meeting.created_at
        )

    past_meetings_stmt = past_meetings_stmt.order_by(Meeting.created_at.desc()).limit(30)
    past_meetings = (await db.execute(past_meetings_stmt)).scalars().all()

    if not past_meetings:
        return []

    past_meeting_ids = [m.id for m in past_meetings]
    past_meeting_map = {m.id: m for m in past_meetings}

    past_items = (
        await db.execute(
            select(ActionItem).where(ActionItem.meeting_id.in_(past_meeting_ids))
        )
    ).scalars().all()

    if not past_items:
        return []

    # Delete existing commitment links for this source meeting to ensure idempotency
    await db.execute(
        delete(CommitmentLink).where(CommitmentLink.source_meeting_id == meeting_id)
    )

    created_links: List[CommitmentLink] = []

    for curr in curr_items:
        curr_vec = generate_embedding(f"{curr.description} owner:{curr.owner}")
        curr_owner_clean = (curr.owner or "").strip().lower()

        best_match: Optional[Tuple[float, ActionItem, str]] = None

        for past in past_items:
            past_meeting = past_meeting_map.get(past.meeting_id)
            past_vec = generate_embedding(f"{past.description} owner:{past.owner}")
            vec_sim = cosine_similarity(curr_vec, past_vec)
            lex_sim = _lexical_jaccard(curr.description, past.description)

            # Owner boost
            past_owner_clean = (past.owner or "").strip().lower()
            owner_matches = (
                curr_owner_clean
                and past_owner_clean
                and curr_owner_clean not in ("unassigned", "team")
                and (curr_owner_clean == past_owner_clean or curr_owner_clean in past_owner_clean or past_owner_clean in curr_owner_clean)
            )

            combined_sim = (vec_sim * 0.65) + (lex_sim * 0.35)
            if owner_matches:
                combined_sim += 0.15

            threshold = COMMITMENT_OWNER_BOOST_THRESHOLD if owner_matches else COMMITMENT_SIMILARITY_THRESHOLD

            if combined_sim >= threshold:
                if not best_match or combined_sim > best_match[0]:
                    best_match = (combined_sim, past, past_meeting.title if past_meeting else "Earlier Meeting")

        if best_match:
            sim_score, matched_past_item, past_meeting_title = best_match
            past_meeting_obj = past_meeting_map.get(matched_past_item.meeting_id)

            days_unresolved = _compute_days_between(
                past_meeting_obj.created_at if past_meeting_obj else None,
                current_meeting.created_at,
            )

            # Determine link type and explanation
            time_ago = _format_weeks_or_days(days_unresolved)
            owner_str = f" by {matched_past_item.owner}" if matched_past_item.owner and matched_past_item.owner != "Unassigned" else ""

            # Check if current item resolves it or reiterates it
            curr_desc_lower = curr.description.lower()
            if any(w in curr_desc_lower for w in ("completed", "done", "resolved", "merged", "finished")):
                link_type = "status_update"
                status_str = "resolved"
                explanation = f"Marked resolved in '{current_meeting.title}' (originally promised {time_ago} in '{past_meeting_title}'{owner_str})."
            elif curr.priority == "high" and matched_past_item.priority in ("medium", "low"):
                link_type = "blocker_escalation"
                status_str = "overdue" if days_unresolved >= 14 else "in_progress"
                explanation = f"Escalated to HIGH priority after being promised {time_ago} in '{past_meeting_title}'{owner_str}, still not done."
            else:
                link_type = "repeated_commitment"
                status_str = "overdue" if days_unresolved >= 14 else "open"
                explanation = f"Promised {time_ago} in '{past_meeting_title}'{owner_str}, raised again in '{current_meeting.title}', still not done."

            # Update current action item fields
            curr.is_repeated_commitment = True
            curr.repeated_from_meeting_id = matched_past_item.meeting_id
            curr.days_unresolved = days_unresolved

            link = CommitmentLink(
                source_action_item_id=curr.id,
                target_action_item_id=matched_past_item.id,
                source_meeting_id=current_meeting.id,
                target_meeting_id=matched_past_item.meeting_id,
                link_type=link_type,
                confidence=round(min(1.0, sim_score), 4),
                similarity_score=round(sim_score, 4),
                days_unresolved=days_unresolved,
                status=status_str,
                explanation=explanation,
            )
            created_links.append(link)
            db.add(link)

    await db.commit()
    logger.info(
        "commitment_tracker: generated %d commitment links for meeting %s",
        len(created_links),
        meeting_id,
    )
    return created_links


# ---------------------------------------------------------------------------
# Decision Contradiction Detection
# ---------------------------------------------------------------------------

async def detect_decision_contradictions(
    db: AsyncSession,
    meeting_id: str,
) -> List[DecisionContradiction]:
    """Scan current meeting decisions against past decisions to flag architectural/business contradictions."""
    current_meeting = await db.get(Meeting, meeting_id)
    if not current_meeting:
        return []

    curr_decisions = (
        await db.execute(
            select(Decision).where(Decision.meeting_id == meeting_id)
        )
    ).scalars().all()

    if not curr_decisions:
        return []

    # Fetch past decisions
    past_meetings_stmt = (
        select(Meeting)
        .where(Meeting.id != meeting_id)
    )
    if current_meeting.user_id:
        past_meetings_stmt = past_meetings_stmt.where(
            (Meeting.user_id == current_meeting.user_id) | (Meeting.user_id.is_(None))
        )
    if current_meeting.created_at:
        past_meetings_stmt = past_meetings_stmt.where(
            Meeting.created_at < current_meeting.created_at
        )

    past_meetings = (await db.execute(past_meetings_stmt.order_by(Meeting.created_at.desc()).limit(30))).scalars().all()
    if not past_meetings:
        return []

    past_map = {m.id: m for m in past_meetings}
    past_decisions = (
        await db.execute(
            select(Decision).where(Decision.meeting_id.in_(list(past_map.keys())))
        )
    ).scalars().all()

    if not past_decisions:
        return []

    # Clean previous contradictions for this meeting
    await db.execute(
        delete(DecisionContradiction).where(DecisionContradiction.new_meeting_id == meeting_id)
    )

    detected: List[DecisionContradiction] = []

    for curr in curr_decisions:
        curr_text = f"{curr.description} {curr.context or ''}".lower()
        curr_vec = generate_embedding(curr_text)

        for past in past_decisions:
            past_text = f"{past.description} {past.context or ''}".lower()
            past_vec = generate_embedding(past_text)

            topic_sim = cosine_similarity(curr_vec, past_vec)

            # Check for contrasting markers or opposing stances
            conflict_found = False
            conflict_reason = ""

            for term_a, term_b in CONTRADICTION_MARKERS:
                if (term_a in curr_text and term_b in past_text) or (term_b in curr_text and term_a in past_text):
                    conflict_found = True
                    conflict_reason = f"Decision shifts stance between '{term_a}' and '{term_b}'"
                    break

            # Negative semantic shift detection
            if not conflict_found and topic_sim >= CONTRADICTION_TOPIC_THRESHOLD:
                neg_in_curr = any(neg in curr_text for neg in ("instead of", "rather than", "abandon", "revert", "cancel", "replace", "deprecated"))
                if neg_in_curr:
                    conflict_found = True
                    conflict_reason = "New decision introduces negation or replacement over earlier agreed direction"

            if conflict_found:
                past_meeting_obj = past_map.get(past.meeting_id)
                past_title = past_meeting_obj.title if past_meeting_obj else "earlier meeting"
                past_date = past_meeting_obj.created_at.strftime("%Y-%m-%d") if past_meeting_obj and past_meeting_obj.created_at else "past"

                summary = (
                    f"Conflict detected: Decision in '{current_meeting.title}' ('{curr.description}') "
                    f"contradicts earlier decision in '{past_title}' on {past_date} ('{past.description}'). "
                    f"Rationale: {conflict_reason}."
                )

                curr.has_contradiction = True
                curr.contradiction_count = getattr(curr, "contradiction_count", 0) + 1

                contra = DecisionContradiction(
                    new_decision_id=curr.id,
                    prior_decision_id=past.id,
                    new_meeting_id=current_meeting.id,
                    prior_meeting_id=past.meeting_id,
                    contradiction_score=round(max(0.70, topic_sim), 4),
                    summary=summary,
                    resolution_status="detected",
                )
                detected.append(contra)
                db.add(contra)

    await db.commit()
    logger.info(
        "commitment_tracker: flagged %d decision contradictions for meeting %s",
        len(detected),
        meeting_id,
    )
    return detected


# ---------------------------------------------------------------------------
# Cross-Meeting Commitment Timeline & Aging Queries
# ---------------------------------------------------------------------------

async def get_commitment_overview(
    db: AsyncSession,
    user_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Retrieve commitment tracking timeline, aging buckets, and chain insights."""
    stmt = (
        select(CommitmentLink)
        .join(Meeting, CommitmentLink.source_meeting_id == Meeting.id)
    )
    if user_id:
        stmt = stmt.where((Meeting.user_id == user_id) | (Meeting.user_id.is_(None)))

    stmt = stmt.order_by(CommitmentLink.created_at.desc()).limit(limit)
    links = (await db.execute(stmt)).scalars().all()

    # Buckets
    fresh_items: List[Dict[str, Any]] = []
    aging_items: List[Dict[str, Any]] = []
    stale_items: List[Dict[str, Any]] = []

    for l in links:
        source_item = await db.get(ActionItem, l.source_action_item_id)
        source_meet = await db.get(Meeting, l.source_meeting_id)
        target_meet = await db.get(Meeting, l.target_meeting_id)

        item_repr = {
            "link_id": l.id,
            "source_meeting_title": source_meet.title if source_meet else "Unknown",
            "target_meeting_title": target_meet.title if target_meet else "Unknown",
            "task_description": source_item.description if source_item else "Task",
            "owner": source_item.owner if source_item else "Unassigned",
            "link_type": l.link_type,
            "days_unresolved": l.days_unresolved,
            "status": l.status,
            "explanation": l.explanation,
            "confidence": l.confidence,
        }

        if l.days_unresolved < 7:
            fresh_items.append(item_repr)
        elif l.days_unresolved <= 21:
            aging_items.append(item_repr)
        else:
            stale_items.append(item_repr)

    # Contradictions query
    contra_stmt = select(DecisionContradiction).order_by(DecisionContradiction.created_at.desc()).limit(20)
    contradictions = (await db.execute(contra_stmt)).scalars().all()
    contra_list = [
        {
            "id": c.id,
            "summary": c.summary,
            "score": c.contradiction_score,
            "status": c.resolution_status,
        }
        for c in contradictions
    ]

    return {
        "total_tracked_commitments": len(links),
        "aging_breakdown": {
            "fresh_under_7_days": len(fresh_items),
            "aging_7_to_21_days": len(aging_items),
            "stale_over_21_days": len(stale_items),
        },
        "stale_commitments": stale_items,
        "aging_commitments": aging_items,
        "recent_links": fresh_items,
        "contradictions_count": len(contra_list),
        "contradictions": contra_list,
    }
