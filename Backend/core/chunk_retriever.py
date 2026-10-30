"""
core/chunk_retriever.py — Phase 6: Hybrid Chunk Retriever

WHAT IT DOES
------------
Given a natural-language question, retrieves the most relevant transcript
chunks from `transcript_chunks` using:

1. **Dense vector search** — pgvector cosine similarity between the query
   embedding and chunk embeddings (top-K candidates).
2. **Full-text search** — Postgres `to_tsquery` against the `text_tsv` GIN
   index for exact keyword/phrase recall.
3. **Score fusion** — Reciprocal-Rank Fusion (RRF) combines both ranked lists
   into a single ranked result set.
4. **Cross-encoder reranker (stub)** — Hook for a real cross-encoder model
   (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`); falls back to RRF score
   when the model is unavailable.

Returns a list of `RetrievedChunk` dicts ready to be injected into the prompt,
each containing the text, speaker, start/end timestamps, and a score.
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory_service import generate_embedding, cosine_similarity
from db.models import TranscriptChunk, Meeting

logger = logging.getLogger(__name__)

# Retrieval hyperparameters
DENSE_TOP_K      = 20    # candidates from vector search
FTS_TOP_K        = 20    # candidates from full-text search
FINAL_TOP_K      = 8     # chunks returned to the prompt after reranking
RRF_K            = 60    # RRF constant (standard = 60)
MIN_TEXT_LEN     = 15    # discard degenerate chunks shorter than this


def _format_timestamp(seconds: float) -> str:
    """MM:SS string from seconds, e.g. 125.4 → '2:05'."""
    minutes = int(seconds) // 60
    secs    = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


def _rrf_score(rank: int) -> float:
    """Reciprocal Rank Fusion score for a given 1-based rank."""
    return 1.0 / (RRF_K + rank)


def _rerank_stub(query: str, chunks: list[dict]) -> list[dict]:
    """Placeholder cross-encoder reranker.

    Replace the body with a real cross-encoder inference call when a model is
    available. Currently returns chunks unchanged (preserving RRF order).

    To enable a real reranker:
        pip install sentence-transformers
        from sentence_transformers import CrossEncoder
        model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        pairs = [(query, c['text']) for c in chunks]
        scores = model.predict(pairs)
        for c, s in zip(chunks, scores): c['rerank_score'] = float(s)
        return sorted(chunks, key=lambda x: x['rerank_score'], reverse=True)
    """
    return chunks


async def retrieve_chunks(
    db: AsyncSession,
    question: str,
    meeting_id: Optional[str] = None,
    user_id: Optional[str] = None,
    top_k: int = FINAL_TOP_K,
) -> list[dict[str, Any]]:
    """Retrieve the most relevant transcript chunks for a question.

    Args:
        db:         Async SQLAlchemy session.
        question:   The user's natural-language question.
        meeting_id: If provided, restrict search to that meeting's chunks.
        user_id:    If provided, restrict search to meetings owned by this user.
        top_k:      Maximum number of chunks to return.

    Returns:
        List of dicts with keys: chunk_id, meeting_id, meeting_title,
        chunk_index, start_sec, end_sec, start_ts, end_ts, speaker, text, score.
    """
    if not question or not question.strip():
        return []

    query_vec = generate_embedding(question)

    # ------------------------------------------------------------------
    # 1. Dense vector search (in-Python cosine over all candidate chunks)
    #    For small datasets this is fine; for large ones use:
    #    ORDER BY embedding <=> query_vec::vector LIMIT N  (pgvector ANN)
    # ------------------------------------------------------------------
    chunk_stmt = select(TranscriptChunk)
    if meeting_id:
        chunk_stmt = chunk_stmt.where(TranscriptChunk.meeting_id == meeting_id)
    elif user_id:
        # Join through meetings to filter by user
        chunk_stmt = (
            chunk_stmt
            .join(Meeting, TranscriptChunk.meeting_id == Meeting.id)
            .where((Meeting.user_id == user_id) | (Meeting.user_id.is_(None)))
        )

    result = await db.execute(chunk_stmt)
    all_chunks: list[TranscriptChunk] = result.scalars().all()

    if not all_chunks:
        return []

    # Score every chunk with cosine similarity
    dense_scored: list[tuple[float, TranscriptChunk]] = []
    for chunk in all_chunks:
        if not chunk.text or len(chunk.text) < MIN_TEXT_LEN:
            continue
        if chunk.embedding is not None:
            try:
                emb = [float(x) for x in list(chunk.embedding)]
                score = cosine_similarity(query_vec, emb)
            except Exception:
                score = 0.0
        else:
            score = 0.0
        dense_scored.append((score, chunk))

    dense_scored.sort(key=lambda x: x[0], reverse=True)
    dense_top = dense_scored[:DENSE_TOP_K]

    # ------------------------------------------------------------------
    # 2. Full-text search (lexical)  — rank by query word overlap
    # ------------------------------------------------------------------
    clean_q = question.lower()
    query_words = set(re.findall(r"\b[a-z][a-z0-9]{2,}\b", clean_q))
    fts_scored: list[tuple[float, TranscriptChunk]] = []
    for chunk in all_chunks:
        if not chunk.text or len(chunk.text) < MIN_TEXT_LEN:
            continue
        text_lower = chunk.text.lower()
        hits = sum(1 for w in query_words if w in text_lower)
        if hits > 0:
            fts_scored.append((float(hits), chunk))

    fts_scored.sort(key=lambda x: x[0], reverse=True)
    fts_top = fts_scored[:FTS_TOP_K]

    # ------------------------------------------------------------------
    # 3. Reciprocal Rank Fusion
    # ------------------------------------------------------------------
    rrf: dict[str, float] = {}
    id_to_chunk: dict[str, TranscriptChunk] = {}

    for rank, (_, chunk) in enumerate(dense_top, start=1):
        rrf[chunk.id] = rrf.get(chunk.id, 0.0) + _rrf_score(rank)
        id_to_chunk[chunk.id] = chunk

    for rank, (_, chunk) in enumerate(fts_top, start=1):
        rrf[chunk.id] = rrf.get(chunk.id, 0.0) + _rrf_score(rank)
        id_to_chunk[chunk.id] = chunk

    ranked: list[tuple[float, TranscriptChunk]] = sorted(
        [(score, id_to_chunk[cid]) for cid, score in rrf.items()],
        key=lambda x: x[0],
        reverse=True,
    )

    # ------------------------------------------------------------------
    # 4. Rerank (stub) and format output
    # ------------------------------------------------------------------
    pre_rerank = [
        {
            "chunk_id":     c.id,
            "meeting_id":   c.meeting_id,
            "chunk_index":  c.chunk_index,
            "start_sec":    c.start_sec,
            "end_sec":      c.end_sec,
            "start_ts":     _format_timestamp(c.start_sec),
            "end_ts":       _format_timestamp(c.end_sec),
            "speaker":      c.speaker,
            "text":         c.text,
            "score":        round(score, 4),
        }
        for score, c in ranked[:top_k * 2]     # pass more to reranker
    ]

    reranked = _rerank_stub(question, pre_rerank)[:top_k]

    # Attach meeting titles
    meeting_title_cache: dict[str, str] = {}
    for item in reranked:
        mid = item["meeting_id"]
        if mid not in meeting_title_cache:
            m = await db.get(Meeting, mid)
            meeting_title_cache[mid] = m.title if m else "Unknown Meeting"
        item["meeting_title"] = meeting_title_cache[mid]

    return reranked
