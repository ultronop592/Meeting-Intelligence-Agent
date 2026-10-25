"""Tests for Phase 3 Outbox models, schemas, and checkpoint persistence helpers."""
import uuid
import pytest
from datetime import datetime, timezone

from db.models import Meeting, ProcessingJob, OutboxDispatch
from models.schemas import AgentState, OutboxChannel, OutboxDispatchRow, OutboxStatus
from db.database import (
    create_or_get_outbox_dispatch,
    get_job_checkpoint,
    get_outbox_dispatch,
    save_job_checkpoint,
    update_job_heartbeat,
    update_outbox_dispatch,
)


def test_outbox_schemas_serialization():
    """Verify Outbox schema models validate and serialize properly."""
    row = OutboxDispatchRow(
        id=str(uuid.uuid4()),
        idempotency_key="meeting_123:action_1:jira",
        meeting_id="meeting_123",
        user_id="user_abc",
        channel=OutboxChannel.JIRA,
        status=OutboxStatus.PENDING,
        payload={"summary": "Fix login bug", "priority": "high"},
    )
    assert row.channel == "jira"
    assert row.status == "pending"
    assert row.payload["priority"] == "high"


def test_agent_state_checkpoint_fields():
    """Verify AgentState supports checkpoint_state and resumed_from_checkpoint."""
    state = AgentState(
        audio_filename="test.mp3",
        checkpoint_state={"transcribe_audio": {"transcript": "Hello world"}},
        resumed_from_checkpoint=True,
    )
    assert state.resumed_from_checkpoint is True
    assert "transcribe_audio" in state.checkpoint_state


@pytest.mark.asyncio
async def test_outbox_dispatch_idempotency_flow(db_session):
    """Verify OutboxDispatch enforces idempotency: same key returns existing row."""
    meeting_id = f"m-{uuid.uuid4().hex[:8]}"
    meeting = Meeting(
        id=meeting_id,
        title="Test Sprint Sync",
        audio_filename="sync.mp3",
        duration_minutes=30,
        short_summary="Sprint planning meeting.",
        detailed_summary="Full sprint planning narrative.",
    )
    db_session.add(meeting)
    await db_session.commit()

    idempotency_key = f"{meeting_id}:action_101:jira"

    # First attempt: creates pending row
    disp1, created1 = await create_or_get_outbox_dispatch(
        idempotency_key=idempotency_key,
        meeting_id=meeting_id,
        channel="jira",
        payload={"summary": "Deploy hotfix"},
        session=db_session,
    )
    assert created1 is True
    assert disp1.status == "pending"
    assert disp1.idempotency_key == idempotency_key

    # Second attempt with same key: returns existing row (no duplicates!)
    disp2, created2 = await create_or_get_outbox_dispatch(
        idempotency_key=idempotency_key,
        meeting_id=meeting_id,
        channel="jira",
        payload={"summary": "Deploy hotfix"},
        session=db_session,
    )
    assert created2 is False
    assert disp2.id == disp1.id

    # Update to 'sent' with external Jira ticket key
    updated = await update_outbox_dispatch(
        idempotency_key=idempotency_key,
        status="sent",
        external_id="PROJ-789",
        session=db_session,
    )
    assert updated is not None
    assert updated.status == "sent"
    assert updated.external_id == "PROJ-789"

    # Query outbox directly
    fetched = await get_outbox_dispatch(idempotency_key, session=db_session)
    assert fetched is not None
    assert fetched.external_id == "PROJ-789"
    assert fetched.status == "sent"


@pytest.mark.asyncio
async def test_outbox_dispatch_failure_retry_increment(db_session):
    """Verify failed dispatch increments retry_count and stores last_error."""
    meeting_id = f"m-{uuid.uuid4().hex[:8]}"
    meeting = Meeting(
        id=meeting_id,
        title="Incident Postmortem",
        audio_filename="postmortem.mp3",
        duration_minutes=15,
        short_summary="Outage review.",
        detailed_summary="Outage narrative.",
    )
    db_session.add(meeting)
    await db_session.commit()

    key = f"{meeting_id}:action_5:email_alice"
    disp, created = await create_or_get_outbox_dispatch(
        idempotency_key=key,
        meeting_id=meeting_id,
        channel="email",
        session=db_session,
    )
    assert created is True
    assert disp.retry_count == 0

    # Simulate timeout / failure
    updated = await update_outbox_dispatch(
        idempotency_key=key,
        status="failed",
        last_error="SendGrid 503 Service Unavailable",
        session=db_session,
    )
    assert updated.status == "failed"
    assert updated.retry_count == 1
    assert "SendGrid 503" in updated.last_error


@pytest.mark.asyncio
async def test_job_checkpoint_persistence(db_session):
    """Verify save_job_checkpoint saves intermediate node data and get_job_checkpoint reads it."""
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    job = ProcessingJob(
        id=job_id,
        status="processing",
        completed_nodes=["upload"],
        checkpoint_state={},
    )
    db_session.add(job)
    await db_session.commit()

    # Save transcription checkpoint
    await save_job_checkpoint(
        job_id=job_id,
        node_name="transcribe_audio",
        node_data={"transcript": "Good morning team, let's review the blockers."},
        completed_nodes=["transcribe_audio"],
        session=db_session,
    )

    checkpoint = await get_job_checkpoint(job_id, session=db_session)
    assert checkpoint is not None
    assert "transcribe_audio" in checkpoint["completed_nodes"]
    assert checkpoint["checkpoint_state"].get("transcript") == "Good morning team, let's review the blockers."

    # Save extraction checkpoint into same job
    await save_job_checkpoint(
        job_id=job_id,
        node_name="extract_information",
        node_data={"extracted_items_count": 3},
        completed_nodes=["extract_information"],
        session=db_session,
    )

    checkpoint2 = await get_job_checkpoint(job_id, session=db_session)
    assert checkpoint2["checkpoint_state"].get("transcript") == "Good morning team, let's review the blockers."
    assert checkpoint2["checkpoint_state"].get("extracted_items_count") == 3
    assert "extract_information" in checkpoint2["completed_nodes"]


@pytest.mark.asyncio
async def test_job_heartbeat_updates(db_session):
    """Verify update_job_heartbeat updates timestamp and worker_id."""
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    job = ProcessingJob(
        id=job_id,
        status="processing",
    )
    db_session.add(job)
    await db_session.commit()

    worker_id = "worker-pool-node-3"
    await update_job_heartbeat(job_id, worker_id=worker_id, session=db_session)

    reloaded = await db_session.get(ProcessingJob, job_id)
    assert reloaded.worker_id == worker_id
    assert reloaded.last_heartbeat is not None

