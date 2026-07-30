# Meeting Intelligence Agent 🎙️🤖

Meeting Intelligence Agent is a professional full-stack application designed to ingest meeting audio recordings, run them through an agentic workflow to transcribe and extract structured information, persist records in Neon Postgres, and automatically synchronize tasks and schedules across Jira, Google Calendar, Slack, and email.

---

## 🌟 Key Features

*   **Multi-Agent Coordination (LangGraph)**: An agent pipeline manages transcription, speaker diarization, structured entity extraction, summarization, and database serialization, followed by auto-integration steps.
*   **Automatic Audio Chunking (FFmpeg)**: Handles single audio files of any size. Files exceeding Groq's 25MB Whisper limit are automatically split into 10-minute lossless chunks using FFmpeg's stream-copy muxer before transcription.
*   **Speaker Diarization (PyAnnote 3.1)**: Identifies and labels speakers (`SPEAKER_00`, `SPEAKER_01`) with timestamp alignment for clear action item and decision attribution.
*   **Interactive Audio Player & Transcript Sync**: Stream meeting audio directly from the backend with seeking, variable playback speeds (`0.75x`–`2.0x`), and synchronized transcript highlighting. Clicking any transcript line jumps the audio to that exact timestamp.
*   **Smart LLM Q&A Engine (`/query`)**: Powered by Groq Llama 3.3 (`llama-3.3-70b-versatile`) with full meeting context retrieval for natural conversational Q&A. Includes a seamless rule-based keyword fallback.
*   **Persistent Background Job Tracking**: Job status and intermediate node timings are persisted in a PostgreSQL `processing_jobs` table, surviving server restarts and multi-worker process environments.
*   **Structured Information Extraction**: Extracts action items, key decisions, participants, and topics with semantic context.
*   **Automatic & Manual Integrations**:
    *   **Jira**: Auto-creates formatted Jira tasks for all identified action items.
    *   **Google Calendar**: Books follow-up meetings via Google Cloud Service Accounts.
    *   **Slack**: Formats summaries and action items into rich Slack Block Kit cards.
    *   **SendGrid**: Personalizes individual transactional emails so recipients only receive tasks assigned to *them*.
*   **Responsive Next.js Frontend**: A modern workspace UI designed for reviewing meeting metadata, listening to synced audio recordings, updating tasks, editing participant emails, and chatting with the conversational agent.

---

## 📂 Project Structure

The project is structured as a monorepo containing two main services:

```
├── Backend/                 # FastAPI + LangGraph + SQLAlchemy service
│   ├── README.md            # Detailed Backend Developer Guide & Architecture docs
│   ├── agents/              # Transcription, Extraction, Summary & Storage agents
│   ├── api/                 # FastAPI routes, audio streaming & middleware
│   ├── core/                # System configuration and structured logger
│   ├── db/                  # SQLAlchemy ORM models (ProcessingJob, Meeting, etc.)
│   ├── graph/               # LangGraph state machine structure
│   ├── tools/               # Integration connectors (Slack, Google Calendar, Jira, SendGrid, PyAnnote)
│   └── tests/               # Pytest suite (71 passing unit & integration tests)
│
├── frontend/                # Next.js App Router UI
│   ├── README.md            # Frontend configuration and components overview
│   ├── app/                 # App Router pages and client state wrappers
│   ├── components/          # Reusable UI widgets, AudioPlayer & workspace viewports
│   ├── lib/                 # Core API Client and React Query hooks
│   ├── types/               # TypeScript API definitions
│   └── tests/               # Vitest client-side integration tests
│
├── API_INTEGRATION_MAP.md   # Endpoint contracts mapping backend schemas to frontend hooks
└── IMPLEMENTATION_NOTES.md  # Architectural assumptions, UX layout, and decisions log
```

