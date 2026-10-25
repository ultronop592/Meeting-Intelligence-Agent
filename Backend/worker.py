"""worker.py — Distributed Background Worker process using Arq.

Solves:
1. Multi-worker reminder race conditions: Runs a SINGLE scheduled cron job for reminders.
2. Mid-pipeline crash recovery: Automatically scans for stuck jobs (>5 min without heartbeat).
3. Queue-based parallel processing: Manages concurrency cap across CPU/API intensive tasks.

Run with:
    arq worker.WorkerSettings
"""

import logging
from typing import Any, Optional

from arq import cron
from arq.connections import RedisSettings

from core.config import settings
from core.queue import get_redis_settings

logger = logging.getLogger("meeting_worker")


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize worker dependencies on startup."""
    logger.info("Initializing Phase 3 Arq Worker...")
    from db.database import init_db
    await init_db()
    logger.info("Arq Worker initialized successfully")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Graceful worker shutdown."""
    logger.info("Shutting down Phase 3 Arq Worker...")


async def process_meeting_job(
    ctx: dict[str, Any],
    job_id: str,
    payload_dict: dict[str, Any],
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Execute durable meeting pipeline with checkpointing and node resumption."""
    logger.info("Worker picked up job %s (user: %s)", job_id, user_id)
    from api.meetings import _process_job
    from models.schemas import ProcessMeetingRequest

    req = ProcessMeetingRequest(**payload_dict)
    await _process_job(job_id=job_id, payload=req, user_id=user_id)
    return {"status": "completed", "job_id": job_id}


async def check_due_reminders_cron(ctx: dict[str, Any]) -> dict[str, Any]:
    """Single distributed cron job for reminders — prevents multi-worker race conditions."""
    logger.info("Arq Cron: Running single distributed check for due reminders...")
    from db.database import AsyncSessionLocal
    from core.reminder_service import check_and_send_due_reminders

    async with AsyncSessionLocal() as session:
        summary = await check_and_send_due_reminders(session)
        logger.info(
            "Distributed reminder run complete | due: %d | sent: %d | already_reminded: %d",
            summary["due_items_found"],
            summary["reminders_sent"],
            summary["already_reminded"],
        )
        return summary


async def recover_stuck_jobs_cron(ctx: dict[str, Any]) -> int:
    """Cron: Scan and recover stuck jobs (>5 min without heartbeat)."""
    logger.info("Arq Cron: Scanning for stuck or orphaned jobs...")
    from db.database import detect_and_recover_stuck_jobs

    recovered_count = await detect_and_recover_stuck_jobs(stuck_threshold_seconds=300)
    if recovered_count > 0:
        logger.warning("Recovered and requeued %d stuck processing job(s)", recovered_count)
    return recovered_count


class WorkerSettings:
    """Arq Worker configuration settings."""
    functions = [
        process_meeting_job,
        check_due_reminders_cron,
        recover_stuck_jobs_cron,
    ]
    cron_jobs = [
        # Single reminder schedule: Run at minute 0 of every hour
        cron(check_due_reminders_cron, hour=None, minute=0),
        # Stuck job monitor: Run every 5 minutes
        cron(recover_stuck_jobs_cron, minute=set(range(0, 60, 5))),
    ]
    redis_settings: RedisSettings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs: int = getattr(settings, "transcription_concurrency", 4)
    job_timeout: int = 1800  # 30 minutes max per meeting
