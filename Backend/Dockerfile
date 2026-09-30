# =============================================================================
# Meeting Intelligence Agent — Backend Dockerfile
# Production-grade container for FastAPI, LangGraph, and ReportLab services
# =============================================================================

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered streaming logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    # Number of uvicorn worker processes.
    # Free tier (512MB RAM): keep at 2 to stay within memory limits.
    # Paid tier (1GB+ RAM): set to 4 for better CPU utilisation.
    # Each worker runs its own DB connection pool, so:
    #   WEB_CONCURRENCY=2, pool_size=10, max_overflow=20 -> 60 total DB connections
    WEB_CONCURRENCY=2

# Install system dependencies:
# - ffmpeg: Required for audio chunking when files exceed Groq 25MB transcription limit
# - curl: Required for healthcheck probes
# - gcc, libpq-dev, python3-dev: Build dependencies for asyncpg and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create a dedicated non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Install Python dependencies first to leverage Docker layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy backend application source code
COPY api/ /app/api/
COPY agents/ /app/agents/
COPY core/ /app/core/
COPY db/ /app/db/
COPY graph/ /app/graph/
COPY models/ /app/models/
COPY tools/ /app/tools/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

# Create uploads directory and set permissions
RUN mkdir -p /tmp/meeting-agent-uploads && \
    chown -R appuser:appuser /app /tmp/meeting-agent-uploads

USER appuser

# Expose default HTTP port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Launch gunicorn with uvicorn workers for production-grade multi-process serving.
#
# --worker-class uvicorn.workers.UvicornWorker
#   Runs each gunicorn worker as a full asyncio + uvicorn process.
#
# --workers ${WEB_CONCURRENCY:-2}
#   Defaults to 2 workers (Render free tier). Override via WEB_CONCURRENCY env var.
#
# --worker-connections 100
#   Max simultaneous connections per worker (100 users / 2 workers = 50 each).
#
# --timeout 120
#   Worker timeout in seconds — long enough for audio upload + LLM processing.
#
# --loop uvloop
#   Drop-in faster event loop implementation (2-4x faster I/O than asyncio default).
CMD ["sh", "-c", \
    "exec gunicorn api.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers ${WEB_CONCURRENCY:-2} \
    --worker-connections 100 \
    --timeout 120 \
    --bind 0.0.0.0:${PORT:-8000} \
    --log-level info"]
