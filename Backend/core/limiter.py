import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate Limiter — backed by Upstash Redis in production, in-memory in dev.
#
# WHY REDIS?
#   The default in-memory backend loses all counters on every server restart
#   (Render free tier restarts frequently). It also gives each dyno/worker its
#   own independent counter, so a user can multiply the rate limit by the
#   number of running instances — brute-force protection becomes ineffective.
#
# HOW IT WORKS:
#   Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN in your .env /
#   Render env vars. The limiter will use Redis to persist counters across
#   restarts and share them across all workers/dynos.
#
# FALLBACK:
#   If the env vars are not set (e.g. local development), the limiter silently
#   falls back to in-memory storage so dev workflows are unaffected.
# ---------------------------------------------------------------------------

_redis_url   = settings.upstash_redis_rest_url.strip()
_redis_token = settings.upstash_redis_rest_token.strip()

if _redis_url and _redis_token:
    # Build a standard redis:// URI that slowapi's storage backend understands.
    # Upstash REST URLs look like: https://<id>.upstash.io
    # We convert to: redis://:<token>@<host>:6379
    try:
        _host = _redis_url.replace("https://", "").replace("http://", "").rstrip("/")
        _storage_uri = f"redis://:{_redis_token}@{_host}:6379"
        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=["120/minute"],
            storage_uri=_storage_uri,
        )
        logger.info("Rate limiter: using Upstash Redis backend (%s)", _host)
    except Exception as _exc:
        logger.warning(
            "Rate limiter: failed to connect to Upstash Redis (%s). "
            "Falling back to in-memory storage.",
            _exc,
        )
        limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
else:
    limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
    logger.debug(
        "Rate limiter: UPSTASH_REDIS_REST_URL not set — using in-memory storage. "
        "Set this env var in production for persistent rate limiting."
    )
