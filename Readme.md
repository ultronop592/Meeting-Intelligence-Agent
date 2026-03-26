# Meeting Intelligence Agent

An end-to-end agentic AI system that automatically processes meeting recordings — transcribing audio, extracting action items and decisions, generating summaries, and pushing results to Jira, Google Calendar, Slack, and email. Built with LangGraph, FastAPI, Groq, and Neon Postgres.

---

## What It Does

Upload a meeting recording (MP3, WAV, M4A) and the agent automatically:

1. **Transcribes** the audio using Groq Whisper (40-min meeting in ~20 seconds)
2. **Extracts** all action items with owners, due dates, and priorities
3. **Identifies** every decision made and participant present
4. **Generates** a structured summary (short + detailed)
5. **Saves** everything to a Neon Postgres database
6. **Creates** one Jira ticket per action item — already assigned
7. **Books** a Google Calendar follow-up meeting for all participants
8. **Sends** each participant a personalised email with only their tasks
9. **Posts** the meeting summary to a Slack channel

A 40-minute meeting is fully processed in 45–90 seconds with zero manual work.

---

## Architecture

```
Audio File Upload (MP3/WAV/M4A)
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │              LangGraph StateGraph                    │
  │                                                     │
  │  Node 1          Node 2           Node 3            │
  │  transcribe  ──► extract      ──► summarise         │
  │  (Whisper)        (Llama 3.3)      (Llama 3.3)      │
  │                                        │            │
  │                                        ▼            │
  │                                   Node 4            │
  │                                   save to DB        │
  │                                   (Neon Postgres)   │
  │                                        │            │
  │                    ┌───────────────────┤            │
  │                    │                   │            │
  │                    ▼                   ▼            │
  │               Node 5              Node 6            │
  │               Jira tickets        Google Calendar   │
  │                    │                   │            │
  │                    └───────────────────┘            │
  │                                   │                 │
  │                                   ▼                 │
  │                              Node 7                 │
  │                         Email + Slack               │
  └─────────────────────────────────────────────────────┘
```

**Tech Stack**

| Layer | Technology |
|---|---|
| Agent framework | LangGraph (StateGraph, conditional edges) |
| LLM + Transcription | Groq API — Whisper + Llama 3.3 70B |
| Backend API | FastAPI + Uvicorn |
| Database | Neon Postgres (SQLAlchemy async + Alembic) |
| Vector search | pgvector (semantic meeting search) |
| Job queue | Upstash Redis |
| Observability | LangSmith |
| Task management | Jira REST API |
| Calendar | Google Calendar API |
| Email | SendGrid |
| Team chat | Slack Incoming Webhooks |
| Backend deploy | Render |
| Frontend deploy | Vercel |

---

## Project Structure

```
meeting-agent/
├── backend/
│   ├── agents/
│   │   ├── transcription.py     # Node 1 — Groq Whisper
│   │   ├── extraction.py        # Node 2 — LLM structured output
│   │   └── summary.py           # Node 3 — LLM meeting summary
│   ├── graph/
│   │   └── agent_graph.py       # LangGraph StateGraph (all 7 nodes)
│   ├── tools/
│   │   ├── jira_tool.py         # Node 5 — creates Jira tickets
│   │   ├── calendar_tool.py     # Node 6 — books Google Calendar event
│   │   ├── email_tool.py        # Node 7 — sends personalised emails
│   │   └── slack_tool.py        # Node 7 — posts Slack summary
│   ├── db/
│   │   ├── models.py            # SQLAlchemy ORM table definitions
│   │   └── database.py          # Neon engine, sessions, Node 4
│   ├── models/
│   │   └── schemas.py           # All Pydantic schemas (LLM + API + DB)
│   ├── api/
│   │   ├── main.py              # FastAPI app entry point
│   │   └── routes.py            # All API endpoints
│   └── core/
│       ├── config.py            # Settings loaded from .env
│       └── logging.py           # Structured JSON logging
├── frontend/                    # Next.js 14 dashboard
├── requirements.txt
├── .env.example
├── .gitignore
└── alembic.ini
```

---

## LangGraph Agent — How It Works

This project uses **LangGraph's StateGraph** to build a multi-node agentic pipeline. Each node is a Python function that receives the shared `AgentState`, does its work, and returns only the fields it changed. LangGraph merges those changes automatically.

```python
# Shared state flows through every node
class AgentState(BaseModel):
    audio_file_path: str        # Input
    transcript:      str        # Node 1 output
    extraction:      ExtractionOutput   # Node 2 output
    summary:         MeetingSummary     # Node 3 output
    meeting_id:      str        # Node 4 output
    jira_ticket_ids: list[str]  # Node 5 output
    calendar_event_id: str      # Node 6 output
    notification_results: list  # Node 7 output
    errors:          list[str]  # Non-fatal errors
    completed_nodes: list[str]  # Progress tracking
```

**Conditional edges** handle failures gracefully — if transcription fails, the graph ends immediately instead of passing an empty transcript to the LLM. If the database save fails, Jira/Calendar/Email are skipped automatically.

```python
graph.add_conditional_edges(
    "transcribe_audio",
    should_continue_after_transcription,
    {"extract_information": "extract_information", "end": END},
)
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- Git

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/meeting-intelligence-agent.git
cd meeting-intelligence-agent
```

### 2. Create virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your API keys. See [Getting API Keys](#getting-api-keys) below.

### 5. Set up the database

```bash
# Run Alembic migrations to create all tables in Neon
alembic upgrade head
```

### 6. Create uploads directory

```bash
mkdir -p /tmp/meeting-agent-uploads
```

### 7. Run the backend

