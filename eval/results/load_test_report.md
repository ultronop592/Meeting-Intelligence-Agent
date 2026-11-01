# Meeting Intelligence Agent — Concurrent Load Testing Report

**Execution Timestamp:** `2026-11-01T10:13:41.836861+00:00`  
**Evaluation Scope:** 10, 25, and 50 simultaneous audio upload requests to FastAPI backend.

---

## 1. Concurrency Benchmark Summary

| Concurrency | Success Rate | Requests/sec | Throughput (MB/s) | p50 Latency (s) | p95 Latency (s) | p99 Latency (s) | RSS Delta (MB) |
|:-----------:|:------------:|:------------:|:-----------------:|:---------------:|:---------------:|:---------------:|:--------------:|
| **10** | 100.0% | 92.0 | 184.0 MB/s | 0.0922s | 0.107s | 0.107s | +0.0 MB |
| **25** | 100.0% | 137.31 | 274.62 MB/s | 0.1773s | 0.1804s | 0.1805s | +0.0 MB |
| **50** | 100.0% | 130.48 | 260.95 MB/s | 0.3726s | 0.3755s | 0.3778s | +0.0 MB |

## 2. Saturation & Breaking Point Analysis

| Concurrency | p50 Latency | p95 Latency | Relative Degradation | Saturation State | Diagnostic Notes |
|:-----------:|:-----------:|:-----------:|:--------------------:|:----------------:|:-----------------|
| **10** | 0.0922s | 0.107s | 1.0x baseline | ✅ **NORMAL** | Optimal throughput |
| **25** | 0.1773s | 0.1804s | 1.69x baseline | ✅ **NORMAL** | Optimal throughput |
| **50** | 0.3726s | 0.3755s | 3.51x baseline | ⚠️ **SATURATED (>3x)** | Latency spike > 3x over baseline |

## 3. Failure Taxonomy Breakdown

| Concurrency | Timeouts | OOM / Resource | Rate Limits (429) | Validation Errors | Server Errors | Connection Drops |
|:-----------:|:--------:|:--------------:|:-----------------:|:-----------------:|:-------------:|:----------------:|
| **10** | 0 | 0 | 0 | 0 | 0 | 0 |
| **25** | 0 | 0 | 0 | 0 | 0 | 0 |
| **50** | 0 | 0 | 0 | 0 | 0 | 0 |

## 4. Production Sizing & Architecture Recommendations

- **Recommended Max Concurrency per Node:** `25` concurrent uploads.
- **Identified Breaking Point:** `50` concurrent workers without horizontal replica scaling.
- **Worker Pool Architecture:** Sized for `4` worker replicas with `8GB` RAM each.
- **Redis Queue Buffer:** `512MB` maxmemory with `volatile-lru` eviction policy.
- **Audio File Safeguard:** `50MB` hard upload limit enforced by reverse proxy.
- **Rate Limiting Policy:** Enforce per-user token bucket at 10 uploads/min to prevent queue saturation.
