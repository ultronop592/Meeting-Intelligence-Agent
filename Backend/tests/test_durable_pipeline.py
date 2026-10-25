"""Tests for Phase 3 Step 3: Durable pipeline checkpointing, crash resumption,
and stuck-job recovery.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from db.models import ProcessingJob
from db.database import (
    create_processing_job,
    detect_and_recover_stuck_jobs,
    get_job_checkpoint,
    save_job_checkpoint,
)
from graph.agent_graph import (
    _hydrate_state_from_checkpoint,
    _make_tracked_node,
    _serialize_node_output,
    arun_meeting_agent,
)
from models.schemas import ActionItem, AgentState, ExtractionOutput, MeetingSummary, Priority


def test_serialize_node_output_with_pydantic_models():
    """Verify serialization handles nested Pydantic models cleanly."""
    extraction = ExtractionOutput(
        action_items=[
            ActionItem(description="Review architecture plan", owner="Dev Lead", priority=Priority.high)
        ],
        participants=["Dev Lead"],
    )
    result = {"extraction": extraction, "model_used": "llama-3.3-70b"}
    serialized = _serialize_node_output("extract_information", result)

    assert serialized["model_used"] == "llama-3.3-70b"
    assert isinstance(serialized["extraction"], dict)
    assert serialized["extraction"]["action_items"][0]["owner"] == "Dev Lead"


def test_hydrate_state_from_checkpoint():
    """Verify state hydration populates AgentState from raw checkpoint dicts."""
    checkpoint_info = {
        "completed_nodes": ["transcribe_audio", "extract_information"],
        "checkpoint_state": {
            "transcribe_audio": {
                "transcript": "Team, we launched the feature yesterday.",
                "speaker_segments": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 5.0}],
            },
            "extract_information": {
                "extraction": {
                    "action_items": [
                        {"description": "Monitor latency", "owner": "Alice", "priority": "medium"}
                    ],
                    "decisions": [],
                    "participants": ["Alice"],
                    "key_topics": ["Feature launch"],
                }
            },
        },
    }

    initial_state = AgentState(audio_filename="meeting.mp3", job_id="job-123")
    hydrated = _hydrate_state_from_checkpoint(initial_state, checkpoint_info)

    assert hydrated.resumed_from_checkpoint is True
    assert hydrated.transcript == "Team, we launched the feature yesterday."
    assert len(hydrated.speaker_segments) == 1
    assert hydrated.extraction is not None
    assert hydrated.extraction.action_items[0].description == "Monitor latency"
    assert "transcribe_audio" in hydrated.completed_nodes


@pytest.mark.asyncio
async def test_stuck_job_heartbeat_detection_and_recovery(db_session):
    """Verify stuck jobs older than timeout are detected, retried, and dead-lettered on max retries."""
    stuck_job_id = f"stuck-{uuid.uuid4().hex[:8]}"
    ten_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=10)

    job = ProcessingJob(
        id=stuck_job_id,
        status="processing",
        last_heartbeat=ten_minutes_ago,
        started_at=ten_minutes_ago,
        retry_count=0,
    )
    db_session.add(job)
    await db_session.commit()

    # Pass 1: detect and recover (attempt 1)
    recovered = await detect_and_recover_stuck_jobs(
        timeout_minutes=5,
        max_retries=3,
        session=db_session,
    )
    assert stuck_job_id in recovered

    reloaded = await db_session.get(ProcessingJob, stuck_job_id)
    assert reloaded.retry_count == 1
    assert reloaded.status == "processing"
    assert any("Heartbeat timeout" in err for err in reloaded.errors)

    # Simulate exceeding max retries
    reloaded.last_heartbeat = ten_minutes_ago
    reloaded.retry_count = 3
    await db_session.commit()

    # Pass 2: hits max_retries (3) -> moves to 'failed' (dead-letter)
    dead_lettered = await detect_and_recover_stuck_jobs(
        timeout_minutes=5,
        max_retries=3,
        session=db_session,
    )
    assert stuck_job_id in dead_lettered

    final_job = await db_session.get(ProcessingJob, stuck_job_id)
    assert final_job.status == "failed"
    assert any("maximum retry attempts" in err for err in final_job.errors)


def test_tracked_node_skips_when_resumed_from_checkpoint():
    """Verify _make_tracked_node skips costly node execution when already finished in checkpoint."""
    mock_costly_func = MagicMock(return_value={"transcript": "new expensive transcription"})
    tracked_node = _make_tracked_node("transcribe_audio", mock_costly_func)

    resumed_state = AgentState(
        audio_filename="recording.mp3",
        resumed_from_checkpoint=True,
        completed_nodes=["transcribe_audio"],
        checkpoint_state={
            "transcribe_audio": {
                "transcript": "Saved transcript from checkpoint - zero re-billing!",
                "speaker_segments": [],
            }
        },
    )

    result = tracked_node(resumed_state)

    # Costly function was NOT called!
    mock_costly_func.assert_not_called()
    assert result["transcript"] == "Saved transcript from checkpoint - zero re-billing!"


@pytest.mark.asyncio
async def test_arun_meeting_agent_hydrates_checkpoint_on_restart(tmp_path):
    """Verify arun_meeting_agent loads checkpoint from DB and passes hydrated state to graph."""
    audio_file = tmp_path / "standup.mp3"
    audio_file.write_bytes(b"dummy-audio-content")

    job_id = f"job-{uuid.uuid4().hex[:8]}"

    mock_checkpoint = {
        "status": "processing",
        "completed_nodes": ["transcribe_audio"],
        "checkpoint_state": {
            "transcribe_audio": {
                "transcript": "Ravi: We completed the auth refactor. Sarah: Great work.",
                "speaker_segments": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 3.0}],
                "transcript_words": [],
            }
        },
    }

    async def mock_graph_ainvoke(state: AgentState):
        assert state.resumed_from_checkpoint is True
        assert state.transcript == "Ravi: We completed the auth refactor. Sarah: Great work."
        return {
            **state.model_dump(),
            "meeting_id": "m-persisted-456",
        }

    with (
        patch("graph.agent_graph.get_job_checkpoint", return_value=mock_checkpoint),
        patch("graph.agent_graph.save_job_checkpoint", return_value=None),
        patch("graph.agent_graph.agent_graph.ainvoke", side_effect=mock_graph_ainvoke),
    ):
        result_state = await arun_meeting_agent(
            audio_file_path=str(audio_file),
            audio_filename="standup.mp3",
            job_id=job_id,
            storage_key="audio/stored_standup.mp3",
        )

    assert result_state.resumed_from_checkpoint is True
    assert result_state.transcript == "Ravi: We completed the auth refactor. Sarah: Great work."
    assert result_state.meeting_id == "m-persisted-456"
