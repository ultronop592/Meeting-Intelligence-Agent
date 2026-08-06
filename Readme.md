# Meeting Intelligence Agent 🎙️🤖

> **Version 2.1.0** · Full-Stack AI Meeting Platform · JWT User Authentication · LangGraph Multi-Agent Pipeline · Neon Postgres + `pgvector` RAG · Dynamic Multi-LLM Routing · Cross-Meeting Analytics Dashboard · Groq Whisper + Llama 3.3/3.1 · Server-Sent Events (SSE) Streaming Q&A · Next.js 16 Frontend

**Meeting Intelligence Agent** is a production-grade full-stack AI platform designed to ingest meeting audio recordings of any length, run them through an agentic multi-stage processing pipeline to transcribe and extract structured intelligence, index records into a cross-meeting vector memory layer, generate cross-meeting analytical insights, and automatically synchronize tasks and schedules across Jira Cloud, Google Calendar, Slack, and email.

---

## 🌟 Key Features

* 🔐 **Full JWT Authentication & Isolation**: End-to-end user authentication powered by `PyJWT` and `passlib[bcrypt]`. Features account registration (`/auth/register`), login (`/auth/login`), profile management (`/auth/me`), meeting data isolation per user, and `slowapi` rate limiting (120 req/min/IP).
* 📊 **Cross-Meeting Analytics Dashboard**: Complete team intelligence hub with 5 aggregate endpoints and interactive Recharts visualizations:
  * **Header Metric Cards**: 7-day and 30-day totals, average duration, action item completion rate, active team load.
  * **Meeting & Action Trend Chart**: Weekly and monthly area chart tracking meeting volume vs. completed action items.
  * **Participant Leaderboard**: Bar chart ranking team members by meeting attendance and action item assignments.
  * **Action Item Distribution**: Multi-segment progress breakdown for Open, In Progress, Done, and Overdue tasks.
  * **Recurring Topic Analysis**: Keyword extraction analyzing key discussion topics across all user meetings.
  * **Owner Breakdown Table**: Detailed task distribution, completion rate, and overdue tracking per owner.
* 🤖 **Multi-Agent Pipeline (LangGraph)**: A directed state machine manages audio validation, PyAnnote speaker diarization, Groq Whisper transcription, structured extraction, summarization, vector indexing, database serialization, and multi-channel integration dispatch.
* ⚡ **Dynamic Multi-LLM Routing (`core/llm_router.py`)**: Intelligently routes tasks between Groq LLM models to optimize throughput, latency, and token cost:
  * **`llama-3.1-8b-instant`**: Fast model used for compact transcripts (<3,000 words), pre-extracted summary formatting, and simple Q&A keyword queries.
  * **`llama-3.3-70b-versatile`**: Powerful model deployed for long/complex transcripts and deep analytical multi-turn Q&A reasoning.
* 🧠 **Cross-Meeting Vector Memory RAG (`core/memory_service.py`)**: Computes 768-dimensional normalized dense feature embeddings for each meeting and persists them in Neon Postgres (`pgvector`). Enables cross-meeting context retrieval via `/memory/search` and multi-meeting synthesized answers.
* 💬 **Real-Time Streaming Q&A SSE (`/query/stream`)**: Interactive chat interface powered by Server-Sent Events (SSE) streaming tokens in real time with a dynamic cursor (`▍`), supported by a rule-based fallback matcher.
* 🎧 **Automatic Audio Chunking (FFmpeg)**: Seamlessly handles audio files of any size. Recordings exceeding Groq's 25MB Whisper limit are automatically segmented into 10-minute lossless chunks using FFmpeg's stream-copy muxer before parallel transcription.
* 👥 **Speaker Diarization (PyAnnote 3.1)**: Identifies and labels speaker turns (`SPEAKER_00`, `SPEAKER_01`) with timestamp alignment for clear action item and decision attribution.
* 🎵 **Interactive Audio Player & Transcript Sync**: Stream meeting audio directly from the backend with scrubbing, variable speed controls (`0.75x`–`2.0x`), and synchronized transcript line highlighting.
* 🔗 **Automatic & Manual Integrations**:
  * **Jira Cloud**: Creates formatted Jira tickets in Atlassian Document Format (ADF) for identified action items.
  * **Google Calendar**: Books follow-up meetings via Google Cloud Service Accounts.
  * **Slack**: Posts summary cards formatted with Slack Block Kit UI components.
  * **SendGrid**: Sends personalized transactional emails ensuring recipients only receive tasks assigned to them.
