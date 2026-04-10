# Meeting Intelligence Agent Frontend

Next.js App Router frontend for the Meeting Intelligence Agent backend.

## Features

- Dashboard and meetings workspace
- Audio upload and processing workflow
- Typed API client with normalized errors
- React Query hooks for list/detail/mutation flows
- Agent chat UI powered by backend `/query` endpoint
- Defensive loading, empty, and error states
- Vitest tests for API client behavior

## Environment

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_UPLOAD_DIR_HINT=/tmp/meeting-agent-uploads
```

`NEXT_PUBLIC_UPLOAD_DIR_HINT` should match backend `UPLOAD_DIR` so the process request can compose `audio_file_path` correctly.

## Local Run

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Scripts

```bash
npm run dev
npm run lint
npm run test
npm run build
npm run start
```

## Backend Endpoints Used

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

## Notes

- If the backend base path changes in the future (for example, adding `/api` prefix), only update `NEXT_PUBLIC_API_BASE_URL`.
- CORS for local frontend origins is configured in `Backend/api/main.py`.
