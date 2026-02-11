#!/usr/bin/env bash
# Rav Itamar — Quick Start Script
# Usage: ./run.sh [--docker | --local]

set -e

MODE="${1:---docker}"

case "$MODE" in
  --docker)
    echo "==> Starting Rav Itamar with Docker Compose..."
    echo "    Make sure OPENAI_API_KEY is set in your environment."
    echo ""

    if [ -z "$OPENAI_API_KEY" ]; then
      echo "ERROR: OPENAI_API_KEY is not set."
      echo "  export OPENAI_API_KEY=sk-your-key-here"
      exit 1
    fi

    docker compose up --build -d
    echo ""
    echo "==> Rav Itamar is running at http://localhost:8000"
    echo "    API docs at http://localhost:8000/docs"
    echo "    Logs: docker compose logs -f app"
    ;;

  --local)
    echo "==> Starting Rav Itamar locally..."
    echo "    Prerequisites: Python 3.12+, PostgreSQL 16 with pgvector"
    echo ""

    # Check .env
    if [ ! -f backend/.env ]; then
      echo "Creating backend/.env from .env.example..."
      cp backend/.env.example backend/.env
      echo "EDIT backend/.env with your OPENAI_API_KEY and database URL."
      exit 1
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
    echo "    For acceptance tests (requires running server + DB):"
    echo "    PYTHONPATH=. pytest tests/test_acceptance.py -v"
    ;;

  *)
    echo "Usage: ./run.sh [--docker | --local | --test]"
    echo ""
    echo "  --docker  Start with Docker Compose (default)"
    echo "  --local   Start locally (requires Python + Postgres)"
    echo "  --test    Run unit tests"
    exit 1
    ;;
esac
