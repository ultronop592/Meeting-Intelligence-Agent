"""
api/commitments.py — Phase 7: Cross-Meeting Commitment Tracking & Differentiator API

Endpoints:
- GET  /commitments/timeline: Full cross-meeting commitment timeline, aging buckets, and contradictions.
- GET  /commitments/meetings/{meeting_id}: Commitment links and detected contradictions for a specific meeting.
- POST /commitments/scan/{meeting_id}: On-demand scan & link commitments across past meetings.
- POST /commitments/detect-hinglish: Analyze code-switching ratio, intent markers, and normalized time.
- POST /commitments/contradictions/{contradiction_id}/resolve: Update resolution status of a contradiction.
"""

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.commitment_tracker import (
    detect_decision_contradictions,
    get_commitment_overview,
    track_and_link_commitments,
)
from core.hinglish_normalizer import (
    detect_code_switching,
    extract_hinglish_commitments,
    normalize_temporal_expressions,
)
from db.database import get_db
from db.models import ActionItem, CommitmentLink, Decision, DecisionContradiction, Meeting, User
from models.schemas import (
    CommitmentLinkItem,
    CommitmentTimelineResponse,
    DecisionContradictionItem,
    HinglishAnalysisRequest,
    HinglishAnalysisResponse,
)

logger = logging.getLogger(__name__)

commitments_router = APIRouter(prefix="/commitments", tags=["commitments"])


@commitments_router.get("/timeline", response_model=CommitmentTimelineResponse)
async def get_timeline(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve cross-meeting commitments timeline, aging buckets, and contradictions."""
    overview = await get_commitment_overview(db=db, user_id=current_user.id, limit=limit)
    return CommitmentTimelineResponse(**overview)


@commitments_router.get("/meetings/{meeting_id}")
async def get_meeting_commitments(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve commitment links and contradictions associated with a specific meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    if meeting.user_id and meeting.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Links where this meeting is source (new repeated promises)
    source_links_stmt = select(CommitmentLink).where(CommitmentLink.source_meeting_id == meeting_id)
    source_links = (await db.execute(source_links_stmt)).scalars().all()

    # Contradictions
    contra_stmt = select(DecisionContradiction).where(DecisionContradiction.new_meeting_id == meeting_id)
    contradictions = (await db.execute(contra_stmt)).scalars().all()

    formatted_links = []
    for l in source_links:
        target_meet = await db.get(Meeting, l.target_meeting_id)
        source_item = await db.get(ActionItem, l.source_action_item_id)
        formatted_links.append({
            "link_id": l.id,
            "target_meeting_id": l.target_meeting_id,
            "target_meeting_title": target_meet.title if target_meet else "Earlier Meeting",
            "task_description": source_item.description if source_item else "",
            "owner": source_item.owner if source_item else "",
            "days_unresolved": l.days_unresolved,
            "status": l.status,
            "explanation": l.explanation,
            "confidence": l.confidence,
            "link_type": l.link_type,
        })

    return {
        "meeting_id": meeting_id,
        "meeting_title": meeting.title,
        "repeated_commitments_count": len(formatted_links),
        "commitment_links": formatted_links,
        "contradictions_count": len(contradictions),
        "contradictions": [
            {
                "id": c.id,
                "summary": c.summary,
                "score": c.contradiction_score,
                "status": c.resolution_status,
            }
            for c in contradictions
        ],
    }


@commitments_router.post("/scan/{meeting_id}")
async def trigger_scan(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger on-demand scan to link repeated commitments and identify decision contradictions."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    if meeting.user_id and meeting.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    links = await track_and_link_commitments(db, meeting_id)
    contradictions = await detect_decision_contradictions(db, meeting_id)

    return {
        "ok": True,
        "meeting_id": meeting_id,
        "links_found": len(links),
        "contradictions_found": len(contradictions),
    }


@commitments_router.post("/detect-hinglish", response_model=HinglishAnalysisResponse)
async def analyze_hinglish(
    payload: HinglishAnalysisRequest,
    current_user: User = Depends(get_current_user),
):
    """Analyze transcript text for Hindi-English code-switching and extract commitments."""
    detection = detect_code_switching(payload.text)
    normalized = normalize_temporal_expressions(payload.text)
    commitments = extract_hinglish_commitments(payload.text)

    return HinglishAnalysisResponse(
        is_code_switched=detection["is_code_switched"],
        score=detection["score"],
        detected_hindi_tokens=detection["detected_hindi_tokens"],
        language=detection["language"],
        normalized_text=normalized,
        extracted_commitments=commitments,
    )


@commitments_router.post("/contradictions/{contradiction_id}/resolve")
async def resolve_contradiction(
    contradiction_id: str,
    resolution_status: str = Query(default="acknowledged", regex="^(acknowledged|overruled|dismissed)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update resolution status of a decision contradiction."""
    contra = await db.get(DecisionContradiction, contradiction_id)
    if not contra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contradiction not found")

    contra.resolution_status = resolution_status
    await db.commit()
    return {"ok": True, "contradiction_id": contradiction_id, "status": resolution_status}
