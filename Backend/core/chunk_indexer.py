"""
core/chunk_indexer.py — Phase 6: Chunk-Level Transcript Indexer

WHAT IT DOES
------------
Splits a meeting's diarized or plain transcript into ~30-60 second windows,
generates a 768-dim embedding per chunk using the same hash-based vectorizer as
memory_service.py, and upserts rows into the `transcript_chunks` table.

Each chunk records:
  - start_sec / end_sec  : position in the audio (seconds)
  - speaker              : dominant speaker label in that window
  - text                 : verbatim dialogue text
  - embedding            : 768-dim float vector for pgvector cosine search

Chunking strategy
-----------------
1. If `transcript_words` JSON is present (word-level timing from Whisper), use it
   to build windows of exactly CHUNK_WINDOW_SEC seconds with CHUNK_OVERLAP_SEC
   overlap to avoid cutting mid-sentence.
2. If only plain/diarized text is available, fall back to sentence-splitting with
   TARGET_CHUNK_TOKENS approximate token count.
"""

import logging
import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory_service import generate_embedding
from db.models import Meeting, TranscriptChunk

logger = logging.getLogger(__name__)

# Tunable constants
CHUNK_WINDOW_SEC  = 45    # target window length in seconds
CHUNK_OVERLAP_SEC = 10    # overlap to avoid boundary cut-offs
TARGET_CHUNK_TOKENS = 200  # approx tokens per chunk for text-only fallback (~150 words)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS string, e.g. 125.4 → '2:05'."""
    minutes = int(seconds) // 60
    secs    = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


