"""
agents/transcription.py  — Node 1 of the LangGraph pipeline.

WHAT IT DOES
------------
Transcribes an audio recording to plain text using Groq Whisper (whisper-large-v3).

SINGLE-FILE LIMIT HANDLING
--------------------------
Groq's Whisper API limits each request to 25 MB.
For files that exceed this limit the module now automatically:
  1. Detects that ffmpeg is available on PATH.
  2. Splits the audio into equal-duration chunks (default: 10 min each)
     using the ffmpeg segment muxer — no re-encoding, very fast.
  3. Sends each chunk to Whisper independently with full retry logic.
  4. Joins the chunk transcripts with a single space to produce the
     complete transcript.

If ffmpeg is NOT installed and a file exceeds the limit, the node returns
a clear error message with installation instructions rather than crashing.

SUPPORTED FORMATS
-----------------
.mp3 .wav .m4a .ogg .flac .webm .mp4
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from groq import APIConnectionError, APIError, APITimeoutError, Groq, RateLimitError
from langsmith import traceable
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import settings
from models.schemas import AgentState

logger = logging.getLogger(__name__)

WHISPER_MODEL = "whisper-large-v3"
SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}
MAX_FILE_SIZE_BYTES = settings.max_upload_size_bytes
MAX_GROQ_TRANSCRIPTION_BYTES = settings.groq_transcription_max_bytes

# Duration of each audio chunk when splitting large files (seconds).
# 10 min @ 128 kbps MP3 ≈ 9.6 MB — well under Groq's 25 MB limit.
CHUNK_DURATION_SECONDS = settings.audio_chunk_duration_seconds


# =============================================================================
# Validation
# =============================================================================

def _validate_audio_file(file_path: str) -> Path:
    """Validate that the file exists, has a supported format, and is within the
    overall upload size limit.

    NOTE: Files exceeding MAX_GROQ_TRANSCRIPTION_BYTES are now *allowed* here;
    the chunking layer handles them transparently.
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"Audio file not found: {file_path}")

    lower_name = path.name.lower()
    suffix = ".mp4" if lower_name.endswith(".mp.4") else path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported file format: {suffix}")

    file_size = path.stat().st_size
    if file_size == 0:
        raise ValueError("Audio file is empty")
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"Audio file too large: {file_size / (1024 * 1024):.2f} MB "
            f"> {MAX_FILE_SIZE_BYTES / (1024 * 1024):.2f} MB max upload limit"
        )

    return path


# =============================================================================
# Whisper API call (with retry)
# =============================================================================

