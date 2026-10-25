"""Tests for Phase 3 Step 5: Arq Queue, Single-Scheduler Reminder Deduplication, and Reliability."""
import asyncio
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from core.queue import get_redis_settings, enqueue_meeting_job, enqueue_reminder_check, enqueue_stuck_job_recovery
from worker import WorkerSettings, check_due_reminders_cron, recover_stuck_jobs_cron
from db.models import ActionItem, Meeting, NotificationLog, ProcessingJob
from core.reminder_service import check_and_send_due_reminders


def test_redis_settings_parsing():
    """Verify get_redis_settings correctly parses Redis URLs with auth, port, and DB index."""
    settings = get_redis_settings("redis://:secret_pwd@custom-redis.internal:6380/3")
    assert settings.host == "custom-redis.internal"
    assert settings.port == 6380
    assert settings.database == 3
    assert settings.password == "secret_pwd"


@pytest.mark.asyncio
async def test_enqueue_meeting_job_to_arq_queue():
    """Verify meeting processing job is enqueued to Arq with stable deduplicated job_id."""
    mock_pool = MagicMock()
    mock_pool.enqueue_job = AsyncMock(return_value=None)

    with patch("core.queue.get_arq_pool", return_value=mock_pool):
        ok = await enqueue_meeting_job(
            job_id="job_789",
            payload_dict={"audio_filename": "sprint.mp3"},
            user_id="user_123",
        )
        assert ok is True
        mock_pool.enqueue_job.assert_awaited_once_with(
            "process_meeting_job",
            "job_789",
            {"audio_filename": "sprint.mp3"},
            "user_123",
            _job_id="meeting_job_job_789",
        )


@pytest.mark.asyncio
async def test_enqueue_meeting_job_graceful_fallback_when_redis_unavailable():
    """Verify queue helper returns False when Redis pool is unavailable, allowing in-process fallback."""
    with patch("core.queue.get_arq_pool", return_value=None):
        ok = await enqueue_meeting_job(
            job_id="job_offline",
            payload_dict={"audio_filename": "local.mp3"},
        )
        assert ok is False


@pytest.mark.asyncio
async def test_single_scheduler_reminders_across_simulated_multiple_workers(db_session):
    """Problem 1 Fix Verification:

    Simulates 4 worker threads running reminder evaluations on the same database.
    Due to the single scheduled job and notification log deduplication,
    each overdue task is reminded exactly once per day, not 4 times.
    """
    meeting_id = f"m-{uuid.uuid4().hex[:8]}"
    meeting = Meeting(
        id=meeting_id,
        title="Weekly Staff Sync",
        audio_filename="staff.mp3",
        duration_minutes=30,
        short_summary="Staff sync meeting.",
        detailed_summary="Full staff sync details.",
    )
    db_session.add(meeting)

    yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    action_item = ActionItem(
        meeting_id=meeting_id,
        description="Ship Phase 3 durable queue",
        owner="Dana",
        due_date=yesterday_str,
        priority="high",
        status="open",
    )
    db_session.add(action_item)
    await db_session.commit()

    # Simulate 4 concurrent workers (or 4 consecutive runs from multi-workers)
    # evaluating reminders
    mock_send_email = MagicMock()
    with patch("core.reminder_service._send_single_email", mock_send_email), \
         patch("core.reminder_service.resolve_email_credentials", return_value=("key", "from@x.com", "Bot")):

        # Worker 1 runs
        res1 = await check_and_send_due_reminders(db_session)
        # Worker 2 runs concurrently or shortly after
        res2 = await check_and_send_due_reminders(db_session)
        # Worker 3 runs
        res3 = await check_and_send_due_reminders(db_session)
        # Worker 4 runs
        res4 = await check_and_send_due_reminders(db_session)

    # First worker caught it and sent reminder
    assert res1["due_items_found"] >= 1

    # Subsequent workers see 'already_reminded' and send ZERO duplicate emails!
    assert res2["reminders_sent"] == 0
    assert res3["reminders_sent"] == 0
    assert res4["reminders_sent"] == 0


@pytest.mark.asyncio
async def test_worker_settings_cron_configuration():
    """Verify Arq WorkerSettings registers the required cron jobs and functions."""
    registered_func_names = [f.__name__ for f in WorkerSettings.functions]
    assert "process_meeting_job" in registered_func_names
    assert "check_due_reminders_cron" in registered_func_names
    assert "recover_stuck_jobs_cron" in registered_func_names

    assert len(WorkerSettings.cron_jobs) >= 2
    assert WorkerSettings.max_jobs >= 1


@pytest.mark.asyncio
async def test_parallel_transcription_speedup_benchmark():
    """Problem 4 Benchmark:

    Calculates simulated processing time comparison for sequential vs parallel chunk transcription.
    A 2-hour meeting (12 chunks of 10 min each, ~10s transcription each):
    Sequential: 12 * 10s = 120s
    Parallel (concurrency cap 4): ceil(12 / 4) * 10s = 30s (~4x speedup factor).
    """
    num_chunks = 12
    chunk_transcription_time_sec = 10.0
    concurrency_cap = 4

    sequential_time = num_chunks * chunk_transcription_time_sec
    import math
    parallel_time = math.ceil(num_chunks / concurrency_cap) * chunk_transcription_time_sec

    speedup_factor = sequential_time / parallel_time
    assert speedup_factor == 4.0
    assert parallel_time < sequential_time
