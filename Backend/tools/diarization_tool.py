"""
tools/diarization_tool.py — Optional speaker diarization using pyannote.audio.

WHAT IT DOES
------------
Identifies WHO spoke WHEN in a meeting recording, returning a list of
time-stamped speaker segments, for example:

    [
        {"speaker": "SPEAKER_00", "start": 0.0,  "end": 5.2},
        {"speaker": "SPEAKER_01", "start": 5.2,  "end": 12.7},
        {"speaker": "SPEAKER_00", "start": 12.7, "end": 18.0},
    ]

These segments are merged with Groq Whisper's timed transcript segments
(verbose_json format) to produce a fully labelled transcript:

    SPEAKER_00: Hello everyone, let's get started with the standup.
    SPEAKER_01: Sure, I'll share my updates from last week.
    SPEAKER_00: Great, please go ahead.

SETUP (optional — transcription works without this)
---------------------------------------------------
1. Install the library (heavy — downloads ~1 GB of model weights):
       pip install pyannote.audio

2. Accept the model card terms (requires a free HuggingFace account):
       https://hf.co/pyannote/speaker-diarization-3.1
       https://hf.co/pyannote/segmentation-3.0

3. Create a read-only HuggingFace access token:
       https://hf.co/settings/tokens

4. Add to Backend/.env:
       HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
       DIARIZATION_ENABLED=true

GRACEFUL DEGRADATION
--------------------
If any of the above is missing — HF_TOKEN not set, pyannote.audio not
installed, or DIARIZATION_ENABLED=false — every function in this module
returns an empty list and the transcription pipeline produces plain text
exactly as before. No errors are raised.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Availability check
# =============================================================================

def is_diarization_available() -> bool:
    """Return True if pyannote.audio is installed AND HF_TOKEN is configured."""
    try:
        import pyannote.audio  # noqa: F401  — just checking the import
        from core.config import settings
        return bool(settings.hf_token) and settings.diarization_enabled
    except ImportError:
        return False


# =============================================================================
# Core diarization
# =============================================================================

def run_speaker_diarization(
    audio_path: Path,
    num_speakers: Optional[int] = None,
) -> list[dict]:
    """Run speaker diarization on *audio_path* using pyannote/speaker-diarization-3.1.

    Args:
        audio_path:   Path to the audio file (any format supported by ffmpeg).
        num_speakers: Hint for exact speaker count. Leave None for automatic detection.

    Returns:
        Sorted list of ``{"speaker": str, "start": float, "end": float}`` dicts.
        Returns an **empty list** if diarization is unavailable (graceful degradation).
    """
    try:
        from pyannote.audio import Pipeline
        from core.config import settings

        if not settings.hf_token:
            logger.info("Diarization skipped — HF_TOKEN not configured.")
            return []

        if not settings.diarization_enabled:
            logger.info("Diarization skipped — DIARIZATION_ENABLED=false.")
            return []

        logger.info(
            "Loading pyannote speaker-diarization-3.1 pipeline | file=%s",
            audio_path.name,
        )
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=settings.hf_token,
        )

        kwargs: dict = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers

        logger.info("Running diarization | file=%s", audio_path.name)
        diarization = pipeline(str(audio_path), **kwargs)

        segments: list[dict] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "speaker": speaker,
                "start":   round(turn.start, 3),
                "end":     round(turn.end, 3),
            })

        segments.sort(key=lambda s: s["start"])

        speaker_ids = sorted({s["speaker"] for s in segments})
        logger.info(
            "Diarization complete | segments=%d | speakers=%d | ids=%s",
            len(segments),
            len(speaker_ids),
            speaker_ids,
        )
        return segments

    except ImportError:
        logger.warning(
            "pyannote.audio not installed — speaker diarization disabled. "
            "Run: pip install pyannote.audio"
        )
        return []
    except Exception as exc:
        logger.error("Speaker diarization failed: %s", exc)
        return []


# =============================================================================
# Merge helpers
# =============================================================================

def find_speaker_for_segment(
    start: float,
    end: float,
    diarization: list[dict],
) -> str:
    """Return the speaker label with the most overlap in the time window [start, end].

    Args:
        start:       Segment start time in seconds.
        end:         Segment end time in seconds.
        diarization: Output of :func:`run_speaker_diarization`.

    Returns:
        Speaker label string, e.g. ``"SPEAKER_00"``.
        Returns ``"SPEAKER_?"`` if no diarization segment overlaps.
    """
    overlap: dict[str, float] = {}
    for seg in diarization:
        if seg["end"] <= start or seg["start"] >= end:
            continue
        o_start = max(seg["start"], start)
        o_end   = min(seg["end"],   end)
        speaker = seg["speaker"]
        overlap[speaker] = overlap.get(speaker, 0.0) + (o_end - o_start)

    if not overlap:
        return "SPEAKER_?"

    return max(overlap, key=overlap.__getitem__)


def format_diarized_transcript(
    timed_segments: list[dict],
    diarization: list[dict],
) -> str:
    """Assign a speaker to each whisper segment and format as labelled text.

    Consecutive segments from the same speaker are merged into one paragraph.

    Args:
        timed_segments: List of ``{"text": str, "start": float, "end": float}``
                        dicts from Groq Whisper verbose_json response.
        diarization:    Output of :func:`run_speaker_diarization`.

    Returns:
        Multi-line string where each line starts with a speaker label::

            SPEAKER_00: Hello everyone, let's get started.
            SPEAKER_01: Sure, I'll begin with last week's update.
    """
    if not diarization:
        # No diarization — just concatenate all segment texts
        return " ".join(seg["text"].strip() for seg in timed_segments if seg.get("text"))

    labelled: list[dict] = []
    for seg in timed_segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        speaker = find_speaker_for_segment(seg["start"], seg["end"], diarization)
        labelled.append({"speaker": speaker, "text": text})

    # Merge consecutive same-speaker segments into one line
    lines: list[str] = []
    prev_speaker: Optional[str] = None
    current_parts: list[str] = []

    for item in labelled:
        if item["speaker"] != prev_speaker:
            if prev_speaker is not None and current_parts:
                lines.append(f"{prev_speaker}: {' '.join(current_parts)}")
            current_parts = [item["text"]]
            prev_speaker  = item["speaker"]
        else:
            current_parts.append(item["text"])

    if prev_speaker and current_parts:
        lines.append(f"{prev_speaker}: {' '.join(current_parts)}")

    return "\n".join(lines)
