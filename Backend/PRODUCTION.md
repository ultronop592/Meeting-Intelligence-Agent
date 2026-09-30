# Production Readiness — Meeting Intelligence Agent Backend

## Concurrency Fixes Applied (Sep 2026)

This document summarises the production hardening changes made to support
100+ concurrent users without crashing or degraded performance.

---

## Fix 1 — DB Connection Pool (config.py / database.py)

| Setting | Before | After | Why |
|---|---|---|---|
| db_pool_size | 2 | 10 | Base slots for concurrent requests |
| db_max_overflow | 3 | 20 | Burst headroom -> 30 total max |
| db_pool_timeout | 30s (default) | 10s | Fail fast instead of queuing |

Neon Connection Limits:
- Free plan: ~20 direct connections (use PgBouncer pooler URL)
- Pro plan: ~100+ connections
- With WEB_CONCURRENCY=2 workers x 30 max connections = 60 total

---

## Fix 2 — Async bcrypt (core/auth.py + api/auth_routes.py)

bcrypt is CPU-bound (~100-200ms per call). Running it synchronously in an
async route handler blocks the entire asyncio event loop.

Before: verify_password() -> event loop stalls for each bcrypt call
After:  verify_password_async() -> bcrypt runs in thread pool executor

All three auth endpoints updated:
- POST /auth/register -> await hash_password_async()
- POST /auth/login   -> await verify_password_async()
- POST /auth/token   -> await verify_password_async()

---

## Fix 3 — Persistent Rate Limiting (core/limiter.py)

Before: In-memory storage -> counters reset on restart, isolated per worker
After:  Upstash Redis -> counters persist across restarts, shared across workers

Setup:
  UPSTASH_REDIS_REST_URL=https://<id>.upstash.io
  UPSTASH_REDIS_REST_TOKEN=<your-token>

Falls back to in-memory if env vars are not set (safe for local dev).

---

## Fix 4 — Multi-Worker Server (Dockerfile + requirements.txt)

Before: Single uvicorn process -> 1 CPU core, no isolation
After:  gunicorn + UvicornWorker -> multi-process, crash isolation, uvloop

WEB_CONCURRENCY=2 (default, override via env var on paid plans)

| Render Plan | RAM  | WEB_CONCURRENCY | Neon Connections |
|-------------|------|-----------------|------------------|
| Free        | 512M | 2               | 60               |
| Standard    | 2GB  | 4               | 120              |
| Pro         | 4GB  | 8               | 240              |

---

## Capacity Estimate (After All Fixes)

| Concurrent Users | Expected Behaviour                                      |
|------------------|---------------------------------------------------------|
| 1-50             | Fast (< 200ms per request)                              |
| 50-100           | Good (< 500ms, bcrypt queued in threads)               |
| 100-200          | Acceptable on paid Render plan (WEB_CONCURRENCY=4)     |
| 200+             | Needs horizontal scaling or dedicated server            |
