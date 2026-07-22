# ═══════════════════════════════════════════════
# Stage 1: Builder — install dependencies
# ═══════════════════════════════════════════════
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ═══════════════════════════════════════════════
# Stage 2: Runtime — slim image with only runtime deps
# ═══════════════════════════════════════════════
FROM python:3.11-slim AS runtime

# Security: run as non-root
RUN groupadd -r pythonai && useradd -r -g pythonai -d /app -s /sbin/nologin pythonai

WORKDIR /app

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=pythonai:pythonai . .

# Create data directories with proper permissions
RUN mkdir -p /app/data /app/checkpoints /app/python_brain_godmode \
    && chown -R pythonai:pythonai /app

# Health check — hits the FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# Expose ports for FastAPI (8765) and Streamlit (8501)
EXPOSE 8765
EXPOSE 8501

# Switch to non-root user
USER pythonai

# Default command starts the API server via the CLI
CMD ["python", "-m", "src.cli", "serve", "--host", "0.0.0.0", "--port", "8765"]
