# ============================================================================
# Grimoire — Backend Dockerfile
# ============================================================================
# Multi-stage build:
#   1) builder — installs Python deps + tree-sitter compilation toolchain
#   2) runtime — slim image with only the installed packages + app code
# ============================================================================

# ── Builder stage ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Build deps: gcc for native extensions (numpy, qdrant, tree-sitter, etc.)
# We don't need them at runtime, so we discard this layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into an isolated prefix so we can copy the whole tree
# into the runtime stage without dragging in pip caches or build artifacts.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime system deps:
#   libgomp1 — OpenMP for numpy/torch
#   curl     — used by HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages installed in the builder stage
COPY --from=builder /install /usr/local

# Pre-download the local embedding model so the first request doesn't pay
# a 60s cold-start penalty. Skip this if VOYAGE_API_KEY is set in production —
# it just means the model file sits unused (~90MB), which is fine.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Application code
COPY app/ ./app/
COPY verify_setup.py ./

# Build-time dependency check. Fails the build loudly if anything is
# missing from requirements.txt rather than discovering it at runtime
# when the user runs `docker compose up`.
RUN python verify_setup.py

# Non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app /home/appuser

USER appuser

# Persistent state directories (Qdrant DB, LangGraph checkpoints).
# These get mounted as volumes in docker-compose, so the data survives
# container restarts.
RUN mkdir -p /app/qdrant_data /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
