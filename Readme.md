# Meeting Intelligence Agent 🎙️🤖

Meeting Intelligence Agent is a professional full-stack application designed to ingest meeting audio recordings, run them through an agentic workflow to transcribe and extract structured information, persist records in Neon Postgres, and automatically synchronize tasks and schedules across Jira, Google Calendar, Slack, and email.

---

## 🌟 Key Features

*   **Multi-Agent Coordination (LangGraph)**: An agent pipeline manages transcription, structured entity extraction, summarization, and database serialization, followed by auto-integration steps.
*   **Audio Upload Stream**: High-performance, memory-efficient streamed upload handling files up to 1GB.
*   **Structured Information Extraction**: Extracts specific action items, key decisions reached, participants list, and overall topics with deep semantic context.
*   **Automatic Integrations**:
    *   **Jira**: Auto-creates formatted Jira tasks for all identified action items.
    *   **Google Calendar**: Books follow-up meetings via Google Cloud Service Accounts.
    *   **Slack**: Formats summaries and action items into Slack cards.
    *   **SendGrid**: Personalizes individual transactional emails so recipients only receive tasks assigned to *them*.
*   **Responsive Next.js Frontend**: A modern workspace UI designed for reviewing meeting metadata, updating tasks, editing participant emails, and chatting with the conversational agent regarding meeting topics.

---

## 📂 Project Structure

The project is structured as a monorepo containing two main services:

```
├── Backend/                 # FastAPI + LangGraph + SQLAlchemy service
│   ├── README.md            # Detailed Backend Developer Guide & Architecture docs
│   ├── agents/              # Transcription, Extraction, and Summary agents
│   ├── api/                 # FastAPI routes and middleware
│   ├── core/                # System configuration and structured logger
│   ├── db/                  # SQLAlchemy tables & DB session dependencies
│   ├── graph/               # LangGraph state machine structure
│   └── tools/               # Integration connectors (Slack, Google Calendar, Jira, SendGrid)
│
├── frontend/                # Next.js App Router UI
│   ├── README.md            # Frontend configuration and components overview
│   ├── app/                 # App Router pages and client state wrappers
│   ├── components/          # Reusable UI widgets and workspace viewports
│   ├── lib/                 # Core API Client and React Query hooks
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
*   **Database**: Neon Serverless Postgres with `pgvector`
*   **ORM**: SQLAlchemy v2 (Asynchronous Asyncpg driver)
*   **Observability**: LangSmith, Structlog (Structured JSON/Console outputs)
*   **SDKs**: Atlassian Python API, SendGrid API, Slack SDK, Google API Python Client

### Frontend
*   **Framework**: Next.js 15 (React 19, TypeScript)
*   **Styles**: Tailwind CSS
*   **State & Fetching**: TanStack React Query v5
*   **Form Validation**: Zod, React Hook Form
*   **Test Suite**: Vitest, React Testing Library

---

## 🚀 Quick Start

### 1. Backend Setup

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
    ```

3.  Boot the FastAPI Uvicorn reload server:
    ```bash
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    ```
    *   Swagger documentation is hosted at `http://localhost:8000/docs`.

### 2. Frontend Setup

1.  Navigate to the `frontend` directory and install packages:
    ```bash
    cd frontend
    npm install
    ```

2.  Create `frontend/.env.local`:
    ```env
    NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
    NEXT_PUBLIC_UPLOAD_DIR_HINT=/tmp/meeting-agent-uploads
    ```

3.  Boot the Next.js development server:
    ```bash
    npm run dev
    ```
    *   Open `http://localhost:3000` in your web browser.

---

## 🚦 End-to-End Processing Workflow

1.  **Ingestion**: The user uploads an audio recording (.mp3, .wav, etc.) in the frontend dashboard.
2.  **Streaming Upload**: The frontend calls `POST /meeting/upload`, which streams the file chunks directly onto the backend disk to minimize server memory footprints.
3.  **Task Queue Trigger**: The frontend calls `POST /meetings/process` with the file metadata, spinning up a background task context.
4.  **Agent Evaluation**:
    *   Groq Whisper transcribes the recording into plaintext.
    *   Llama-3.3 extracts entities (tasks, owners, dates, and topics) returning strict JSON structures.
    *   Llama-3.3 evaluates the transcript to form title blocks and short summaries.
    *   The engine writes structural rows to tables (`meetings`, `action_items`, `decisions`, `participants`).
5.  **Integration Sync**: The graph automatically proceeds to:
    *   Create corresponding tickets in Jira Cloud.
    *   Add a follow-up date invitation in Google Calendar.
    *   Submit summary logs to Slack.
    *   Distribute personalized assignments to emails via SendGrid.
6.  **Polling & State Management**: The frontend polls `GET /meetings/status/{job_id}` at 2-second intervals, displaying intermediate progress cards before pulling detailed outputs via `GET /meetings/{meeting_id}`.

---

## 🧪 Quality and Verification Checks

### Frontend
Run the UI validation suites:
```bash
cd frontend
npm run lint    # ESLint verification
npm run test    # Vitest testing
npm run build   # Next.js compilation validation
```

### Backend
Run Python tests:
```bash
cd Backend
pytest
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more details.
