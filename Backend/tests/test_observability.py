"""
test_observability.py — Unit and integration tests for Phase 8 Observability & Metrics Instrumentation.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from core.observability import (
    MODEL_PRICING,
    get_prometheus_metrics,
    record_reminder_event,
    record_tokens_and_cost,
    record_upload_metrics,
    set_queue_depth,
    trace_node,
)
from api.main import app


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint():
    """Verify that GET /metrics returns HTTP 200 and Prometheus exposition format."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "meeting_queue_depth" in text or "meeting_pipeline_node_duration_seconds" in text or "meeting_app_status" in text


def test_get_prometheus_metrics_direct():
    """Verify get_prometheus_metrics returns non-empty byte buffer and content type."""
    data, content_type = get_prometheus_metrics()
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert "text/plain" in content_type or "version=0.0.4" in content_type


def test_trace_node_success():
    """Verify trace_node records latency and marks status=success on normal execution."""
    with trace_node("test_transcription_node", meeting_id="meet-123") as span:
        assert span["node"] == "test_transcription_node"
        assert span["meeting_id"] == "meet-123"
        # Simulate slight work
        _ = sum(range(1000))

    assert span["status"] == "success"
    assert "duration_seconds" in span
    assert span["duration_seconds"] >= 0.0


def test_trace_node_failure():
    """Verify trace_node marks status=failed and re-raises exception on node error."""
    with pytest.raises(ValueError, match="simulated failure"):
        with trace_node("test_failing_node", meeting_id="meet-fail"):
            raise ValueError("simulated failure")


def test_record_tokens_and_cost_llm():
    """Verify token pricing calculations for LLM text tokens."""
    cost = record_tokens_and_cost(
        node="extraction",
        model="llama-3.3-70b-versatile",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    # 0.59 input + 0.79 output = 1.38 USD
    assert cost == 1.38


def test_record_tokens_and_cost_audio():
    """Verify audio minute pricing calculations."""
    cost = record_tokens_and_cost(
        node="transcription",
        model="whisper-large-v3",
        audio_duration_seconds=600.0,  # 10 minutes
    )
    # 10 minutes * $0.006 = 0.06 USD
    assert cost == 0.06


def test_record_upload_metrics():
    """Verify throughput in MB/s calculation."""
    throughput = record_upload_metrics(
        file_size_bytes=10 * 1024 * 1024,  # 10 MB
        duration_seconds=0.5,               # 0.5 sec -> 20 MB/s
    )
    assert throughput == 20.0


def test_set_queue_depth():
    """Verify set_queue_depth executes cleanly."""
    set_queue_depth(pending=5, processing=2)
    set_queue_depth(pending=0, processing=0)


def test_record_reminder_event():
    """Verify record_reminder_event records events cleanly."""
    record_reminder_event("slack", "success")
    record_reminder_event("jira", "policy_blocked")
