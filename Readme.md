# Meeting Intelligence Agent 🎙️🤖

> **Version 2.0.0** · Full-Stack AI Meeting Platform · JWT User Authentication · LangGraph Multi-Agent Pipeline · Neon Postgres + `pgvector` RAG · Dynamic Multi-LLM Routing · Groq Whisper + Llama 3.3/3.1 · Server-Sent Events (SSE) Streaming Q&A · Next.js 16 Frontend

**Meeting Intelligence Agent** is a production-grade full-stack AI platform designed to ingest meeting audio recordings of any length, run them through an agentic multi-stage processing pipeline to transcribe and extract structured intelligence, index records into a cross-meeting vector memory layer, and automatically synchronize tasks and schedules across Jira Cloud, Google Calendar, Slack, and email.

---

## 🌟 Key Features

* 🔐 **Full JWT Authentication & Security**: End-to-end user authentication powered by `PyJWT` and `passlib[bcrypt]`. Features user registration (`/auth/register`), login (`/auth/login`), profile retrieval (`/auth/me`), meeting data isolation per user, and `slowapi` rate limiting (120 req/min/IP).
* 🤖 **Multi-Agent Coordination (LangGraph)**: A 7-node directed state machine manages audio validation, PyAnnote speaker diarization, Groq Whisper transcription, structured extraction, summarization, vector indexing, database serialization, and multi-channel integration dispatch.
* ⚡ **Dynamic Multi-LLM Routing (`core/llm_router.py`)**: Intelligently routes tasks between Groq LLM models to optimize throughput, latency, and token cost:
  * **`llama-3.1-8b-instant`**: Fast model used for compact transcripts (<3,000 words), pre-extracted summary formatting, and simple Q&A keyword queries.
  * **`llama-3.3-70b-versatile`**: Powerful model deployed for long/complex transcripts and deep analytical multi-turn Q&A reasoning.
* 🧠 **Cross-Meeting Vector Memory RAG (`core/memory_service.py`)**: Computes 768-dimensional normalized dense feature embeddings for each meeting and persists them in Neon Postgres (`pgvector`). Enables cross-meeting context retrieval via `/memory/search` and multi-meeting synthesized answers.
* 💬 **Real-Time Streaming Q&A SSE (`/query/stream`)**: Interactive chat interface powered by Server-Sent Events (SSE) streaming tokens in real time with a dynamic cursor (`▍`), supported by a rule-based fallback matcher.
* 🎧 **Automatic Audio Chunking (FFmpeg)**: Seamlessly handles audio files of any size. Recordings exceeding Groq's 25MB Whisper limit are automatically segmented into 10-minute lossless chunks using FFmpeg's stream-copy muxer before parallel transcription.
* 👥 **Speaker Diarization (PyAnnote 3.1)**: Identifies and labels speaker turns (`SPEAKER_00`, `SPEAKER_01`) with timestamp alignment for clear action item and decision attribution.
* 🎵 **Interactive Audio Player & Transcript Sync**: Stream meeting audio directly from the backend with scrubbing, variable speed controls (`0.75x`–`2.0x`), and synchronized transcript line highlighting. Clicking any transcript line seeks audio directly to that exact timestamp.
* 📊 **Persistent Background Job Tracking**: Job progress, node completion timestamps, error traces, and execution metrics are persisted in a PostgreSQL `processing_jobs` table, surviving server restarts and multi-worker deployment environments.
* 📝 **Structured Information Extraction**: Extracts action items (with owner, priority, and due date), key decisions, participants, and topics with speaker context.
* 🔗 **Automatic & Manual Integrations**:
  * **Jira Cloud**: Creates formatted Jira tickets in Atlassian Document Format (ADF) for identified action items.
  * **Google Calendar**: Books follow-up meetings via Google Cloud Service Accounts.
  * **Slack**: Posts summary cards formatted with Slack Block Kit UI components.
  * **SendGrid**: Sends personalized transactional emails ensuring recipients only receive tasks assigned to them.
