"""Redis cache service using Upstash REST API for 10K-scale response caching.

This module provides:
- Per-user analytics caching (TTL 5 min)
- Meeting list caching (TTL 30 sec)
- Meeting detail caching (TTL 60 sec)
- Manual cache invalidation on write operations
"""

import hashlib
import json
import logging
import time
from typing import Any, Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_UPSTASH_URL   = (settings.upstash_redis_rest_url   or "").strip().rstrip("/")
_UPSTASH_TOKEN = (settings.upstash_redis_rest_token or "").strip()

_ENABLED = bool(_UPSTASH_URL and _UPSTASH_TOKEN)

# Default TTLs (seconds)
TTL_ANALYTICS   = 300   # 5 min
TTL_MEETING_LIST= 30    # 30 sec
TTL_MEETING_DETAIL = 60 # 60 sec
TTL_SHORT       = 10


def _cache_enabled() -> bool:
    return _ENABLED


async def _upstash_command(*args) -> Any:
    """Send a single Redis command to Upstash REST API."""
    if not _ENABLED:
        return None
    url = f"{_UPSTASH_URL}/{'/'.join(str(a) for a in args)}"
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {_UPSTASH_TOKEN}"})
            if resp.status_code == 200:
                body = resp.json()
                return body.get("result")
    except Exception as exc:
        logger.debug("Redis cache command failed (non-fatal): %s", exc)
    return None


def _make_key(*parts: str) -> str:
    raw = ":".join(parts)
    if len(raw) > 200:
        raw = hashlib.sha256(raw.encode()).hexdigest()
    return f"mia:{raw}"


async def cache_get(key: str) -> Optional[Any]:
    """Get a cached JSON value. Returns None on miss or error."""
    if not _ENABLED:
        return None
    result = await _upstash_command("GET", key)
    if result is None:
        return None
    try:
        return json.loads(result)
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = TTL_ANALYTICS) -> bool:
    """Set a JSON-serialized value with TTL in seconds."""
    if not _ENABLED:
        return False
    try:
        serialized = json.dumps(value, default=str)
    except Exception:
        return False
    result = await _upstash_command("SET", key, serialized, "EX", ttl)
    return result == "OK"


async def cache_delete(*keys: str) -> None:
    """Invalidate one or more cache keys."""
    if not _ENABLED or not keys:
        return
    for key in keys:
        await _upstash_command("DEL", key)


async def cache_delete_pattern_scan(prefix: str) -> None:
    """Delete all keys matching a prefix (uses SCAN to avoid blocking)."""
    if not _ENABLED:
        return
    try:
        cursor = "0"
        while True:
            result = await _upstash_command("SCAN", cursor, "MATCH", f"{prefix}*", "COUNT", 100)
            if not isinstance(result, list) or len(result) < 2:
                break
            cursor = str(result[0])
            keys = result[1]
            if keys:
                for k in keys:
                    await _upstash_command("DEL", k)
            if cursor == "0":
                break
    except Exception as exc:
        logger.debug("cache_delete_pattern_scan failed (non-fatal): %s", exc)


# ─── Convenience cache key builders ─────────────────────────────────────────

def key_analytics_summary(user_id: str) -> str:
    return _make_key("analytics", "summary", user_id)

def key_analytics_participants(user_id: str) -> str:
    return _make_key("analytics", "participants", user_id)

def key_analytics_timeline(user_id: str) -> str:
    return _make_key("analytics", "timeline", user_id)

def key_analytics_action_items(user_id: str) -> str:
    return _make_key("analytics", "action_items", user_id)

def key_analytics_topics(user_id: str) -> str:
    return _make_key("analytics", "topics", user_id)

def key_meetings_list(user_id: str, limit: int, offset: int) -> str:
    return _make_key("meetings", "list", user_id, str(limit), str(offset))

def key_meeting_detail(meeting_id: str) -> str:
    return _make_key("meeting", "detail", meeting_id)


async def invalidate_user_analytics(user_id: str) -> None:
    """Invalidate all analytics cache keys for a user (call after write ops)."""
    await cache_delete(
        key_analytics_summary(user_id),
        key_analytics_participants(user_id),
        key_analytics_timeline(user_id),
        key_analytics_action_items(user_id),
        key_analytics_topics(user_id),
    )


async def invalidate_meetings_list(user_id: str) -> None:
    """Invalidate meetings list cache (all pages) for a user."""
    await cache_delete_pattern_scan(_make_key("meetings", "list", user_id))


async def invalidate_meeting_detail(meeting_id: str) -> None:
    """Invalidate a specific meeting's detail cache."""
    await cache_delete(key_meeting_detail(meeting_id))
