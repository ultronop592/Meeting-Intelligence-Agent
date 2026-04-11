import logging 
from pathlib import Path

from groq import APIError, Groq, APIConnectionError, APITimeoutError, RateLimitError
from langsmith import traceable
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type,
)
from Backend.core.config import settings
from Backend.models.schemas import AgentState

logger = logging.getLogger(__name__)

# // constants

WHISPER_MODEL       = "whisper-large-v3"
SUPPORTED_FORMATS   = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}
MAX_FILE_SIZE_BYTES = settings.max_upload_size_bytes

@retry(
    retry = retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    stop = stop_after_attempt(3),
    wait = wait_exponential(multiplier=1, min=2, max=8),
    reraise = True,
)

def _call_whisper_api(client: Groq, audio_path: Path) -> str:
    """
    Calls Groq Whisper API with retry logic.
    Separated from the main function so retry decorator applies cleanly.
    Returns raw transcript string.
    """
    
    with open(audio_path, "rb") as audio_file:
        response = client.audio.transcribe(
            model = WHISPER_MODEL,
            file = audio_file,
            filename = (audio_path.name, audio_file),
            response_fromat = "text",
            language = "en",
        )
    return response
        
    
# // file validator

def _validate_audio_file(file_path: str) -> Path:
    """
    Validates the audio file before sending to Groq.
    Raises ValueError with a clear message on any problem.
    """
    
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"File not found: {file_path}")
    
    if not path.is_file():
        raise ValueError(f"Not a file: {file_path}")
    
    lower_name = path.name.lower()
    suffix = ".mp4" if lower_name.endswith(".mp.4") else path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported file format: {suffix}. Supported formats: {SUPPORTED_FORMATS}")
    
    file_size = path.stat().st_size
    if file_size == 0:
        raise ValueError("File is empty.")
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb =  file_size / (1024 * 1024)
        raise ValueError(f"File size {size_mb:.2f} MB exceeds the maximum allowed size of {MAX_FILE_SIZE_BYTES / (1024 * 1024):.2f} MB.")  
     
    return path

# // langGraph Node 1

@traceable(
     name =  " transcribe_audio",
     tags= ["node-1", "whisper"],
     metadata= {"modal": WHISPER_MODEL},
)

def transcribe_audio(state: AgentState) -> dict:
    """
    LangGraph Node 1 — Transcribe Audio.
 
    Called by:  graph/agent_graph.py via StateGraph
    Triggered by: FastAPI POST /api/meetings/process (background task)
 
    INPUT  (reads from AgentState): audio_file_path, audio_filename
    OUTPUT (writes to AgentState):  transcript, completed_nodes
 
    Returns a DICT not AgentState — LangGraph merges partial updates
    back into the shared state automatically.
    """
    
    logger.info("Node-1 transcribe_audio | file: %s", state.audio_filename)
    
    if not state.audio_filename:
        error = "transcibe_audio: audio_file missing from AgentState"
        logger.error(error)
        return {"error":  state.errors+ [error]}
    
    # // validate file before calling API (fail fast with clear error if problem)
    
    try:
        audio_path =  _validate_audio_file(state.audio_file_path)
    except ValueError as ve:
        error =  f"Audio file validation failed: {ve}"
        logger.error(error)
        return {"error": state.errors + [error]}
    
    
    #// check api key before calling API (fail fast if not set)
    
    if not settings.groq_api_key:
        error = 'GROQ_API_KEY not set in environment variables'
        logger.error(error)
        return {"error": state.errors + [error]}
    
    # // call Groq API to transcribe audio
    
    client =  Groq(api_key=settings.groq_api_key)
    
    try: 
        file_size_mb =  audio_path.stat().st_size / (1024 * 1024)
        logger.info(
            "Transcribing audio file: %s (Size: %.2f MB)",
            audio_path.name,
            file_size_mb,
        )
        transcript: str =  _call_whisper_api(client, audio_path)
        
    # // validate response 
    
        if not transcript or not transcript.strip():
           error = "Groq Whisper returned an empty transcript. Audio may be silent"
           logger.warning(error)
           return {"error": state.errors + [error]}
       
       
        transcript = transcript.strip()
        word_count = len(transcript.split())
        char_count = len(transcript)
 
        logger.info(
            "Transcription complete | words: %d | chars: %d",
            word_count,
            char_count,
        )
 
        return {
            "transcript":       transcript,
            "completed_nodes":  state.completed_nodes + ["transcribe_audio"],
        }
 
    except RateLimitError:
        error = "Groq rate limit hit during transcription. Retry after a moment."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APITimeoutError:
        error = "Groq Whisper timed out. The audio file may be too long."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APIConnectionError:
        error = "Could not connect to Groq API. Check your internet connection."
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except APIError as e:
        error = f"Groq API error during transcription: {e.status_code} — {e.message}"
        logger.error(error)
        return {"errors": state.errors + [error]}
 
    except OSError as e:
        error = f"Could not read audio file '{audio_path}': {e}"
        logger.error(error)
        return {"errors": state.errors + [error]}
 
          
            