@retry(
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _call_whisper_api(client: Groq, audio_path: Path) -> str:
    with open(audio_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=audio_file,
            response_format="text",
            language="en",
        )
    return str(response)


# =============================================================================
# Audio chunking (ffmpeg-based, for files > Groq 25 MB limit)
# =============================================================================

def _ffmpeg_available() -> bool:
    """Return True if ffmpeg is found on the system PATH."""
    return shutil.which("ffmpeg") is not None


def _split_audio_with_ffmpeg(audio_path: Path, chunk_dir: str) -> list[Path]:
    """Use ffmpeg's segment muxer to split *audio_path* into equal-duration chunks.

    The split uses stream-copy (`-c copy`) — no re-encoding — so it is very
    fast and lossless.  Each chunk is named ``chunk_000.ext``, ``chunk_001.ext``, etc.

    Args:
        audio_path: Path to the source audio file.
        chunk_dir:  Directory where chunk files will be written.

    Returns:
        Sorted list of chunk file paths.

    Raises:
        RuntimeError: If ffmpeg exits with a non-zero return code.
    """
    suffix = audio_path.suffix.lower()
    output_pattern = os.path.join(chunk_dir, f"chunk_%03d{suffix}")

    cmd = [
        "ffmpeg",
        "-i", str(audio_path),
        "-f", "segment",
        "-segment_time", str(CHUNK_DURATION_SECONDS),
        "-c", "copy",                # stream-copy: no re-encode, very fast
        "-reset_timestamps", "1",    # timestamps restart at 0 for each chunk
        output_pattern,
        "-y",                        # overwrite if somehow a file exists
        "-loglevel", "error",        # suppress progress noise; keep errors
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr_preview = result.stderr[:600].strip()
        raise RuntimeError(
            f"ffmpeg failed to split audio (exit {result.returncode}):\n{stderr_preview}"
        )

    chunks = sorted(Path(chunk_dir).glob(f"chunk_*{suffix}"))
    if not chunks:
        raise RuntimeError(
            "ffmpeg ran but produced no output chunks. "
            "The audio file may be corrupt or in an unsupported container."
        )

    logger.info(
        "Audio split into %d chunk(s) of ~%ds each | source=%s",
        len(chunks),
        CHUNK_DURATION_SECONDS,
        audio_path.name,
    )
    return chunks


def _transcribe_in_chunks(client: Groq, audio_path: Path) -> str:
    """Split *audio_path* into chunks and transcribe each one.

    Chunk transcripts are joined with a single space so the output reads as
    one continuous document.

    Args:
        client:     Authenticated Groq client.
        audio_path: Path to the large audio file (> Groq 25 MB limit).

    Returns:
        Full merged transcript string.

    Raises:
        ValueError:  ffmpeg is not installed.
        RuntimeError: Splitting or all-chunks-empty.
    """
    if not _ffmpeg_available():
        raise ValueError(
            f"Audio file is {audio_path.stat().st_size / (1024 * 1024):.1f} MB, "
            f"which exceeds Groq's {MAX_GROQ_TRANSCRIPTION_BYTES // (1024 * 1024)} MB "
            "per-request limit. "
            "Install ffmpeg to enable automatic chunked transcription: "
            "https://ffmpeg.org/download.html  "
            "(Windows: winget install ffmpeg  |  macOS: brew install ffmpeg)"
        )

    with tempfile.TemporaryDirectory(prefix="meeting_agent_chunks_") as chunk_dir:
        chunks = _split_audio_with_ffmpeg(audio_path, chunk_dir)
        transcripts: list[str] = []

        for i, chunk_path in enumerate(chunks):
            chunk_size_mb = chunk_path.stat().st_size / (1024 * 1024)
            logger.info(
                "Transcribing chunk %d/%d | %.2f MB | file=%s",
                i + 1, len(chunks), chunk_size_mb, chunk_path.name,
            )

            try:
                chunk_text = _call_whisper_api(client, chunk_path).strip()
                if chunk_text:
                    transcripts.append(chunk_text)
                else:
                    logger.warning("Chunk %d/%d returned empty transcript", i + 1, len(chunks))
            except (RateLimitError, APITimeoutError, APIConnectionError, APIError) as exc:
                logger.error("Chunk %d/%d transcription failed: %s", i + 1, len(chunks), exc)
                # Re-raise — caller's except block handles Groq-specific errors
                raise

        if not transcripts:
            raise RuntimeError(
                "Chunked transcription produced no output. "
                "All chunks returned empty transcripts."
            )

    merged = " ".join(transcripts)
    logger.info(
        "Chunked transcription complete | chunks=%d | words=%d",
        len(transcripts),
        len(merged.split()),
    )
    return merged


# =============================================================================
# LangGraph Node 1 — transcribe_audio
# =============================================================================

@traceable(name="transcribe_audio", tags=["node-1", "whisper"], metadata={"model": WHISPER_MODEL})
def transcribe_audio(state: AgentState) -> dict:
    """Node 1: transcribe the uploaded audio file to plain text.

    Automatically uses chunked transcription for files that exceed Groq's
    25 MB per-request limit. Requires ffmpeg to be available on PATH.
    """
    logger.info("Node 1 - transcribe_audio | file=%s", state.audio_filename)

    if not state.audio_file_path:
        error = "transcribe_audio: audio_file_path missing from state"
        return {"errors": state.errors + [error]}

    if not settings.groq_api_key:
        return {"errors": state.errors + ["GROQ_API_KEY is not set"]}

    try:
        audio_path = _validate_audio_file(state.audio_file_path)
        client = Groq(api_key=settings.groq_api_key, timeout=settings.groq_timeout_seconds)

        file_size = audio_path.stat().st_size
        if file_size > MAX_GROQ_TRANSCRIPTION_BYTES:
            # Large file — use automatic chunking via ffmpeg
            logger.info(
                "File size %.2f MB exceeds Groq limit %.0f MB — using chunked transcription",
                file_size / (1024 * 1024),
                MAX_GROQ_TRANSCRIPTION_BYTES / (1024 * 1024),
            )
            transcript = _transcribe_in_chunks(client, audio_path)
        else:
            # Small file — send directly to Whisper in one request
            transcript = _call_whisper_api(client, audio_path).strip()

        if not transcript:
            return {"errors": state.errors + ["Whisper returned an empty transcript"]}

        logger.info("Transcription complete | words=%d", len(transcript.split()))
        return {
            "transcript": transcript,
            "completed_nodes": state.completed_nodes + ["transcribe_audio"],
        }

    except ValueError as e:
        return {"errors": state.errors + [f"Audio validation failed: {e}"]}
    except RateLimitError:
        return {"errors": state.errors + ["Groq rate limit reached during transcription"]}
    except APITimeoutError:
        return {"errors": state.errors + ["Groq timed out during transcription"]}
    except APIConnectionError as e:
        detail = str(e)
        if "Server disconnected without sending a response" in detail or "EOF occurred" in detail:
            return {
                "errors": state.errors
                + [
                    "Groq connection dropped while uploading audio. "
                    "Try a smaller file or retry in a few moments."
                ]
            }
        return {"errors": state.errors + ["Could not connect to Groq during transcription"]}
    except APIError as e:
        return {"errors": state.errors + [f"Groq API error during transcription: {e}"]}
    except OSError as e:
        return {"errors": state.errors + [f"Unable to read audio file: {e}"]}
    except RuntimeError as e:
        return {"errors": state.errors + [f"Audio chunking failed: {e}"]}
    except Exception as e:
        message = str(e)
        if "Server disconnected without sending a response" in message or "EOF occurred" in message:
            return {
                "errors": state.errors
                + [
                    "Groq upload failed due to connection interruption (SSL EOF). "
                    "Retry with a smaller file or check network/VPN/proxy."
                ]
            }
        return {"errors": state.errors + [f"Unexpected transcription failure: {e}"]}
