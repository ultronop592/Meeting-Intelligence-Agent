"""
core/observability.py — Phase 8: OpenTelemetry Tracing & Prometheus Metrics Instrumentation

Provides comprehensive telemetry across:
1. Upload & queue latency
2. Pipeline node execution times (transcription, extraction, verifier, summary, save, commitments)
3. Failure rates and error taxonomy
4. Token consumption and estimated dollar costs
5. Reminder delivery success rates
6. Real-time Prometheus /metrics exposition endpoint
"""

import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, Optional

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        REGISTRY,
        generate_latest,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Model pricing in USD per 1,000,000 tokens
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant":    {"input": 0.05, "output": 0.08},
    "whisper-large-v3":        {"minute": 0.006},  # $0.006 per minute
    "default":                 {"input": 0.20, "output": 0.50},
}

if PROMETHEUS_AVAILABLE:
    # 1. Pipeline node latency histogram
    PIPELINE_NODE_DURATION = Histogram(
        "meeting_pipeline_node_duration_seconds",
        "Execution duration of each pipeline node in seconds",
        ["node", "status"],
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 45.0, 90.0, 180.0, 300.0),
    )

    # 2. Queue depth gauge
    QUEUE_DEPTH = Gauge(
        "meeting_queue_depth",
        "Number of jobs currently pending or active in the processing queue",
        ["state"],  # "pending", "processing"
    )

    # 3. Pipeline failures counter
    PIPELINE_FAILURES = Counter(
        "meeting_pipeline_failures_total",
        "Total number of pipeline processing failures",
        ["node", "error_type"],
    )

    # 4. Token consumption counter
    TOKEN_USAGE = Counter(
        "meeting_llm_tokens_total",
        "Total LLM tokens consumed across all meetings",
        ["model", "node", "token_type"],  # token_type: "prompt", "completion"
    )

    # 5. Estimated cost in USD counter
    ESTIMATED_COST_USD = Counter(
        "meeting_cost_usd_total",
        "Estimated cumulative LLM & audio processing cost in USD",
        ["model", "node"],
    )

    # 6. Reminder and Outbox delivery counter
    REMINDER_DELIVERIES = Counter(
        "meeting_reminder_deliveries_total",
        "Total external reminders and outbox dispatches",
        ["channel", "status"],  # status: "success", "failure", "policy_blocked"
    )

    # 7. Upload metrics
    UPLOAD_BYTES = Counter(
        "meeting_upload_bytes_total",
        "Total bytes of audio files uploaded",
    )
    UPLOAD_DURATION = Histogram(
        "meeting_upload_duration_seconds",
        "Time taken to receive audio uploads in seconds",
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    )
    UPLOAD_THROUGHPUT_MB_S = Gauge(
        "meeting_upload_throughput_mb_per_second",
        "Instantaneous upload throughput in MB/s",
    )
    ACTIVE_MEETINGS = Gauge(
        "meeting_active_processing_count",
        "Current count of meetings actively processing",
    )
else:
    # Dummy fallbacks if prometheus_client is absent
    PIPELINE_NODE_DURATION = None
    QUEUE_DEPTH = None
    PIPELINE_FAILURES = None
    TOKEN_USAGE = None
    ESTIMATED_COST_USD = None
    REMINDER_DELIVERIES = None
    UPLOAD_BYTES = None
    UPLOAD_DURATION = None
    UPLOAD_THROUGHPUT_MB_S = None
    ACTIVE_MEETINGS = None


# ---------------------------------------------------------------------------
# Tracing & Metric Recording Functions
# ---------------------------------------------------------------------------

@contextmanager
def trace_node(node_name: str, meeting_id: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
    """Context manager to trace a pipeline node, measuring latency, recording Prometheus metrics,
    and capturing failures."""
    start_time = time.perf_counter()
    ctx: Dict[str, Any] = {"node": node_name, "meeting_id": meeting_id, "status": "success", "error": None}
    if ACTIVE_MEETINGS and node_name == "transcription":
        ACTIVE_MEETINGS.inc()
    try:
        yield ctx
    except Exception as exc:
        ctx["status"] = "failed"
        ctx["error"] = type(exc).__name__
        if PIPELINE_FAILURES:
            PIPELINE_FAILURES.labels(node=node_name, error_type=type(exc).__name__).inc()
        raise
    finally:
        duration = time.perf_counter() - start_time
        ctx["duration_seconds"] = duration
        if PIPELINE_NODE_DURATION:
            PIPELINE_NODE_DURATION.labels(node=node_name, status=ctx["status"]).observe(duration)
        if ACTIVE_MEETINGS and node_name == "save_to_database":
            ACTIVE_MEETINGS.dec()
        logger.info(
            "OTel Span [%s] meeting=%s status=%s duration=%.3fs",
            node_name,
            meeting_id or "unknown",
            ctx["status"],
            duration,
        )


def record_tokens_and_cost(
    node: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    audio_duration_seconds: float = 0.0,
) -> float:
    """Record LLM token consumption, calculate cost, and increment Prometheus counters.
    Returns estimated dollar cost for this invocation."""
    cost = 0.0
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])

    if audio_duration_seconds > 0:
        minutes = audio_duration_seconds / 60.0
        min_rate = pricing.get("minute", 0.006)
        cost += minutes * min_rate
    else:
        in_rate = pricing.get("input", 0.20) / 1_000_000.0
        out_rate = pricing.get("output", 0.50) / 1_000_000.0
        cost += (prompt_tokens * in_rate) + (completion_tokens * out_rate)

    cost = round(cost, 6)

    if PROMETHEUS_AVAILABLE:
        if prompt_tokens > 0:
            TOKEN_USAGE.labels(model=model, node=node, token_type="prompt").inc(prompt_tokens)
        if completion_tokens > 0:
            TOKEN_USAGE.labels(model=model, node=node, token_type="completion").inc(completion_tokens)
        if cost > 0:
            ESTIMATED_COST_USD.labels(model=model, node=node).inc(cost)

    return cost


def record_reminder_event(channel: str, status: str) -> None:
    """Track external dispatch event (Jira, Slack, Email, Calendar)."""
    if PROMETHEUS_AVAILABLE and REMINDER_DELIVERIES:
        REMINDER_DELIVERIES.labels(channel=channel, status=status).inc()


def record_upload_metrics(file_size_bytes: int, duration_seconds: float) -> float:
    """Track audio upload size, duration, and calculate throughput in MB/s."""
    duration = max(0.001, duration_seconds)
    mb = file_size_bytes / (1024.0 * 1024.0)
    throughput = mb / duration

    if PROMETHEUS_AVAILABLE:
        if UPLOAD_BYTES:
            UPLOAD_BYTES.inc(file_size_bytes)
        if UPLOAD_DURATION:
            UPLOAD_DURATION.observe(duration)
        if UPLOAD_THROUGHPUT_MB_S:
            UPLOAD_THROUGHPUT_MB_S.set(round(throughput, 2))

    return round(throughput, 2)


def set_queue_depth(pending: int, processing: int) -> None:
    """Update active queue gauge."""
    if PROMETHEUS_AVAILABLE and QUEUE_DEPTH:
        QUEUE_DEPTH.labels(state="pending").set(pending)
        QUEUE_DEPTH.labels(state="processing").set(processing)


def get_prometheus_metrics() -> tuple[bytes, str]:
    """Generate Prometheus metrics in exposition format."""
    if not PROMETHEUS_AVAILABLE:
        # Fallback text exposition if prometheus_client not available
        content = b"# Prometheus client not installed\nmeeting_app_status 1\n"
        return content, "text/plain; version=0.0.4"
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST

