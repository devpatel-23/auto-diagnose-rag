# Dockerfile
# -----------
# Builds a container image for the FastAPI backend.
# Used when deploying with Docker (not strictly needed for Render's native Python,
# but good practice and useful for other cloud providers).
#
# BUILD:   docker build -t vehicle-repair-chatbot .
# RUN:     docker run -p 8000:8000 --env-file .env vehicle-repair-chatbot
#
# MULTI-STAGE BUILD:
# Stage 1 (builder): Install dependencies into a virtual env
# Stage 2 (runtime): Copy only what's needed — smaller final image
# This reduces image size from ~1.2GB to ~350MB

# ── Stage 1: Builder ──────────────────────────────────────
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies needed to compile some Python packages
# (psycopg2, pgvector need libpq headers)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python dependencies
# We copy requirements.txt FIRST (before the app code) because:
# Docker caches layers — if requirements.txt hasn't changed,
# this entire layer is cached and pip install doesn't re-run.
# This makes rebuilds much faster.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install only runtime system deps (not build tools)
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY backend/ ./backend/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Create a non-root user for security
# Running as root in a container is a security risk
RUN useradd --create-home --shell /bin/bash appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port (documentation only — doesn't actually open the port)
EXPOSE 8000

# Health check — Docker will periodically call this
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/admin/health')"

# Default command
# PORT env var is injected by Render/Heroku
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
