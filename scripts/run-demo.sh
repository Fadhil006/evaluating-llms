#!/usr/bin/env bash
# Local synthetic demo only; never attaches to or resumes a live database.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export EXECUTION_MODE=demo
export DATABASE_PATH="$ROOT/data/live-unused.sqlite3"
export DEMO_DATABASE_PATH="$ROOT/data/beginner-demo.sqlite3"
export OPENROUTER_API_KEY=''
export OPENCODE_ZEN_API_KEY=''
export OPENCODE_API_KEY=''
export MANUAL_DAILY_ATTEMPT_CAP=10000 # Synthetic fixture throughput only.
PORT="${PORT:-18202}"
cd "$ROOT/frontend"
npm run build
cd "$ROOT/backend"
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.worker &
WORKER=$!
trap 'kill "$WORKER" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
