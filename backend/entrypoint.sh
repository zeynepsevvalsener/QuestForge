#!/usr/bin/env bash
set -e

# Apply database migrations, then start the API server.
# Migrations are real Alembic revisions (see alembic/versions/); the schema is
# never silently auto-created at runtime.
echo "Running database migrations (alembic upgrade head)..."
alembic upgrade head

# Honour the platform-provided $PORT (Railway/Render) and fall back to 8000.
PORT="${PORT:-8000}"
echo "Starting QuestForge API on :${PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
