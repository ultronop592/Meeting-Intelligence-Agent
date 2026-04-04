# Meeting Intelligence Agent

This repository contains a backend-first agentic pipeline for meeting processing.

## Frontend (New)

A production-ready Next.js frontend now exists under `frontend/` with:

- Claude-style workspace UI (sidebar, conversation area, composer, insights panel)
- Full endpoint integration to discovered backend routes
- Typed API client (`frontend/lib/api`), hooks, and reusable components
- Polling for long-running jobs with exponential backoff
- Route guard/token injection support
- Tests and build validation

Run frontend:

```bash
cd frontend
npm install
npm run dev
```

Quality checks:

```bash
cd frontend
npm run lint
npm run test
npm run build
```

Integration details are documented in root `API_INTEGRATION_MAP.md`.
Architecture notes are documented in root `IMPLEMENTATION_NOTES.md`.

It uses:
- LangGraph for orchestration
- Groq (Whisper + Llama) for transcription and extraction/summarization
- Neon Postgres (via SQLAlchemy) for persistence
- Jira, Google Calendar, SendGrid, and Slack integrations

## Important update

This project is using Neon Postgres, not Supabase.

Database settings in code:
- `DATABASE_URL` (async driver: `postgresql+asyncpg://...neon.tech/...`)
- `DATABASE_URL_SYNC` (sync driver: `postgresql+psycopg2://...neon.tech/...`)

See:
- `Backend/core/config.py`
- `Backend/db/database.py`
- `Backend/models/schemas.py` (`HealthResponse.database = "neon"`)

## Current workspace structure

```text
.
├── Readme.md
└── Backend
    ├── .env
    ├── requirements.txt
    ├── agents
    │   ├── extraction.py
    │   ├── summary.py
    │   └── transcription.py
    ├── api
    │   ├── main.py
    │   └── routes.py
    ├── core
    │   ├── config.py
    │   └── logging.py
    ├── db
    │   ├── database.py
    │   └── models.py
    ├── graph
    │   └── agent_graph.py
    ├── models
    │   └── schemas.py
    └── tools
        ├── calender_tool.py
        ├── email_tool.py
        ├── jira_tool.py
        └── slack_tool.py
```

## Pipeline overview (as implemented)

LangGraph flow in `Backend/graph/agent_graph.py`:

1. `transcribe_audio` (`Backend/agents/transcription.py`)
2. `extract_information` (`Backend/agents/extraction.py`)
3. `generate_summary` (`Backend/agents/summary.py`)
4. `save_to_database` (`Backend/db/database.py`)
5. `create_jira_tickets` (`Backend/tools/jira_tool.py`)
6. `book_calendar` (`Backend/tools/calender_tool.py`)
7. `send_notifications` (`Backend/tools/slack_tool.py`, which also calls email sending)

Database save includes:
- meetings
- action_items
- decisions
- participants
- notifications_log

## Tech stack (from code and requirements)

- Python 3.11+
- FastAPI + Uvicorn
- LangGraph + LangSmith (optional)
- Groq SDK
- SQLAlchemy + asyncpg + psycopg2-binary + Alembic
- pgvector
- atlassian-python-api
- google-api-python-client
- SendGrid
- slack-sdk
- Upstash Redis client
- Tenacity, Structlog, Pydantic

See exact pinned versions in `Backend/requirements.txt`.

## Environment variables

Configured in `Backend/core/config.py`:

```bash
# App
APP_ENV=development
SECRET_KEY=change-me

# Groq
GROQ_API_KEY=...

# Neon Postgres
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.neon.tech/db?sslmode=require
DATABASE_URL_SYNC=postgresql+psycopg2://user:pass@ep-xxx.neon.tech/db?sslmode=require

# LangSmith (optional)
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=meeting-intelligence-agent

# Jira
JIRA_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=PROJ

# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS_JSON=
GOOGLE_CALENDAR_ID=

# SendGrid
SENDGRID_API_KEY=
SENDER_EMAIL=
SENDER_NAME=Meeting Intelligence Agent

# Slack
SLACK_WEBHOOK_URL=
SLACK_CHANNEL=#meeting-summaries

# Upstash
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=

# Upload handling
MAX_UPLOAD_SIZE_MB=25
UPLOAD_DIR=/tmp/meeting-agent-uploads
```

## Setup (current backend workspace)

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r Backend/requirements.txt
```

3. Create/update environment variables in `Backend/.env`.
4. Ensure Neon database URLs are valid.
5. Run migrations (if Alembic is configured in your local setup):

```bash
alembic upgrade head
```

## Current status note

`Backend/api/main.py` and `Backend/api/routes.py` are currently empty in this workspace snapshot. The core agent, DB, and integration modules exist, but API entrypoints/routes still need to be implemented or restored before running the full HTTP service.

## Database decision

Why Neon instead of Supabase (current project direction):
- standard Postgres connection model
- direct SQLAlchemy usage
- existing code and environment variables are already aligned to Neon

## License

MIT