*For in-depth backend design patterns, schemas, and node specifications, please consult the [Backend Developer Guide](file:///c:/Agentic%20AI%20Project/Backend/README.md).*

---

## 🛠️ Technology Stack

### Backend
*   **Framework**: FastAPI (Python 3.10+)
*   **Agent Flow**: LangGraph, LangChain Core
*   **Inference APIs**: Groq (`whisper-large-v3`, `llama-3.3-70b-versatile`)
*   **Diarization & Audio Processing**: PyAnnote.audio 3.1, FFmpeg
*   **Database**: Neon Serverless Postgres with `pgvector`
*   **ORM**: SQLAlchemy v2 (Asynchronous Asyncpg driver + SQLite in-memory for testing)
*   **Observability**: LangSmith, Structlog (Structured JSON/Console outputs)
*   **SDKs**: Atlassian Python API, SendGrid API, Slack SDK, Google API Python Client
*   **Test Runner**: Pytest + pytest-asyncio (71 unit & integration tests)

### Frontend
*   **Framework**: Next.js 15 (React 19, TypeScript)
*   **Styles**: Tailwind CSS
*   **State & Fetching**: TanStack React Query v5
*   **Form Validation**: Zod, React Hook Form
*   **Test Suite**: Vitest, React Testing Library

---

## 🚀 Quick Start

### 1. System Dependencies (Optional for large audio & diarization)
*   **FFmpeg**: Required for automatic audio chunking of files >25MB.
    *   Windows: `winget install ffmpeg` or copy `ffmpeg.exe` to `Backend/venv/Scripts/`
    *   macOS: `brew install ffmpeg`
    *   Linux: `sudo apt install ffmpeg`

### 2. Backend Setup

1.  Navigate to the `Backend` directory, configure a virtual environment, and install dependencies:
    ```bash
    cd Backend
    python -m venv venv
    
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate

    pip install -r requirements.txt
    ```

2.  Create `Backend/.env` with required API keys and DB URLs:
    ```env
    APP_ENV=development
    SECRET_KEY=generate-a-secure-secret-key
    GROQ_API_KEY=your-groq-api-key
    DATABASE_URL=postgresql+asyncpg://user:pass@host/db?sslmode=require
    DATABASE_URL_SYNC=postgresql+psycopg2://user:pass@host/db?sslmode=require
    
    # Optional Speaker Diarization
    HF_TOKEN=your-huggingface-token
    DIARIZATION_ENABLED=true
    ```

3.  Boot the FastAPI Uvicorn reload server:
    ```bash
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    ```
    *   Swagger documentation is hosted at `http://localhost:8000/docs`.

### 3. Frontend Setup

1.  Navigate to the `frontend` directory and install packages:
    ```bash
    cd frontend
    npm install
    ```

2.  Create `frontend/.env.local`:
    ```env
    NEXT_PUBLIC_API_URL=http://localhost:8000
    ```

3.  Boot the Next.js development server:
    ```bash
    npm run dev
    ```
    *   Open `http://localhost:3000` in your web browser.

---

## 🚦 End-to-End Processing Workflow

1.  **Ingestion**: User uploads an audio recording (.mp3, .wav, .m4a, .mp4, etc.) in the frontend dashboard.
2.  **Streaming Upload**: `POST /meeting/upload` streams the file to the upload directory.
3.  **Task Queue Trigger**: `POST /meetings/process` starts background job processing, tracking progress in the Postgres `processing_jobs` table.
4.  **Agent Evaluation**:
    *   **Node 1 (`transcribe_audio`)**: Runs PyAnnote diarization (if enabled) and Groq Whisper transcription. Large files (>25MB) are automatically split using FFmpeg before Whisper transcription.
    *   **Node 2 (`extract_information`)**: Groq Llama 3.3 extracts action items, decisions, participants, and topics into structured JSON.
    *   **Node 3 (`generate_summary`)**: Groq Llama 3.3 generates title, short summary, and detailed narrative.
    *   **Node 4 (`save_to_database`)**: Writes full meeting record, speaker transcripts, action items, decisions, and participants to PostgreSQL.
5.  **Integration Sync (Nodes 5–7)**:
    *   Creates formatted Jira Cloud tickets.
    *   Schedules Google Calendar follow-up invitations.
    *   Posts Slack Block Kit summary cards.
    *   Sends personalized SendGrid transactional emails to participants.
6.  **Interactive Playback & Q&A**: User reviews meeting details, listens to synchronized audio with active speaker line highlighting, and asks questions via the Groq Llama 3.3 Q&A engine.

---

## 🧪 Quality and Verification Checks

### Backend Test Suite
Run the 71-test automated suite (covers routes, audio chunking, diarization, and LLM Q&A):
```bash
cd Backend
pytest
```

### Frontend Build & Lint
Run the UI validation suites:
```bash
cd frontend
npm run lint    # ESLint verification
npm run test    # Vitest testing
npm run build   # Next.js compilation validation
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more details.
