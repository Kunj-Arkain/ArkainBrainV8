FROM python:3.11-slim

WORKDIR /app

# System deps (including PostgreSQL client libs for psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps — install then freeze exact versions for reproducibility
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn && \
    pip freeze > /app/requirements.lock

# Copy project
COPY . .

# Create output directories + persistent data mount point
RUN mkdir -p output/recon data/regulations/us_states logs /data/output /data/logs

# Pre-create CrewAI config to prevent tracing prompt
RUN mkdir -p /root/.crewai /tmp/crewai_storage && \
    echo '{"tracing_enabled": false, "tracing_disabled": true}' > /root/.crewai/config.json && \
    echo '{"tracing_enabled": false, "tracing_disabled": true}' > /tmp/crewai_storage/config.json

# Railway sets PORT env var
EXPOSE ${PORT:-8080}

# Health check — Railway and Docker Compose use this to verify the app is alive
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/health')" || exit 1

# Run Flask via gunicorn
# 1 worker: parallelism comes from subprocess workers (worker.py), not gunicorn.
# 8 threads: handles concurrent HTTP requests + SSE log streams.
# --max-requests: recycles worker to prevent memory leaks. Sessions survive
#   because SECRET_KEY is persisted to file (not regenerated per-process).
# Subprocess pipeline workers survive gunicorn restarts (start_new_session=True).
CMD gunicorn web_app:app \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 1 \
    --threads 8 \
    --timeout 900 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 500 \
    --max-requests-jitter 50
