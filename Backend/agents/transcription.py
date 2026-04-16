import logging
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


def _validate_audio_file(file_path: str) -> Path:
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
            f"Audio file too large: {file_size / (1024 * 1024):.2f}MB > {MAX_FILE_SIZE_BYTES / (1024 * 1024):.2f}MB"
        )
    if file_size > MAX_GROQ_TRANSCRIPTION_BYTES:
        raise ValueError(
            "Audio exceeds Groq transcription limit "
            f"({file_size / (1024 * 1024):.2f}MB > {MAX_GROQ_TRANSCRIPTION_BYTES / (1024 * 1024):.2f}MB). "
            "Please upload a shorter/lower-bitrate clip."
        )

    return path


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


@traceable(name="transcribe_audio", tags=["node-1", "whisper"], metadata={"model": WHISPER_MODEL})
def transcribe_audio(state: AgentState) -> dict:
    logger.info("Node 1 - transcribe_audio | file=%s", state.audio_filename)

    if not state.audio_file_path:
        error = "transcribe_audio: audio_file_path missing from state"
        return {"errors": state.errors + [error]}

    if not settings.groq_api_key:
        return {"errors": state.errors + ["GROQ_API_KEY is not set"]}

    try:
        audio_path = _validate_audio_file(state.audio_file_path)
        transcript = _call_whisper_api(
            Groq(api_key=settings.groq_api_key, timeout=settings.groq_timeout_seconds),
            audio_path,
        ).strip()

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
