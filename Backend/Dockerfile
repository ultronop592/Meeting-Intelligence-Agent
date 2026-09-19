# =============================================================================
# Meeting Intelligence Agent — Backend Dockerfile
# Production-grade container for FastAPI, LangGraph, and ReportLab services
# =============================================================================

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered streaming logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

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

# Create uploads directory and set permissions
RUN mkdir -p /tmp/meeting-agent-uploads && \
    chown -R appuser:appuser /app /tmp/meeting-agent-uploads

USER appuser

# Expose default HTTP port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Launch uvicorn server respecting Render's dynamic $PORT
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
