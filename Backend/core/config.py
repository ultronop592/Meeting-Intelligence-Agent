
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
 
 
class Settings(BaseSettings):
    """
    All application settings loaded from environment variables / .env file.
    Types are enforced — DATABASE_URL must be a string, MAX_UPLOAD_SIZE_MB an int.
    """
 
    model_config = SettingsConfigDict(
        env_file=".env",  # Load from Backend/.env when running from the Backend directory
        env_file_encoding="utf-8",
        case_sensitive=False,     # GROQ_API_KEY and groq_api_key both work
        extra="ignore",           # Ignore unknown env vars (don't crash)
    )
 
    # --- App -----------------------------------------------------------------
    app_env:    str = "development"       # development | production
    secret_key: str = "change-me"
    app_name:   str = "Meeting Intelligence Agent"
    app_version:str = "2.0.0"
 
    # --- Groq ----------------------------------------------------------------
    groq_api_key: str
    groq_timeout_seconds: int = 120
    groq_transcription_max_mb: int = 24

    # --- Multi-LLM Routing ---------------------------------------------------
    # Fast/cheap model: used for short transcripts, compact summaries, and
    # simple Q&A keyword lookups.  Override via LLM_FAST_MODEL in .env.
    llm_fast_model: str = "llama-3.1-8b-instant"
    # Powerful model: used for long/complex transcripts and analytical Q&A.
    # Override via LLM_POWERFUL_MODEL in .env.
    llm_powerful_model: str = "llama-3.3-70b-versatile"
    # Transcript word count cutoff: transcripts with fewer words use the fast
    # model for extraction.  Override via LLM_ROUTING_WORD_THRESHOLD in .env.
    llm_routing_word_threshold: int = 3000
 
    # --- Neon (Postgres) -----------------------------------------------------
    database_url:      str   # async  URL  — postgresql+asyncpg://...
    database_url_sync: str   # sync   URL  — postgresql+psycopg2://...
 
    # --- LangSmith (optional — disable by setting langchain_tracing_v2=false) -
    langchain_tracing_v2: bool = False
    langchain_api_key:    str  = ""
    langchain_project:    str  = "meeting-intelligence-agent"
 
    # --- Jira ----------------------------------------------------------------
    jira_url:         str = ""
    jira_email:       str = ""
    jira_api_token:   str = ""
    jira_project_key: str = "PROJ"
 
    # --- Google Calendar -----------------------------------------------------
    google_calendar_credentials_json: str = ""
    google_calendar_id:               str = ""
 
    # --- SendGrid ------------------------------------------------------------
    sendgrid_api_key: str = ""
    sender_email:     str = ""
    sender_name:      str = "Meeting Intelligence Agent"
 
    # --- Slack ---------------------------------------------------------------
    slack_webhook_url: str = ""
    slack_channel:     str = "#meeting-summaries"
 
    # --- Upstash Redis -------------------------------------------------------
    upstash_redis_rest_url:   str = ""
    upstash_redis_rest_token: str = ""
 
    # --- File upload ---------------------------------------------------------
    max_upload_size_mb: int = 1024
    upload_dir:         str = "/tmp/meeting-agent-uploads"

    # --- Audio chunking (for files > Groq 25 MB transcription limit) ---------
    # Duration of each chunk in seconds. 600 s = 10 min.
    # At 128 kbps MP3: 10 min ≈ 9.6 MB — well under Groq's 25 MB limit.
    # Requires ffmpeg to be installed on the system PATH.
    audio_chunk_duration_seconds: int = 600

    # --- Speaker Diarization (optional) --------------------------------------
    # Identifies WHO spoke WHEN and labels the transcript:
    #   SPEAKER_00: Hello everyone.
    #   SPEAKER_01: Let's start with updates.
    #
    # Requires:
    #   1. pip install pyannote.audio  (heavy: ~1 GB model download)
    #   2. Accept model terms at https://hf.co/pyannote/speaker-diarization-3.1
    #   3. Accept model terms at https://hf.co/pyannote/segmentation-3.0
    #   4. Set HF_TOKEN=<your token> in .env
    #
    # If hf_token is empty OR pyannote.audio is not installed,
    # transcription falls back to plain non-diarized text automatically.
    hf_token:            str  = ""    # HuggingFace access token
    diarization_enabled: bool = True  # Set False to always skip diarization
 
    # --- Computed properties -------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
 
    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def groq_transcription_max_bytes(self) -> int:
        return self.groq_transcription_max_mb * 1024 * 1024
 
    @property
    def langsmith_enabled(self) -> bool:
        return self.langchain_tracing_v2 and bool(self.langchain_api_key)
 
 
@lru_cache()
def get_settings() -> Settings:
    """
    Returns the singleton Settings instance.
    @lru_cache ensures .env is only read once — not on every import.
    Call this as: settings = get_settings()
    Or use the module-level shortcut below.
    """
    return Settings()
 
 
# Module-level shortcut — import this directly:
# from backend.core.config import settings
settings = get_settings()
