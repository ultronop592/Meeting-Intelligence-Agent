# Meeting Intelligence Agent Frontend

Production-ready Next.js App Router frontend for Meeting Intelligence Agent.

## Features

- Claude-style workspace layout
	- left sidebar meeting history
	- central conversation/workspace pane
	- bottom composer for upload/process trigger
	- right insights panel for summary, decisions, tasks
- Full backend endpoint integration (see root `API_INTEGRATION_MAP.md`)
- Typed API client with normalized errors
- Polling with exponential backoff for long-running meeting jobs
- Toast notifications and defensive loading/error/empty states
- Auth layer deferred (to be added with backend auth endpoints)
- Unit tests for API client and workspace page flow

## Tech Stack

- Next.js App Router + TypeScript
- Tailwind CSS
- Sonner toasts
- Zod validation
- Vitest + Testing Library

## Environment Variables

Copy `.env.example` to `.env.local` and set values:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_UPLOAD_DIR_HINT=/tmp/meeting-agent-uploads
```

## Run

```bash
npm install
npm run dev
```

Open http://localhost:3000.

## Quality Checks

```bash
npm run lint
npm run test
npm run build
```

## Notes

- Current backend route files have syntax issues; frontend integration map is built from discovered route/schema intent.
- If backend path prefix changes (for example `/api`), update `NEXT_PUBLIC_API_BASE_URL` accordingly.