* 🎨 **Modern Next.js 16 Frontend**: Modern workspace UI built with Next.js App Router, React 19, Tailwind CSS, TanStack React Query v5, Zod schemas, and dark glassmorphic UI design.

---

## 🏛️ Architecture & Pipeline Overview

### LangGraph State Machine

```mermaid
graph TD
    A[Node 1: transcribe_audio] -->|Has Transcript| B[Node 2: extract_information]
    A -->|Empty Transcript| End1[END]
    B -->|Has Extraction| C[Node 3: generate_summary]
    B -->|Extraction Failed| End2[END]
    C -->|Has Summary| D[Node 4: save_to_database & index_memory]
    C -->|Summary Failed| End3[END]
    D -->|Has meeting_id| E[Node 5: create_jira_tickets]
    D -->|DB Fail| End4[END]
    E --> F[Node 6: book_calendar]
    F --> G[Node 7: send_notifications]
    G --> H[END]
    
    style A fill:#4b6cb7,stroke:#fff,stroke-width:2px,color:#fff
    style D fill:#198754,stroke:#fff,stroke-width:2px,color:#fff
    style G fill:#fd7e14,stroke:#fff,stroke-width:2px,color:#fff
```

### Database Schema (Neon Postgres + pgvector)

```
  ┌─────────────────────────────────────────────────────────────┐
  │                            users                            │
  ├─────────────────────────────────────────────────────────────┤
  │ id (PK) | email (Unique) | hashed_password | full_name       │
  │ created_at                                                  │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ 1:N
          ┌──────────────────────┴──────────────────────┐
          ▼                                             ▼
  ┌──────────────────────────────┐              ┌──────────────────────────────┐
  │           meetings           │              │       processing_jobs        │
  ├──────────────────────────────┤              ├──────────────────────────────┤
  │ id (PK)                      │              │ id (PK)                      │
  │ user_id (FK -> users.id)     │              │ user_id (FK -> users.id)     │
  │ title                        │              │ meeting_id (FK)              │
  │ audio_filename               │              │ status                       │
  │ duration_minutes             │              │ completed_nodes              │
  │ short_summary                │              │ node_timings                 │
  │ detailed_summary             │              │ started_at | completed_at    │
  │ transcript                   │              └──────────────────────────────┘
  │ diarized_transcript          │
  │ transcript_embedding (768)  │
  │ embedding_status             │
  │ created_at                   │
  └──────────────┬───────────────┘
                 │ 1:N
         ┌───────┼───────────────────────┐
         ▼       ▼                       ▼
  ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
  │ action_items │        │  decisions   │        │ participants │
  ├──────────────┤        ├──────────────┤        ├──────────────┤
  │ id (PK)      │        │ id (PK)      │        │ id (PK)      │
  │ meeting_id   │        │ meeting_id   │        │ meeting_id   │
  │ description  │        │ description  │        │ name         │
  │ owner        │        │ context      │        │ email (Opt)  │
  │ due_date     │        │ created_at   │        │ created_at   │
  │ priority     │        └──────────────┘        └──────────────┘
  │ jira_ticket  │
  │ status       │
  └──────────────┘
```

---

## 🛠️ Technology Stack

