# ==============================================================================
# Production Dockerfile for AI Code Review & Automated Test Generator
# ==============================================================================

FROM python:3.10-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    PORT=8000

WORKDIR ${APP_HOME}

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create a non-privileged system user for sandboxed security
RUN groupadd -g 10001 appuser && \
    useradd -u 10000 -g appuser -s /bin/bash -m appuser

# Copy source code and test files
COPY app/ ./app/
COPY tests/ ./tests/
COPY README.md .

# Transfer ownership to non-root user
RUN chown -R appuser:appuser ${APP_HOME}

# Switch to non-root execution user
USER appuser

EXPOSE 8000

# Docker healthcheck querying the /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch production ASGI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
