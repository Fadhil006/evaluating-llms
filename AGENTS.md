# ChatGPT project context

This directory is a local mirror of the ChatGPT project “AI - Survey on Evaluating LLM”.

- Treat every file under `sources/` as read-only reference material.
- Do not edit, rename, move, or delete synced project files.
- These files may be replaced the next time a task is created from this ChatGPT project.

## Project instructions

This project has no custom instructions.

## Layout and current state

- `app.py` is the Streamlit workbench for explicit two-model live comparisons, synthetic offline demonstrations, saved-run inspection and CSV downloads.
- `evaluation/` is the shared Python package: `dataset.py` validates versioned JSONL questions and paired paraphrases; `runner.py` freezes configs and dataset snapshots, dispatches fixtures or live requests, and persists responses; `scoring.py` applies per-item deterministic/proxy rules; `analysis.py` aggregates and exports results; `openrouter.py`, `opencode.py`, and `access.py` handle provider integration and access checks; `__main__.py` is the CLI (one live model per run).
- `datasets/v1.0/dev.jsonl` contains four development items; `datasets/v1.0/benchmark.jsonl` contains 24 held-out items (12 original/paraphrase pairs). Keep splits separate; do not tune rules using held-out outputs.
- `tests/` contains `unittest` coverage for the loader, scoring, runner, live/provider paths, analysis and app. Provider calls in tests are mocked. `pyproject.toml` declares Python 3.11+ and optional `streamlit` UI dependency.
- `runs/` and `.env` are local ignored artifacts; never commit credentials, run outputs, or synthetic scores as measured results. Existing local live attempts do not constitute verified successful live model measurements. **Measured results pending.**
- `README.md` documents installation and usage; `protocol.md` describes actual evaluation rules and limitations. `project_overview.md` summarizes the survey. `plan.md`, `BUILD_PLAN.md` and `implementation_plan.md` contain proposed/historical scope, not proof of implemented features.
- `sources/ai_project.md` is the synced text of the 2024 survey *A Survey on Evaluation of Large Language Models*; `sources/figure-1.png` through `figure-3.png` are reference figures.

## Working conventions and verified commands

- Keep `sources/` read-only as specified above. Edit top-level Markdown only when asked; distinguish survey findings, proposals, synthetic fixture outputs, and actually measured model results. Use the survey as the primary reference for claims about its contents.
- Prefer small changes to the existing package and shared runner; do not duplicate evaluation logic in Streamlit and CLI. Validate question pairs before execution and preserve frozen run configs and append-only response/attempt logs. Never silently retry an unresolved live attempt or interpret a proxy/review outcome as objective correctness.
- Run tests from the repository root with `python -m unittest discover -s tests` (verified: 82 tests passed, 14 optional UI tests skipped with system Python) or `.venv/bin/python -m unittest discover -s tests` (verified: all 82 passed with Streamlit installed). The stdlib CLI fixture invocation documented in `README.md` was exercised end-to-end on the dev dataset; it creates a synthetic run and CSV without network access.
- Install the optional UI with `python -m pip install '.[ui]'` and start it with `streamlit run app.py` when Streamlit is installed. Live CLI requests require explicit `--live`, provider, model and key; do not run them as verification without explicit authorization and account checks.
- Graphify is optional tooling: run it only for a user-invoked `/init`, not routinely or via hooks/watchers. During this `/init`, `graphify extract . --code-only` was denied by the shell permission policy; no graph was built or verified.
