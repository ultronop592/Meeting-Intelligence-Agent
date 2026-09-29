import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.file_cleanup import cleanup_stale_uploads, delete_audio_file
from graph.agent_graph import arun_meeting_agent
from models.schemas import AgentState


def test_delete_audio_file_existing(tmp_path):
    test_file = tmp_path / "sample.mp3"
    test_file.write_bytes(b"dummy audio content")
    assert test_file.exists()

    result = delete_audio_file(str(test_file))
    assert result is True
    assert not test_file.exists()


def test_delete_audio_file_nonexistent(tmp_path):
    missing_file = tmp_path / "does_not_exist.mp3"
    result = delete_audio_file(str(missing_file))
    assert result is False


def test_delete_audio_file_empty_or_none():
    assert delete_audio_file(None) is False
    assert delete_audio_file("") is False


def test_cleanup_stale_uploads(tmp_path):
    upload_dir = str(tmp_path)

    # 1. Fresh file (modified just now)
    fresh_file = tmp_path / "fresh.mp3"
    fresh_file.write_bytes(b"fresh audio")

    # 2. Stale file (modified 25 hours ago)
    stale_file = tmp_path / "stale.mp3"
    stale_file.write_bytes(b"stale audio")
    old_time = time.time() - (25 * 3600)
    os.utime(str(stale_file), (old_time, old_time))

    cleaned = cleanup_stale_uploads(upload_dir, max_age_hours=24)
    assert cleaned == 1
    assert fresh_file.exists()
    assert not stale_file.exists()


def test_cleanup_stale_uploads_missing_dir():
    assert cleanup_stale_uploads("/nonexistent/upload/dir", max_age_hours=24) == 0


@pytest.mark.asyncio
async def test_arun_meeting_agent_cleans_up_audio(tmp_path):
    audio_file = tmp_path / "meeting_to_delete.mp3"
    audio_file.write_bytes(b"audio test content")
    assert audio_file.exists()

    mock_state_dict = {
        "audio_file_path": str(audio_file),
        "audio_filename": "meeting_to_delete.mp3",
        "meeting_id": "mock-meeting-id",
        "completed_nodes": ["transcribe_audio"],
        "errors": [],
    }

    with patch("graph.agent_graph.agent_graph.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = mock_state_dict
        result = await arun_meeting_agent(
            audio_file_path=str(audio_file),
            audio_filename="meeting_to_delete.mp3",
            cleanup_audio=True,
        )
        assert not audio_file.exists()


@pytest.mark.asyncio
async def test_arun_meeting_agent_retains_audio_when_disabled(tmp_path):
    audio_file = tmp_path / "meeting_to_keep.mp3"
    audio_file.write_bytes(b"audio test content")
    assert audio_file.exists()

    mock_state_dict = {
        "audio_file_path": str(audio_file),
        "audio_filename": "meeting_to_keep.mp3",
        "meeting_id": "mock-meeting-id",
        "completed_nodes": ["transcribe_audio"],
        "errors": [],
    }

    with patch("graph.agent_graph.agent_graph.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = mock_state_dict
        result = await arun_meeting_agent(
            audio_file_path=str(audio_file),
            audio_filename="meeting_to_keep.mp3",
            cleanup_audio=False,
        )
        assert audio_file.exists()
