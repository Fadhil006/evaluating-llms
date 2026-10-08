# ChatGPT project context

This directory is a local mirror of the ChatGPT project “AI - Survey on Evaluating LLM”.

- Treat every file under `sources/` as read-only reference material.
- Do not edit, rename, move, or delete synced project files.
- These files may be replaced the next time a task is created from this ChatGPT project.

## Project instructions

This project has no custom instructions.

## Layout and current state

- The current LLM Comparison Lab is `frontend/` (React) plus `backend/` (FastAPI, SQLAlchemy, durable worker); it supports provider discovery/free-price enforcement, experiments, results, blinded review, exports and a synthetic demo mode. Root `app.py` and `evaluation/` are the preserved earlier Flask/CLI prototype; do not confuse its run data or protocol with the new app.
- `evaluation/` is the shared Python package: `dataset.py` validates versioned JSONL questions and paired paraphrases; `runner.py` freezes configs and dataset snapshots, dispatches fixtures or live requests, and persists responses; `scoring.py` applies per-item deterministic/proxy rules; `analysis.py` aggregates and exports results; `openrouter.py`, `opencode.py`, and `access.py` handle provider integration and access checks; `__main__.py` is the CLI (one live model per run).
- `datasets/v1.0/dev.jsonl` contains four development items; `datasets/v1.0/benchmark.jsonl` contains 24 held-out items (12 original/paraphrase pairs). Keep splits separate; do not tune rules using held-out outputs.
- `tests/` contains `unittest` coverage for the loader, scoring, runner, live/provider paths, analysis and app. Provider calls in tests are mocked. `pyproject.toml` declares Python 3.11+ and optional Flask UI dependency.
- `runs/`, databases, and `.env` are local ignored artifacts; never commit credentials or report synthetic scores as measured. New app experiment 4 completed 20/20 live responses on two OpenRouter price-verified free routes over ten original items; this is only a small convenience-sample smoke run, not broad performance evidence. Zen price-verified free routes are listed, but the server currently does not recognize `OPENCODE_ZEN_API_KEY`.
- `README.md` documents installation and usage; `protocol.md` describes actual evaluation rules and limitations. `project_overview.md` summarizes the survey. `plan.md`, `BUILD_PLAN.md` and `implementation_plan.md` contain proposed/historical scope, not proof of implemented features.
- `sources/ai_project.md` is the synced text of the 2024 survey *A Survey on Evaluation of Large Language Models*; `sources/figure-1.png` through `figure-3.png` are reference figures.
- This project draws on the survey's what/where/how dimensions, but does not implement its full scope or MT-Bench, Chatbot Arena, PandaLM, HELM, AlpacaEval, or LLM judging. `README.md` keeps clickable references; `protocol.md` distinguishes deterministic scoring from review-only proxies.

## Working conventions and verified commands

- Keep `sources/` read-only as specified above. Edit top-level Markdown only when asked; distinguish survey findings, proposals, synthetic fixture outputs, and actually measured model results. Use the survey as the primary reference for claims about its contents.
- Prefer small changes to the existing package and shared runner; do not duplicate evaluation logic in Flask and CLI. Validate question pairs before execution and preserve frozen run configs and append-only response/attempt logs. Never silently retry an unresolved live attempt or interpret a proxy/review outcome as objective correctness.
- The preserved root Flask/CLI prototype tests run with `.venv/bin/python -m unittest discover -s tests`. The current app backend checks run from `backend/` with `.venv/bin/python -m pytest -q` and `.venv/bin/ruff check app tests alembic scripts`; frontend checks run from `frontend/` with `npm run typecheck`, `npm run build`, and `npm run test:e2e`. Demo/browser tests use fixtures; live calls are separate and must be reported independently.
- Install the optional UI with `python -m pip install '.[ui]'` and start it locally with `python app.py`; open `http://127.0.0.1:8501` on the same machine. Live CLI requests require explicit `--live`, provider, model and key; do not run them as verification without explicit authorization and account checks.
- Graphify is optional tooling: run it only for a user-invoked `/init`, not routinely or via hooks/watchers. During this `/init`, `graphify extract . --code-only` was denied by the shell permission policy; no graph was built or verified.
