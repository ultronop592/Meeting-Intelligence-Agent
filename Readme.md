# Meeting Intelligence Agent

Meeting Intelligence Agent is a full-stack application that ingests meeting audio, processes it through an agent pipeline, stores structured outputs in Neon Postgres, and exposes a modern Next.js UI for reviewing summaries, decisions, action items, and agent chat.

## Project Structure

- `Backend/`: FastAPI + LangGraph + SQLAlchemy service
- `frontend/`: Next.js App Router UI with typed API client and React Query hooks
- `API_INTEGRATION_MAP.md`: endpoint mapping notes
- `IMPLEMENTATION_NOTES.md`: architecture and implementation notes

## Tech Stack

- Backend: FastAPI, Uvicorn, LangGraph, Groq, SQLAlchemy, Neon Postgres, pgvector
- Frontend: Next.js, React, TypeScript, Tailwind CSS, React Query, Zod

## Quick Start

### 1. Backend setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r Backend/requirements.txt
```

Create `Backend/.env` with the required values (minimum for local start):

```bash
APP_ENV=development
SECRET_KEY=change-me

GROQ_API_KEY=your-key

DATABASE_URL=postgresql+asyncpg://user:pass@host/db?sslmode=require
DATABASE_URL_SYNC=postgresql+psycopg2://user:pass@host/db?sslmode=require

MAX_UPLOAD_SIZE_MB=1024
UPLOAD_DIR=/tmp/meeting-agent-uploads
```

Run backend from the `Backend/` directory:

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend setup

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_UPLOAD_DIR_HINT=/tmp/meeting-agent-uploads
```

Run frontend:

```bash
npm run dev
```

Frontend: `http://localhost:3000`
Backend docs: `http://localhost:8000/docs`

## Verified API Integration

Frontend API client in `frontend/lib/api/meetings.ts` is wired to backend routes in `Backend/api/routes.py`:

- `GET /health`
- `POST /meeting/upload`
- `POST /meetings/process`
- `GET /meetings/status/{job_id}`
- `GET /meetings`
- `GET /meetings/{meeting_id}`
- `PATCH /meetings/{meeting_id}/action-items/{item_id}`
- `PATCH /meetings/{meeting_id}/participants/{participant_id}?email=...`
- `DELETE /meetings/{meeting_id}`
- `POST /meetings/{meeting_id}/send/email`
- `POST /meetings/{meeting_id}/send/slack`
- `POST /meetings/{meeting_id}/send/jira`
- `POST /meetings/{meeting_id}/send/calendar?days_from_now=...`
- `POST /query`

## End-to-End Flow

1. Upload audio from Meetings page (`/meeting/upload`)
2. Start processing job (`/meetings/process`)
3. Poll job status until complete (`/meetings/status/{job_id}`)
4. Load meeting list and details (`/meetings`, `/meetings/{meeting_id}`)
5. Use meeting-level chat via `/query`
6. Trigger send actions (email/slack/jira/calendar)

## Quality Checks

Frontend:

```bash
cd frontend
npm run lint
npm run test
npm run build
```

Backend (if you use pytest locally):

```bash
pytest
```

## Notes

- The backend normalizes Neon async URLs from `sslmode=require` to `ssl=require` for `asyncpg` compatibility.
- CORS is configured for local frontend origins (`localhost:3000` and `localhost:3001`).

## License

MIT
