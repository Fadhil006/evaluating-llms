# LLM Comparison Lab

Local single-user workspace for designing, running, and inspecting small LLM comparisons. It provides OpenRouter discovery, strict free-only checks, versioned dataset import, a durable experiment queue/worker, task-specific scores, results, and blinded human review. This is an implementation inspired by Chang et al.'s LLM evaluation survey; it does not reproduce the paper or every benchmark it discusses.

## Prerequisites

Python 3.12+ and Node.js 24 LTS (tested locally with Python 3.14 and Node 26). SQLite is included with Python. Run commands from the indicated directory; keep the database on local disk.

## Start locally

From the repository root:

```bash
cp .env.example .env   # optional: defaults work without an .env file
```

The empty key placeholders are intentional. Put `OPENROUTER_API_KEY` and `OPENCODE_ZEN_API_KEY` in `.env` on the **server only**. Missing keys are a normal unavailable state. `FREE_ONLY=true` cannot be disabled. `EXECUTION_MODE=demo` uses a separate `data/demo.sqlite3` database, makes no provider calls, and serves only synthetic fixture models/answers. Demo results are not measurements of real models. Never put keys in `frontend/`, browser storage, or `VITE_` variables.

In terminal 1:

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]' -c requirements.lock
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In terminal 2:

```bash
cd frontend
npm ci
npm run dev
```

In a third terminal start the durable worker:

```bash
cd backend
EXECUTION_MODE=live .venv/bin/python -m app.worker
```

Open http://127.0.0.1:5173/. Check `/api/health` and `/api/settings` for safe status. Catalog refresh uses configured providers. For execution, select at least two exact routes with fresh verified zero-cost evidence and configured credentials; unknown, paid, stale, unsupported, unavailable, and unconfigured routes are blocked. Zen pricing uses a dated exact-ID official allowlist; the key must still be configured before Zen routes can run. No model is substituted automatically. If fewer than two eligible routes are available, keep the comparison as a draft.

For the offline fixture demo, stop the services and use the same startup commands with `EXECUTION_MODE=demo` in each terminal. Run migrations against the demo DB before starting. Refresh Models, install the original CC0 dataset, select the two DEMONSTRATION fixture routes, design the quick ten-item run, save it, then Start. The demo worker uses no provider keys/network. Change mode only when all three processes are stopped; mode-specific databases are separate. Migrations are explicit, never automatic on API startup.

Stop API, worker, and Vite with Ctrl+C.

## Docker Compose

With Docker Engine and the Compose plugin installed:

```bash
cp .env.example .env   # optional; add provider keys here only for live mode
docker compose up --build
```

Compose runs the migration once, then starts the API and separate worker with the same persistent named volume. The API is published only on `127.0.0.1:8000`; the worker is not published. The frontend production build is served by FastAPI. Open http://127.0.0.1:8000. `docker compose down` stops services but preserves the database volume. `docker compose down -v` permanently deletes that volume and all stored datasets/experiments—back up first.

For Compose demo mode without a `.env` file, run `EXECUTION_MODE=demo docker compose up --build`; the demo and live databases remain separate paths in the same volume.

## Verification and schema changes

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests alembic

cd ../frontend
npm ci
npm run typecheck
npm run build
npm run test:e2e
```

The browser test uses `/usr/bin/chromium` and starts an isolated demo API, worker, and Vite server; override `PYTHON` if the backend interpreter is elsewhere. It exercises catalog/dataset setup, a synthetic ten-item run, pause/resume/cancel, results, all export formats, a blinded vote, and assignment reload. It does not verify live provider calls.

Regenerate the conspicuously synthetic fixture report with `cd backend && .venv/bin/python scripts/generate_sample_report.py`; it writes `docs/sample-report.md` using a temporary SQLite database and no live provider calls.

The Python dependency pins are in `backend/requirements.lock` (pip-compile from `backend/pyproject.toml`); npm dependencies are in `frontend/package-lock.json`. Back up SQLite only after stopping API and worker, or use SQLite's backup API; include the WAL state in any consistent backup. Use Alembic revisions for schema changes.

## Current limits / unfinished release work

- Local, single-user only; no authentication or public deployment.
- Provider availability/pricing is dynamic. One saved 10-item live comparison (experiment 4) completed on two OpenRouter verified-free routes; it is a convenience-sample smoke test, not broad superiority evidence. OpenRouter quota reports may be unknown; application counters cannot see external key usage. Zen currently has free-price catalog entries, but no Zen key is recognized by this server, so it cannot execute Zen requests yet.
- Demo responses are synthetic and identical across fixture routes; they only verify workflow and data flow.
- Convenience dataset is 30 original items, not a validated benchmark or basis for broad superiority claims. Models/provider routes may change; retries can have unknown remote outcomes.
- Fairness/calibration and optional judge/robustness/uncertainty extensions are unfinished.
- Full release security audit and restore rehearsal, user-selectable fixture failure scenarios, live Zen execution, and human review/export of the saved live run remain incomplete. A generated synthetic sample report and a standard-library SQLite backup/restore test are included.

See `plan.md` and `docs/BUILD_STATUS.md` for phase status, exact verification and the Commander resume instructions.
