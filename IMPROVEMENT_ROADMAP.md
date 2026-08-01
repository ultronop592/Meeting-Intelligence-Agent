# 🚀 Meeting Intelligence Agent — Improvement Roadmap

> **Current State Snapshot**: `v2.0.0` · LangGraph pipeline · Neon Postgres + pgvector · Groq Whisper + Llama · Multi-LLM routing · Cross-meeting vector memory (RAG) · Streaming Q&A (SSE) · Next.js 15 frontend

---

## 📊 Current Project State

### ✅ What's Already Working

| Layer | Feature | Status |
|-------|---------|--------|
| Backend | LangGraph 7-node pipeline (transcribe → extract → summarize → save → jira → calendar → slack/email) | ✅ Complete |
| Backend | Groq Whisper transcription + FFmpeg auto-chunking for large files | ✅ Complete |
| Backend | PyAnnote speaker diarization (SPEAKER_00, SPEAKER_01) | ✅ Complete |
| Backend | Multi-LLM smart routing (8b instant vs 70b versatile) | ✅ Complete |
| Backend | Cross-meeting vector memory layer (pgvector RAG) | ✅ Complete |
| Backend | Streaming Q&A SSE endpoint (`/query/stream`) | ✅ Complete |
| Backend | Direct memory search endpoint (`/memory/search`) | ✅ Complete |
| Backend | Jira, Slack, Google Calendar, SendGrid integrations | ✅ Complete |
| Backend | Background job tracking with Postgres persistence | ✅ Complete |
| Frontend | Meeting upload + live job progress tracker | ✅ Complete |
| Frontend | Audio player with transcript sync + timestamp-click | ✅ Complete |
| Frontend | Streaming agent chat with blinking cursor (▍) | ✅ Complete |
| Frontend | Meeting detail (action items, decisions, participants) | ✅ Complete |

### ❌ Known Gaps / Missing Pieces

| Area | Gap |
|------|-----|
| Security | **No authentication or authorization** — all endpoints are publicly accessible |
| Security | No rate limiting on any endpoint |
| UX | No real-time pipeline progress — frontend polls with fixed intervals |
| UX | Agent chat has no conversation history / multi-turn context |
| UX | Memory layer has no frontend UI or search page |
| Analytics | No usage dashboard, no processing stats, no cross-meeting trend charts |
| Search | No meeting-wide search beyond the memory endpoint |
| Speaker Labels | Diarization gives `SPEAKER_00` names, not real names — no speaker identity linking |
| Observability | Logs are structured but not aggregated — no alerting or error tracking |
| Testing | No frontend Vitest tests — test suite is backend-only |
| Production | No Docker / Docker Compose config for self-hosted deployment |
| Production | No environment separation (dev vs staging vs prod) config |

---

## 🗺️ Improvement Phases

---

### 🔐 Phase 1 — Authentication & Security (High Priority)

**Why**: All endpoints are currently open. Any API key in `.env` can be abused by anyone with network access.

| # | Task | Files Affected |
|---|------|----------------|
| 1.1 | Add JWT-based user authentication with `python-jose` + `passlib` | `core/auth.py` *(NEW)*, `db/models.py`, `api/routes.py` |
| 1.2 | Add `User` table to DB (`id`, `email`, `hashed_password`, `created_at`) | `db/models.py`, `db/database.py` |
| 1.3 | `POST /auth/register` and `POST /auth/login` endpoints | `api/auth_routes.py` *(NEW)* |
| 1.4 | Protect all meeting endpoints with `Depends(get_current_user)` | `api/routes.py` |
| 1.5 | Associate each meeting with the uploading user (`meeting.user_id`) | `db/models.py`, `db/database.py` |
| 1.6 | Add `slowapi` rate limiter (e.g., 60 requests/min/IP on upload) | `api/main.py` |
| 1.7 | Frontend login/register page + JWT token management via `localStorage` | `frontend/app/(auth)/` *(NEW)* |

```
Backend: python-jose, passlib, slowapi
Frontend: jwt-decode
```

---

### ⚡ Phase 2 — Real-Time Pipeline Progress via WebSockets (High Priority)

**Why**: The current frontend polling model creates unnecessary DB load and slow perceived performance. Users stare at a blank spinner.

| # | Task | Files Affected |
|---|------|----------------|
| 2.1 | Add `WebSocket` connection manager class | `core/ws_manager.py` *(NEW)* |
| 2.2 | Add `GET /meetings/ws/{job_id}` WebSocket endpoint for live pipeline events | `api/routes.py` |
| 2.3 | Push node completion events from agent graph to connected WebSocket clients | `graph/agent_graph.py`, `db/database.py` |
| 2.4 | Replace frontend polling hook (`use-job-status.ts`) with WebSocket listener | `frontend/lib/hooks/use-job-status.ts` |
| 2.5 | Animated node-by-node progress stepper UI component | `frontend/components/processing/pipeline-tracker.tsx` *(NEW)* |

