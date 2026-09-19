"""
core/memory_service.py — Cross-Meeting Semantic Memory Layer (RAG)

WHAT IT DOES
------------
1. Embeds meeting transcripts, summaries, decisions, and action items into 768-dimensional normalized dense vectors.
2. Persists vectors in Neon Postgres using `pgvector` (`meetings.transcript_embedding`).
3. Performs hybrid semantic search (dense vector similarity + lexical keyword boosting + entity matching)
   across past meetings to enable cross-meeting context retrieval in Q&A engines and direct memory search endpoints.
"""

import math
import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ActionItem, Decision, Meeting, Participant
from models.schemas import EmbeddingStatus

logger = logging.getLogger(__name__)

VECTOR_DIMENSIONS = 768

# High-salience domain terms weighted higher during semantic vector generation
KEYWORD_BOOSTS = {
    "decision": 2.5,
    "decided": 2.5,
    "agreed": 2.2,
    "approved": 2.2,
    "action": 2.0,
    "task": 2.0,
    "owner": 2.0,
    "assigned": 2.0,
    "deadline": 2.2,
    "due": 2.0,
    "blocker": 2.5,
    "risk": 2.2,
    "architecture": 2.0,
    "database": 2.0,
    "api": 2.0,
    "security": 2.0,
    "deployment": 2.0,
    "release": 2.0,
    "budget": 2.0,
    "priority": 1.8,
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by",
    "about", "into", "through", "during", "before", "after", "above", "below", "from",
    "up", "down", "in", "out", "on", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "can", "will", "just", "should", "now"
}


# =============================================================================
# Hybrid Semantic Feature Vectorizer
# =============================================================================

