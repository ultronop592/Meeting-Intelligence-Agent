# Meeting Intelligence Agent Frontend

Next.js 15 App Router frontend for the Meeting Intelligence Agent backend.

## Features

- **Dashboard and Meetings Workspace**: Complete UI for reviewing meetings, action items, decisions, attendees, and notification logs.
- **Interactive Audio Player & Transcript Sync**: Custom audio player with scrubber, variable speed controls (`0.75x`–`2.0x`), and interactive speaker-line highlighting. Clicking any transcript line seeks the audio directly to that timestamp.
- **Audio Upload & Processing Workflow**: Drag-and-drop file upload with real-time processing timeline polling.
- **Smart Conversational Q&A**: In-page Chat UI powered by the backend Groq Llama 3.3 RAG engine via `/query`.
- **Integrations Dispatch**: Manual 1-click dispatch controls for Slack, Jira, SendGrid Email, and Google Calendar.
- **Typed API Client**: Built with TanStack React Query v5 and Zod schema validations.
- **Vitest & Next.js Build Tests**: Clean TypeScript type-safety and unit testing setup.

## Environment

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Local Run

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Scripts

```bash
npm run dev     # Boot Next.js dev server
npm run lint    # Run ESLint
npm run test    # Run Vitest test suite
npm run build   # Compile Next.js production build
npm run start   # Run production build server
```

## Backend Endpoints Used

- `GET /health`
- `POST /meeting/upload`
- `POST /meetings/process`
- `GET /meetings/status/{job_id}`
- `GET /meetings`
- `GET /meetings/{meeting_id}`
- `GET /meetings/{meeting_id}/audio`
- `PATCH /meetings/{meeting_id}/action-items/{item_id}`
- `PATCH /meetings/{meeting_id}/participants/{participant_id}?email=...`
- `DELETE /meetings/{meeting_id}`
- `POST /meetings/{meeting_id}/send/email`
- `POST /meetings/{meeting_id}/send/slack`
- `POST /meetings/{meeting_id}/send/jira`
- `POST /meetings/{meeting_id}/send/calendar?days_from_now=...`
- `POST /query`

## Notes

- CORS for local frontend origins (`http://localhost:3000`, `http://localhost:3001`) is pre-configured in `Backend/api/main.py`.
