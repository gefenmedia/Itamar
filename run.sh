#!/usr/bin/env bash
# Rav Itamar — Quick Start Script
# No API keys needed. Uses Ollama (local LLM) + sentence-transformers (local embeddings).
# Usage: ./run.sh [--docker | --local | --test]

set -e

MODE="${1:---docker}"

case "$MODE" in
  --docker)
    echo "==> Starting Rav Itamar with Docker Compose..."
    echo "    No API keys required. Ollama runs locally."
    echo ""
    echo "    Services: PostgreSQL + pgvector, Ollama (llama3.2), App"
    echo "    First start will pull ~2GB Ollama model. Be patient."
    echo ""

    docker compose up --build -d
    echo ""
    echo "==> Rav Itamar is starting..."
    echo "    App:      http://localhost:8000"
    echo "    API docs: http://localhost:8000/docs"
    echo "    Ollama:   http://localhost:11434"
    echo ""
    echo "    Logs: docker compose logs -f app"
    echo "    Note: first request may be slow while Ollama loads the model."
    ;;

  --local)
    echo "==> Starting Rav Itamar locally..."
    echo "    Prerequisites:"
    echo "      - Python 3.12+"
    echo "      - PostgreSQL 16 with pgvector extension"
    echo "      - Ollama installed (https://ollama.ai)"
    echo ""

    # Check Ollama is running
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
      echo "ERROR: Ollama is not running at localhost:11434"
      echo "  Install: curl -fsSL https://ollama.ai/install.sh | sh"
      echo "  Start:   ollama serve"
      echo "  Pull:    ollama pull llama3.2"
      exit 1
    fi

    # Check model is available
    if ! curl -s http://localhost:11434/api/tags | grep -q "llama3.2"; then
      echo "==> Pulling llama3.2 model (first time only)..."
      ollama pull llama3.2
    fi

    # Check .env
    if [ ! -f backend/.env ]; then
      echo "Creating backend/.env from .env.example..."
      cp backend/.env.example backend/.env
    fi

    # Install deps
    echo "==> Installing Python dependencies..."
    pip install -r backend/requirements.txt

    # Create storage dir
    mkdir -p storage/pdfs

    # Start
    echo "==> Starting server..."
    cd backend
    PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ;;

  --test)
    echo "==> Running tests..."
    cd backend
    PYTHONPATH=. python -m pytest tests/test_unit.py -v
    echo ""
    echo "==> Unit tests complete."
    echo "    For acceptance tests (requires running server + DB + Ollama):"
    echo "    PYTHONPATH=. pytest tests/test_acceptance.py -v"
    ;;

  *)
    echo "Usage: ./run.sh [--docker | --local | --test]"
    echo ""
    echo "  --docker  Start with Docker Compose (default, recommended)"
    echo "  --local   Start locally (requires Python + Postgres + Ollama)"
    echo "  --test    Run unit tests"
    echo ""
    echo "No API keys required. Everything runs locally."
    exit 1
    ;;
esac