**WebSocket Event Format:**
```json
{
  "event": "node_completed",
  "node": "extract_information",
  "job_id": "abc-123",
  "completed_nodes": ["transcribe_audio", "extract_information"],
  "elapsed_ms": 4200
}
```

---

### 💬 Phase 3 — Multi-Turn Conversational Memory in Agent Chat (High Priority)

**Why**: The current Q&A chat is stateless — each message is independently context-less. The agent cannot answer follow-up questions like *"tell me more about the second decision"*.

| # | Task | Files Affected |
|---|------|----------------|
| 3.1 | Add `ChatSession` table in DB (`id`, `meeting_id`, `user_id`, `messages JSON`, `created_at`) | `db/models.py` |
| 3.2 | Extend `AgentQueryRequest` with `session_id?: string` | `models/schemas.py` |
| 3.3 | Maintain rolling chat history in `POST /query` + `POST /query/stream` | `api/routes.py` |
| 3.4 | Trim history to last `N` turns to avoid context overflow | `api/routes.py` |
| 3.5 | Persist conversation to DB on each exchange | `db/database.py` |
| 3.6 | Frontend chat history persistence across page refreshes | `frontend/lib/hooks/use-agent-chat.ts` |
| 3.7 | Suggested quick-questions panel (contextual chips like "Who owns this action?" / "Summarize decisions") | `frontend/components/chat/chat-suggestions.tsx` *(NEW)* |

---

### 📊 Phase 4 — Analytics Dashboard (Medium Priority)

**Why**: Currently the analytics page is empty. Cross-meeting insights would make the product genuinely valuable for teams.

| # | Task | Files Affected |
|---|------|----------------|
| 4.1 | `GET /analytics/summary` endpoint: total meetings, avg duration, total action items, completion rate | `api/routes.py` |
| 4.2 | `GET /analytics/participants` — leaderboard of most active participants + action item load | `api/routes.py` |
| 4.3 | `GET /analytics/timeline` — meeting frequency over time (weekly/monthly) | `api/routes.py` |
| 4.4 | `GET /analytics/action-items` — open/done/overdue breakdown by owner | `api/routes.py` |
| 4.5 | Action item completion trend chart (line chart per week) | `frontend/app/(app)/analytics/page.tsx` |
| 4.6 | Participant activity breakdown (bar chart) | `frontend/app/(app)/analytics/page.tsx` |
| 4.7 | Top recurring topics / keywords extracted from all meetings | `api/routes.py`, memory_service extension |
| 4.8 | Meeting statistics header cards (7-day, 30-day stats) | `frontend/components/analytics/` *(NEW)* |

**Recommended chart library**: `recharts` (already React-compatible, 0 config)

---

### 🔍 Phase 5 — Global Search, Speaker Identity & Observability (Medium Priority)

#### 5A — Global Full-Text Search

| # | Task | Files Affected |
|---|------|----------------|
| 5A.1 | `GET /search?q=` endpoint using Postgres `tsvector` full-text search on meetings + action items + decisions | `api/routes.py` |
| 5A.2 | Frontend global search bar (currently visual-only) — wire to real API | `frontend/components/layout/` |
| 5A.3 | Search results page with highlighted excerpts | `frontend/app/(app)/search/` *(NEW)* |
| 5A.4 | Semantic search toggle — run against `/memory/search` for semantic mode vs full-text | `frontend/app/(app)/search/` |

#### 5B — Speaker Identity Resolution

| # | Task | Files Affected |
|---|------|----------------|
| 5B.1 | Add speaker name mapping to participant record (`speaker_label` field) | `db/models.py` |
| 5B.2 | UI to map `SPEAKER_00` → "Alice Chen" on meeting detail page | `frontend/app/(app)/meetings/[id]/page.tsx` |
| 5B.3 | Retroactively rewrite diarized transcript with resolved names on save | `db/database.py` |

#### 5C — Error Tracking & Observability

| # | Task | Files Affected |
|---|------|----------------|
| 5C.1 | Integrate Sentry (`sentry-sdk`) for backend exception capture | `api/main.py`, `requirements.txt` |
| 5C.2 | Add pipeline latency tracking: report node timing breakdowns to LangSmith | `graph/agent_graph.py` |
| 5C.3 | Health check extension: report DB connectivity, Groq API reachability | `api/routes.py` |

---

### 🏗️ Phase 6 — Production Hardening & Deployment (Medium Priority)

