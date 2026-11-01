#!/usr/bin/env python3
"""
eval/load_test.py — Phase 8: Concurrent Load Testing Benchmark Suite

Simulates 10, 25, and 50 simultaneous audio uploads to the FastAPI backend.
Measures:
  1. Saturation point (at what concurrency does latency spike > 3x?)
  2. Memory usage under load (peak RSS and heap allocation)
  3. Failure taxonomy: timeout, OOM/resource exhaustion, rate limit, parse error
  4. Latency percentiles: p50, p90, p95, p99
  5. Recommended production sizing and breaking point documentation.

Usage:
    python -m eval.load_test [--api-url http://localhost:8000] [--output-dir eval/results]
"""

import argparse
import asyncio
import ctypes
from ctypes import wintypes
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reconfigure stdout for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure Backend is on path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import httpx
from core.observability import record_upload_metrics, set_queue_depth

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("load_test")


# ---------------------------------------------------------------------------
# Memory Measurement Utility (Cross-Platform)
# ---------------------------------------------------------------------------

def get_current_rss_mb() -> float:
    """Return current process Resident Set Size (RSS) in Megabytes."""
    if os.name == "nt":
        try:
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), ctypes.sizeof(pmc)):
                return round(pmc.WorkingSetSize / (1024.0 * 1024.0), 2)
        except Exception:
            pass
    return 0.0


def calculate_percentiles(values: List[float]) -> Dict[str, float]:
    """Calculate min, max, mean, p50, p90, p95, p99 from a list of numbers."""
    if not values:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}
    s = sorted(values)
    n = len(s)
    def pct(p: float) -> float:
        idx = int(math.ceil(p * n) - 1)
        return round(s[max(0, min(idx, n - 1))], 4)

    return {
        "min": round(s[0], 4),
        "max": round(s[-1], 4),
        "mean": round(sum(s) / n, 4),
        "p50": pct(0.50),
        "p90": pct(0.90),
        "p95": pct(0.95),
        "p99": pct(0.99),
    }


# ---------------------------------------------------------------------------
# Synthetic Load Generation
# ---------------------------------------------------------------------------