### Backend
* **Framework**: FastAPI (Python 3.12+)
* **Security & Auth**: PyJWT, Passlib (bcrypt), SlowAPI rate limiting
* **Agent Pipeline**: LangGraph 0.2.55, LangChain Core
* **LLM & Transcription**: Groq (`whisper-large-v3`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`)
* **LLM Router**: Custom `LLMRouter` (`core/llm_router.py`)
* **Vector Memory (RAG)**: `MemoryService` (`core/memory_service.py`), Neon Postgres `pgvector`
* **Speaker Diarization**: PyAnnote.audio 3.1, FFmpeg
* **Database & ORM**: Neon Serverless Postgres with `pgvector`, SQLAlchemy v2 (Asyncpg driver)
* **Integrations**: Atlassian Python API, SendGrid SDK, Slack SDK, Google API Python Client
* **Test Suite**: Pytest + pytest-asyncio (29 passing unit & integration tests)

### Frontend
* **Framework**: Next.js 16 (React 19, TypeScript)
* **Auth**: Context AuthProvider (`lib/api/auth.ts`) & protected page router
* **Styling**: Tailwind CSS v4, Lucide React icons, Glassmorphism design tokens
* **State & Data Fetching**: TanStack React Query v5
* **Form & Toast Validation**: Zod, Sonner toasts
* **Testing**: Vitest, React Testing Library

---

## 📂 Project Directory Structure

```
├── Backend/                 # FastAPI + LangGraph + SQLAlchemy service
│   ├── agents/              # LangGraph node agents (transcription, extraction, summary)
│   ├── api/                 # FastAPI routes, auth routes, SSE streaming & middleware
│   │   ├── auth_routes.py   # Auth endpoints (/auth/register, /auth/login, /auth/me)
│   │   ├── main.py          # CORS, SlowAPI Rate Limiter, GZip, Exception handlers
│   │   └── routes.py        # Protected meeting & intelligence API routes
│   ├── core/                # Core system modules
│   │   ├── auth.py          # JWT creation/verification & get_current_user dependency
│   │   ├── config.py        # Typed settings loader (Pydantic BaseSettings)
│   │   ├── llm_router.py    # Multi-LLM model routing engine (8B vs 70B)
│   │   ├── logging.py       # Structlog structured JSON logger
│   │   └── memory_service.py# Vector embedding generator & pgvector RAG memory search
│   ├── db/                  # SQLAlchemy ORM models (User, Meeting, ActionItem, etc.)
│   ├── graph/               # LangGraph state graph definition & node edge flow
│   ├── models/              # Pydantic validation schemas & API data contracts
│   ├── tools/               # External integration connectors (Jira, Slack, Calendar, SendGrid)
│   └── tests/               # Pytest automated test suite (test_auth, test_routes, test_memory, etc.)
│
├── frontend/                # Next.js 16 App Router UI
│   ├── app/                 # App Router pages
│   │   ├── (auth)/          # Authentication pages (/login, /register)
│   │   ├── (app)/           # Protected workspace (/dashboard, /meetings, /agent-chat, /analytics)
│   │   └── layout.tsx       # Root layout with AuthProvider & ToastProvider
│   ├── components/          # Sidebar, Navbar, AudioPlayer, ChatDrawer, PipelineTracker
│   ├── lib/                 # API Client, Auth helpers, custom React Query & SSE hooks
│   └── tests/               # Vitest client testing suite
│
├── README.md                # Unified Project Documentation
├── API_INTEGRATION_MAP.md   # Endpoint contracts mapping backend endpoints to frontend hooks
├── IMPLEMENTATION_NOTES.md  # Architectural decisions & design log
└── IMPROVEMENT_ROADMAP.md   # Project status snapshot & improvement phases
```

---

## 🌐 API Reference

### Authentication Endpoints
* `POST /auth/register` — Register a new account (`email`, `password`, `full_name`) -> returns JWT token & user object.
* `POST /auth/login` — Authenticate user (`email`, `password`) -> returns JWT token & user object.
* `POST /auth/token` — OAuth2 compatible form login endpoint.
* `GET /auth/me` — Retrieve current authenticated user profile.

### Meeting & Processing Endpoints (Protected)
* `POST /meeting/upload` — Upload meeting audio file (MP3, WAV, M4A, FLAC, OGG, WEBM, MP4).
* `POST /meetings/process` — Start asynchronous background processing pipeline job.
* `GET /meetings/status/{job_id}` — Get background job progress and node completion state.
* `GET /meetings` — List meetings belonging to the authenticated user.
* `GET /meetings/{meeting_id}` — Get complete meeting details (action items, decisions, participants).
* `GET /meetings/{meeting_id}/audio` — Stream audio with `Accept-Ranges` byte-seeking support.
* `PATCH /meetings/{meeting_id}/action-items/{item_id}` — Update action item status (`open`, `in_progress`, `done`).
* `PATCH /meetings/{meeting_id}/participants/{participant_id}` — Save participant email.
* `DELETE /meetings/{meeting_id}` — Delete meeting record.

### Conversational & Memory Endpoints (Protected)
* `POST /query` — Non-streaming LLM Q&A with multi-LLM router & cross-meeting RAG context.
* `POST /query/stream` — Real-time token streaming Q&A via Server-Sent Events (SSE).
* `POST /memory/search` — Search cross-meeting vector memory using semantic similarity.

### Integration Dispatch Endpoints (Protected)
* `POST /meetings/{meeting_id}/send/email` — Send SendGrid transactional emails.
* `POST /meetings/{meeting_id}/send/slack` — Post summary cards to Slack.
* `POST /meetings/{meeting_id}/send/jira` — Create Jira Cloud tickets.
* `POST /meetings/{meeting_id}/send/calendar` — Book follow-up meeting on Google Calendar.

---

## 🚀 Quick Start Guide

### 1. System Requirements
* **Python**: 3.10+
* **Node.js**: 18+
* **FFmpeg**: Required for audio chunking of files >25MB.
  * Windows: `winget install ffmpeg`
  * macOS: `brew install ffmpeg`
  * Linux: `sudo apt install ffmpeg`

### 2. Backend Setup

1. Navigate to `Backend`, create a virtual environment, and install dependencies:
   ```bash
   cd Backend
   python -m venv venv

   # Windows (PowerShell)
   .\venv\Scripts\Activate.ps1
   # macOS/Linux
   source venv/bin/activate

   pip install -r requirements.txt
   ```

2. Create `Backend/.env`:
   ```env
   APP_ENV=development
   SECRET_KEY=your-secure-jwt-secret-key
   GROQ_API_KEY=gsk_your_groq_api_key

   # Multi-LLM Model Routing Defaults
   LLM_FAST_MODEL=llama-3.1-8b-instant
   LLM_POWERFUL_MODEL=llama-3.3-70b-versatile
   LLM_ROUTING_WORD_THRESHOLD=3000

   # Postgres Database URLs (Neon Postgres)
   DATABASE_URL=postgresql+asyncpg://user:pass@host/db?sslmode=require
   DATABASE_URL_SYNC=postgresql+psycopg2://user:pass@host/db?sslmode=require

   # Speaker Diarization (Optional)
   HF_TOKEN=your_huggingface_access_token
   DIARIZATION_ENABLED=true

   # Integration Credentials (Optional)
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
   SENDGRID_API_KEY=SG...
   JIRA_URL=https://yourcompany.atlassian.net
   JIRA_EMAIL=dev@yourcompany.com
   JIRA_API_TOKEN=your_jira_token
   GOOGLE_CALENDAR_CREDENTIALS_JSON='{"type": "service_account", ...}'
   ```

3. Start the FastAPI server:
   ```bash
   uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
   ```
   * Access interactive Swagger docs at `http://localhost:8000/docs`.

### 3. Frontend Setup

1. Navigate to `frontend` and install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Create `frontend/.env.local`:
   ```env
   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
   ```

3. Launch Next.js development server:
   ```bash
   npm run dev
   ```
   * Open `http://localhost:3000` in your web browser.

---

## 🧪 Testing

### Backend Test Suite (Pytest)
Runs full integration and unit tests using an in-memory SQLite database:
```bash
cd Backend
.\venv\Scripts\python.exe -m pytest
```
* Result: `29 passed in 4.98s`

### Frontend Testing & Production Build
```bash
cd frontend
npm test        # Vitest test suite
npm run build   # Production Next.js build verification
```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
