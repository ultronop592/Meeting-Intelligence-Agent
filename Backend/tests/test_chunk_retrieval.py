"""
Backend/tests/test_chunk_retrieval.py — Phase 6: Chunk-Level Retrieval Unit Tests
"""

import pytest
from sqlalchemy import select

from core.chunk_indexer import (
    _build_chunks_from_text,
    _build_chunks_from_words,
    _dominant_speaker,
    _format_timestamp,
    index_meeting_chunks,
)
from core.chunk_retriever import (
    _format_timestamp as retriever_format_timestamp,
    _rerank_stub,
    _rrf_score,
    retrieve_chunks,
)
from api.chat import SYSTEM_CHAT_PROMPT, _build_full_meeting_context
from db.models import Meeting, TranscriptChunk, User


def test_timestamp_formatting():
    assert _format_timestamp(0) == "0:00"
    assert _format_timestamp(65) == "1:05"
    assert _format_timestamp(125.4) == "2:05"
    assert retriever_format_timestamp(360) == "6:00"


def test_dominant_speaker_selection():
    words = [
        {"word": "Hi", "speaker": "SPEAKER_00"},
        {"word": "there", "speaker": "SPEAKER_00"},
        {"word": "everyone", "speaker": "SPEAKER_01"},
    ]
    assert _dominant_speaker(words) == "SPEAKER_00"
    assert _dominant_speaker([]) is None


def test_build_chunks_from_words():
    # Construct 100 words spread across 90 seconds
    words = []
    for i in range(90):
        words.append({
            "word": f"word_{i}",
            "start": float(i),
            "end": float(i + 0.8),
            "speaker": "SPEAKER_00" if i < 45 else "SPEAKER_01",
        })

    chunks = _build_chunks_from_words(words)
    assert len(chunks) >= 2
    first_chunk = chunks[0]
    assert first_chunk["start_sec"] == 0.0
    assert first_chunk["speaker"] == "SPEAKER_00"
    assert "word_0" in first_chunk["text"]


def test_build_chunks_from_text_diarized():
    text = (
        "[SPEAKER_00 00:00:05] Good morning team. Today we decide our database architecture. "
        "[SPEAKER_01 00:01:10] I strongly advocate for PostgreSQL with pgvector for vector search."
    )
    chunks = _build_chunks_from_text(text)
    assert len(chunks) >= 1
    texts = [c["text"] for c in chunks]
    full_combined = " ".join(texts)
    assert "PostgreSQL" in full_combined or "database" in full_combined


def test_rrf_scoring():
    r1 = _rrf_score(1)
    r2 = _rrf_score(2)
    assert r1 > r2
    assert round(r1, 4) == round(1.0 / 61.0, 4)


def test_reranker_stub():
    sample = [{"chunk_id": "1", "text": "sample text", "score": 0.8}]
    result = _rerank_stub("query", sample)
    assert result == sample


def test_system_chat_prompt_includes_citations():
    assert "⏱ [MM:SS]" in SYSTEM_CHAT_PROMPT
    assert "timestamp" in SYSTEM_CHAT_PROMPT.lower()
    assert "citation" in SYSTEM_CHAT_PROMPT.lower() or "cite" in SYSTEM_CHAT_PROMPT.lower()


@pytest.mark.asyncio
async def test_index_and_retrieve_meeting_chunks(db_session):
    # Create meeting
    meeting = Meeting(
        id="meet-phase6-test",
        title="Architecture & Scaling Sync",
        audio_filename="sync.mp3",
        duration_minutes=30,
        short_summary="Discussed caching and PostgreSQL vector retrieval.",
        detailed_summary="The team agreed on Redis caching and chunk-level embeddings.",
        transcript=(
            "[SPEAKER_00 00:00:10] Let us review caching and retrieval upgrades. "
            "[SPEAKER_01 00:00:55] We will use Redis for session caching and PostgreSQL with pgvector for chunks. "
            "[SPEAKER_00 00:02:15] Action item for Bob to implement the chunk indexer by Friday."
        ),
    )
    db_session.add(meeting)
    await db_session.commit()

    # Index chunks
    indexed_count = await index_meeting_chunks(db_session, meeting.id)
    assert indexed_count > 0

    # Query chunks via hybrid retrieval
    chunks = await retrieve_chunks(
        db=db_session,
        question="What did we decide about Redis caching?",
        meeting_id=meeting.id,
        top_k=3,
    )

    assert len(chunks) > 0
    top_chunk = chunks[0]
    assert "start_ts" in top_chunk
    assert "end_ts" in top_chunk
    assert "text" in top_chunk
    assert top_chunk["meeting_id"] == meeting.id


@pytest.mark.asyncio
async def test_chat_context_incorporates_chunks(db_session):
    meeting = Meeting(
        id="meet-phase6-chat",
        title="Weekly Sprint Planning",
        audio_filename="sprint.mp3",
        duration_minutes=15,
        short_summary="Sprint 42 planning session.",
        detailed_summary="Discussed release timeline and security audit.",
        transcript=(
            "[SPEAKER_00 00:00:05] Welcome everyone. "
            "[SPEAKER_01 00:01:00] The security audit is scheduled for next Tuesday."
        ),
    )
    db_session.add(meeting)
    await db_session.commit()

    await index_meeting_chunks(db_session, meeting.id)

    # Context builder
    context, sources = await _build_full_meeting_context(
        db=db_session,
        question="When is the security audit?",
        meeting_id=meeting.id,
    )

    assert "RELEVANT TRANSCRIPT EXCERPTS" in context
    assert "⏱ [" in context
    assert any(s.startswith("chunk:") for s in sources)

