"""core/queue.py — Distributed Job Queue integration via Arq and Redis.

Provides a durable async task queue for offloading heavy pipeline jobs,
cron-based stuck-job recovery, and deduplicated reminder scheduling across
multi-worker deployments.
"""

import logging
from typing import Any, Optional
from urllib.parse import urlparse

from arq.connections import ArqRedis, RedisSettings, create_pool

from core.config import settings

logger = logging.getLogger(__name__)

_arq_pool: Optional[ArqRedis] = None


def get_redis_settings(url: Optional[str] = None) -> RedisSettings:
    """Parse a redis connection URL into an Arq RedisSettings object."""
    redis_url = url or settings.redis_url or "redis://localhost:6379/0"
    parsed = urlparse(redis_url)

    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    database = int(parsed.path.lstrip("/") or "0") if parsed.path else 0
    password = parsed.password

    return RedisSettings(
        host=host,
        port=port,
        database=database,
        password=password,
        conn_timeout=3,
    )


async def get_arq_pool() -> Optional[ArqRedis]:
    """Retrieve or initialize the shared Arq Redis connection pool.

    Returns None if Redis is unreachable, allowing transparent in-process fallback.
    """
    global _arq_pool
    if _arq_pool is not None:
        return _arq_pool

    if not getattr(settings, "enable_arq_queue", True):
        logger.debug("Arq queue disabled by settings")
        return None

    try:
        redis_settings = get_redis_settings()
        _arq_pool = await create_pool(redis_settings)
        logger.info("Connected to Arq Redis pool at %s:%s", redis_settings.host, redis_settings.port)
        return _arq_pool
    except Exception as exc:
        logger.debug("Arq Redis pool connection unavailable (%s) — using local fallback", exc)
        return None


async def close_arq_pool() -> None:
    """Close the active Arq Redis pool on application shutdown."""
    global _arq_pool
    if _arq_pool is not None:
        try:
            await _arq_pool.close()
        except Exception:
            pass
        _arq_pool = None


async def enqueue_meeting_job(
    job_id: str,
    payload_dict: dict[str, Any],
    user_id: Optional[str] = None,
) -> bool:
    """Enqueue a meeting pipeline processing job onto the Arq queue.

    Returns True if successfully enqueued onto Redis, False if queue is unavailable.
    """
    pool = await get_arq_pool()
    if not pool:
        return False

    try:
        # Use stable _job_id to prevent duplicate enqueues of the same processing job
        await pool.enqueue_job(
            "process_meeting_job",
            job_id,
            payload_dict,
            user_id,
            _job_id=f"meeting_job_{job_id}",
        )
        logger.info("Successfully enqueued meeting processing job %s onto Arq", job_id)
        return True
    except Exception as exc:
        logger.warning("Failed to enqueue job %s onto Arq (%s) — falling back to local task", job_id, exc)
        return False


async def enqueue_reminder_check() -> bool:
    """Enqueue a single reminder evaluation job onto the distributed queue."""
    pool = await get_arq_pool()
    if not pool:
        return False

    try:
        await pool.enqueue_job("check_due_reminders_cron", _job_id="cron_check_reminders")
        return True
    except Exception as exc:
        logger.debug("Failed to enqueue reminder check onto Arq: %s", exc)
        return False


async def enqueue_stuck_job_recovery() -> bool:
    """Enqueue a stuck-job recovery job onto the distributed queue."""
    pool = await get_arq_pool()
    if not pool:
        return False

    try:
        await pool.enqueue_job("recover_stuck_jobs_cron", _job_id="cron_recover_stuck_jobs")
        return True
    except Exception as exc:
        logger.debug("Failed to enqueue stuck job recovery onto Arq: %s", exc)
        return False
