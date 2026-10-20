#!/usr/bin/env bash
# Local live app. Starting the server does not start or resume comparisons.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export LCLAB_ENV_FILE="${1:-$ROOT/.env}"
export EXECUTION_MODE=live
export DATABASE_PATH="$ROOT/data/beginner-live.sqlite3"
export DEMO_DATABASE_PATH="$ROOT/data/beginner-demo.sqlite3"
export FREE_ONLY=true
PORT="${PORT:-18202}"
cd "$ROOT/frontend"
npm run build
cd "$ROOT/backend"
.venv/bin/python -c 'from app.config import load_settings; s = load_settings(); print("Provider keys configured:", {"OpenRouter": bool(s.openrouter_api_key.get_secret_value()), "OpenCode Zen": bool(s.opencode_zen_api_key.get_secret_value())})'
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.worker &
WORKER=$!
trap 'kill "$WORKER" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