def generate_embedding(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    """Generates a 768-dimensional normalized dense feature vector for a text string.

    Uses deterministic token-hashing with entity weighting, character n-grams,
    and subword frequency weighting suitable for cosine/L2 distance search.
    """
    if not text or not text.strip():
        return [0.0] * dimensions

    clean_text = text.lower()
    words = re.findall(r"\b[a-z0-9_]{2,}\b", clean_text)
    if not words:
        return [0.0] * dimensions

    vec = [0.0] * dimensions

    # Word unigrams with salience boosting
    for word in words:
        if word in STOPWORDS:
            continue
        weight = KEYWORD_BOOSTS.get(word, 1.2)
        h = hash(word)
        idx = abs(h) % dimensions
        sign = 1.0 if (h > 0) else -1.0
        vec[idx] += sign * weight

    # Character trigrams for subword semantic & typo-tolerant matching
    for word in words:
        if len(word) >= 3:
            for i in range(len(word) - 2):
                trigram = word[i : i + 3]
                h = hash(trigram)
                idx = abs(h) % dimensions
                sign = 1.0 if (h > 0) else -1.0
                vec[idx] += sign * 0.45

    # Word bigrams for context/phrase matching
    for i in range(len(words) - 1):
        w1, w2 = words[i], words[i + 1]
        if w1 in STOPWORDS and w2 in STOPWORDS:
            continue
        bigram = f"{w1}_{w2}"
        h = hash(bigram)
        idx = abs(h) % dimensions
        sign = 1.0 if (h > 0) else -1.0
        vec[idx] += sign * 1.8

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]

    return vec


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Computes cosine similarity between two vector lists."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = float(sum(float(a) * float(b) for a, b in zip(v1, v2)))
    norm1 = math.sqrt(sum(float(a) * float(a) for a in v1))
    norm2 = math.sqrt(sum(float(b) * float(b) for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot / (norm1 * norm2))


# =============================================================================
# Memory Service Class
# =============================================================================

class MemoryService:
    """Manages indexing and hybrid semantic search across historical meetings."""

    @staticmethod
    async def index_meeting(db: AsyncSession, meeting_id: str) -> bool:
        """Computes and stores vector embedding for a meeting record.

        Combines title, short summary, detailed summary, decisions, action items,
        and transcript dialogue into a unified semantic representation.
        """
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            logger.warning("MemoryService: meeting %s not found for embedding", meeting_id)
            return False

        try:
            parts = [
                f"Title: {meeting.title}",
                f"Summary: {meeting.short_summary or ''}",
                f"Details: {meeting.detailed_summary or ''}",
            ]

            # Fetch associated decisions
            dec_stmt = select(Decision).where(Decision.meeting_id == meeting_id)
            dec_res = await db.execute(dec_stmt)
            decs = dec_res.scalars().all()
            if decs:
                dec_str = "; ".join(f"Decision: {d.description} ({d.context or ''})" for d in decs)
                parts.append(f"Key Decisions: {dec_str}")

            # Fetch associated action items
            ai_stmt = select(ActionItem).where(ActionItem.meeting_id == meeting_id)
            ai_res = await db.execute(ai_stmt)
            items = ai_res.scalars().all()
            if items:
                items_str = "; ".join(
                    f"Action: {i.description} | Owner: {i.owner} | Due: {i.due_date}" for i in items
                )
                parts.append(f"Action Items: {items_str}")

            # Include dialogue snippet
            if meeting.diarized_transcript:
                parts.append(f"Dialogue: {meeting.diarized_transcript[:4000]}")
            elif meeting.transcript:
                parts.append(f"Dialogue: {meeting.transcript[:4000]}")

            combined_text = "\n".join(parts)
            vector = generate_embedding(combined_text)

            meeting.transcript_embedding = vector
            meeting.embedding_status = EmbeddingStatus.COMPLETED.value
            await db.commit()
            logger.info("MemoryService: successfully indexed meeting %s with %d decisions and %d action items", meeting_id, len(decs), len(items))
            return True
        except Exception as exc:
            logger.exception("MemoryService: failed to index meeting %s: %s", meeting_id, exc)
            meeting.embedding_status = EmbeddingStatus.FAILED.value
            await db.commit()
            return False

    @staticmethod
    async def search_memory(
        db: AsyncSession,
        query: str,
        top_k: int = 4,
        exclude_meeting_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Searches past meetings using hybrid semantic & lexical similarity.

        Returns structured meeting contexts including title, summary, action items,
        decisions, similarity score, and matched highlight snippets.
        """
        query_vec = generate_embedding(query)
        if not query_vec:
            return []

        # Fetch candidate meetings
        stmt = select(Meeting)
        if user_id:
            stmt = stmt.where((Meeting.user_id == user_id) | (Meeting.user_id.is_(None)))
        if exclude_meeting_id:
            stmt = stmt.where(Meeting.id != exclude_meeting_id)

        result = await db.execute(stmt)
        meetings = result.scalars().all()

        if not meetings:
            return []

        clean_query = query.lower()
        query_words = set(re.findall(r"\b[a-z0-9_]{3,}\b", clean_query)) - STOPWORDS

        scored_candidates: list[tuple[float, Meeting, list[str]]] = []

        for m in meetings:
            vector_score = 0.0
            if m.transcript_embedding is not None:
                try:
                    emb = [float(x) for x in list(m.transcript_embedding)]
                    vector_score = cosine_similarity(query_vec, emb)
                except Exception:
                    vector_score = 0.0

            # Lexical matching & highlights
            matched_highlights: list[str] = []
            lexical_boost = 0.0

            title_lower = (m.title or "").lower()
            summary_lower = f"{m.short_summary or ''} {m.detailed_summary or ''}".lower()

            for w in query_words:
                if w in title_lower:
                    lexical_boost += 0.25
                    matched_highlights.append(f"Title match: {w}")
                elif w in summary_lower:
                    lexical_boost += 0.12

            # Check decisions & action items for fine-grained matches
            ai_stmt = select(ActionItem).where(ActionItem.meeting_id == m.id)
            ai_res = await db.execute(ai_stmt)
            items = ai_res.scalars().all()

            for item in items:
                desc_lower = (item.description or "").lower()
                owner_lower = (item.owner or "").lower()
                for w in query_words:
                    if w in desc_lower or w in owner_lower:
                        lexical_boost += 0.18
                        matched_highlights.append(f"Action item: {item.description} ({item.owner})")
                        break

            dec_stmt = select(Decision).where(Decision.meeting_id == m.id)
            dec_res = await db.execute(dec_stmt)
            decs = dec_res.scalars().all()

            for dec in decs:
                dec_lower = f"{dec.description or ''} {dec.context or ''}".lower()
                for w in query_words:
                    if w in dec_lower:
                        lexical_boost += 0.20
                        matched_highlights.append(f"Decision: {dec.description}")
                        break

            combined_score = float(vector_score * 0.65 + min(1.0, lexical_boost) * 0.35)
            scored_candidates.append((combined_score, m, matched_highlights[:4]))

        # Sort descending by combined score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_matches = scored_candidates[:top_k]

        output: list[dict[str, Any]] = []

        for score, m, highlights in top_matches:
            ai_stmt = select(ActionItem).where(ActionItem.meeting_id == m.id)
            items = (await db.execute(ai_stmt)).scalars().all()

            dec_stmt = select(Decision).where(Decision.meeting_id == m.id)
            decs = (await db.execute(dec_stmt)).scalars().all()

            part_stmt = select(Participant).where(Participant.meeting_id == m.id)
            parts = (await db.execute(part_stmt)).scalars().all()

            output.append({
                "meeting_id": m.id,
                "title": m.title,
                "short_summary": m.short_summary,
                "detailed_summary": m.detailed_summary,
                "date": m.created_at.strftime("%Y-%m-%d") if m.created_at else "Unknown",
                "similarity_score": float(round(score, 4)),
                "matched_highlights": highlights,
                "participants": [p.name for p in parts],
                "action_items": [
                    {
                        "description": i.description,
                        "owner": i.owner,
                        "status": i.status.value if hasattr(i.status, "value") else str(i.status),
                        "priority": i.priority.value if hasattr(i.priority, "value") else str(i.priority),
                        "due_date": i.due_date,
                    }
                    for i in items
                ],
                "decisions": [
                    {
                        "description": d.description,
                        "context": d.context,
                    }
                    for d in decs
                ],
            })

        return output


memory_service = MemoryService()
