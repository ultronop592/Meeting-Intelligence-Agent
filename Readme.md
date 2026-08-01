# Meeting Intelligence Agent 🎙️🤖

> **Version 2.0.0** · LangGraph Multi-Agent Pipeline · Neon Postgres + pgvector RAG · Dynamic Multi-LLM Routing · Groq Whisper + Llama 3.3/3.1 · SSE Streaming Q&A · Next.js 15 Frontend

**Meeting Intelligence Agent** is a production-grade full-stack application designed to ingest meeting audio recordings of any size, run them through an agentic multi-stage pipeline to transcribe and extract structured intelligence, index records into a cross-meeting vector memory layer, and automatically synchronize tasks and schedules across Jira, Google Calendar, Slack, and email.

---

## 🌟 Key Features

*   **Multi-Agent Coordination (LangGraph)**: A 7-node directed graph manages audio validation, PyAnnote speaker diarization, Groq Whisper transcription, structured extraction, summarization, vector indexing, database serialization, and multi-channel integration dispatch.
*   **Dynamic Multi-LLM Routing (`core/llm_router.py`)**: Intelligently routes tasks between Groq models to optimize throughput, latency, and token cost:
    *   **`llama-3.1-8b-instant`**: Used for compact transcripts (<3,000 words), pre-extracted summary formatting, and simple Q&A keyword queries.
    *   **`llama-3.3-70b-versatile`**: Deployed for long/complex transcripts and deep analytical multi-turn Q&A reasoning.
*   **Cross-Meeting Vector Memory RAG (`core/memory_service.py`)**: Computes 768-dimensional normalized dense feature embeddings for each meeting and persists them in Neon Postgres (`pgvector`). Enables cross-meeting context retrieval via `/memory/search` and multi-meeting synthesized answers.
*   **Real-Time Streaming Q&A SSE (`/query/stream`)**: Interactive chat interface powered by Server-Sent Events (SSE) streaming tokens in real time with a dynamic cursor (`▍`), supported by a rule-based fallback matcher.
*   **Automatic Audio Chunking (FFmpeg)**: Seamlessly handles audio files of any length. Recordings exceeding Groq's 25MB Whisper limit are automatically segmented into 10-minute lossless chunks using FFmpeg's stream-copy muxer before parallel transcription.
*   **Speaker Diarization (PyAnnote 3.1)**: Identifies and labels speaker turns (`SPEAKER_00`, `SPEAKER_01`) with timestamp alignment for clear action item and decision attribution.
*   **Interactive Audio Player & Transcript Sync**: Stream meeting audio directly from the backend with scrubbing, variable speed controls (`0.75x`–`2.0x`), and synchronized transcript line highlighting. Clicking any line jumps audio directly to that exact timestamp.
*   **Persistent Background Job Tracking**: Job progress, node completion timestamps, error traces, and execution metrics are persisted in a PostgreSQL `processing_jobs` table, surviving server restarts and multi-worker deployment environments.
*   **Structured Information Extraction**: Extracts action items (with owner, priority, and due date), key decisions, participants, and topics with speaker context.
*   **Automatic & Manual Integrations**:
    *   **Jira Cloud**: Creates formatted Jira tickets in Atlassian Document Format (ADF) for identified action items.
    *   **Google Calendar**: Books follow-up meetings via Google Cloud Service Accounts.
    *   **Slack**: Posts summary cards formatted with Slack Block Kit UI components.
    *   **SendGrid**: Sends personalized transactional emails ensuring recipients only receive tasks assigned to them.
*   **Responsive Next.js 15 Frontend**: Modern workspace UI built with Next.js App Router, React 19, Tailwind CSS, TanStack React Query v5, and Zod schemas.

---

## 📂 Project Structure

