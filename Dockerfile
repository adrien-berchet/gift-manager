# syntax=docker/dockerfile:1
# Gift Manager Dockerfile
# Multi-stage build for optimized production image

# =============================================================================
# Base stage - Python dependencies
# =============================================================================
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# =============================================================================
# Builder stage - Install dependencies
# =============================================================================
FROM base AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies from the lockfile without installing the local package.
COPY pyproject.toml uv.lock ./
RUN pip install --upgrade pip && \
    pip install uv==0.10.7 && \
    uv export --quiet --frozen --no-dev --no-emit-project --format requirements.txt --output-file /tmp/requirements.txt && \
    pip install --require-hashes -r /tmp/requirements.txt

# =============================================================================
# Development stage
# =============================================================================
FROM base AS development

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install development dependencies
RUN pip install debugpy ipython

# Set development environment
ENV DJANGO_ENV=development \
    DEBUG=true

# Copy application code
COPY . .

# Expose ports (Django dev server + debugpy)
EXPOSE 8000 5678

# Run development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# =============================================================================
# Production stage
# =============================================================================
FROM base AS production

# Create non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set production environment
ENV DJANGO_ENV=production \
    DEBUG=false

# Copy application code
COPY --chown=appuser:appgroup . .

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R appuser:appgroup /app

# Static files are collected during deployment when production secrets are present.

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", \
     "--worker-class", "gthread", "--worker-tmp-dir", "/dev/shm", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "--capture-output", "--enable-stdio-inheritance", \
     "GiftManager.wsgi:app"]
