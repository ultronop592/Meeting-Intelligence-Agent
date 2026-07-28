"""
test_transcription.py — Unit tests for the audio chunking / transcription module.

All tests mock ffmpeg subprocess and the Groq API client so no real processes
or network calls are made.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from io import BytesIO


# Ensure env vars are set before importing app modules
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")

from agents.transcription import (
    _ffmpeg_available,
    _split_audio_with_ffmpeg,
    _transcribe_in_chunks,
    _validate_audio_file,
    transcribe_audio,
    MAX_GROQ_TRANSCRIPTION_BYTES,
)
from models.schemas import AgentState


# =============================================================================
# _validate_audio_file
# =============================================================================

def test_validate_audio_file_not_found():
    with pytest.raises(ValueError, match="Audio file not found"):
        _validate_audio_file("/nonexistent/path/audio.mp3")


def test_validate_audio_file_unsupported_format(tmp_path):
    fake = tmp_path / "recording.txt"
    fake.write_bytes(b"data")
    with pytest.raises(ValueError, match="Unsupported file format"):
        _validate_audio_file(str(fake))


def test_validate_audio_file_empty(tmp_path):
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="Audio file is empty"):
        _validate_audio_file(str(empty))


def test_validate_audio_file_valid(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake-audio-data")
    result = _validate_audio_file(str(audio))
    assert result == audio


def test_validate_audio_file_large_file_allowed(tmp_path):
    """Files > groq_transcription_max_bytes should NOT be rejected by validation
    anymore — the chunking layer handles them."""
    audio = tmp_path / "big.wav"
    audio.write_bytes(b"x")  # real small file, but we patch st_size

    original_stat = Path.stat

    def patched_stat(self, *args, **kwargs):
        result = original_stat(self, *args, **kwargs)
        # Only fake the size; preserve st_mode so is_file() still works
        import stat as stat_mod
        result = type(result)  # Can't set attrs on os.stat_result
        # Use os.stat_result via mock that delegates mode to real result
        real = original_stat(audio)
        mock_stat = MagicMock()
        mock_stat.st_size = MAX_GROQ_TRANSCRIPTION_BYTES + 1
        mock_stat.st_mode = real.st_mode
        return mock_stat

    with patch.object(Path, "stat", patched_stat):
        result = _validate_audio_file(str(audio))
        assert result.suffix == ".wav"


# =============================================================================
# _ffmpeg_available
# =============================================================================

def test_ffmpeg_available_when_present():
    with patch("agents.transcription.shutil.which", return_value="/usr/bin/ffmpeg"):
        assert _ffmpeg_available() is True


def test_ffmpeg_not_available():
    with patch("agents.transcription.shutil.which", return_value=None):
        assert _ffmpeg_available() is False


# =============================================================================
# _split_audio_with_ffmpeg
# =============================================================================

def test_split_audio_with_ffmpeg_success(tmp_path):
    """ffmpeg returns 0 and chunk files exist → returns sorted list of paths."""
    audio_path = tmp_path / "recording.mp3"
    audio_path.write_bytes(b"fake-mp3-data")

    # Create fake chunk files that ffmpeg would produce
    chunk_dir = str(tmp_path / "chunks")
    os.makedirs(chunk_dir)
    (Path(chunk_dir) / "chunk_000.mp3").write_bytes(b"chunk0")
    (Path(chunk_dir) / "chunk_001.mp3").write_bytes(b"chunk1")
    (Path(chunk_dir) / "chunk_002.mp3").write_bytes(b"chunk2")

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("agents.transcription.subprocess.run", return_value=mock_result):
        chunks = _split_audio_with_ffmpeg(audio_path, chunk_dir)

    assert len(chunks) == 3
    assert all(c.suffix == ".mp3" for c in chunks)
    assert chunks == sorted(chunks)


def test_split_audio_with_ffmpeg_failure(tmp_path):
    """Non-zero exit code from ffmpeg → RuntimeError."""
    audio_path = tmp_path / "recording.mp3"
    audio_path.write_bytes(b"fake-mp3-data")

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Error: Invalid data"

    with patch("agents.transcription.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="ffmpeg failed to split audio"):
            _split_audio_with_ffmpeg(audio_path, str(tmp_path / "chunks"))


def test_split_audio_no_chunks_produced(tmp_path):
    """ffmpeg succeeds but produces no output files → RuntimeError."""
    audio_path = tmp_path / "recording.wav"
    audio_path.write_bytes(b"data")

    mock_result = MagicMock()
    mock_result.returncode = 0

    chunk_dir = str(tmp_path / "empty_chunks")
    os.makedirs(chunk_dir)

    with patch("agents.transcription.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="produced no output chunks"):
            _split_audio_with_ffmpeg(audio_path, chunk_dir)


# =============================================================================
# _transcribe_in_chunks
# =============================================================================

def test_transcribe_in_chunks_ffmpeg_not_installed(tmp_path):
    """When ffmpeg is missing, raise ValueError with install instructions."""
    audio_path = tmp_path / "big.mp3"
    audio_path.write_bytes(b"x" * (MAX_GROQ_TRANSCRIPTION_BYTES + 1))

    with patch("agents.transcription._ffmpeg_available", return_value=False):
        with pytest.raises(ValueError, match="Install ffmpeg"):
            _transcribe_in_chunks(MagicMock(), audio_path)


def test_transcribe_in_chunks_merges_transcripts(tmp_path):
    """Two chunks each return text → merged with a space."""
    audio_path = tmp_path / "long.mp3"
    audio_path.write_bytes(b"x" * (MAX_GROQ_TRANSCRIPTION_BYTES + 1))

    chunk1 = tmp_path / "chunk_000.mp3"
    chunk2 = tmp_path / "chunk_001.mp3"
    chunk1.write_bytes(b"chunk1-audio")
    chunk2.write_bytes(b"chunk2-audio")

    with (
        patch("agents.transcription._ffmpeg_available", return_value=True),
        patch("agents.transcription._split_audio_with_ffmpeg", return_value=[chunk1, chunk2]),
        patch("agents.transcription._call_whisper_api", side_effect=["Hello world", "Goodbye world"]),
    ):
        result = _transcribe_in_chunks(MagicMock(), audio_path)

    assert result == "Hello world Goodbye world"


def test_transcribe_in_chunks_skips_empty_chunks(tmp_path):
    """Empty chunk transcripts are skipped; non-empty ones still merged."""
    audio_path = tmp_path / "long.mp3"
    audio_path.write_bytes(b"x" * (MAX_GROQ_TRANSCRIPTION_BYTES + 1))

    chunk1 = tmp_path / "chunk_000.mp3"
    chunk2 = tmp_path / "chunk_001.mp3"
    chunk1.write_bytes(b"audio1")
    chunk2.write_bytes(b"audio2")

    with (
        patch("agents.transcription._ffmpeg_available", return_value=True),
        patch("agents.transcription._split_audio_with_ffmpeg", return_value=[chunk1, chunk2]),
        patch("agents.transcription._call_whisper_api", side_effect=["Real transcript", ""]),
    ):
        result = _transcribe_in_chunks(MagicMock(), audio_path)

    assert result == "Real transcript"


def test_transcribe_in_chunks_all_empty_raises(tmp_path):
    """If all chunks are empty, RuntimeError is raised."""
    audio_path = tmp_path / "silent.mp3"
    audio_path.write_bytes(b"x" * (MAX_GROQ_TRANSCRIPTION_BYTES + 1))

    chunk1 = tmp_path / "chunk_000.mp3"
    chunk1.write_bytes(b"audio")

    with (
        patch("agents.transcription._ffmpeg_available", return_value=True),
        patch("agents.transcription._split_audio_with_ffmpeg", return_value=[chunk1]),
        patch("agents.transcription._call_whisper_api", return_value="   "),
    ):
        with pytest.raises(RuntimeError, match="no output"):
            _transcribe_in_chunks(MagicMock(), audio_path)


# =============================================================================
# transcribe_audio (LangGraph node)
# =============================================================================

def test_transcribe_audio_missing_path():
    state = AgentState(audio_file_path=None, audio_filename="test.mp3")
    result = transcribe_audio(state)
    assert any("missing" in e for e in result["errors"])


def test_transcribe_audio_no_api_key(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"data")
    state = AgentState(audio_file_path=str(audio), audio_filename="meeting.mp3")

    with patch("agents.transcription.settings") as mock_settings:
        mock_settings.groq_api_key = ""
        mock_settings.max_upload_size_bytes = 1024 * 1024 * 1024
        mock_settings.groq_transcription_max_bytes = 25 * 1024 * 1024
        result = transcribe_audio(state)

    assert any("GROQ_API_KEY" in e for e in result["errors"])


def test_transcribe_audio_small_file_direct_path(tmp_path):
    """Files under Groq limit go through the direct (non-chunked) path."""
    audio = tmp_path / "short.mp3"
    audio.write_bytes(b"small-audio-data")
    state = AgentState(audio_file_path=str(audio), audio_filename="short.mp3")

    with (
        patch("agents.transcription._call_whisper_api", return_value="Stand-up done."),
        patch("agents.transcription.Groq"),
    ):
        result = transcribe_audio(state)

    assert result["transcript"] == "Stand-up done."
    assert "transcribe_audio" in result["completed_nodes"]


def test_transcribe_audio_large_file_uses_chunking(tmp_path):
    """Files over Groq limit automatically use chunked transcription."""
    audio = tmp_path / "big_meeting.mp3"
    # Write content larger than the Groq limit so the real stat().st_size triggers
    big_content = b"x" * (MAX_GROQ_TRANSCRIPTION_BYTES + 1)
    audio.write_bytes(big_content)

    state = AgentState(audio_file_path=str(audio), audio_filename="big_meeting.mp3")

    with (
        patch("agents.transcription._transcribe_in_chunks", return_value="Full meeting transcript") as mock_chunk,
        patch("agents.transcription.Groq"),
    ):
        result = transcribe_audio(state)

    mock_chunk.assert_called_once()
    assert result["transcript"] == "Full meeting transcript"
    assert "transcribe_audio" in result["completed_nodes"]


def test_transcribe_audio_chunking_ffmpeg_missing(tmp_path):
    """When ffmpeg is absent and file is large, node returns a clear error."""
    audio = tmp_path / "big.mp3"
    big_content = b"x" * (MAX_GROQ_TRANSCRIPTION_BYTES + 1)
    audio.write_bytes(big_content)

    state = AgentState(audio_file_path=str(audio), audio_filename="big.mp3")

    with (
        patch("agents.transcription._transcribe_in_chunks",
              side_effect=ValueError("Install ffmpeg to enable automatic chunked transcription")),
        patch("agents.transcription.Groq"),
    ):
        result = transcribe_audio(state)

    # ValueError from _transcribe_in_chunks is caught as 'Audio validation failed: ...'
    assert result["errors"]
    combined = " ".join(result["errors"])
    assert "Install ffmpeg" in combined or "validation failed" in combined
