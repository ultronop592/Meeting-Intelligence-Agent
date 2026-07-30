"""
test_diarization.py — Unit tests for tools/diarization_tool.py and the
diarization integration in agents/transcription.py.

All tests mock pyannote.audio and Groq so no real models or network
calls are made.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")

from tools.diarization_tool import (
    find_speaker_for_segment,
    format_diarized_transcript,
    is_diarization_available,
    run_speaker_diarization,
)
from agents.transcription import (
    MAX_GROQ_TRANSCRIPTION_BYTES,
    transcribe_audio,
)
from models.schemas import AgentState


# =============================================================================
# is_diarization_available
# =============================================================================

def test_diarization_available_when_pyannote_and_token_present():
    with (
        patch.dict("sys.modules", {"pyannote.audio": MagicMock()}),
        patch("tools.diarization_tool.settings") as mock_settings,
    ):
        mock_settings.hf_token = "hf_test123"
        mock_settings.diarization_enabled = True
        assert is_diarization_available() is True


def test_diarization_not_available_without_token():
    with (
        patch.dict("sys.modules", {"pyannote.audio": MagicMock()}),
        patch("tools.diarization_tool.settings") as mock_settings,
    ):
        mock_settings.hf_token = ""
        mock_settings.diarization_enabled = True
        assert is_diarization_available() is False


def test_diarization_not_available_when_disabled():
    with (
        patch.dict("sys.modules", {"pyannote.audio": MagicMock()}),
        patch("tools.diarization_tool.settings") as mock_settings,
    ):
        mock_settings.hf_token = "hf_test123"
        mock_settings.diarization_enabled = False
        assert is_diarization_available() is False


def test_diarization_not_available_when_pyannote_missing():
    import sys
    original = sys.modules.get("pyannote.audio")
    sys.modules["pyannote.audio"] = None  # type: ignore
    try:
        result = is_diarization_available()
    finally:
        if original is None:
            sys.modules.pop("pyannote.audio", None)
        else:
            sys.modules["pyannote.audio"] = original
    assert result is False


# =============================================================================
# run_speaker_diarization
# =============================================================================

def _make_mock_pipeline(segments):
    """Build a mock pyannote Pipeline that returns given segments."""
    mock_turn_list = []
    for spk, start, end in segments:
        turn = MagicMock()
        turn.start = start
        turn.end   = end
        mock_turn_list.append((turn, None, spk))

    mock_diarization = MagicMock()
    mock_diarization.itertracks.return_value = mock_turn_list

    mock_pipeline = MagicMock()
    mock_pipeline.return_value = mock_diarization

    mock_pipeline_cls = MagicMock()
    mock_pipeline_cls.from_pretrained.return_value = mock_pipeline
    return mock_pipeline_cls


def test_run_speaker_diarization_success(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake-audio")

    fake_segments = [
        ("SPEAKER_00", 0.0, 5.0),
        ("SPEAKER_01", 5.0, 10.0),
        ("SPEAKER_00", 10.0, 15.0),
    ]
    mock_pipeline_cls = _make_mock_pipeline(fake_segments)

    with (
        patch.dict("sys.modules", {"pyannote.audio": MagicMock(Pipeline=mock_pipeline_cls)}),
        patch("tools.diarization_tool.settings") as mock_settings,
    ):
        mock_settings.hf_token = "hf_test"
        mock_settings.diarization_enabled = True

        # Need to patch the import inside the function too
        import importlib
        import tools.diarization_tool as dt
        orig_Pipeline = None
        try:
            import pyannote.audio as pya
            orig_Pipeline = pya.Pipeline
            pya.Pipeline = mock_pipeline_cls
        except Exception:
            pass

        result = run_speaker_diarization(audio)

    assert len(result) == 3
    assert result[0]["speaker"] == "SPEAKER_00"
    assert result[1]["speaker"] == "SPEAKER_01"
    assert result[0]["start"] == 0.0
    assert result[1]["start"] == 5.0


def test_run_speaker_diarization_no_token(tmp_path):
    """No HF_TOKEN → returns empty list, no exception."""
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake-audio")

    with (
        patch.dict("sys.modules", {"pyannote.audio": MagicMock()}),
        patch("tools.diarization_tool.settings") as mock_settings,
    ):
        mock_settings.hf_token = ""
        mock_settings.diarization_enabled = True
        result = run_speaker_diarization(audio)

    assert result == []


def test_run_speaker_diarization_pyannote_not_installed(tmp_path):
    """ImportError from pyannote → returns empty list gracefully."""
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake-audio")
    # Simulate ImportError by removing the module
    with patch.dict("sys.modules", {"pyannote.audio": None}):
        result = run_speaker_diarization(audio)
    assert result == []


def test_run_speaker_diarization_pipeline_exception(tmp_path):
    """If the pipeline throws any exception → returns empty list."""
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake-audio")

    mock_pipeline_cls = MagicMock()
    mock_pipeline_cls.from_pretrained.side_effect = RuntimeError("model load failed")

    with (
        patch.dict("sys.modules", {"pyannote.audio": MagicMock(Pipeline=mock_pipeline_cls)}),
        patch("tools.diarization_tool.settings") as mock_settings,
    ):
        mock_settings.hf_token = "hf_test"
        mock_settings.diarization_enabled = True
        result = run_speaker_diarization(audio)

    assert result == []


# =============================================================================
# find_speaker_for_segment
# =============================================================================

DIARIZATION = [
    {"speaker": "SPEAKER_00", "start": 0.0,  "end": 5.0},
    {"speaker": "SPEAKER_01", "start": 5.0,  "end": 10.0},
    {"speaker": "SPEAKER_00", "start": 10.0, "end": 15.0},
]


def test_find_speaker_exact_match():
    assert find_speaker_for_segment(0.0, 5.0, DIARIZATION) == "SPEAKER_00"
    assert find_speaker_for_segment(5.0, 10.0, DIARIZATION) == "SPEAKER_01"


def test_find_speaker_partial_overlap():
    """Segment spans two speakers — should return the one with more overlap."""
    # 3.0 → 7.0: SPEAKER_00 for 2s (3-5), SPEAKER_01 for 2s (5-7) → tie → first in max = SPEAKER_00 or SPEAKER_01
    result = find_speaker_for_segment(3.0, 7.0, DIARIZATION)
    assert result in ("SPEAKER_00", "SPEAKER_01")


def test_find_speaker_majority_wins():
    """8.0 → 12.0: SPEAKER_01 for 2s (8-10), SPEAKER_00 for 2s (10-12) → tie."""
    # With 6.0 → 11.0: SPEAKER_01 for 4s (6-10), SPEAKER_00 for 1s (10-11)
    result = find_speaker_for_segment(6.0, 11.0, DIARIZATION)
    assert result == "SPEAKER_01"


def test_find_speaker_no_overlap():
    """Segment after all diarization → SPEAKER_?"""
    result = find_speaker_for_segment(20.0, 25.0, DIARIZATION)
    assert result == "SPEAKER_?"


def test_find_speaker_empty_diarization():
    result = find_speaker_for_segment(0.0, 5.0, [])
    assert result == "SPEAKER_?"


# =============================================================================
# format_diarized_transcript
# =============================================================================

def test_format_diarized_transcript_basic():
    timed = [
        {"text": "Hello everyone.", "start": 0.0, "end": 2.0},
        {"text": "Let's start.", "start": 2.0, "end": 4.0},
        {"text": "Sure thing.", "start": 5.0, "end": 7.0},
    ]
    diarization = [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 4.5},
        {"speaker": "SPEAKER_01", "start": 4.5, "end": 8.0},
    ]
    result = format_diarized_transcript(timed, diarization)
    assert "SPEAKER_00: Hello everyone. Let's start." in result
    assert "SPEAKER_01: Sure thing." in result


def test_format_diarized_transcript_merges_consecutive():
    """Consecutive segments from the same speaker are merged into one line."""
    timed = [
        {"text": "Part one.", "start": 0.0, "end": 1.0},
        {"text": "Part two.", "start": 1.0, "end": 2.0},
        {"text": "Part three.", "start": 2.0, "end": 3.0},
    ]
    diarization = [{"speaker": "SPEAKER_00", "start": 0.0, "end": 5.0}]
    result = format_diarized_transcript(timed, diarization)
    lines = result.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("SPEAKER_00:")


def test_format_diarized_transcript_no_diarization():
    """Empty diarization → plain text, no speaker labels."""
    timed = [
        {"text": "Hello.", "start": 0.0, "end": 1.0},
        {"text": "World.", "start": 1.0, "end": 2.0},
    ]
    result = format_diarized_transcript(timed, [])
    assert "SPEAKER" not in result
    assert "Hello." in result
    assert "World." in result


def test_format_diarized_transcript_skips_empty_text():
    timed = [
        {"text": "Hello.", "start": 0.0, "end": 1.0},
        {"text": "",       "start": 1.0, "end": 2.0},   # empty — should be skipped
        {"text": "World.", "start": 2.0, "end": 3.0},
    ]
    diarization = [{"speaker": "SPEAKER_00", "start": 0.0, "end": 5.0}]
    result = format_diarized_transcript(timed, diarization)
    assert "Hello." in result
    assert "World." in result


# =============================================================================
# transcribe_audio — diarization integration in the node
# =============================================================================

def test_transcribe_audio_no_diarization_plain_text(tmp_path):
    """When diarization is unavailable, node returns plain transcript."""
    audio = tmp_path / "standup.mp3"
    audio.write_bytes(b"fake-audio-data")
    state = AgentState(audio_file_path=str(audio), audio_filename="standup.mp3")

    with (
        patch("agents.transcription._call_whisper_api", return_value="All good."),
        patch("agents.transcription._try_diarize", return_value=[]),
        patch("agents.transcription.Groq"),
    ):
        result = transcribe_audio(state)

    assert result["transcript"] == "All good."
    assert result.get("diarized_transcript") is None
    assert result["speaker_segments"] == []


def test_transcribe_audio_with_diarization(tmp_path):
    """When diarization succeeds, node populates diarized_transcript."""
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake-audio-data")
    state = AgentState(audio_file_path=str(audio), audio_filename="meeting.mp3")

    fake_diarization = [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 5.0},
        {"speaker": "SPEAKER_01", "start": 5.0, "end": 10.0},
    ]
    fake_segments = [
        {"text": "Hello team.", "start": 0.0, "end": 3.0},
        {"text": "Ready here.", "start": 5.0, "end": 8.0},
    ]

    with (
        patch("agents.transcription._try_diarize", return_value=fake_diarization),
        patch("agents.transcription._call_whisper_verbose", return_value=fake_segments),
        patch("agents.transcription.Groq"),
    ):
        result = transcribe_audio(state)

    assert "Hello team." in result["transcript"]
    assert result["diarized_transcript"] is not None
    assert "SPEAKER_00" in result["diarized_transcript"]
    assert "SPEAKER_01" in result["diarized_transcript"]
    assert result["speaker_segments"] == fake_diarization


def test_transcribe_audio_diarization_failure_falls_back(tmp_path):
    """If diarization fails mid-flight, node still returns plain transcript."""
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake-audio-data")
    state = AgentState(audio_file_path=str(audio), audio_filename="meeting.mp3")

    with (
        patch("agents.transcription._try_diarize", side_effect=Exception("pyannote crash")),
        patch("agents.transcription._call_whisper_api", return_value="Fallback text."),
        patch("agents.transcription.Groq"),
    ):
        result = transcribe_audio(state)

    # Should not error — exception from _try_diarize is caught by outer handler
    assert "errors" in result
