# Implementation Notes

## Architecture

Frontend is implemented as a standalone Next.js App Router project in `frontend/` with TypeScript and Tailwind.

Structure:

- `frontend/app/`: route entrypoints (`/login`, `/workspace`)
- `frontend/components/`: reusable UI and workspace components
- `frontend/lib/api/`: centralized API client + endpoint modules
- `frontend/types/`: backend contract types
- `frontend/hooks/`: async state hooks and polling behavior
- `frontend/tests/`: API client + page flow tests (Vitest)

## Key Decisions

1. Backend-first API contracts from source code
- Backend files currently contain syntax inconsistencies, so runtime OpenAPI consumption was not reliable.
- Endpoint contracts were inferred directly from route decorators and schema models.

2. Centralized API client
- `apiRequest()` supports:
  - base URL from `NEXT_PUBLIC_API_BASE_URL`
  - optional bearer token injection from local storage
  - normalized `ApiError` with parsed backend payload
  - safe JSON parsing and typed responses

3. Claude-style UX
- Left: history sidebar
- Center: conversation/workspace pane with summary, action items, participants, and composer
- Right: insights panel (summary/action items/decisions)
- Light-first neutral palette, subtle borders/shadows, premium spacing

4. Async behavior
- No websocket/SSE routes found.
- Implemented long-job polling with exponential backoff:
  - initial interval: 1200ms
  - bounded retries and max delay
  - terminal states: completed/completed_with_errors/failed

5. Route guards
- Removed login/middleware guard for now based on latest product direction.
- Workspace is directly accessible until backend auth/session endpoints are added.
- API client still supports Authorization header injection to enable auth later without refactor.

6. Defensive handling
- Input validation for process and action item update via Zod.
- Defensive empty/loading/error/success states throughout workspace.
- Toast feedback for all key operations.

## Important Assumptions

- Upload + process flow requires constructing `audio_file_path` expected by backend process endpoint. Since upload response does not include full path, frontend uses `NEXT_PUBLIC_UPLOAD_DIR_HINT` to compose path.
- Backend import path casing and typing issues may need correction server-side before full runtime integration.

## Security Notes

- No secrets are hardcoded in frontend.
- `.env.example` added under `frontend/.env.example`.
- Existing backend `.env` appears to include sensitive values and should be rotated/removed from source control.
