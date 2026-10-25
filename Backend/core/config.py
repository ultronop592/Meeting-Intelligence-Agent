
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
 
 
class Settings(BaseSettings):
    """
    All application settings loaded from environment variables / .env file.
    Types are enforced — DATABASE_URL must be a string, MAX_UPLOAD_SIZE_MB an int.
    """
 
    model_config = SettingsConfigDict(
        env_file=(".env", "Backend/.env"),  # Load from Backend/.env when running from root or Backend directory
        env_file_encoding="utf-8",
        case_sensitive=False,     # GROQ_API_KEY and groq_api_key both work
        extra="ignore",           # Ignore unknown env vars (don't crash)
    )
 
    # --- App -----------------------------------------------------------------
    app_env:    str = "development"       # development | production
    secret_key: str = "change-me"
    app_name:   str = "Meeting Intelligence Agent"
    app_version:str = "2.0.0"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
 
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

    # --- OpenRouter (Agent Chat Chatbot) -------------------------------------
    openrouter_api_key:  str = ""
    opernrouter_api_key: str = ""  # Deprecated alias kept for backwards compatibility with legacy .env files
    openrouter_model:    str = "meta-llama/llama-3.3-70b-instruct"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
 
    # --- Neon (Postgres) -----------------------------------------------------
    database_url:      str   # async  URL  — postgresql+asyncpg://...
    database_url_sync: str   # sync   URL  — postgresql+psycopg2://...
    db_pool_size:      int = 10  # Enough for 100 concurrent users (10 base slots)
    db_max_overflow:   int = 20  # Burst headroom → 30 total max connections
    db_pool_recycle:   int = 300 # Recycle connections every 5m to avoid idle disconnects
    db_pool_timeout:   int = 10  # Fail fast after 10s instead of queuing for 30s
 
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
 
    # --- Redis / Arq Queue ---------------------------------------------------
    redis_url:                str = "redis://localhost:6379/0"
    upstash_redis_rest_url:   str = ""
    upstash_redis_rest_token: str = ""
 
    # --- File upload & storage cleanup ---------------------------------------
    max_upload_size_mb: int = 1024
    upload_dir:         str = "/tmp/meeting-agent-uploads"
    delete_audio_after_processing: bool = True
    cleanup_stale_uploads_hours: int = 24

    # --- Object Storage (Cloudflare R2 / AWS S3 / MinIO) ---------------------
    storage_backend:                 str = "local"  # "local" or "s3"
    s3_endpoint_url:                 str = ""       # e.g. https://<account_id>.r2.cloudflarestorage.com
    s3_access_key_id:                str = ""
    s3_secret_access_key:            str = ""
    s3_bucket_name:                  str = ""
    s3_region_name:                  str = "auto"
    s3_presigned_url_expire_seconds: int = 3600
    # Set to false for storage providers that don't support S3 multipart uploads
    # (e.g. Supabase Storage). When false, files are buffered and uploaded via
    # a single put_object call, which works for all S3-compatible providers.
    s3_multipart_enabled: bool = True

    # --- Audio chunking & Parallel Transcription -----------------------------
    # Duration of each chunk in seconds. 600 s = 10 min.
    # At 128 kbps MP3: 10 min ≈ 9.6 MB — well under Groq's 25 MB limit.
    # Requires ffmpeg to be installed on the system PATH.
    audio_chunk_duration_seconds:       int   = 600
    audio_chunk_silence_window_seconds: int   = 30
    transcription_concurrency:          int   = 4

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

    @property
    def s3_supports_multipart(self) -> bool:
        """Returns False for storage providers that don't support S3 multipart uploads.

        Supabase Storage returns HTTP 540 on CreateMultipartUpload — multipart
        must be avoided there.  We auto-detect by endpoint URL and also honour
        the explicit S3_MULTIPART_ENABLED=false override in .env.
        """
        if not self.s3_multipart_enabled:
            return False
        endpoint = (self.s3_endpoint_url or "").lower()
        # Supabase Storage S3 API does not support multipart uploads
        if "supabase.co" in endpoint:
            return False
        return True

    @property
    def supabase_tus_endpoint(self) -> Optional[str]:
        """Returns the Supabase TUS resumable-upload endpoint URL, or None if not applicable.

        Derived from the S3 endpoint URL:
          https://<project>.storage.supabase.co/storage/v1/s3
          →  https://<project>.storage.supabase.co/storage/v1/upload/resumable
        """
        endpoint = (self.s3_endpoint_url or "").strip()
        if not endpoint or "supabase.co" not in endpoint.lower():
            return None
        # Strip trailing /s3 (or /s3/) and replace with /upload/resumable
        base = endpoint.rstrip("/")
        if base.endswith("/s3"):
            base = base[:-3]
        return base.rstrip("/") + "/upload/resumable"

    @property
    def effective_openrouter_api_key(self) -> str:
        return (self.openrouter_api_key or self.opernrouter_api_key or "").strip()
 
 
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
