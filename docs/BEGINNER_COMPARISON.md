# Beginner comparison workflow

## Edited checkout and preserved evidence

Implementation lives on branch `beginner-comparison` in `/home/fadhil/Projects/llm-comparison-beginner`. Development and initial verification used `/tmp/opencode/llm-comparison-beginner`; the committed branch was then checked out in the persistent location. The requested `/home/fadhil/Projects/evaluating_llms/evaluating_llms-2.0` is a symlink to the protected synced checkout. No synced source files, credentials, original database, `.arena/` content, or original `.env.example` edits were overwritten. This worktree starts from commit `f1d9ee3`.

The original server at `http://127.0.0.1:18201` was inspected, not restarted. Its process uses the original backend and a separate database at `/home/fadhil/Documents/Codex/2026-10-18/skill-creator-home-fadhil-codex-skills-3/work/web-validation/live-test.sqlite3`. On inspection, experiment 1 was paused for `rate_limit`: 0 successful, 1 failed, 19 pending; one consumed attempt. The earlier uncertain outcome has not been retried. Its account observation of 0/50 usage does not prove a model is available.

## Run the real local app (current instance)

The current server at **http://127.0.0.1:18202/experiments** is in **live mode**.
It reads the existing credential file without copying or exposing its values:

```bash
bash scripts/run-live.sh /home/fadhil/Projects/evaluating_llms/evaluating_llms-2.0/.env
```

Run this from `/home/fadhil/Projects/llm-comparison-beginner`. It uses the separate
`data/beginner-live.sqlite3` database and leaves the earlier server/database alone.
Starting the server does not start or resume a comparison. Empty catalogs load
automatically; selectors default to eligible choices, with unavailable choices
available through an explicit checkbox and explanatory details. At verification,
19 OpenRouter routes and 8 Zen routes were eligible; these counts can change.
Credential presence and catalog reachability do not prove generation success.

Use `SHOW_BROWSER=1 node scripts/verify-live-selection.mjs` from `frontend/` to
check real catalog selection and the review screen without creating, starting,
or resuming any comparison. This script blocks those mutation requests.

## Optional synthetic demonstration

The implementation worktree reuses the original installed backend virtual environment and frontend `node_modules` through ignored local symlinks. A fresh checkout instead needs the normal installation from the README (`backend/.venv`, backend dependencies, and `frontend/npm ci`). Do not copy a `.env` containing credentials into a browser directory.

From this worktree:

```bash
bash scripts/run-demo.sh
```

Open **http://127.0.0.1:18202/experiments**. The launcher builds the frontend, explicitly migrates only `data/beginner-demo.sqlite3`, runs the demo worker, and serves the app on localhost. It sets demo mode and clears all provider key environment variables. Port 18201 and the previous live database are not used. Stop with Ctrl+C; the demo database is retained. For a different local port: `PORT=18203 bash scripts/run-demo.sh`.

The launcher sets a 10,000-attempt daily ceiling for **synthetic fixtures only**, so repeated demonstrations do not consume the live worker's default daily budget. Each comparison still has its own absolute attempt cap.

This is a synthetic workflow demonstration, **not a real comparison of model ability**. The sample questions are authored convenience examples, not an established benchmark. Synthetic route latency is local fixture-processing time, not model speed.

## First comparison

1. **Choose questions.** Keep “Try sample questions” for a first run. Preview the questions. For your own questions, use the validated import path; retain version, source, license, split and family metadata. The default small sample selects up to ten questions using the local seed, not every question in a larger dataset.
2. **Choose models.** In live mode, filter by All providers, OpenRouter, or OpenCode Zen; search and choose Model A and Model B. Two routes from one provider or one from each are supported. Exact provider/route pairs must differ. Provider routing can affect results even for the same model name. Demo mode uses two clearly synthetic fixture routes instead.
3. **Review and start.** Check selected question count, repetitions, initial requests, possible retries and absolute attempt cap. Advanced controls are optional. A local seed selects/orders questions; it does not make hosted model answers deterministic. Verified-free pricing is dated evidence, not a permanent guarantee. Starting freezes configuration and dataset identity; the backend rechecks eligibility.
4. **Watch progress.** Completed answers and durable attempt logs are retained through pause/cancel. Pause stops new dispatches; active remote requests may finish. Resume continues remaining work, not the whole comparison. Uncertain remote outcomes require acknowledgement before a retry; a request may already have consumed provider quota.
5. **Compare answers.** Open the saved comparison, then Summary and Answers. Navigate matching question/repetition/variant groups. Hide names for a less identity-influenced view, or use the separate randomized human-review workflow. Inspect missing/failed/truncated answers separately from scored answers. Automatic checks have narrow definitions and explicit denominators; no single overall winner is claimed.
6. **Export.** Download CSV, JSON, HTML or Markdown. Exports retain provider/route identity, frozen configuration, provenance and durable attempts. CSV has additive metadata JSON columns; JSON is the most convenient machine-readable report.

## Live mode and provider setup

**Do not expose this app publicly or collect other users' API keys.** It remains local and single-user, without authentication or tenant-level authorization. A hosted bring-your-own-key product needs authenticated ownership enforcement on every API/export/worker job, HTTPS, secret-safe logging, short-lived or encrypted server-side credential storage, key deletion, per-user budgets/rate limits, provider endpoint allowlisting, and a tested privacy/retention policy. Encryption at rest cannot protect keys from a compromised running application. A synthetic-only public demo is a safer first deployment, but still needs abuse/resource controls. Adding an API-key textbox is not sufficient.

See [provider configuration](PROVIDER_CONFIGURATION.md) for canonical/legacy Zen key precedence, current official endpoint evidence, and pricing expiry. Configure server-side credentials and use a **separate live database**. Do not change an existing server's mode while it is running. Key presence is not authentication proof; quota may be unknown. Expired, missing or nonzero price evidence remains blocked by the backend.

Implementation verification does not authorize new live generation. Before any real test, approve the exact provider/route pair, request count, retries, attempt cap and current verified pricing. Do not automatically resume experiment 1.

## Optional AI judge

The [AI-judge design](AI_JUDGE_DESIGN.md) is a later opt-in extension, not a working control or dependency. It recommends separate judge route/credentials, explicit data-sharing and spend approval, a versioned rubric, hidden identities, both answer orders, ties/cannot-judge, retained reasons/raw output and separate scores. A ChatGPT/Codex subscription does not grant this app API access or permission to reuse a desktop session.

## Verification

From `backend/`:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests alembic scripts
```

From `frontend/`:

```bash
npm run typecheck
npm run build
npm run test:e2e
```

Browser tests start an isolated synthetic API/worker/database and Chromium. Provider-selection error cases use explicit browser mocks. None of these tests establish live authentication, real model quality or provider availability. Final execution results and screenshot paths are recorded in the delivery report.

For a visible desktop/mobile walkthrough against the local demo, run from `frontend/`:

```bash
SHOW_BROWSER=1 node scripts/verify-demo.mjs
```

It refuses non-demo mode, creates a synthetic 20-request comparison, checks paired answers, hides identities, downloads all four formats, checks browser errors and page width, and writes [desktop model selection](screenshots/model-selection-desktop.png), [mobile model selection](screenshots/model-selection-mobile.png), [desktop results](screenshots/results-desktop.png), and [mobile results](screenshots/results-mobile.png). Omit `SHOW_BROWSER=1` for headless verification. This uses installed Chromium through Playwright; no embedded in-app browser tool was available in the implementation session.