* 🎨 **Modern Next.js 16 Frontend**: Modern workspace UI built with Next.js App Router, React 19, Tailwind CSS v4, TanStack React Query v5, Zod schemas, Recharts, and dark glassmorphic UI design.

---

## 🏛️ System Architecture & Diagram Maps

### 1. High-Level System Architecture

```mermaid
graph TB
    subgraph "Client Layer (Frontend)"
        UI["Next.js 16 App Router UI"]
        AQ["TanStack React Query v5"]
        SSE_Client["EventSource / Fetch SSE Client"]
    end

    subgraph "API & Security Layer (FastAPI Backend)"
        GW["FastAPI Gateway (main.py / routes.py)"]
        AUTH["JWT Auth Guard (core/auth.py)"]
        RL["SlowAPI Rate Limiter (120 req/min)"]
        ROUTER["Multi-LLM Router (core/llm_router.py)"]
    end

    subgraph "Agentic Pipeline (LangGraph)"
        LG["LangGraph State Engine"]
        N1["Node 1: Transcribe & Diarize"]
        N2["Node 2: Extract Info"]
        N3["Node 3: Generate Summary"]
        N4["Node 4: DB Save & RAG Vector Index"]
        N5["Node 5-7: Integrations (Jira/Calendar/Slack/Email)"]
    end

    subgraph "Persistence & Memory Layer"
        PG[("Neon Postgres DB")]
        VEC[("pgvector (768-dim Memory RAG)")]
    end

    subgraph "External Cloud Services"
        GROQ["Groq AI API (Whisper + Llama)"]
        JIRA["Jira Cloud API"]
        GCAL["Google Calendar API"]
        SLACK["Slack Webhooks"]
        SG["SendGrid Email API"]
    end

    UI <--> AQ
    UI <--> SSE_Client
    AQ <--> GW
    SSE_Client <--> GW
    GW --> AUTH
    GW --> RL
    GW --> ROUTER
    GW --> LG

    LG --> N1 --> N2 --> N3 --> N4 --> N5
    N1 <--> GROQ
    N2 <--> ROUTER
    N3 <--> ROUTER
    ROUTER <--> GROQ

    N4 --> PG
    N4 --> VEC
    N5 --> JIRA
    N5 --> GCAL
    N5 --> SLACK
    N5 --> SG
```

---

### 2. LangGraph Multi-Agent Pipeline Map

```mermaid
graph TD
    Start([Audio File Upload]) --> Node1["Node 1: transcribe_audio<br/>(Groq Whisper + PyAnnote Diarization)"]
    
    Node1 -->|Transcript Produced| Node2["Node 2: extract_information<br/>(Action Items, Decisions, Participants)"]
    Node1 -->|Audio Invalid/Empty| EndFailed([Terminated: Audio Error])
    
    Node2 -->|Extraction Valid| Node3["Node 3: generate_summary<br/>(Short & Detailed Executive Summary)"]
    Node2 -->|Extraction Failed| EndFailed
    
    Node3 -->|Summary Complete| Node4["Node 4: save_to_database & index_memory<br/>(Postgres Insert + pgvector Embedding RAG)"]
    Node3 -->|Summary Failed| EndFailed
    
    Node4 -->|Meeting ID Generated| Node5["Node 5: create_jira_tickets<br/>(Atlassian ADF Tickets)"]
    Node4 -->|DB Commit Failed| EndFailed
    
    Node5 --> Node6["Node 6: book_calendar<br/>(Google Calendar Sync)"]
    Node6 --> Node7["Node 7: send_notifications<br/>(Slack Block Kit + SendGrid Emails)"]
    Node7 --> EndSuccess([Pipeline Completed Successfully])

    style Start fill:#4B6CB7,stroke:#FFF,stroke-width:2px,color:#FFF
    style Node4 fill:#198754,stroke:#FFF,stroke-width:2px,color:#FFF
    style EndSuccess fill:#28A745,stroke:#FFF,stroke-width:2px,color:#FFF
    style EndFailed fill:#DC3545,stroke:#FFF,stroke-width:2px,color:#FFF
```

---

### 3. Cross-Meeting RAG & Analytics Flow Map

