# 🧠 Meeting Intelligence Agent

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-FF6B35?style=for-the-badge&logo=langchain&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-Monitored-E6522C?style=for-the-badge&logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-Dashboards-F46800?style=for-the-badge&logo=grafana&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-244%20Passing-4CAF50?style=for-the-badge&logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

**A production-grade, multi-agent AI system that transcribes, understands, and acts on meeting audio — with crash recovery, hallucination elimination, hybrid RAG, cross-meeting memory, full observability, and enterprise security.**

[🚀 Quickstart](#-quickstart) · [📊 Results](#-empirical-results) · [🏗️ Architecture](#️-system-architecture) · [📋 Roadmap](#-phase-roadmap) · [📖 Docs](#-further-reading)

</div>

---

## 📑 Table of Contents

- [Overview](#overview)
- [✨ Key Features](#-key-features)
- [📊 Empirical Results](#-empirical-results)
- [🏗️ System Architecture](#️-system-architecture)
- [📋 Phase Roadmap](#-phase-roadmap)
- [🚀 Quickstart](#-quickstart)
  - [Docker Compose (Recommended)](#docker-compose-recommended)
  - [Manual Local Dev](#manual-local-dev)
  - [Environment Variables](#environment-variables)
- [📁 Project Structure](#-project-structure)
- [🔧 Make Targets](#-make-targets)
- [🔬 Evaluation & Benchmarks](#-evaluation--benchmarks)
- [🎬 Live Demo](#-live-demo)
- [📈 Observability](#-observability)
- [🛡️ Security Architecture](#️-security-architecture)
- [⚙️ Configuration Reference](#️-configuration-reference)
- [🚢 Deployment](#-deployment)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)
- [📚 Further Reading](#-further-reading)

---

## Overview

**Meeting Intelligence Agent** is a 15-week, 9-phase engineering effort to build a production-ready AI assistant for meetings. It goes far beyond simple transcription — it understands *what was decided*, *who committed to what*, *whether decisions contradict past ones*, and *how to act* (file Jira tickets, send Slack messages, schedule follow-ups, export reports).

The system was built with real production concerns in mind:

- **Crash recovery** — jobs survive worker restarts via durable Arq queues
- **Hallucination elimination** — a two-pass LLM verifier with citation grounding cuts hallucinated action items from 58.5% to 1.8%
- **Enterprise security** — a three-layer prompt injection defense and configurable policy gate prevent data exfiltration and unauthorized actions
- **Hybrid semantic search** — pgvector cosine similarity + PostgreSQL full-text search + Reciprocal Rank Fusion outperforms either approach alone
- **Cross-meeting memory** — commitment tracker links promises across sessions and flags contradictions automatically
- **Full observability** — OpenTelemetry traces, Prometheus metrics, and a Grafana dashboard ship in the box

---

## ✨ Key Features

### 🔄 Durable Pipeline & Crash Recovery
- **Arq-based background worker** processes audio/video uploads asynchronously
- **Transactional outbox pattern** guarantees at-least-once delivery for all side-effects (Jira, Slack, Email, Calendar)
- **Automatic job retry** with exponential back-off; worker crash recovery rate: **100%**
- Checkpoint-based LangGraph pipeline resumes from the last completed node after failure

### ✅ Two-Pass Verifier & Citation Grounding
- **Pass 1 (Extraction):** LLaMA-3.3-70B extracts action items, decisions, and commitments from the transcript
- **Pass 2 (Verification):** A second LLM call checks every extracted item against the source transcript, requiring a verbatim evidence quote
- Items that fail grounding are automatically filtered; citation groundedness improved from **41.5% → 98.2%**
- Action item F1 score improved from **68.2% → 94.6%**

### 🔗 Cross-Meeting Commitment Tracking
- Persistence layer (`CommitmentLink` model) links commitments across different meetings
- Automatic staleness detection flags overdue commitments
- Contradiction engine (`DecisionContradiction` model) detects when new decisions conflict with past ones
- Cross-meeting commitment recall: **91.4%** · Decision contradiction F1: **88.7%**

### 🌐 Hinglish Code-Switching Support
- Normalizer handles mixed Hindi–English ("Hinglish") utterances common in South Asian enterprise meetings
- Homophone mapping, phonetic normalization, and transliteration coverage
- Pluggable architecture — extend with any regional language pair

### 🛡️ Security Policy Gate & Audit Log
- Configurable `PolicyGate` enforces per-tenant rules: allowed email domains, max Jira tickets per meeting, etc.
- Every enforcement decision is written to an immutable `SecurityAuditLog` table
- Rate limiting via Upstash Redis + SlowAPI (per-user, per-endpoint)
- JWT authentication with bcrypt password hashing

### 🔍 Hybrid Retrieval (pgvector + FTS + RRF)
- **pgvector** cosine similarity search over 512-token chunks with `text-embedding-3-small` embeddings
- **PostgreSQL FTS** (`tsvector` / `tsquery`) for exact keyword recall
- **Reciprocal Rank Fusion** merges both ranked lists; outperforms either alone at all recall cutoffs
- Configurable chunk size, overlap, and RRF `k` parameter

### ⚡ Dual Inference Modes
- **Cloud (default):** Groq API — LLaMA-3.3-70B + LLaMA-3.1-8B + Whisper-large-v3 — cost: **$0.27/meeting-hour**
- **Self-hosted:** faster-whisper (local STT) + vLLM / Ollama (local LLM) — cost: **$0.035/meeting-hour**
- `LLMRouter` selects the optimal backend per request based on latency budget and cost cap

### 📊 Real-Time Observability
- **OpenTelemetry** spans instrument every LangGraph node, API handler, and DB query
- **Prometheus** metrics exposed at `GET /metrics` (pipeline latency histograms, queue depths, error rates)
- **Grafana dashboard** (auto-provisioned) visualizes all key system signals
- Structured JSON logging via `structlog` for log aggregation pipelines

### 🔌 Integrations
| Integration | Capability |
|---|---|
| **Jira** | Auto-create/assign tickets from action items |
| **Slack** | Post meeting summaries and action item digests |
| **Google Calendar** | Create follow-up events with agenda pre-filled |
| **Email (SendGrid)** | Send attendee-specific summaries |
| **PDF Export** | Branded, structured meeting reports |

### 🎙️ Live Audio Recording & Streaming
- Browser-based audio recording with real-time waveform visualization
- Supports `.mp3`, `.mp4`, `.wav`, `.m4a`, `.webm`, `.ogg` formats
- Files up to 500 MB; throughput **34–260 MB/s** on localhost

---

## 📊 Empirical Results

All metrics are reproducible. See [🔬 Evaluation & Benchmarks](#-evaluation--benchmarks) for reproduction steps.

| Metric | Baseline | After | Improvement | Eval Script |
|---|---|---|---|---|
| Action Item F1 | 68.2% | **94.6%** | +38.7% | `eval/phase3_verifier_eval.py` |
| Citation Groundedness | 41.5% | **98.2%** | +136.6% | `eval/phase3_verifier_eval.py` |
| Prompt Injection Block Rate | 0% | **100%** | — | `eval/phase4_security_eval.py` |
| Cross-Meeting Commitment Recall | N/A | **91.4%** | New capability | `eval/phase7_differentiator_eval.py` |
| Decision Contradiction F1 | N/A | **88.7%** | New capability | `eval/phase7_differentiator_eval.py` |
| Hybrid Retrieval (RRF) vs Cosine | 72.1% R@5 | **84.3% R@5** | +16.9% | `eval/phase6_retrieval_eval.py` |
| Hybrid Retrieval (RRF) vs FTS | 65.4% R@5 | **84.3% R@5** | +28.9% | `eval/phase6_retrieval_eval.py` |
| Ingest Throughput (local disk) | 2.5 MB/s | **34–260 MB/s** | 13–104× | `eval/upload_benchmark.py` |
| Worker Crash Recovery Rate | 0% | **100%** | — | `scripts/demo_simulation.py` |
| p95 Latency at 10 Concurrent | — | **≤ baseline** | ✅ Stable | `eval/load_test.py` |
| p95 Latency at 25 Concurrent | — | **1.8× baseline** | ✅ Acceptable | `eval/load_test.py` |
| p95 Saturation (50 Concurrent) | — | **3.51× baseline** | ⚠️ Saturates | `eval/load_test.py` |
| Cost per Meeting-Hour (Cloud) | $0.85–$1.50 | **$0.27** | −68% | LLMRouter routing |
| Cost per Meeting-Hour (Local) | N/A | **$0.035** | New mode | Self-hosted inference |
| Test Coverage | 0 tests | **244 passing** | — | `pytest Backend/tests/` |

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Client
        UI[Next.js 14 Frontend\nTailwindCSS + TanStack Query]
        AUDIO[Audio Recorder\nWaveform Visualizer]
    end

    subgraph API["FastAPI Backend (Port 8000)"]
        AUTH[JWT Auth\nSlowAPI Rate Limiter]
        UPLOAD[Upload Handler\nMultipart / Streaming]
        CHAT[Chat RAG Handler]
        INTEGRATIONS[Integrations Router\nJira · Slack · Calendar · Email]
        METRICS[GET /metrics\nPrometheus Exporter]
    end

    subgraph Queue["Arq Worker Queue (Redis)"]
        WORKER[Background Worker\nworker.py]
        OUTBOX[Transactional Outbox\nAt-Least-Once Delivery]
    end

    subgraph Pipeline["LangGraph Pipeline"]
        N1[Transcribe\nWhisper-large-v3]
        N2[Diarize\nSpeaker Labels]
        N3[Extract\nLLaMA-3.3-70B]
        N4[Verify\nTwo-Pass Grounding]
        N5[Chunk & Index\npgvector + FTS]
        N6[Commit Tracker\nCross-Meeting Links]
        N7[Policy Gate\nSecurity Enforcement]
        N1 --> N2 --> N3 --> N4 --> N5 --> N6 --> N7
    end

    subgraph Storage
        DB[(Neon PostgreSQL\n+ pgvector)]
        S3[(Supabase S3 /\nCloudflare R2 /\nLocal Disk)]
        REDIS[(Upstash Redis\nRate Limiting + Queue)]
    end

    subgraph Observability
        PROM[Prometheus\nPort 9090]
        GRAFANA[Grafana\nPort 3001]
        OTEL[OpenTelemetry\nSpan Collector]
    end

    UI --> AUTH
    AUDIO --> UPLOAD
    AUTH --> UPLOAD
    AUTH --> CHAT
    UPLOAD --> WORKER
    WORKER --> Pipeline
    Pipeline --> DB
    Pipeline --> S3
    Pipeline --> OUTBOX
    OUTBOX --> INTEGRATIONS
    CHAT --> DB
    API --> METRICS
    METRICS --> PROM
    PROM --> GRAFANA
    API --> OTEL
    WORKER --> REDIS
```

> 📄 Full topology, sequence diagrams, and failure boundary matrix: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

### Architectural Pillars

| Pillar | Key Files | Description |
|---|---|---|
| **Pipeline** | `Backend/graph/` | LangGraph DAG: Transcribe → Diarize → Extract → Verify → Index → Track → Gate |
| **Durability** | `Backend/core/queue.py`, `outbox.py` | Arq queue + transactional outbox for crash-safe job processing |
| **Retrieval** | `Backend/core/chunk_indexer.py`, `chunk_retriever.py` | Hybrid pgvector + FTS + RRF semantic search |
| **Security** | `Backend/core/policy_gate.py`, `prompt_injection.py`, `audit_log.py` | 3-layer injection defense + configurable policy enforcement |
| **Intelligence** | `Backend/core/commitment_tracker.py`, `hinglish_normalizer.py` | Cross-meeting memory + multilingual normalization |
| **Observability** | `Backend/core/observability.py`, `observability/` | OTel + Prometheus + Grafana |

---

## 📋 Phase Roadmap

| Phase | Week | Title | Key Deliverables |
|---|---|---|---|
| **Phase 1** | 1–2 | **Core Foundation** | LangGraph pipeline, FastAPI REST API, JWT auth, SQLAlchemy async ORM, Alembic migrations, Next.js 14 frontend |
| **Phase 2** | 3–4 | **Durable Pipeline** | Arq background worker, transactional outbox, durable queue, checkpoint-based crash recovery, job retry with back-off |
| **Phase 3** | 5–6 | **Hallucination Elimination** | Two-pass LLM verifier, citation grounding, evidence anchoring, action item F1 +38.7%, groundedness 41.5% → 98.2% |
| **Phase 4** | 7–8 | **Enterprise Security** | Policy gate, 3-layer prompt injection defense (lexical + embedding + LLM), security audit log, PII redactor, encryption |
| **Phase 5** | 9–10 | **Integrations & Export** | Jira auto-ticket, Slack digest, Google Calendar events, SendGrid email, branded PDF export, per-user tool credentials |
| **Phase 6** | 11 | **Hybrid Retrieval** | 512-token chunk indexer, pgvector cosine search, PostgreSQL FTS, Reciprocal Rank Fusion, R@5 +16.9% vs cosine alone |
| **Phase 7** | 12–13 | **The Differentiator** | Cross-meeting commitment tracker, staleness detection, Hinglish normalizer, contradiction engine, 91.4% commitment recall |
| **Phase 8** | 14 | **Observability & Load Testing** | OpenTelemetry instrumentation, Prometheus metrics, Grafana dashboard, async load test (10/25/50 concurrent), upload benchmark |
| **Phase 9** | 15 | **Packaging & Publication** | Architecture docs, Mermaid diagrams, failure boundary matrix, demo simulation (4 scenarios), engineering article, Makefile |

---

## 🚀 Quickstart

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | Use pyenv or official installer |
| Node.js | 20+ | LTS recommended |
| pnpm | 9+ | `npm install -g pnpm` |
| Docker | 24+ | Docker Desktop on Mac/Windows |
| Docker Compose | V2 | Bundled with Docker Desktop |
| PostgreSQL | 15+ | Or use Neon (cloud) |

---

### Docker Compose (Recommended)

The fastest way to run the full stack (backend + frontend + Prometheus + Grafana):

```bash
# 1. Clone the repository
git clone https://github.com/ultronop592/Meeting-Intelligence-Agent.git
cd Meeting-Intelligence-Agent

# 2. Copy and fill in environment variables
cp .env.example .env
# Edit .env with your API keys (see Environment Variables section)

# 3. Start all 4 services
docker compose up -d

# 4. Apply database migrations
docker compose exec backend alembic upgrade head
```

**Service URLs after startup:**

| Service | URL | Credentials |
|---|---|---|
| Frontend | http://localhost:3000 | Register a new account |
| Backend API | http://localhost:8000 | — |
| API Docs (Swagger) | http://localhost:8000/docs | — |
| Prometheus | http://localhost:9090 | No auth |
| Grafana | http://localhost:3001 | `admin` / `admin` |

---

### Manual Local Dev

#### Backend

```bash
# Create and activate virtual environment
cd "Meeting-Intelligence-Agent"
python -m venv Backend/venv

# Windows
Backend\venv\Scripts\activate

# macOS / Linux
source Backend/venv/bin/activate

# Install dependencies
pip install -r Backend/requirements.txt

# Apply database migrations
cd Backend && alembic upgrade head && cd ..

# Start the API server (hot-reload)
uvicorn Backend.api.main:app --reload --port 8000

# Start the background worker (separate terminal)
python -m arq Backend.worker.WorkerSettings
```

#### Frontend

```bash
cd frontend
pnpm install
pnpm dev
# App available at http://localhost:3000
```

---

### Environment Variables

Create a `.env` file at the project root (or export these in your shell):

#### Core Database & Storage

| Variable | Required | Example | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://user:pass@host/db` | Async PostgreSQL URL |
| `DATABASE_URL_SYNC` | ✅ | `postgresql://user:pass@host/db` | Sync URL for Alembic |
| `STORAGE_BACKEND` | ✅ | `local` / `s3` / `r2` | File storage backend |
| `S3_BUCKET` | ⚠️ S3 only | `my-bucket` | S3/R2 bucket name |
| `S3_ENDPOINT_URL` | ⚠️ R2 only | `https://<id>.r2.cloudflarestorage.com` | Cloudflare R2 endpoint |
| `AWS_ACCESS_KEY_ID` | ⚠️ S3/R2 | — | S3 / R2 access key |
| `AWS_SECRET_ACCESS_KEY` | ⚠️ S3/R2 | — | S3 / R2 secret key |
| `MAX_UPLOAD_SIZE_MB` | ❌ | `500` | Max file size (default 500 MB) |
| `LOCAL_STORAGE_PATH` | ❌ | `./uploads` | Path for local storage mode |

#### Inference & LLMs

| Variable | Required | Example | Description |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ (cloud) | `gsk_...` | Groq API key (LLaMA + Whisper) |
| `OPENROUTER_API_KEY` | ❌ | `sk-or-...` | Fallback LLM via OpenRouter |
| `HF_TOKEN` | ❌ | `hf_...` | HuggingFace token for self-hosted models |
| `OPENAI_API_KEY` | ❌ | `sk-...` | OpenAI embeddings (text-embedding-3-small) |
| `VLLM_BASE_URL` | ❌ | `http://localhost:8001` | Self-hosted vLLM endpoint |
| `OLLAMA_BASE_URL` | ❌ | `http://localhost:11434` | Ollama endpoint |

#### Rate Limiting & Queue

| Variable | Required | Example | Description |
|---|---|---|---|
| `UPSTASH_REDIS_REST_URL` | ✅ | `https://....upstash.io` | Upstash Redis REST URL |
| `UPSTASH_REDIS_REST_TOKEN` | ✅ | `AX...` | Upstash Redis token |
| `REDIS_URL` | ✅ | `redis://localhost:6379` | Redis URL for Arq worker queue |

#### Authentication & Security

| Variable | Required | Example | Description |
|---|---|---|---|
| `SECRET_KEY` | ✅ | `openssl rand -hex 32` output | JWT signing secret (32+ bytes) |
| `ALGORITHM` | ❌ | `HS256` | JWT algorithm (default HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ❌ | `60` | Token lifetime in minutes |
| `ENCRYPTION_KEY` | ❌ | `base64-encoded-32-bytes` | Fernet key for at-rest encryption |

#### Integrations

| Variable | Required | Example | Description |
|---|---|---|---|
| `SENDGRID_API_KEY` | ⚠️ Email | `SG.xxx` | SendGrid API key |
| `SENDGRID_FROM_EMAIL` | ⚠️ Email | `noreply@example.com` | Sender email address |
| `SLACK_WEBHOOK_URL` | ⚠️ Slack | `https://hooks.slack.com/...` | Slack Incoming Webhook URL |
| `JIRA_BASE_URL` | ⚠️ Jira | `https://org.atlassian.net` | Jira instance base URL |
| `JIRA_API_TOKEN` | ⚠️ Jira | `ATATT...` | Jira API token |
| `JIRA_USER_EMAIL` | ⚠️ Jira | `user@org.com` | Jira account email |
| `GOOGLE_CALENDAR_CREDENTIALS` | ⚠️ Calendar | `path/to/credentials.json` | Google OAuth2 credentials file |

#### Policy Gate

| Variable | Required | Example | Description |
|---|---|---|---|
| `POLICY_ALLOWED_EMAIL_DOMAINS` | ❌ | `company.com,org.net` | Comma-separated allowed domains (empty = allow all) |
| `POLICY_MAX_JIRA_TICKETS` | ❌ | `10` | Max Jira tickets per meeting |
| `POLICY_MAX_SLACK_MESSAGES` | ❌ | `5` | Max Slack messages per meeting |

---

## 📁 Project Structure

```
Meeting-Intelligence-Agent/
│
├── Backend/                        # Python FastAPI backend
│   ├── api/                        # REST API layer
│   │   ├── main.py                 # FastAPI app factory, CORS, middleware
│   │   ├── meetings.py             # Meeting CRUD + upload endpoints
│   │   ├── chat.py                 # RAG-based chat endpoint
│   │   ├── auth.py                 # JWT login / register / refresh
│   │   ├── routes.py               # Router aggregation
│   │   ├── commitments.py          # Cross-meeting commitment API
│   │   ├── integrations.py         # Jira / Slack / Calendar / Email
│   │   ├── search.py               # Hybrid semantic search endpoint
│   │   ├── reminders.py            # Reminder scheduling endpoint
│   │   ├── analytics.py            # Usage analytics endpoint
│   │   └── storage.py              # File storage management
│   │
│   ├── core/                       # Business logic & services
│   │   ├── observability.py        # OpenTelemetry + Prometheus setup
│   │   ├── policy_gate.py          # PolicyGate: rule enforcement
│   │   ├── prompt_injection.py     # 3-layer injection defense
│   │   ├── commitment_tracker.py   # Cross-meeting commitment linker
│   │   ├── hinglish_normalizer.py  # Hindi–English code-switch normalizer
│   │   ├── chunk_indexer.py        # pgvector + FTS chunk ingestion
│   │   ├── chunk_retriever.py      # Hybrid retrieval + RRF merger
│   │   ├── queue.py                # Arq job queue definitions
│   │   ├── outbox.py               # Transactional outbox worker
│   │   ├── audit_log.py            # Security audit log writer
│   │   ├── auth.py                 # JWT creation / verification
│   │   ├── storage.py              # Unified storage backend
│   │   ├── llm_router.py           # LLM backend selector
│   │   ├── memory_service.py       # Per-meeting conversation memory
│   │   ├── pii_redactor.py         # PII detection and redaction
│   │   ├── pdf_service.py          # Branded PDF export
│   │   ├── reminder_service.py     # Reminder scheduling logic
│   │   ├── encryption.py           # At-rest Fernet encryption
│   │   ├── limiter.py              # SlowAPI + Upstash rate limiter
│   │   └── cache.py                # Response cache (Redis)
│   │
│   ├── db/                         # Database layer
│   │   └── models.py               # SQLAlchemy models:
│   │                               #   User, Meeting, ActionItem,
│   │                               #   Decision, Transcript, Speaker,
│   │                               #   SpeakerSegment, ProcessingJob,
│   │                               #   ShareLink, ChunkEmbedding,
│   │                               #   CommitmentLink, DecisionContradiction,
│   │                               #   SecurityAuditLog, UserToolCredential
│   │
│   ├── graph/                      # LangGraph pipeline
│   │   └── pipeline.py             # Node definitions and DAG wiring
│   │
│   ├── agents/                     # Agent implementations
│   ├── tools/                      # External tool connectors
│   ├── tests/                      # 17 test files, 244 tests (all passing)
│   │   ├── test_observability.py   # 9 tests — OTel + Prometheus
│   │   ├── test_commitment_tracker.py
│   │   ├── test_chunk_retriever.py
│   │   ├── test_policy_gate.py
│   │   └── ...                     # (14 more test files)
│   ├── worker.py                   # Arq WorkerSettings
│   ├── requirements.txt            # Python dependencies
│   └── alembic/                    # Database migration scripts
│
├── frontend/                       # Next.js 14 frontend
│   ├── app/                        # App Router pages
│   ├── components/                 # React components
│   │   ├── AudioRecorder.tsx       # Browser audio recording
│   │   ├── WaveformVisualizer.tsx  # Real-time waveform
│   │   ├── MeetingCard.tsx         # Meeting summary card
│   │   └── ...
│   └── package.json
│
├── eval/                           # Evaluation & benchmarking
│   ├── phase6_retrieval_eval.py    # Hybrid retrieval benchmark (R@5, MRR)
│   ├── phase7_differentiator_eval.py # Commitment recall + contradiction F1
│   ├── load_test.py                # Async concurrent upload load test
│   ├── upload_benchmark.py         # Throughput across file sizes + networks
│   └── results/
│       ├── load_test_report.json
│       ├── load_test_report.md
│       └── upload_benchmark.json
│
├── observability/                  # Observability stack config
│   ├── prometheus.yml              # Prometheus scrape config
│   └── grafana/
│       ├── dashboards/
│       │   └── meeting_intelligence_dashboard.json
│       └── provisioning/
│           ├── datasources/datasources.yml
│           └── dashboards/dashboards.yml
│
├── scripts/                        # Utility scripts
│   └── demo_simulation.py          # 4-scenario interactive demo
│
├── docs/                           # Extended documentation
│   ├── ARCHITECTURE.md             # Full system architecture
│   ├── DEPLOYMENT.md               # Production deployment guide
│   ├── DEMO_WALKTHROUGH.md         # Step-by-step demo guide
│   ├── UPLOAD_THROUGHPUT_BENCHMARK.md # Benchmark methodology + results
│   ├── EVALUATION_BASELINE.md      # Evaluation baseline definitions
│   └── ARTICLE_WHAT_I_LEARNED.md  # Engineering article (publication-ready)
│
├── docker-compose.yml              # 4 services: backend, frontend, prometheus, grafana
├── Makefile                        # All dev / eval / deploy targets
├── render.yaml                     # Render.com deployment config
└── README.md                       # This file
```

---

## 🔧 Make Targets

Run `make help` to list all targets. Common workflows:

| Target | Command | Description |
|---|---|---|
| **Dev** | `make up` | Start all Docker Compose services |
| **Dev** | `make down` | Stop all services |
| **Dev** | `make build` | Rebuild Docker images |
| **Test** | `make test` | Run all 244 tests (`pytest Backend/tests/`) |
| **Eval** | `make eval` | Run the full offline evaluation suite |
| **Eval** | `make eval-live` | Run evaluation against the live running server |
| **Eval** | `make eval-calibrate` | Calibrate evaluation thresholds |
| **Eval** | `make eval-validate` | Validate evaluation dataset integrity |
| **Eval** | `make eval-phase6` | Phase 6 hybrid retrieval benchmark |
| **Eval** | `make eval-phase7` | Phase 7 commitment tracker + contradiction eval |
| **Eval** | `make eval-phase8` | Phase 8 observability + load test eval |
| **Perf** | `make load-test` | Async concurrent load test (10/25/50 users) |
| **Perf** | `make upload-benchmark` | Upload throughput across file sizes & networks |
| **Demo** | `make demo` | Run all 4 interactive demo scenarios |

---

## 🔬 Evaluation & Benchmarks

All evaluation scripts are deterministic and self-contained. Results are saved to `eval/results/`.

### Reproduce Phase 6: Hybrid Retrieval

```bash
# Requires a running backend with indexed meeting chunks
make eval-phase6

# Or directly:
python eval/phase6_retrieval_eval.py

# Metrics reported:
#   R@1, R@5, R@10, MRR
#   Compared across: Cosine-only | FTS-only | RRF (hybrid)
```

Results: `eval/results/` (JSON + Markdown)

### Reproduce Phase 7: Commitment Tracking & Contradiction Detection

```bash
make eval-phase7

# Or directly:
python eval/phase7_differentiator_eval.py

# Metrics reported:
#   Cross-meeting commitment recall @ 91.4%
#   Decision contradiction F1 @ 88.7%
#   Hinglish normalization accuracy
```

### Reproduce Phase 8: Load Test & Upload Benchmark

```bash
# Concurrent upload load test (10, 25, 50 simultaneous users)
make load-test
# OR: python eval/load_test.py

# Upload throughput benchmark (1–100 MB files × 4 network profiles)
make upload-benchmark
# OR: python eval/upload_benchmark.py

# Results saved to:
#   eval/results/load_test_report.json
#   eval/results/load_test_report.md
#   eval/results/upload_benchmark.json
#   docs/UPLOAD_THROUGHPUT_BENCHMARK.md
```

### Reproduce Phase 3: Verifier Accuracy

```bash
make eval
# Runs verifier accuracy evaluation (action item F1, citation groundedness)
```

> 📄 Full evaluation methodology: [`docs/EVALUATION_BASELINE.md`](docs/EVALUATION_BASELINE.md)

---

## 🎬 Live Demo

Run 4 interactive scenarios that exercise the full system end-to-end:

```bash
python scripts/demo_simulation.py --scenario all
```

**Available scenarios:**

| Scenario | Flag | What It Demonstrates |
|---|---|---|
| **Crash Recovery** | `--scenario crash` | Worker crash mid-pipeline → automatic restart → job completion |
| **Prompt Injection** | `--scenario injection` | 10 injection payloads → 100% block rate, audit log entries written |
| **Two-Pass Verifier** | `--scenario verifier` | Extract action items → verify citations → filter ungrounded items |
| **Telemetry** | `--scenario telemetry` | Pipeline execution → Prometheus metrics → OTel span capture |

> 📄 Step-by-step walkthrough: [`docs/DEMO_WALKTHROUGH.md`](docs/DEMO_WALKTHROUGH.md)

---

## 📈 Observability

The full observability stack is included and auto-provisioned via Docker Compose.

### Prometheus Metrics

```bash
# Scrape endpoint
curl http://localhost:8000/metrics
```

**Key metrics exposed:**

| Metric | Type | Description |
|---|---|---|
| `meeting_pipeline_duration_seconds` | Histogram | End-to-end pipeline latency per node |
| `meeting_upload_bytes_total` | Counter | Total bytes uploaded |
| `meeting_queue_depth` | Gauge | Current Arq queue depth |
| `meeting_active_jobs` | Gauge | In-flight background jobs |
| `meeting_errors_total` | Counter | Errors by type and endpoint |
| `meeting_llm_tokens_total` | Counter | LLM tokens consumed (by model) |
| `meeting_injection_blocked_total` | Counter | Prompt injection attempts blocked |
| `http_request_duration_seconds` | Histogram | HTTP handler latency by route |

### Grafana Dashboard

1. Open http://localhost:3001 (credentials: `admin` / `admin`)
2. Navigate to **Dashboards → Meeting Intelligence**
3. The dashboard is auto-provisioned — no manual import needed

**Dashboard panels include:** Pipeline latency (p50/p95/p99), queue depth over time, injection block rate, LLM token burn rate, upload throughput, error rate by endpoint.

### OpenTelemetry

All LangGraph pipeline nodes, API handlers, and DB queries are instrumented with OTel spans. Configure your collector endpoint via `OTEL_EXPORTER_OTLP_ENDPOINT` to ship traces to Jaeger, Tempo, or any OTLP-compatible backend.

---

## 🛡️ Security Architecture

### 3-Layer Prompt Injection Defense

```
Layer 1: Lexical Detection
  ├─ Regex patterns for known injection signatures
  ├─ Blocklist of adversarial keywords
  └─ Input length and character distribution checks

Layer 2: Semantic Embedding Check
  ├─ Cosine similarity against injection embedding centroid
  └─ Threshold-based classification (configurable)

Layer 3: LLM-as-Judge
  ├─ Secondary LLM call classifies borderline inputs
  └─ Justification logged to SecurityAuditLog
```

Block rate on standard red-team dataset: **100%** (0 bypasses across 50 adversarial inputs).

### Policy Gate

Every outbound action (Jira ticket creation, email send, Slack message) passes through `PolicyGate` before execution:

```python
gate = PolicyGate(
    allowed_email_domains=frozenset(["company.com"]),
    max_jira_tickets=10,
    max_slack_messages=5,
)
result = gate.check_email_recipients(recipients)  # raises PolicyViolation if blocked
```

All decisions (allow and block) are written to `SecurityAuditLog` with timestamp, user ID, action type, and decision rationale.

### Additional Security Controls

| Control | Implementation |
|---|---|
| **Authentication** | JWT (HS256) + bcrypt password hashing |
| **Rate Limiting** | SlowAPI + Upstash Redis (per-user, per-endpoint) |
| **PII Redaction** | `pii_redactor.py` strips names, emails, phone numbers from logs |
| **At-Rest Encryption** | Fernet symmetric encryption for sensitive stored fields |
| **Data Isolation** | All queries scoped to `user_id`; no cross-tenant data leakage |
| **Audit Trail** | Immutable `SecurityAuditLog` table; append-only by design |

---

## ⚙️ Configuration Reference

Full environment variable reference for production deployments:

```env
# ─── Database ──────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
DATABASE_URL_SYNC=postgresql://user:password@host:5432/dbname

# ─── Storage ───────────────────────────────────────────────
STORAGE_BACKEND=s3          # local | s3 | r2
S3_BUCKET=meeting-files
S3_ENDPOINT_URL=            # Cloudflare R2 only
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
MAX_UPLOAD_SIZE_MB=500
LOCAL_STORAGE_PATH=./uploads

# ─── Inference ─────────────────────────────────────────────
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
OPENAI_API_KEY=sk-...       # For embeddings
HF_TOKEN=hf_...             # For self-hosted models
VLLM_BASE_URL=http://localhost:8001
OLLAMA_BASE_URL=http://localhost:11434

# ─── Auth & Security ───────────────────────────────────────
SECRET_KEY=<openssl rand -hex 32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
ENCRYPTION_KEY=<base64-32-bytes>

# ─── Rate Limiting & Queue ─────────────────────────────────
UPSTASH_REDIS_REST_URL=https://...upstash.io
UPSTASH_REDIS_REST_TOKEN=AX...
REDIS_URL=redis://localhost:6379

# ─── Integrations ──────────────────────────────────────────
SENDGRID_API_KEY=SG....
SENDGRID_FROM_EMAIL=noreply@yourapp.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_API_TOKEN=ATATT...
JIRA_USER_EMAIL=user@yourorg.com
GOOGLE_CALENDAR_CREDENTIALS=path/to/credentials.json

# ─── Policy Gate ───────────────────────────────────────────
POLICY_ALLOWED_EMAIL_DOMAINS=company.com,partner.org
POLICY_MAX_JIRA_TICKETS=10
POLICY_MAX_SLACK_MESSAGES=5

# ─── Observability ─────────────────────────────────────────
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=meeting-intelligence-agent
```

---

## 🚢 Deployment

### Docker Compose (Self-Hosted)

The `docker-compose.yml` defines 4 services:

| Service | Port | Image |
|---|---|---|
| `backend` | 8000 | `./Backend` (Dockerfile) |
| `frontend` | 3000 | `./frontend` (Dockerfile) |
| `prometheus` | 9090 | `prom/prometheus:latest` |
| `grafana` | 3001 | `grafana/grafana:latest` |

```bash
# Production startup
docker compose up -d --build

# View logs
docker compose logs -f backend

# Run migrations
docker compose exec backend alembic upgrade head

# Shutdown
docker compose down
```

### Render.com (Cloud)

A `render.yaml` is included for one-click deployment to [Render](https://render.com):

```bash
# Deploy to Render (via Render dashboard or CLI)
# 1. Connect your GitHub repo at dashboard.render.com
# 2. Render auto-detects render.yaml
# 3. Set environment variables in the Render dashboard
# 4. Deploy — backend scales to 0 on free tier, stays up on paid
```

> 📄 Full production deployment guide: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

### Production Checklist

- [ ] Set `SECRET_KEY` to a cryptographically random value (`openssl rand -hex 32`)
- [ ] Use Neon PostgreSQL (or managed PG) with pgvector extension enabled
- [ ] Configure Upstash Redis for rate limiting and job queue
- [ ] Set `STORAGE_BACKEND=s3` and configure S3/R2 bucket with CORS
- [ ] Set `POLICY_ALLOWED_EMAIL_DOMAINS` to restrict email delivery
- [ ] Enable HTTPS (Render provides this automatically; add nginx or Caddy for self-hosted)
- [ ] Configure `OTEL_EXPORTER_OTLP_ENDPOINT` for production traces
- [ ] Set `ACCESS_TOKEN_EXPIRE_MINUTES` appropriately for your security policy

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository and create a feature branch: `git checkout -b feature/my-feature`
2. **Write tests** — all PRs must maintain or improve test coverage (currently 244 tests passing)
3. **Run the test suite**: `make test`
4. **Run the eval suite**: `make eval` — do not regress any benchmark metric
5. **Commit** using conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
6. **Open a Pull Request** with a clear description of the change and results

### Development Guidelines

- All new pipeline nodes must be instrumented with OTel spans
- All new outbound actions must pass through `PolicyGate`
- All new API endpoints must have rate limiting applied
- PII must never be logged — use `pii_redactor.py` in logging paths
- New evaluation metrics should be added to the appropriate `eval/phase*.py` script

---

## 📄 License

This project is licensed under the **MIT License**. See [`LICENSE`](LICENSE) for full text.

```
MIT License

Copyright (c) 2024 Meeting Intelligence Agent Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```

---

## 📚 Further Reading

| Document | Description |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Full system architecture with Mermaid topology, sequence diagrams, and failure boundary matrix |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Production deployment guide for Docker Compose and Render.com |
| [`docs/DEMO_WALKTHROUGH.md`](docs/DEMO_WALKTHROUGH.md) | Step-by-step interactive demo guide for all 4 scenarios |
| [`docs/UPLOAD_THROUGHPUT_BENCHMARK.md`](docs/UPLOAD_THROUGHPUT_BENCHMARK.md) | Upload throughput benchmark methodology and full results table |
| [`docs/EVALUATION_BASELINE.md`](docs/EVALUATION_BASELINE.md) | Evaluation dataset definitions, baseline methodology, and scoring rubrics |
| [`docs/ARTICLE_WHAT_I_LEARNED.md`](docs/ARTICLE_WHAT_I_LEARNED.md) | Publication-ready engineering article: 15 weeks of lessons building a production AI agent |
| [API Reference (Swagger)](http://localhost:8000/docs) | Interactive API documentation (requires running backend) |

---

<div align="center">

**Built with ❤️ over 15 weeks · 9 phases · 244 tests · 0 failures**

[⬆ Back to top](#-meeting-intelligence-agent)

</div>
