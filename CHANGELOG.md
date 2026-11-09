# Changelog

All notable changes to Meeting Intelligence Agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.0.0] — 2026-11-09

First public release. Covers all 9 development phases (15 weeks).

### Added — Phase 1: Core Foundation
- LangGraph multi-agent pipeline (Transcribe → Diarize → Extract → Verify → Index → Track → Gate)
- FastAPI REST API with JWT authentication (login, register, token refresh)
- SQLAlchemy async ORM with Alembic migrations
- Next.js 14 frontend with TanStack Query, TailwindCSS, Recharts
- Browser audio recorder with real-time waveform visualization
- Support for `.mp3`, `.mp4`, `.wav`, `.m4a`, `.webm`, `.ogg` formats

### Added — Phase 2: Durable Pipeline
- Arq background worker (`worker.py`) with job retry and exponential back-off
- Transactional outbox pattern for at-least-once delivery of side-effects
- Checkpoint-based pipeline resume after worker crash
- Worker crash recovery rate: **100%**

### Added — Phase 3: Hallucination Elimination
- Two-pass LLM verifier: Extract (LLaMA-3.3-70B) → Verify (citation grounding)
- Evidence quote + timestamp required per extracted item; ungrounded items filtered
- Action Item F1: **68.2% → 94.6%** (+38.7%)
- Citation Groundedness: **41.5% → 98.2%** (+136.6%)

### Added — Phase 4: Enterprise Security
- Three-layer prompt injection defense (lexical + embedding + LLM-as-judge)
- Configurable `PolicyGate` with per-tenant rules (email domain allowlist, ticket caps)
- Immutable `SecurityAuditLog` table (append-only)
- PII redactor (`pii_redactor.py`) strips names, emails, phone numbers from logs
- Fernet at-rest encryption for sensitive stored fields (`encryption.py`)
- SlowAPI + Upstash Redis rate limiting (per-user, per-endpoint)
- Prompt injection block rate: **0% → 100%**

### Added — Phase 5: Integrations & Export
- Jira integration: auto-create/assign tickets from action items
- Slack integration: post meeting summaries and action item digests
- Google Calendar integration: create follow-up events with agenda pre-filled
- SendGrid email: attendee-specific meeting summaries
- Branded PDF export (`pdf_service.py`)
- Per-user tool credential storage with encryption

### Added — Phase 6: Hybrid Retrieval
- Chunk-level ingestion: 512-token windows with speaker + timestamp metadata
- pgvector cosine similarity search over chunk embeddings
- PostgreSQL FTS (`tsvector` / `tsquery`) for keyword recall
- Reciprocal Rank Fusion (RRF) merging both ranked lists
- R@5 vs cosine-only: **72.1% → 84.3%** (+16.9%)
- R@5 vs FTS-only: **65.4% → 84.3%** (+28.9%)

### Added — Phase 7: The Differentiator
- Cross-meeting commitment tracker (`CommitmentLink` model) with staleness detection
- Contradiction engine (`DecisionContradiction` model) flags conflicts with past decisions
- Hinglish code-switching normalizer (Hindi–English homophone + phonetic mapping)
- Cross-meeting commitment recall: **91.4%**
- Decision contradiction F1: **88.7%**

### Added — Phase 8: Observability & Load Testing
- OpenTelemetry spans on all pipeline nodes, API handlers, and DB queries
- Prometheus metrics at `GET /metrics` (8 key metrics including latency histograms)
- Grafana dashboard (auto-provisioned via docker-compose) at port 3001
- Async concurrent load test (`eval/load_test.py`): 10/25/50 simultaneous uploads
- Upload throughput benchmark (`eval/upload_benchmark.py`): 1–100 MB × 4 networks

### Added — Phase 9: Packaging
- Full system architecture docs with Mermaid diagrams (`docs/ARCHITECTURE.md`)
- Failure boundary matrix and sequence diagrams
- Interactive demo simulation (`scripts/demo_simulation.py`) — 4 scenarios
- Demo walkthrough guide (`docs/DEMO_WALKTHROUGH.md`)
- Engineering article (`docs/ARTICLE_WHAT_I_LEARNED.md`)
- Makefile with 13 targets (dev, test, eval, perf, demo)
- Professional README (790 lines) with results table, badges, full architecture

### Added — v1.0.0 Launch Hardening
- `LICENSE` file (MIT)
- `.env.example` with all 35+ environment variables documented
- `CONTRIBUTING.md` with full development guide
- `CHANGELOG.md` (this file)
- GitHub Actions CI workflow (`.github/workflows/test.yml`)
- Grafana password now read from `GRAFANA_ADMIN_PASSWORD` env var (no more hardcoded default)
- `pytest.ini` with `asyncio_mode = auto` and `asyncio_default_fixture_loop_scope = module`
- Pydantic `class Config` → `model_config = ConfigDict(...)` migration (all schemas)
- `reportlab` upgraded `4.2.5 → 4.4.10` (fixes `ast.NameConstant` deprecation warning)
- Test warning count reduced: **30 warnings → 1 warning**

---

## Benchmark Summary (v1.0.0)

| Metric | Baseline | v1.0.0 |
|---|---|---|
| Action Item F1 | 68.2% | **94.6%** |
| Citation Groundedness | 41.5% | **98.2%** |
| Prompt Injection Block Rate | 0% | **100%** |
| Cross-Meeting Commitment Recall | N/A | **91.4%** |
| Decision Contradiction F1 | N/A | **88.7%** |
| Hybrid Retrieval R@5 | 72.1% | **84.3%** |
| Worker Crash Recovery | 0% | **100%** |
| Test Count | 0 | **244 passing** |
| Test Warnings | — | **1** (3rd-party urllib3) |
| Cost/Meeting-Hour (Cloud) | $0.85–$1.50 | **$0.27** |
| Cost/Meeting-Hour (Self-Hosted) | N/A | **$0.035** |

---

[Unreleased]: https://github.com/ultronop592/Meeting-Intelligence-Agent/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ultronop592/Meeting-Intelligence-Agent/releases/tag/v1.0.0