```mermaid
graph LR
    subgraph "Query / Analytics Inputs"
        Q_User["User Query / Q&A"]
        Q_Dash["Analytics Page"]
    end

    subgraph "Service Engine"
        Router["LLM Router Engine"]
        MemService["MemoryService RAG Engine"]
        AnalyticsAgg["Analytics Aggregator"]
    end

    subgraph "Vector & Data Storage"
        V_Memory[("pgvector Embeddings<br/>(Cosine Distance)")]
        DB_Tables[("Postgres Tables<br/>(meetings, action_items, participants)")]
    end

    subgraph "Output Generation"
        SSE["SSE Token Stream (/query/stream)"]
        SummaryCard["Summary & Leaderboards"]
        Recharts["Recharts Visualizations"]
    end

    Q_User --> Router
    Router --> MemService
    MemService <--> V_Memory
    MemService --> SSE

    Q_Dash --> AnalyticsAgg
    AnalyticsAgg <--> DB_Tables
    AnalyticsAgg --> SummaryCard
    AnalyticsAgg --> Recharts
```

---

### 4. Database Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    users ||--o{ meetings : "owns"
    users ||--o{ processing_jobs : "launches"
    meetings ||--o{ action_items : "contains"
    meetings ||--o{ decisions : "contains"
    meetings ||--o{ participants : "includes"
    meetings ||--o{ notifications_log : "records"

    users {
        string id PK
        string email UK
        string hashed_password
        string full_name
        datetime created_at
    }

    meetings {
        string id PK
        string user_id FK
        string title
        string audio_filename
        int duration_minutes
        text short_summary
        text detailed_summary
        text transcript
        text diarized_transcript
        vector transcript_embedding
        string embedding_status
        datetime created_at
    }

    action_items {
        string id PK
        string meeting_id FK
        text description
        string owner
        string due_date
        string priority
        string jira_ticket_id
        string status
        datetime created_at
    }

    decisions {
        string id PK
        string meeting_id FK
        text description
        text context
        datetime created_at
    }

    participants {
        string id PK
        string meeting_id FK
        string name
        string email
        datetime created_at
    }

    notifications_log {
        string id PK
        string meeting_id FK
        string type
        string status
        text detail
        datetime created_at
    }

    processing_jobs {
        string id PK
        string user_id FK
        string meeting_id FK
        string status
        json completed_nodes
        json node_timings
        datetime started_at
        datetime completed_at
    }
```

---

## 🗺️ Future Roadmap & Architectural Evolution

Based on [IMPROVEMENT_ROADMAP.md](file:///c:/Agentic%20AI%20Project/IMPROVEMENT_ROADMAP.md), the system is evolving through planned phases to add real-time streaming, multi-turn chat memory, global search, and production infrastructure:

```mermaid
graph TD
    P1["Phase 1: JWT Auth & Security<br/>(COMPLETED v2.0.0)"] --> P4["Phase 4: Analytics Dashboard<br/>(COMPLETED v2.1.0)"]
    P4 --> P2["Phase 2: WebSocket Live Stepper<br/>(PLANNED)"]
    P2 --> P3["Phase 3: Multi-Turn Agent Memory<br/>(PLANNED)"]
    P3 --> P5["Phase 5: Global Search & Speaker ID<br/>(PLANNED)"]
    P5 --> P6["Phase 6: Docker & CI/CD Hardening<br/>(PLANNED)"]
    P6 --> P7["Phase 7: Advanced Voice & PDF Export<br/>(STRETCH)"]

    style P1 fill:#28A745,stroke:#FFF,color:#FFF
    style P4 fill:#28A745,stroke:#FFF,color:#FFF
    style P2 fill:#FF9F43,stroke:#FFF,color:#FFF
    style P3 fill:#FF9F43,stroke:#FFF,color:#FFF
    style P5 fill:#17A2B8,stroke:#FFF,color:#FFF
    style P6 fill:#17A2B8,stroke:#FFF,color:#FFF
    style P7 fill:#6C757D,stroke:#FFF,color:#FFF
```

### Planned Phase Overview

| Phase | Target Area | Key Enhancements | Files / Components Affected |
|-------|-------------|------------------|-----------------------------|
| **Phase 2** | Real-Time Pipeline Progress | WebSocket connection manager (`ws_manager.py`) pushing live node completion step events directly to an animated frontend step tracker component. | `core/ws_manager.py`, `api/routes.py`, `components/processing/pipeline-tracker.tsx` |
| **Phase 3** | Multi-Turn Conversational Memory | Database-backed rolling chat session history (`ChatSession` table) allowing follow-up context queries (e.g. *"who owns the second item?"*). | `db/models.py`, `api/routes.py`, `components/chat/chat-suggestions.tsx` |
| **Phase 5A** | Global Search | Postgres `tsvector` full-text search combined with `/memory/search` semantic similarity toggle across meetings, decisions, and action items. | `api/routes.py`, `app/(app)/search/` |
| **Phase 5B** | Speaker Identity Resolution | Mapping speaker labels (`SPEAKER_00` → "Alice Chen") with retroactive transcript rewriting on save. | `db/models.py`, `app/(app)/meetings/[id]/` |
| **Phase 5C** | Observability & Error Tracking | Sentry exception capture integration (`sentry-sdk`) and LangSmith node latency tracking. | `api/main.py`, `graph/agent_graph.py` |
| **Phase 6** | Production Hardening | Docker & Docker Compose configuration, Alembic database migrations, and GitHub Actions CI/CD pipeline. | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` |
| **Phase 7** | Voice & Advanced Workflow | In-browser live audio recording (`MediaRecorder`), PDF summary export, and cron deadline email reminders. | `components/audio/`, export utilities |

---

## 🌐 API Reference Map

### Authentication Endpoints (Public)
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

### Analytics Endpoints (Protected)
* `GET /analytics/summary` — Returns meeting totals, average duration, action completion rates, and 7d/30d comparison stats.
* `GET /analytics/participants` — Returns participant leaderboard with attendance count and action items load.
* `GET /analytics/timeline?period=weekly|monthly` — Returns meeting frequency and completion data points over time.
* `GET /analytics/action-items` — Returns status breakdown (`open`, `in_progress`, `done`, `overdue`) overall and per owner.
* `GET /analytics/topics` — Returns top recurring keywords and topic frequency extracted from all meetings.

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
* **Test Suite**: Pytest + pytest-asyncio (Passing unit & integration tests)

### Frontend
* **Framework**: Next.js 16 (React 19, TypeScript)
* **Auth**: Context AuthProvider (`lib/api/auth.ts`) & protected page router
* **Styling**: Tailwind CSS v4, Lucide React icons, Glassmorphism design tokens
* **Data Fetching & State**: TanStack React Query v5
* **Charts & Visualizations**: Recharts (`^2.12.7`)
* **Form & Toast Validation**: Zod, Sonner toasts
* **Testing & Verification**: Vitest, Next.js production build compiler

---

## 📂 Repository Directory Structure Map

```
├── Backend/                 # FastAPI + LangGraph + SQLAlchemy service
│   ├── agents/              # LangGraph node agents (transcription, extraction, summary)
│   ├── api/                 # FastAPI routes, auth routes, analytics routes, SSE streaming & middleware
│   │   ├── auth_routes.py   # Auth endpoints (/auth/register, /auth/login, /auth/me)
│   │   ├── main.py          # CORS, SlowAPI Rate Limiter, GZip, Exception handlers
│   │   └── routes.py        # Protected meeting, analytics & intelligence API routes
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
│   └── tests/               # Pytest automated test suite (test_auth, test_routes, test_analytics, test_memory)
│
├── frontend/                # Next.js 16 App Router UI
│   ├── app/                 # App Router pages
│   │   ├── (auth)/          # Authentication pages (/login, /register)
│   │   ├── (app)/           # Protected workspace (/dashboard, /meetings, /agent-chat, /analytics)
│   │   └── layout.tsx       # Root layout with AuthProvider & ToastProvider
│   ├── components/          # Analytics charts, Sidebar, Navbar, AudioPlayer, ChatDrawer
│   │   └── analytics/       # Analytics Dashboard chart and table components
│   ├── lib/                 # API Client, Auth helpers, Analytics API, custom React Query & SSE hooks
│   └── tests/               # Vitest client testing suite
│
├── README.md                # Unified Project Documentation
├── API_INTEGRATION_MAP.md   # Endpoint contracts mapping backend endpoints to frontend hooks
├── IMPLEMENTATION_NOTES.md  # Architectural decisions & design log
└── IMPROVEMENT_ROADMAP.md   # Project status snapshot & improvement phases
```

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
.\venv\Scripts\pytest.exe
```

### Frontend Testing & Production Build
```bash
cd frontend
npm test        # Vitest test suite
npm run build   # Production Next.js build verification
```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