**Why**: The project runs fine locally but has no production configuration, no containerization, and no CI pipeline.

| # | Task | Description |
|---|------|-------------|
| 6.1 | **Docker + Docker Compose** | `Dockerfile` for Backend, `Dockerfile` for Frontend, `docker-compose.yml` at root |
| 6.2 | **Environment Separation** | `core/config.py` dev/staging/prod profiles; separate `.env.production` template |
| 6.3 | **Alembic Migrations** | Generate versioned migration files from current schema; replace `create_all` with `alembic upgrade head` |
| 6.4 | **Frontend Vitest Tests** | Add component tests for `ChatBubble`, `AudioPlayer`, `MeetingCard` |
| 6.5 | **CI/CD GitHub Actions** | `.github/workflows/ci.yml` — run `pytest`, `tsc --noEmit`, `npm run lint` on every push |
| 6.6 | **CORS Hardening** | Restrict `allow_origins` to explicit production domain list |
| 6.7 | **File Cleanup Worker** | Periodic background task to delete processed audio files from upload directory |

---

### 🎤 Phase 7 — Voice & Advanced Features (Stretch Goals)

| # | Feature | Description |
|---|---------|-------------|
| 7.1 | **Live Meeting Recording** | Browser-side `MediaRecorder` API streaming → backend via chunked WebSocket upload |
| 7.2 | **Action Item Notifications** | Cron job sending due-date reminder emails 24h before task deadlines |
| 7.3 | **Meeting Templates** | Pre-set agenda templates (Sprint Retro, Design Review, 1:1) that pre-populate expected outputs |
| 7.4 | **Meeting Comparison** | Side-by-side diff of decisions across two meetings |
| 7.5 | **Custom LLM Provider** | Support OpenAI / Anthropic / Ollama as backend alternatives to Groq |
| 7.6 | **PDF Export** | One-click export of meeting summary + action items as a formatted PDF |
| 7.7 | **Public Meeting Share Link** | Generate a read-only shareable URL for a meeting without login |

---

## 📅 Suggested Execution Order

```
Week 1-2  │ Phase 1   — Authentication & Security (blocks everything else in production)
Week 3    │ Phase 2   — WebSocket real-time pipeline progress
Week 4    │ Phase 3   — Multi-turn chat memory
Week 5-6  │ Phase 4   — Analytics Dashboard
Week 7    │ Phase 5A  — Global search
Week 7    │ Phase 5B  — Speaker identity resolution
Week 8    │ Phase 5C  — Observability (Sentry + LangSmith)
Week 9    │ Phase 6   — Docker, CI/CD, Alembic migrations
Week 10+  │ Phase 7   — Stretch goals (voice recording, notifications, PDF export)
```

---

## 🧩 Quick Wins (Can Be Done Anytime, Low Effort)

| Item | Effort | Value |
|------|--------|-------|
| Add `retry` logic to Groq calls in extraction + summary agents | 1h | High |
| Add `/memory/search` page in frontend (search UI for cross-meeting memory) | 2h | High |
| Dark/light theme toggle persisted to `localStorage` | 1h | Medium |
| Speaker label assignment UI (`SPEAKER_00` → name) on meeting detail page | 2h | High |
| Add `X-Request-ID` tracing header to all API responses | 30m | Medium |
| Keyboard shortcuts for chat (Ctrl+Enter to send, Esc to clear) | 30m | Medium |
| Add `updated_at` column to `action_items` to track when status changes | 1h | Medium |
| Show `llm_model_used` in meeting detail for transparency | 1h | Low |
| Add pagination to `/meetings` list in frontend | 2h | High |
| Add file size validation feedback on upload (before hitting API) | 1h | Medium |

---

## 📁 New Files That Will Be Created in Future Phases

```
Backend/
├── core/
│   ├── auth.py              (Phase 1 — JWT utilities)
│   └── ws_manager.py        (Phase 2 — WebSocket connection manager)
├── api/
│   └── auth_routes.py       (Phase 1 — login/register endpoints)
└── alembic/                 (Phase 6 — schema migration scripts)

frontend/
├── app/
│   ├── (auth)/              (Phase 1 — login/register pages)
│   ├── search/              (Phase 5A — global search results page)
│   └── analytics/           (Phase 4 — full analytics dashboard)
├── components/
│   ├── analytics/            (Phase 4 — chart components)
│   └── processing/           (Phase 2 — pipeline step tracker)
└── .github/
    └── workflows/
        └── ci.yml            (Phase 6 — CI/CD pipeline)
```

---

> **Last updated**: July 31, 2026
> **Current version**: `v2.0.0` — Multi-LLM Routing + Streaming Q&A + Vector Memory Layer complete
