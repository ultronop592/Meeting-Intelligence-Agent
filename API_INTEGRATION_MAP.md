# API Integration Map

This document maps every backend endpoint discovered in the workspace and how the frontend integrates each one.

## Discovery Scope

- Code inspected:
  - `Backend/api/main.py`
  - `Backend/api/routes.py`
  - `Backend/models/schemas.py`
- OpenAPI docs path in code: `/docs`, `/redoc` (only when not production).
- OpenAPI JSON path expected from FastAPI defaults: `/openapi.json`.
- Mapping below is based on route decorators and schema models and matches frontend client usage.

## Endpoint Contract Table

| Endpoint | Method | Request Schema | Response Schema | Auth Requirement | Error Shape | Frontend Integration |
|---|---|---|---|---|---|---|
| `/health` | GET | None | `HealthResponse` (`status`, `version`, optional `database`) | None found | Global: `{ detail, path }` on unhandled exception | `meetingApi.health()` in `frontend/lib/api/meetings.ts` |
| `/` | GET | None | `{ message, version, docs }` | None found | Global: `{ detail, path }` | Not needed in UI; omitted intentionally |
| `/meeting/upload` | POST | `multipart/form-data` with `file` | `{ filename, stored_filename, size_bytes, size_mb }` | None found | `HTTPException` 400 detail string for invalid type/size/empty file | `meetingApi.uploadAudio(file)` wired in composer upload flow |
| `/meetings/process` | POST | `ProcessMeetingRequest` (`audio_file_path`, `audio_filename`) | Start-processing payload with `job_id`, `status` | None found | `HTTPException` 400 if file missing | `meetingApi.processMeeting(payload)` starts job after upload |
| `/meetings/status/{job_id}` | GET | Path `job_id` | Job status: `status`, `completed_nodes`, `errors`, optional counts/meeting metadata | None found | `HTTPException` 404 `{ detail }` if unknown job | `meetingApi.getProcessingStatus(jobId)` in polling hook |
| `/meetings` | GET | Query: `limit`, `offset` | `MeetingListItem[]` | None found | Unhandled/global errors as above | `meetingApi.listMeetings()` in sidebar history |
| `/meetings/{meeting_id}` | GET | Path `meeting_id` | `MeetingDetailResponse` (`meeting`, `action_items`, `decisions`, `participants`, `notifications`) | None found | `HTTPException` 404 `{ detail }` | `meetingApi.getMeetingDetail(id)` for main/detail panels |
| `/meetings/{meeting_id}/action-items/{item_id}` | PATCH | `UpdateActionItemRequest` (`status: open|in_progress|done`) | `ActionItemRow` | None found | 404 not found, 403 ownership mismatch | `meetingApi.updateActionItem(...)` wired to status buttons |
| `/meetings/{meeting_id}` | DELETE | Path `meeting_id` | `{ deleted: true, meeting_id }` | None found | 404 not found | `meetingApi.deleteMeeting(id)` wired to Delete action |
| `/meetings/{meeting_id}/send/email` | POST | None | Tool result object (`sent`, `failed`, optional `message`) | None found | 404 meeting not found | `meetingApi.sendEmail(id)` wired in top actions |
| `/meetings/{meeting_id}/send/slack` | POST | None | Tool result object | None found | 404 meeting not found | `meetingApi.sendSlack(id)` wired in top actions |
| `/meetings/{meeting_id}/send/jira` | POST | None | Tool result object (`created`, `failed`, optional `message`) | None found | 404 meeting not found | `meetingApi.sendJira(id)` wired in top actions |
| `/meetings/{meeting_id}/send/calendar` | POST | Query optional `days_from_now` | Tool result object | None found | 404 meeting not found | `meetingApi.sendCalendar(id, days)` wired in top actions |
| `/meetings/{meeting_id}/participants/{participant_id}` | PATCH | Query `email` | `ParticipantRow` | None found | 404 participant, 403 ownership mismatch | `meetingApi.updateParticipantEmail(...)` wired in participants section |
| `/query` | POST | `AgentQueryRequest` (`question`, optional `meeting_id`) | `AgentQueryResponse` (`answer`, `sources`) | None found | 400 empty question, 404 meeting not found | `meetingApi.queryAgent(payload)` wired in `agent-chat` and meeting detail chat |

## Explicit Integration/Non-Integration Notes

- All discovered route-decorated endpoints are implemented in the frontend API client.
- No backend websocket/SSE endpoint was discovered.
- Long-running process updates are implemented via polling in `frontend/lib/hooks/use-job-status.ts`.
- Transcript retrieval endpoint was not discovered in backend routes; transcript display cannot be wired until such endpoint is added.
- Auth/session endpoints were not discovered in backend routes; UI route guards are deferred and can be enabled later.