```
├── Backend/                 # FastAPI + LangGraph + SQLAlchemy service
│   ├── README.md            # Detailed Backend Developer Guide & Architecture docs
│   ├── agents/              # LangGraph node agents (transcription, extraction, summary)
│   ├── api/                 # FastAPI routes, file streaming, SSE streaming & middleware
│   │   ├── main.py          # CORS, GZip, Exception handlers & app lifespan
│   │   └── routes.py        # API endpoints (/meeting/upload, /query/stream, /memory/search, etc.)
│   ├── core/                # Core system modules
│   │   ├── config.py        # Typed settings loader (Pydantic BaseSettings)
│   │   ├── llm_router.py    # Multi-LLM model routing engine (8B vs 70B)
│   │   ├── logging.py       # Structlog structured JSON logger
│   │   └── memory_service.py# Vector embedding generator & pgvector RAG memory search
│   ├── db/                  # SQLAlchemy ORM models & DB helper functions
│   ├── graph/               # LangGraph state graph definition & node edge flow
│   ├── models/              # Pydantic validation schemas & API data contracts
│   ├── tools/               # External integration connectors (Jira, Slack, Calendar, SendGrid, PyAnnote)
│   └── tests/               # Pytest automated test suite (71 passing unit & integration tests)
│
├── frontend/                # Next.js 15 App Router UI
│   ├── README.md            # Frontend configuration and component overview
│   ├── app/                 # App Router pages (meetings workspace, upload, details, chat)
│   ├── components/          # UI widgets, AudioPlayer, ChatDrawer, PipelineTracker
│   ├── lib/                 # API Client, custom React Query & SSE hooks
│   ├── types/               # TypeScript definitions matching Backend Pydantic schemas
│   └── tests/               # Vitest client testing setup
│
├── API_INTEGRATION_MAP.md   # Endpoint contracts mapping backend endpoints to frontend hooks
├── IMPLEMENTATION_NOTES.md  # Architectural decisions, layout specifications & design log
└── IMPROVEMENT_ROADMAP.md   # Project status snapshot & future phase roadmap (Phases 1–7)
```