```bash
uvicorn backend.api.main:app --reload --port 8000
```

API is now running at `http://localhost:8000`
Interactive docs at `http://localhost:8000/docs`

### 8. Run the frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Frontend is now running at `http://localhost:3000`

---

## Getting API Keys

| Service | Where to get it | Free tier |
|---|---|---|
| **Groq** | [console.groq.com](https://console.groq.com) → API Keys | Yes — generous daily limit |
| **Neon** | [neon.tech](https://neon.tech) → New Project → Connection Details | Yes — 500 MB |
| **LangSmith** | [smith.langchain.com](https://smith.langchain.com) → Settings → API Keys | Yes — 5,000 traces/month |
| **Jira** | [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) | Yes — up to 10 users |
| **Google Calendar** | [console.cloud.google.com](https://console.cloud.google.com) → Enable Calendar API → Service Account | Yes — free |
| **SendGrid** | [sendgrid.com](https://sendgrid.com) → Settings → API Keys | Yes — 100 emails/day |
| **Slack** | [api.slack.com/apps](https://api.slack.com/apps) → Incoming Webhooks | Yes — all plans |
| **Upstash Redis** | [upstash.com](https://upstash.com) → Create Database | Yes — 10k req/day |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/meetings/upload` | Upload audio file |
| `POST` | `/api/meetings/process` | Trigger agent pipeline |
| `GET` | `/api/meetings` | List all meetings |
| `GET` | `/api/meetings/{id}` | Full meeting detail |
| `GET` | `/api/meetings/{id}/status` | Poll processing progress |
| `PATCH` | `/api/meetings/{id}/action-items/{item_id}` | Update task status |
| `DELETE` | `/api/meetings/{id}` | Delete meeting |

Full interactive documentation available at `/docs` when the server is running.

---

## Environment Variables

```bash
# Groq — AI transcription and LLM
GROQ_API_KEY=gsk_...

# Neon — Postgres database
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.neon.tech/db?sslmode=require
DATABASE_URL_SYNC=postgresql+psycopg2://user:pass@ep-xxx.neon.tech/db?sslmode=require

# LangSmith — agent observability (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=meeting-intelligence-agent

# Jira
JIRA_URL=https://yourname.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=ATAT...
JIRA_PROJECT_KEY=PROJ

# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS_JSON={"type":"service_account",...}
GOOGLE_CALENDAR_ID=you@gmail.com

# SendGrid
SENDGRID_API_KEY=SG....
SENDER_EMAIL=noreply@yourdomain.com
SENDER_NAME=Meeting Intelligence Agent

# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL=#meeting-summaries

# Upstash Redis
UPSTASH_REDIS_REST_URL=https://....upstash.io
UPSTASH_REDIS_REST_TOKEN=AX...

# App
APP_ENV=development
SECRET_KEY=your_64_char_random_hex
MAX_UPLOAD_SIZE_MB=25
UPLOAD_DIR=/tmp/meeting-agent-uploads
```

---

## Deployment

### Backend — Render

1. Push code to GitHub
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your GitHub repository
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`
6. Add all environment variables from `.env`
7. Deploy

### Frontend — Vercel

1. Go to [vercel.com](https://vercel.com) → New Project
2. Import your GitHub repository
3. Set root directory to `frontend`
4. Add `NEXT_PUBLIC_API_URL` pointing to your Render URL
5. Deploy

### Database migrations on deploy

```bash
# Run once after first deploy
alembic upgrade head
```

---

## Processing Time

For a 40-minute meeting recording:

| Step | Time |
|---|---|
| File upload | 5–15 sec |
| Groq Whisper transcription | 15–25 sec |
| LLM extraction | 8–15 sec |
| LLM summary | 5–10 sec |
| Database save | 1–2 sec |
| Jira tickets (5 items) | 3–8 sec |
| Google Calendar | 1–3 sec |
| Emails + Slack | 3–8 sec |
| **Total** | **45–90 sec** |

Processing runs as a background job so the API returns immediately and the frontend polls for progress.

---

## API Cost Per Meeting

All services used have free tiers that cover development and light production use.

| Service | Calls per meeting | Free limit |
|---|---|---|
| Groq | 3 (Whisper × 1, Llama × 2) | ~14,400 req/day |
| Jira | 1 per action item (~5) | Unlimited |
| Google Calendar | 1 | Unlimited |
| SendGrid | 1 per participant (~5) | 100 emails/day |
| Slack | 1 | Unlimited |

---

## Key Technical Decisions

**Why LangGraph over a simple function chain?**
LangGraph provides typed shared state across nodes, conditional branching (failed transcription stops the graph), built-in error accumulation, and a clear visual mental model of the pipeline. A plain function chain has no state management, no conditional logic, and breaks silently.

**Why Groq over OpenAI?**
Groq runs Whisper and Llama on custom LPU chips — 10–30x faster than standard GPU inference. A 40-minute meeting transcribes in 20 seconds instead of 8 minutes. Same API interface as OpenAI.

**Why Neon over Supabase?**
Neon is standard Postgres with a serverless hosting layer. Uses SQLAlchemy directly — the industry standard Python ORM. Supabase has been intermittently blocked by Indian ISPs. Neon has not.

**Why async SQLAlchemy?**
FastAPI is async. A sync database driver blocks the event loop — the server can only handle one request at a time. `asyncpg` keeps the server non-blocking under concurrent load.

**Why background jobs for processing?**
HTTP requests time out after 30 seconds. A 90-second processing job would be killed mid-pipeline without a background job queue. Upstash Redis queues the job, FastAPI returns immediately, and the frontend polls for completion.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---
