"""
Backend/tests/test_differentiator.py — Phase 7: Differentiator Unit & Integration Tests
"""

from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient, ASGITransport

from core.commitment_tracker import (
    _compute_days_between,
    _format_weeks_or_days,
    detect_decision_contradictions,
    get_commitment_overview,
    track_and_link_commitments,
)
from core.hinglish_normalizer import (
    build_hinglish_system_instruction,
    detect_code_switching,
    extract_hinglish_commitments,
    normalize_temporal_expressions,
)
from db.models import ActionItem, CommitmentLink, Decision, DecisionContradiction, Meeting
from api.main import app


def test_format_weeks_or_days():
    assert _format_weeks_or_days(0) == "earlier today"
    assert _format_weeks_or_days(1) == "yesterday"
    assert _format_weeks_or_days(5) == "5 days ago"
    assert _format_weeks_or_days(7) == "1 week ago"
    assert _format_weeks_or_days(21) == "3 weeks ago"


def test_compute_days_between():
    dt1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    dt2 = datetime(2026, 10, 22, tzinfo=timezone.utc)
    assert _compute_days_between(dt1, dt2) == 21
    assert _compute_days_between(dt2, dt1) == 0


def test_hinglish_code_switching_detection():
    # English only
    eng_text = "Good morning everyone. Today we are discussing the API architecture and sprint goals."
    res_eng = detect_code_switching(eng_text)
    assert not res_eng["is_code_switched"]
    assert res_eng["language"] == "en"

    # Hinglish text
    hi_text = "Main kal tak pull request merge kar dunga, tension mat lo bhai. Database ka blocker abhi pending hai."
    res_hi = detect_code_switching(hi_text)
    assert res_hi["is_code_switched"]
    assert res_hi["language"] == "hi-en"
    assert len(res_hi["detected_hindi_tokens"]) >= 2


def test_hinglish_temporal_normalization():
    raw = "Kal shaam tak delivery ho jayegi, parson tak client review hai."
    norm = normalize_temporal_expressions(raw)
    assert "tomorrow evening" in norm
    assert "in 2 days" in norm


def test_hinglish_commitment_extraction():
    transcript = "[SPEAKER_01 00:02:15] Main payment gateway bug fix kar dunga kal tak."
    commitments = extract_hinglish_commitments(transcript)
    assert len(commitments) == 1
    c = commitments[0]
    assert c["owner"] == "SPEAKER_01"
    assert "payment gateway bug" in c["description"].lower()
    assert c["due_date"] == "tomorrow"


def test_hinglish_system_instruction_prompt():
    prompt = build_hinglish_system_instruction()
    assert "HINGLISH / INDIAN-LANGUAGE" in prompt
    assert "kar dunga" in prompt
    assert "kal tak" in prompt


@pytest.mark.asyncio
async def test_cross_meeting_commitment_linking(db_session):
    # Meeting 1 (3 weeks ago)
    t1 = datetime.now(timezone.utc) - timedelta(days=21)
    m1 = Meeting(
        id="meet-diff-1",
        title="Sprint 40 Planning",
        audio_filename="sprint40.mp3",
        duration_minutes=30,
        short_summary="Sprint 40 kickoff.",
        detailed_summary="Tasks assigned for auth and caching.",
        created_at=t1,
    )
    db_session.add(m1)

    ai1 = ActionItem(
        id="item-diff-1",
        meeting_id=m1.id,
        description="Implement Redis caching for API session tokens",
        owner="Alice",
        due_date="2026-10-15",
        status="open",
        created_at=t1,
    )
    db_session.add(ai1)
    await db_session.commit()

    # Meeting 2 (Today - task raised again, still open)
    t2 = datetime.now(timezone.utc)
    m2 = Meeting(
        id="meet-diff-2",
        title="Sprint 43 Sync",
        audio_filename="sprint43.mp3",
        duration_minutes=25,
        short_summary="Sprint 43 progress check.",
        detailed_summary="Discussed delayed caching task.",
        created_at=t2,
    )
    db_session.add(m2)

    ai2 = ActionItem(
        id="item-diff-2",
        meeting_id=m2.id,
        description="Complete Redis session caching for API endpoints",
        owner="Alice",
        due_date="2026-11-05",
        status="open",
        created_at=t2,
    )
    db_session.add(ai2)
    await db_session.commit()

    # Run commitment linking
    links = await track_and_link_commitments(db_session, m2.id)

    assert len(links) == 1
    link = links[0]
    assert link.source_action_item_id == ai2.id
    assert link.target_action_item_id == ai1.id
    assert link.source_meeting_id == m2.id
    assert link.target_meeting_id == m1.id
    assert link.link_type == "repeated_commitment"
    assert link.days_unresolved >= 20
    assert "Promised 3 weeks ago" in link.explanation or "weeks ago" in link.explanation
    assert ai2.is_repeated_commitment is True
    assert ai2.repeated_from_meeting_id == m1.id


@pytest.mark.asyncio
async def test_decision_contradiction_detection(db_session):
    t1 = datetime.now(timezone.utc) - timedelta(days=14)
    m1 = Meeting(
        id="meet-contra-1",
        title="Architecture Decision Session",
        audio_filename="arch.mp3",
        duration_minutes=20,
        short_summary="Database selection.",
        detailed_summary="Team chose PostgreSQL with pgvector.",
        created_at=t1,
    )
    db_session.add(m1)

    d1 = Decision(
        id="dec-contra-1",
        meeting_id=m1.id,
        description="We chose PostgreSQL for primary storage and vector retrieval",
        context="Postgres is relational and supports pgvector",
        created_at=t1,
    )
    db_session.add(d1)
    await db_session.commit()

    # Meeting 2 (Conflicting decision)
    t2 = datetime.now(timezone.utc)
    m2 = Meeting(
        id="meet-contra-2",
        title="Infrastructure Revision",
        audio_filename="infra.mp3",
        duration_minutes=20,
        short_summary="Database reconsidered.",
        detailed_summary="Team decided to migrate from PostgreSQL to MongoDB.",
        created_at=t2,
    )
    db_session.add(m2)

    d2 = Decision(
        id="dec-contra-2",
        meeting_id=m2.id,
        description="We agreed to replace PostgreSQL and use MongoDB for all storage",
        context="MongoDB document schema chosen instead of postgresql",
        created_at=t2,
    )
    db_session.add(d2)
    await db_session.commit()

    contradictions = await detect_decision_contradictions(db_session, m2.id)

    assert len(contradictions) >= 1
    c = contradictions[0]
    assert c.new_decision_id == d2.id
    assert c.prior_decision_id == d1.id
    assert c.contradiction_score >= 0.70
    assert "Conflict detected" in c.summary
    assert d2.has_contradiction is True


@pytest.mark.asyncio
async def test_get_commitment_overview(db_session):
    overview = await get_commitment_overview(db_session, limit=10)
    assert "total_tracked_commitments" in overview
    assert "aging_breakdown" in overview
    assert "fresh_under_7_days" in overview["aging_breakdown"]
    assert "stale_commitments" in overview