*For in-depth backend architecture and node specifications, consult the [Backend Developer Guide](file:///c:/Agentic%20AI%20Project/Backend/README.md).*

---

## 🛠️ Technology Stack

### Backend
*   **Framework**: FastAPI (Python 3.10+)
*   **Agent Pipeline**: LangGraph, LangChain Core
*   **LLM & Speech Engines**: Groq (`whisper-large-v3`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`)
*   **LLM Routing**: Custom `LLMRouter` (`core/llm_router.py`)
*   **Vector Memory (RAG)**: `MemoryService` (`core/memory_service.py`), Neon Postgres `pgvector`
*   **Speaker Diarization**: PyAnnote.audio 3.1, FFmpeg
*   **Database**: Neon Serverless Postgres with `pgvector`
*   **ORM**: SQLAlchemy v2 (Asyncpg driver for production, SQLite in-memory for testing)
*   **Observability & Logs**: LangSmith, Structlog
*   **Integrations SDKs**: Atlassian Python API, SendGrid API, Slack SDK, Google API Python Client
*   **Test Suite**: Pytest + pytest-asyncio (71 passing unit & integration tests)

### Frontend
*   **Framework**: Next.js 15 (React 19, TypeScript)
*   **Styling**: Tailwind CSS
*   **State & Data Fetching**: TanStack React Query v5
*   **Form Validation**: Zod, React Hook Form
*   **Testing**: Vitest, React Testing Library

---

## 🚀 Quick Start

### 1. Prerequisites & System Dependencies
*   **Python**: 3.10+
*   **Node.js**: 18+
*   **FFmpeg**: Required for audio chunking of files >25MB.
    *   Windows: `winget install ffmpeg` or copy `ffmpeg.exe` to `Backend/venv/Scripts/`
    *   macOS: `brew install ffmpeg`
    *   Linux: `sudo apt install ffmpeg`

### 2. Backend Setup

1.  Navigate to `Backend`, create a virtual environment, and install dependencies:
    ```bash
    cd Backend
    python -m venv venv
    
    # Windows (PowerShell)
    .\venv\Scripts\Activate.ps1
    # macOS/Linux
    source venv/bin/activate

    pip install -r requirements.txt
    ```

2.  Create `Backend/.env` configuration:
    ```env
    APP_ENV=development
    SECRET_KEY=your-secure-secret-key
    GROQ_API_KEY=your-groq-api-key
    
    # Multi-LLM Model Routing Defaults
    LLM_FAST_MODEL=llama-3.1-8b-instant
    LLM_POWERFUL_MODEL=llama-3.3-70b-versatile
    LLM_ROUTING_WORD_THRESHOLD=3000
    
    # Postgres Database URLs
    DATABASE_URL=postgresql+asyncpg://user:pass@host/db?sslmode=require
    DATABASE_URL_SYNC=postgresql+psycopg2://user:pass@host/db?sslmode=require
    
    # Speaker Diarization (Optional)
    HF_TOKEN=your-huggingface-token
    DIARIZATION_ENABLED=true
    
    # Integrations (Optional)
    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
    SENDGRID_API_KEY=SG...
    JIRA_URL=https://yourcompany.atlassian.net
    JIRA_EMAIL=dev@yourcompany.com
    JIRA_API_TOKEN=your-jira-token
    GOOGLE_CALENDAR_CREDENTIALS_JSON='{"type": "service_account", ...}'
    ```

3.  Run the FastAPI backend server:
    ```bash
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    ```
    *   Interactive OpenAPI Swagger docs are available at `http://localhost:8000/docs`.

### 3. Frontend Setup

1.  Navigate to `frontend` and install dependencies:
    ```bash
    cd frontend
    npm install
    ```

2.  Create `frontend/.env.local`:
    ```env
    NEXT_PUBLIC_API_URL=http://localhost:8000
    ```

3.  Start the Next.js development server:
    ```bash
    npm run dev
    ```
    *   Open `http://localhost:3000` in your web browser.

---

## 🚦 End-to-End Processing Workflow

```
  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
  │ Audio Upload    │ ───► │ Background Job  │ ───► │ Node 1:         │
  │ (POST /upload)  │      │ Tracking (DB)   │      │ Transcribe      │
  └─────────────────┘      └─────────────────┘      └────────┬────────┘
                                                             │
  ┌─────────────────┐      ┌─────────────────┐               ▼
  │ Node 4: Save &  │ ◄─── │ Node 3:         │ ◄─── ┌─────────────────┐
  │ Vector Memory   │      │ Summarize       │      │ Node 2: Extract │
  └────────┬────────┘      └─────────────────┘      └─────────────────┘
           │
           ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │ Nodes 5–7: Integration Sync                                      │
  │ Jira Tickets ──► Google Calendar ──► Slack Cards ──► Email Alerts │
  └───────────────────────────────────────────────────────────────────┘
```

1.  **Ingestion**: User uploads a meeting recording (.mp3, .wav, .m4a, .mp4, etc.) via the workspace dashboard.
2.  **Streaming Upload**: `POST /meeting/upload` streams the file to disk in chunked buffers.
3.  **Job Enqueue**: `POST /meetings/process` initializes job tracking in `processing_jobs`.
4.  **Agentic Graph Execution**:
    *   **`transcribe_audio`**: Runs PyAnnote diarization and Groq Whisper. Files >25MB are chunked with FFmpeg.
    *   **`extract_information`**: Dynamic router assigns `llama-3.1-8b-instant` or `llama-3.3-70b-versatile` to extract structured JSON entities.
    *   **`generate_summary`**: Summarization agent produces title, short summary, and detailed summary.
    *   **`save_to_database`**: Persists meeting details, speaker segments, action items, decisions, and participants to Postgres in a single transaction. Also invokes `MemoryService.index_meeting()` to generate and store 768-dim `pgvector` embeddings.
5.  **Automated Integrations**:
    *   Creates Jira Cloud issues.
    *   Schedules Google Calendar follow-up meetings.
    *   Posts Slack Block Kit summary cards.
    *   Sends personalized SendGrid emails.
6.  **Interactive Workspace & Real-Time Q&A**: Users listen to synced audio, update action item statuses, and chat with the AI via `/query/stream` (SSE streaming) with cross-meeting vector memory context.

---

## 🧪 Quality and Verification Checks

### Backend Test Suite
Run the 71-test automated Pytest suite (covers routes, audio chunking, diarization, multi-LLM routing, vector memory, and streaming SSE):
```bash
cd Backend
.\venv\Scripts\python.exe -m pytest tests/ -v
```

### Frontend Validation
Run UI linting, type checks, and Vitest test suites:
```bash
cd frontend
npm run lint    # ESLint checking
npm run test    # Vitest component testing
npm run build   # Next.js production build compilation check
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more details.
