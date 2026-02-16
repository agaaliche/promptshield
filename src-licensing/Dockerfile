# PromptShield Licensing Server — Cloud Run container
FROM python:3.12-slim

# Prevent .pyc files and enable unbuffered stdout for Cloud Run logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps required by asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip install --no-cache-dir email-validator

# Copy application source
COPY main.py config.py database.py models.py schemas.py auth.py crypto.py ./
COPY routers/ ./routers/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Non-root user for security
RUN addgroup --system app && adduser --system --ingroup app app
USER app

# Cloud Run injects PORT (default 8080)
ENV PORT=8080

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

# Run with uvicorn; use shell form so $PORT is expanded at runtime
CMD uvicorn main:app --host 0.0.0.0 --port $PORT --log-level info