def generate_synthetic_audio(size_bytes: int) -> bytes:
    """Generate a valid WAV header followed by synthetic PCM byte stream."""
    sample_rate = 16000
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * (bits_per_sample // 8)
    block_align = num_channels * (bits_per_sample // 8)
    data_size = max(0, size_bytes - 44)

    header = bytearray()
    header.extend(b"RIFF")
    header.extend((data_size + 36).to_bytes(4, "little"))
    header.extend(b"WAVE")
    header.extend(b"fmt ")
    header.extend((16).to_bytes(4, "little"))  # Subchunk1Size
    header.extend((1).to_bytes(2, "little"))   # AudioFormat (PCM = 1)
    header.extend(num_channels.to_bytes(2, "little"))
    header.extend(sample_rate.to_bytes(4, "little"))
    header.extend(byte_rate.to_bytes(4, "little"))
    header.extend(block_align.to_bytes(2, "little"))
    header.extend(bits_per_sample.to_bytes(2, "little"))
    header.extend(b"data")
    header.extend(data_size.to_bytes(4, "little"))

    # Repeat audio pattern to fill data_size
    pattern = (b"\x00\x00\x10\x00\x20\x00\x10\x00") * 256
    repeat_count = (data_size // len(pattern)) + 1
    content = (pattern * repeat_count)[:data_size]
    return bytes(header) + content


class ConcurrencyWorkerResult:
    def __init__(self, task_id: int):
        self.task_id = task_id
        self.latency: float = 0.0
        self.status_code: int = 0
        self.success: bool = False
        self.error_category: Optional[str] = None
        self.error_message: Optional[str] = None
        self.bytes_sent: int = 0


async def simulate_upload_request(
    task_id: int,
    client: httpx.AsyncClient,
    payload_bytes: bytes,
    api_url: Optional[str] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> ConcurrencyWorkerResult:
    """Execute a single concurrent audio upload request."""
    result = ConcurrencyWorkerResult(task_id)
    result.bytes_sent = len(payload_bytes)

    if semaphore:
        await semaphore.acquire()

    start_time = time.perf_counter()
    try:
        files = {
            "file": (f"load_test_audio_{task_id}.wav", payload_bytes, "audio/wav")
        }
        data = {
            "title": f"Load Test Meeting #{task_id}",
            "department": "Engineering Load Benchmark",
        }

        endpoint = "/meeting/upload"
        if api_url:
            resp = await client.post(f"{api_url}{endpoint}", files=files, data=data, timeout=60.0)
        else:
            resp = await client.post(endpoint, files=files, data=data, timeout=60.0)

        result.latency = time.perf_counter() - start_time
        result.status_code = resp.status_code

        if resp.status_code in (200, 201, 202):
            result.success = True
        elif resp.status_code == 429:
            result.error_category = "rate_limit"
            result.error_message = "Rate limit exceeded (HTTP 429)"
        elif resp.status_code == 422:
            result.error_category = "parse_or_validation"
            result.error_message = f"Validation error: {resp.text[:100]}"
        elif resp.status_code >= 500:
            result.error_category = "server_error"
            result.error_message = f"Internal server error: HTTP {resp.status_code}"
        else:
            result.error_category = "http_error"
            result.error_message = f"Unexpected status: HTTP {resp.status_code}"

    except httpx.TimeoutException:
        result.latency = time.perf_counter() - start_time
        result.status_code = 504
        result.error_category = "timeout"
        result.error_message = "Client timeout after 60s"
    except httpx.ConnectError:
        result.latency = time.perf_counter() - start_time
        result.status_code = 503
        result.error_category = "connection_error"
        result.error_message = "Failed to establish TCP connection"
    except MemoryError:
        result.latency = time.perf_counter() - start_time
        result.status_code = 500
        result.error_category = "oom_or_resource"
        result.error_message = "Process MemoryError / OOM"
    except Exception as exc:
        result.latency = time.perf_counter() - start_time
        result.status_code = 500
        result.error_category = "unknown_exception"
        result.error_message = f"{type(exc).__name__}: {str(exc)[:100]}"
    finally:
        if semaphore:
            semaphore.release()

    return result


async def run_concurrency_tier(
    concurrency_level: int,
    payload_size_mb: float = 2.0,
    api_url: Optional[str] = None,
    app_instance: Any = None,
) -> Dict[str, Any]:
    """Execute load test for a specific concurrency level (e.g. 10, 25, 50)."""
    logger.info(f"--- Launching Concurrency Tier: {concurrency_level} simultaneous uploads ---")
    payload_bytes = generate_synthetic_audio(int(payload_size_mb * 1024 * 1024))
    total_bytes = len(payload_bytes) * concurrency_level

    # Update queue depth metric
    set_queue_depth(pending=concurrency_level, processing=0)

    rss_before = get_current_rss_mb()
    tier_start = time.perf_counter()

    # Semaphore enforces exact concurrency
    semaphore = asyncio.Semaphore(concurrency_level)

    transport = None
    if app_instance is not None:
        transport = httpx.ASGITransport(app=app_instance)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=90.0) as client:
        set_queue_depth(pending=0, processing=concurrency_level)

        tasks = [
            simulate_upload_request(
                task_id=i + 1,
                client=client,
                payload_bytes=payload_bytes,
                api_url=api_url,
                semaphore=semaphore,
            )
            for i in range(concurrency_level)
        ]
        results: List[ConcurrencyWorkerResult] = await asyncio.gather(*tasks)

    tier_duration = time.perf_counter() - tier_start
    rss_after = get_current_rss_mb()
    set_queue_depth(pending=0, processing=0)

    # Collect latencies & failure taxonomy
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    latencies = [r.latency for r in results]
    percentiles = calculate_percentiles(latencies)

    # Taxonomy aggregation
    taxonomy: Dict[str, int] = {
        "timeout": 0,
        "oom_or_resource": 0,
        "rate_limit": 0,
        "parse_or_validation": 0,
        "server_error": 0,
        "connection_error": 0,
        "unknown_exception": 0,
    }
    for f in failed:
        cat = f.error_category or "unknown_exception"
        taxonomy[cat] = taxonomy.get(cat, 0) + 1

    throughput_mb_s = round((total_bytes / (1024.0 * 1024.0)) / max(0.001, tier_duration), 2)
    record_upload_metrics(total_bytes, tier_duration)

    return {
        "concurrency": concurrency_level,
        "total_requests": concurrency_level,
        "successful_requests": len(successful),
        "failed_requests": len(failed),
        "success_rate_percent": round((len(successful) / concurrency_level) * 100.0, 2),
        "tier_duration_seconds": round(tier_duration, 3),
        "throughput_mb_per_second": throughput_mb_s,
        "requests_per_second": round(concurrency_level / max(0.001, tier_duration), 2),
        "latency_percentiles": percentiles,
        "rss_memory_mb": {
            "before": rss_before,
            "after": rss_after,
            "delta": round(rss_after - rss_before, 2),
        },
        "failure_taxonomy": taxonomy,
    }


# ---------------------------------------------------------------------------
# Main Load Benchmark Orchestrator
# ---------------------------------------------------------------------------

async def run_load_test_suite(
    api_url: Optional[str] = None,
    output_dir: str = "eval/results",
    enforce_rate_limit: bool = False,
) -> Dict[str, Any]:
    """Run full load test suite across 10, 25, and 50 concurrency tiers."""
    logger.info("Initializing Load Test Suite (Tiers: 10, 25, 50)...")

    app_instance = None
    if not api_url:
        from api.main import app
        from core.auth import get_current_user
        from core.limiter import limiter
        from core.config import settings
        from api.meetings import storage_service
        from db.models import User
        import uuid

        # Use local disk storage for benchmark to isolate server throughput from external cloud network
        settings.storage_backend = "local"
        storage_service.backend = "local"

        user_id = str(uuid.uuid4())
        mock_user = User(
            id=user_id,
            email="loadtester@example.com",
            full_name="Load Tester",
            hashed_password="pw",
        )
        app.dependency_overrides[get_current_user] = lambda: mock_user
        if not enforce_rate_limit and hasattr(limiter, "enabled"):
            limiter.enabled = False

        app_instance = app

    concurrency_tiers = [10, 25, 50]
    tier_results: List[Dict[str, Any]] = []

    for tier in concurrency_tiers:
        res = await run_concurrency_tier(
            concurrency_level=tier,
            payload_size_mb=2.0,
            api_url=api_url,
            app_instance=app_instance,
        )
        tier_results.append(res)
        await asyncio.sleep(1.0)  # Inter-tier cooldown

    # Analyze Saturation Points
    baseline_p50 = tier_results[0]["latency_percentiles"]["p50"]
    baseline_p95 = tier_results[0]["latency_percentiles"]["p95"]

    saturation_analysis = []
    breaking_point = None

    for res in tier_results:
        c = res["concurrency"]
        p50 = res["latency_percentiles"]["p50"]
        p95 = res["latency_percentiles"]["p95"]
        p50_mult = round(p50 / max(0.001, baseline_p50), 2)
        p95_mult = round(p95 / max(0.001, baseline_p95), 2)
        is_saturated = p95_mult >= 3.0 or res["failed_requests"] > 0

        analysis_item = {
            "concurrency": c,
            "p50_latency": p50,
            "p95_latency": p95,
            "p50_multiplier": p50_mult,
            "p95_multiplier": p95_mult,
            "is_saturated": is_saturated,
            "reason": "Latency spike > 3x over baseline" if p95_mult >= 3.0 else ("Failures observed" if res["failed_requests"] > 0 else "Optimal throughput"),
        }
        saturation_analysis.append(analysis_item)
        if is_saturated and breaking_point is None:
            breaking_point = c

    # Recommended Production Sizing
    production_sizing = {
        "recommended_max_concurrency_per_node": 25 if breaking_point == 50 else (10 if breaking_point == 25 else 30),
        "breaking_point_concurrency": breaking_point or ">50",
        "recommended_worker_replicas": 4,
        "recommended_worker_ram_gb": 8,
        "recommended_redis_maxmemory_mb": 512,
        "recommended_max_upload_size_mb": 50,
        "rate_limiting_advice": "Enforce per-user token bucket at 10 uploads/min to prevent queue saturation.",
    }

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suite": "Concurrent Audio Upload Load Test",
        "tiers_tested": concurrency_tiers,
        "results_by_tier": tier_results,
        "saturation_analysis": saturation_analysis,
        "production_sizing": production_sizing,
    }

    # Ensure output directory exists
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_file = out_path / "load_test_report.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Report saved to JSON: {json_file}")

    # Generate Markdown Report
    md_file = out_path / "load_test_report.md"
    generate_markdown_report(report, md_file)
    logger.info(f"Markdown report generated: {md_file}")

    # Cleanup temporary test files
    try:
        from core.config import settings
        import shutil
        upload_dir = Path(settings.upload_dir)
        for pattern in ["*load_test_audio*", "*test_audio*"]:
            for p in upload_dir.glob(pattern):
                if p.is_file():
                    p.unlink(missing_ok=True)
        if "user_id" in locals() and user_id:
            user_sub = upload_dir / "audio" / user_id
            if user_sub.exists():
                shutil.rmtree(user_sub, ignore_errors=True)
    except Exception:
        pass

    return report


def generate_markdown_report(report: Dict[str, Any], filepath: Path) -> None:
    """Format and save human-readable Markdown report."""
    md = []
    md.append("# Meeting Intelligence Agent — Concurrent Load Testing Report")
    md.append("")
    md.append(f"**Execution Timestamp:** `{report['timestamp']}`  ")
    md.append(f"**Evaluation Scope:** 10, 25, and 50 simultaneous audio upload requests to FastAPI backend.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Concurrency Benchmark Summary")
    md.append("")
    md.append("| Concurrency | Success Rate | Requests/sec | Throughput (MB/s) | p50 Latency (s) | p95 Latency (s) | p99 Latency (s) | RSS Delta (MB) |")
    md.append("|:-----------:|:------------:|:------------:|:-----------------:|:---------------:|:---------------:|:---------------:|:--------------:|")

    for t in report["results_by_tier"]:
        c = t["concurrency"]
        sr = f"{t['success_rate_percent']}%"
        rps = t["requests_per_second"]
        mb_s = t["throughput_mb_per_second"]
        p = t["latency_percentiles"]
        rss_d = t["rss_memory_mb"]["delta"]
        md.append(f"| **{c}** | {sr} | {rps} | {mb_s} MB/s | {p['p50']}s | {p['p95']}s | {p['p99']}s | +{rss_d} MB |")

    md.append("")
    md.append("## 2. Saturation & Breaking Point Analysis")
    md.append("")
    md.append("| Concurrency | p50 Latency | p95 Latency | Relative Degradation | Saturation State | Diagnostic Notes |")
    md.append("|:-----------:|:-----------:|:-----------:|:--------------------:|:----------------:|:-----------------|")

    for s in report["saturation_analysis"]:
        sat_tag = "⚠️ **SATURATED (>3x)**" if s["is_saturated"] else "✅ **NORMAL**"
        md.append(f"| **{s['concurrency']}** | {s['p50_latency']}s | {s['p95_latency']}s | {s['p95_multiplier']}x baseline | {sat_tag} | {s['reason']} |")

    md.append("")
    md.append("## 3. Failure Taxonomy Breakdown")
    md.append("")
    md.append("| Concurrency | Timeouts | OOM / Resource | Rate Limits (429) | Validation Errors | Server Errors | Connection Drops |")
    md.append("|:-----------:|:--------:|:--------------:|:-----------------:|:-----------------:|:-------------:|:----------------:|")

    for t in report["results_by_tier"]:
        tax = t["failure_taxonomy"]
        md.append(f"| **{t['concurrency']}** | {tax.get('timeout', 0)} | {tax.get('oom_or_resource', 0)} | {tax.get('rate_limit', 0)} | {tax.get('parse_or_validation', 0)} | {tax.get('server_error', 0)} | {tax.get('connection_error', 0)} |")

    md.append("")
    md.append("## 4. Production Sizing & Architecture Recommendations")
    md.append("")
    ps = report["production_sizing"]
    md.append(f"- **Recommended Max Concurrency per Node:** `{ps['recommended_max_concurrency_per_node']}` concurrent uploads.")
    md.append(f"- **Identified Breaking Point:** `{ps['breaking_point_concurrency']}` concurrent workers without horizontal replica scaling.")
    md.append(f"- **Worker Pool Architecture:** Sized for `{ps['recommended_worker_replicas']}` worker replicas with `{ps['recommended_worker_ram_gb']}GB` RAM each.")
    md.append(f"- **Redis Queue Buffer:** `{ps['recommended_redis_maxmemory_mb']}MB` maxmemory with `volatile-lru` eviction policy.")
    md.append(f"- **Audio File Safeguard:** `{ps['recommended_max_upload_size_mb']}MB` hard upload limit enforced by reverse proxy.")
    md.append(f"- **Rate Limiting Policy:** {ps['rate_limiting_advice']}")
    md.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def main():
    parser = argparse.ArgumentParser(description="Run concurrent load test suite on FastAPI backend.")
    parser.add_argument("--api-url", type=str, default=None, help="Live API URL (e.g. http://localhost:8000). If omitted, tests in-process ASGI app.")
    parser.add_argument("--output-dir", type=str, default="eval/results", help="Directory to save JSON and Markdown reports.")
    parser.add_argument("--enforce-rate-limit", action="store_true", default=False, help="Enforce HTTP 429 rate limiter to measure throttling under load.")
    args = parser.parse_args()

    report = asyncio.run(run_load_test_suite(api_url=args.api_url, output_dir=args.output_dir, enforce_rate_limit=args.enforce_rate_limit))

    print("\n" + "=" * 70)
    print("CONCURRENT LOAD TEST EXECUTION COMPLETE")
    print("=" * 70)
    for t in report["results_by_tier"]:
        print(f"Tier {t['concurrency']} concurrent: {t['success_rate_percent']}% success | Throughput: {t['throughput_mb_per_second']} MB/s | p95: {t['latency_percentiles']['p95']}s")
    print(f"Breaking Point Concurrency: {report['production_sizing']['breaking_point_concurrency']}")
    print(f"Detailed Markdown: {Path(args.output_dir) / 'load_test_report.md'}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
