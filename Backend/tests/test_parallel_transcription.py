"""Tests for Phase 3 Step 2: VAD silence-aware cutting, parallel chunk transcription,
boundary deduplication, and global speaker consistency.
"""
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.transcription import (
    _compute_smart_cut_points,
    _deduplicate_boundary_text,
    _detect_silence_intervals,
    _transcribe_in_chunks,
    assign_speakers_to_words,
)


def test_detect_silence_intervals_parsing():
    """Verify regex parsing of ffmpeg silencedetect stderr output."""
    fake_stderr = """
[silencedetect @ 000001] silence_start: 595.234
[silencedetect @ 000001] silence_end: 596.102 | silence_duration: 0.868
[silencedetect @ 000001] silence_start: 1198.5
[silencedetect @ 000001] silence_end: 1200.0 | silence_duration: 1.5
    """
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stderr = fake_stderr

    with (
        patch("agents.transcription._ffmpeg_available", return_value=True),
        patch("agents.transcription.subprocess.run", return_value=mock_run),
    ):
        intervals = _detect_silence_intervals(Path("dummy.mp3"))

    assert len(intervals) == 2
    assert intervals[0] == (595.234, 596.102)
    assert intervals[1] == (1198.5, 1200.0)


def test_compute_smart_cut_points_selects_pauses():
    """Verify smart cut points choose silence center near 600s instead of rigid cutting."""
    total_duration = 1800.0  # 30 min audio
    silences = [
        (200.0, 201.0),
        (594.0, 596.0),  # Close to 600s (center: 595.0)
        (1202.0, 1204.0), # Close to 1200s (center: 1203.0)
    ]

    cut_points = _compute_smart_cut_points(
        total_duration=total_duration,
        target_chunk_duration=600.0,
        search_window=30.0,
        silences=silences,
    )

    assert len(cut_points) == 2
    assert cut_points[0] == 595.0  # Chose silence center rather than 600.0
    assert cut_points[1] == 1203.0  # Chose silence center rather than 1200.0


def test_compute_smart_cut_points_fallback_when_no_silence():
    """Verify fallback to exact target when no silence pause exists in search window."""
    total_duration = 1500.0
    silences = [(100.0, 102.0)]  # None near 600s or 1200s

    cut_points = _compute_smart_cut_points(
        total_duration=total_duration,
        target_chunk_duration=600.0,
        search_window=30.0,
        silences=silences,
    )

    assert len(cut_points) == 2
    assert cut_points[0] == 600.0
    assert cut_points[1] == 1200.0


def test_deduplicate_boundary_text():
    """Verify removal of duplicated phrases across chunk seams."""
    # Suffix of chunk1 matches prefix of chunk2
    chunk1 = "We will review the quarterly budget next Tuesday morning."
    chunk2 = "Tuesday morning we will also discuss infrastructure costs."

    merged = _deduplicate_boundary_text(chunk1, chunk2, max_overlap_words=10)
    assert merged == "We will review the quarterly budget next Tuesday morning. we will also discuss infrastructure costs."

    # No duplicate overlap
    chunk_a = "First topic is authentication."
    chunk_b = "Second topic is database caching."
    merged_clean = _deduplicate_boundary_text(chunk_a, chunk_b)
    assert merged_clean == "First topic is authentication. Second topic is database caching."


def test_parallel_chunk_transcription_execution(tmp_path):
    """Verify chunks are transcribed in parallel with correct timestamp offsets."""
    audio_path = tmp_path / "long_meeting.mp3"
    audio_path.write_bytes(b"x" * 1000)

    chunk0 = tmp_path / "chunk_000.mp3"
    chunk1 = tmp_path / "chunk_001.mp3"
    chunk2 = tmp_path / "chunk_002.mp3"
    chunk0.write_bytes(b"c0")
    chunk1.write_bytes(b"c1")
    chunk2.write_bytes(b"c2")

    mock_client = MagicMock()

    # Simulate verbose transcription for 3 chunks with artificial delay
    def mock_verbose(client, path):
        time.sleep(0.05)  # slight delay to prove parallel execution
        idx = int(path.stem.split("_")[-1])
        return [
            {"text": f"Chunk {idx} discussion.", "start": 1.0, "end": 4.0},
        ]

    with (
        patch("agents.transcription._ffmpeg_available", return_value=True),
        patch("agents.transcription._split_audio_with_ffmpeg", return_value=[chunk0, chunk1, chunk2]),
        patch("agents.transcription._call_whisper_verbose", side_effect=mock_verbose),
    ):
        t0 = time.perf_counter()
        plain, timed_segments = _transcribe_in_chunks(
            mock_client,
            audio_path,
            want_timed=True,
            concurrency=3,
        )
        elapsed = time.perf_counter() - t0

    # 3 chunks of 0.05s in parallel should take ~0.05-0.10s, NOT sequential 0.15s
    assert elapsed < 0.14
    assert len(timed_segments) == 3
    # Verify accurate global offsets applied (chunk 0 @ 0s, chunk 1 @ 600s, chunk 2 @ 1200s)
    assert timed_segments[0]["start"] == 1.0
    assert timed_segments[0]["end"] == 4.0
    assert timed_segments[1]["start"] == 601.0
    assert timed_segments[1]["end"] == 604.0
    assert timed_segments[2]["start"] == 1201.0
    assert timed_segments[2]["end"] == 1204.0


def test_global_speaker_consistency_across_chunks():
    """Verify global diarization segments properly label words across chunk boundaries."""
    # Global speaker timeline from whole-file diarization
    speaker_segments = [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 45.0},
        {"speaker": "SPEAKER_01", "start": 45.0, "end": 90.0},
        {"speaker": "SPEAKER_00", "start": 610.0, "end": 640.0},  # Same speaker in chunk 2!
    ]

    # Words with global offsets: chunk 1 words (0-60s) and chunk 2 words (600s+)
    words = [
        {"word": "Welcome", "start": 5.0, "end": 5.5},       # in chunk 1 -> SPEAKER_00
        {"word": "Thanks", "start": 50.0, "end": 50.4},      # in chunk 1 -> SPEAKER_01
        {"word": "Continuing", "start": 615.0, "end": 616.0},# in chunk 2 -> SPEAKER_00 (consistent!)
    ]

    labeled_words = assign_speakers_to_words(words, speaker_segments)

    assert labeled_words[0]["speaker"] == "SPEAKER_00"
    assert labeled_words[1]["speaker"] == "SPEAKER_01"
    assert labeled_words[2]["speaker"] == "SPEAKER_00"  # Consistency preserved across chunk 2!
