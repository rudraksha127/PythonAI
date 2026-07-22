#!/usr/bin/env bash
# PythonAI — Unix Deployment Script
# Usage:  bash deploy.sh [setup|docker|help]

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"

show_help() {
    cat <<EOF
PythonAI Deployment Script

Usage:
  ./deploy.sh setup       # Create venv, install deps, init data
  ./deploy.sh docker      # Build and run with Docker Compose
  ./deploy.sh help        # Show this help
EOF
}

do_setup() {
    echo "=== PythonAI Setup ==="

    # Step 1: Create virtual environment
    if [ ! -d "$VENV" ]; then
        echo "[1/4] Creating virtual environment..."
        python3 -m venv "$VENV"
    else
        echo "[1/4] Virtual environment exists, skipping."
    fi

    PYTHON="$VENV/bin/python"
    PIP="$VENV/bin/pip"

    # Step 2: Install dependencies
    echo "[2/4] Installing dependencies..."
    "$PIP" install --upgrade pip
    "$PIP" install -r "$ROOT/requirements.txt"

    # Step 3: Verify
    echo "[3/4] Verifying installation..."
    "$PYTHON" -c "import torch; import transformers; import chromadb; import ollama; import sentence_transformers; print('All core imports OK')"

    # Step 4: Next steps
    echo "[4/4] Setup complete!"
    cat <<EOF

Next steps:
  1. Ensure Ollama is running:        ollama serve
  2. Pull the RAG model:              ollama pull qwen2.5-coder:14b
  3. Run the assistant:               $PYTHON -m src.rag.rag_engine
  4. Or use the CLI:                  $PYTHON -m src.cli status

Quick start:
  $PYTHON -m src.cli ask "Explain Python decorators"

Docker deployment:
  ./deploy.sh docker
EOF
}

do_docker() {
    echo "=== PythonAI Docker Deployment ==="

    if ! command -v docker &> /dev/null; then
        echo "Error: Docker is not installed." >&2
        exit 1
    fi

    echo "[1/3] Building Docker images..."
    docker compose build

    echo "[2/3] Starting services..."
    docker compose up -d

    echo "[3/3] Services started!"
    cat <<EOF

Services:
  - Ollama API:  http://localhost:11434
  - PythonAI:    docker compose exec pythonai python -m src.cli status
  - Web UI:      http://localhost:8501

Pull a model first:
  docker compose exec ollama ollama pull qwen2.5-coder:14b

Then ask a question:
  docker compose exec pythonai python -m src.cli ask "Explain Python decorators"

Open the Web UI in your browser:
  http://localhost:8501

Stop:
  docker compose down
EOF
}

# ─── Main ───
case "${1:-help}" in
    setup)  do_setup ;;
    docker) do_docker ;;
    *)      show_help ;;
esac
