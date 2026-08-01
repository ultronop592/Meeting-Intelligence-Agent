# Meeting Intelligence Agent Frontend

Next.js 15 App Router frontend workspace for the **Meeting Intelligence Agent** backend service.

---

## Features

- **Dashboard & Meetings Workspace**: Complete UI for reviewing meeting recordings, short and detailed summaries, action items, key decisions, participants, and notification dispatch logs.
- **Interactive Audio Player & Transcript Sync**: Custom audio player with scrubber, variable speed controls (`0.75x`–`2.0x`), and interactive speaker line highlighting. Clicking any transcript line seeks the audio player directly to that exact timestamp.
- **Audio Upload & Processing Pipeline**: Drag-and-drop file upload interface with a live background job progress tracker polling `GET /meetings/status/{job_id}`.
- **Real-Time Streaming Conversational Chat UI**: In-page agent chat drawer powered by Server-Sent Events (SSE) streaming tokens from `POST /query/stream` with a dynamic typing cursor (`▍`) and rule-based fallback support.
- **Cross-Meeting Memory Search UI**: Interface for querying cross-meeting vector memory via `POST /memory/search`.
- **1-Click Integrations Dispatch**: Interactive controls for manual live dispatches to Slack, Jira Cloud, SendGrid Email, and Google Calendar.
- **Action Item & Participant Management**: Update action item status (`open`, `in_progress`, `done`) and save participant email addresses.
- **Typed API Client**: Built using TanStack React Query v5 and Zod schema validation.
- **Vitest & Next.js Build Suite**: TypeScript type-safety and unit testing configuration.

---

## Environment Setup

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Local Development

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your web browser.

---

## Scripts

```bash
npm run dev     # Launch Next.js development server
npm run lint    # Run ESLint code checks
npm run test    # Execute Vitest component test suite
npm run build   # Compile production build
npm run start   # Run production build server
```

---

## Backend Endpoints Used

- `GET /health` — System & database health verification
- `POST /meeting/upload` — Audio file upload streaming
- `POST /meetings/process` — Trigger background pipeline job
- `GET /meetings/status/{job_id}` — Background job progress status
- `GET /meetings` — Paginated meetings list
- `GET /meetings/{meeting_id}` — Meeting detail view
- `GET /meetings/{meeting_id}/audio` — Audio streaming with `Accept-Ranges` byte-seeking support
- `PATCH /meetings/{meeting_id}/action-items/{item_id}` — Update action item status
- `PATCH /meetings/{meeting_id}/participants/{participant_id}?email=...` — Save participant email
- `DELETE /meetings/{meeting_id}` — Delete meeting record
- `POST /meetings/{meeting_id}/send/email` — Dispatch SendGrid emails
- `POST /meetings/{meeting_id}/send/slack` — Dispatch Slack Block Kit summary cards
- `POST /meetings/{meeting_id}/send/jira` — Dispatch Jira Cloud tickets
- `POST /meetings/{meeting_id}/send/calendar?days_from_now=...` — Book Google Calendar follow-up
- `POST /query` — Non-streaming LLM Q&A
- `POST /query/stream` — Real-time Server-Sent Events (SSE) token streaming Q&A
- `POST /memory/search` — Cross-meeting vector memory RAG search

---

## Notes

- CORS for local frontend origins (`http://localhost:3000`, `http://localhost:3001`) is pre-configured in `Backend/api/main.py`.