def _dominant_speaker(word_list: list[dict]) -> str | None:
    """Return the speaker label that produced the most words in a window."""
    counts: dict[str, int] = {}
    for w in word_list:
        sp = w.get("speaker") or w.get("speaker_label")
        if sp:
            counts[sp] = counts.get(sp, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _build_chunks_from_words(words: list[dict]) -> list[dict]:
    """Build timed chunks from Whisper word-level JSON.

    Each word dict is expected to have keys: `word`, `start`, `end`, and
    optionally `speaker` or `speaker_label`.
    """
    if not words:
        return []

    chunks = []
    window_start = words[0].get("start", 0.0)
    window_words: list[dict] = []

    for w in words:
        w_start = float(w.get("start", 0.0))
        w_end   = float(w.get("end",   w_start + 0.1))

        # Flush when window exceeds target length
        if window_words and (w_start - window_start) >= CHUNK_WINDOW_SEC:
            chunks.append({
                "start_sec": window_start,
                "end_sec":   w_end,
                "speaker":   _dominant_speaker(window_words),
                "text":      " ".join(wd.get("word", "") for wd in window_words).strip(),
                "words":     window_words,
            })
            # Slide window: keep overlap words
            overlap_cutoff = w_start - CHUNK_OVERLAP_SEC
            window_words   = [wd for wd in window_words if float(wd.get("start", 0)) >= overlap_cutoff]
            window_start   = window_words[0]["start"] if window_words else w_start

        window_words.append(w)

    # Final chunk
    if window_words:
        last_end = float(words[-1].get("end", window_start))
        chunks.append({
            "start_sec": window_start,
            "end_sec":   last_end,
            "speaker":   _dominant_speaker(window_words),
            "text":      " ".join(wd.get("word", "") for wd in window_words).strip(),
            "words":     window_words,
        })

    return chunks


def _build_chunks_from_text(text: str, seconds_per_word: float = 0.4) -> list[dict]:
    """Fallback: split plain/diarized text into approximate time windows.

    Estimates timestamps using a constant seconds-per-word rate (≈ 150 wpm).
    Parses diarized format:  [SPEAKER_01 00:00:05] Some words here
    """
    # Try to detect diarized format with timestamps
    speaker_pattern = re.compile(
        r"\[([A-Z_0-9]+)\s+(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.*?)(?=\[|\Z)", re.DOTALL
    )
    matches = list(speaker_pattern.finditer(text))

    if matches:
        # Build word list from diarized blocks
        words: list[dict] = []
        for m in matches:
            speaker  = m.group(1)
            ts_str   = m.group(2)
            block    = m.group(3).strip()
            # Parse timestamp
            ts_parts = ts_str.split(":")
            if len(ts_parts) == 2:
                start = int(ts_parts[0]) * 60 + int(ts_parts[1])
            else:
                start = int(ts_parts[0]) * 3600 + int(ts_parts[1]) * 60 + int(ts_parts[2])

            block_words = block.split()
            for i, w in enumerate(block_words):
                words.append({
                    "word":    w,
                    "start":   start + i * seconds_per_word,
                    "end":     start + (i + 1) * seconds_per_word,
                    "speaker": speaker,
                })
        return _build_chunks_from_words(words)

    # Flat text fallback: no timing info
    all_words = text.split()
    chunks = []
    target_words = int(CHUNK_WINDOW_SEC / seconds_per_word)
    overlap_words = int(CHUNK_OVERLAP_SEC / seconds_per_word)
    i = 0
    chunk_idx = 0
    while i < len(all_words):
        window = all_words[i : i + target_words]
        start_sec = i * seconds_per_word
        end_sec   = (i + len(window)) * seconds_per_word
        chunks.append({
            "start_sec": start_sec,
            "end_sec":   end_sec,
            "speaker":   None,
            "text":      " ".join(window),
        })
        i += target_words - overlap_words
        chunk_idx += 1

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def index_meeting_chunks(db: AsyncSession, meeting_id: str) -> int:
    """Delete old chunks for a meeting and re-index with fresh embeddings.

    Returns the number of chunks written, or 0 on failure.
    """
    meeting: Meeting | None = await db.get(Meeting, meeting_id)
    if not meeting:
        logger.warning("chunk_indexer: meeting %s not found", meeting_id)
        return 0

    try:
        # --- 1. Build raw chunk dicts ----------------------------------------
        raw_chunks: list[dict] = []

        if meeting.transcript_words:
            # Best quality: word-level Whisper timing
            words = meeting.transcript_words
            if isinstance(words, list) and words:
                raw_chunks = _build_chunks_from_words(words)

        if not raw_chunks:
            # Fallback to diarized or plain text
            text = meeting.diarized_transcript or meeting.transcript or ""
            if text.strip():
                raw_chunks = _build_chunks_from_text(text)

        if not raw_chunks:
            logger.info("chunk_indexer: no transcript data for meeting %s", meeting_id)
            return 0

        # --- 2. Delete stale chunks -----------------------------------------
        await db.execute(
            delete(TranscriptChunk).where(TranscriptChunk.meeting_id == meeting_id)
        )

        # --- 3. Embed and insert --------------------------------------------
        chunk_objects: list[TranscriptChunk] = []
        for idx, raw in enumerate(raw_chunks):
            text_content = raw.get("text", "").strip()
            if not text_content:
                continue

            # Enrich embedding text with speaker + timestamp context
            speaker_tag = f"[{raw['speaker']}] " if raw.get("speaker") else ""
            ts_tag      = f"[{_format_timestamp(raw['start_sec'])}] "
            embed_text  = f"{speaker_tag}{ts_tag}{text_content}"

            embedding = generate_embedding(embed_text)

            chunk_objects.append(
                TranscriptChunk(
                    meeting_id  = meeting_id,
                    chunk_index = idx,
                    start_sec   = raw["start_sec"],
                    end_sec     = raw["end_sec"],
                    speaker     = raw.get("speaker"),
                    text        = text_content,
                    embedding   = embedding,
                )
            )

        db.add_all(chunk_objects)
        await db.commit()

        logger.info(
            "chunk_indexer: indexed %d chunks for meeting %s (%.1f–%.1f sec)",
            len(chunk_objects),
            meeting_id,
            raw_chunks[0]["start_sec"] if raw_chunks else 0,
            raw_chunks[-1]["end_sec"]  if raw_chunks else 0,
        )
        return len(chunk_objects)

    except Exception as exc:
        logger.exception("chunk_indexer: failed to index meeting %s: %s", meeting_id, exc)
        await db.rollback()
        return 0
