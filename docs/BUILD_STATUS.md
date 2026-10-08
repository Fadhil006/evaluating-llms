# LLM Comparison Lab — Build Status

Last updated: 2026-10-08.

## Current state

- Stage: Phases 1, 3, 4, 5, 6 and P8.1–P8.5 pass local/fixture gates. Live catalog metadata verifies 19 OpenRouter and 10 Zen free-price routes. A separate 10-item/2-model OpenRouter run completed 20 responses; Zen credentials remain unconfigured. Phase 7 and full P8.6 review/export/security release verification remain open.
- Active package: core local/demo application delivered. Next work, if continuing, is optional P7.A robustness or release follow-up for P8.6.
- Initial inspected repository contained only `ai_project.md`, `plan.md` and this progress record.
- OpenRouter/Zen catalog metadata checks and bounded free-route runs were performed 2026-10-08. Price evidence allows 19 OpenRouter routes and 10 Zen free-price routes; only OpenRouter is credential-ready. One limited 10-item OpenRouter experiment completed; earlier individual route smoke requests failed. No broad performance claim is made.
- Live Models shows the 29 price-verified routes and warns when a route lacks credentials; the experiment selector shows only the 19 credential-ready OpenRouter routes. Paid/unknown/unsupported routes remain hidden.

## Required continuation routine

**Read `plan.md` and this file at every session start. Check the plan before each work package, after verification, and before advancing a phase.** Inspect current code and changes before editing. Update both records only from actual evidence.

For each package record:

```text
Package ID / date:
State: pending | in_progress | blocked | completed
Changed files:
Working behavior:
Verification commands and actual results:
Evidence type: fixture | local integration | browser | live
Limitations / blockers:
Next concrete action:
```

## Phase ledger

| Phase | Status | Evidence | Remaining gate |
|---|---|---|---|
| 1 — Foundation | Passed (local) | Fresh migration/restart/constraints, 4 tests, lint, frontend build, API and Chromium navigation smoke | None for Phase 1 |
| 2 — Providers | Pricing/discovery and a limited OpenRouter live run verified | Current catalog: 19 OpenRouter, 10 Zen free-price routes; 10-item/2-model OpenRouter run completed | Zen key not recognized; individual other free routes can be rate-limited or return invalid schemas |
| 3 — Datasets/design | Gate passed (P3.1–P3.5 at current scope) | 30 original items, import, saved IDs, estimates, form, start-time immutable config; integration tests | No Phase 3 blockers; execution/results belong to later phases |
| 4 — Runner | Local/fixture gate passed | Durable separate worker, latest evidence persisted at dispatch, budgets/retries/quota pause/recovery, progress controls and Playwright workflow | Live provider quotas/external key usage are inherently not fully observable; no live run |
| 5 — Metrics | Local gate passed | Versioned scorers, persisted/recoverable results, denominators, route latency/usage and reports | No broader statistical/generalization claims; optional uncertainty module is P7 |
| 6 — Results/review | Local/fixture browser gate passed | Dashboard, answer inspection, genuine identity-redacted review payload, route-attributed preferences and reload | Manual human-factors/accessibility audit beyond browser checks remains desirable |
| 7 — Extensions | Not implemented; disabled by default | None | Robustness pairs, item-cluster uncertainty intervals, optional LLM judging |
| 8 — Release | P8.1–P8.5 verified locally; P8.6 partial | Safe exports/docs/Compose; demo and one live 10-item run; backup/restore test | Live human review/export of the successful run, full security audit and optional extensions |

Entries below are chronological package notes. The latest final-verification entry supersedes earlier notes that say a router, UI, worker, or browser flow had not yet been integrated.

### P6.1/P6.2 frontend results and inspection / 2026-10-08

- State: **implemented; frontend typecheck and production build passed. P6.3–P6.5 and Phase 6 browser gate remain open.**
- Changed files: `frontend/src/ResultsPanel.tsx`, `frontend/src/Experiments.tsx`, `plan.md`, `docs/BUILD_STATUS.md`.
- Working behavior: non-draft results use Recharts `ResponsiveContainer`/`BarChart` with `accessibilityLayer` plus a metric table as a chart-independent source. Shows task metric quality and eligibility denominator, complete/scheduled, failure/pending/cancelled, truncated/malformed/identity mismatch, route median/p95 latency with sample count, nullable token totals and common-completed item/repetition/variant coverage. Filters aggregates by metric/model/task and response jobs by model/task/status through the paginated responses endpoint. Inspector shows same-key route responses, prompt/context/choices/references, plain-text response, status/error, normalized value and scorer explanation/denominators, missing/truncated/malformed states. Model identity is visible by design; latency is described as route measurement under run conditions, not intrinsic speed. Keyboard-native select/buttons and loading/empty/error states included.
- Verification (from `frontend/`): `npm run typecheck && npm run build` → **passed**. Vite reported the existing Node `module.register()` deprecation and a >500 kB bundle advisory. Evidence: static frontend checks only; no browser test or human review performed.
- Limitations: no P6.5 browser gate, no P6.3/P6.4 human review implementation, and no live provider execution. Dashboard quality table/chart are from stable aggregate results; those are fetched once progress is no longer queued/running (including partial paused/terminal results).
- Next concrete action: resolve P2/P4 backend gates and run the fixture-backed browser flow; implement P6.3 review protocol separately.

### P6.3/P6.4 blinded review backend / 2026-10-08

- State: **backend slice locally verified; Phase 6 gate remains open pending P6.5 browser flow**.
- Changed files: `backend/app/services/review.py`, `backend/app/api/review.py`, `backend/tests/test_review.py`, `plan.md`, `docs/BUILD_STATUS.md`. No ORM, migration, main app or frontend edits.
- Working behavior: server-generated opaque assignment IDs; persistence of randomized pair A/B response mapping; assignment JSON limited to opaque ID/mode/task text/answers and optional references; exact rubric v1 anchors are implemented in service definitions and scores allow null N/A or 1–5; rating/vote uniqueness failures return 409; comments are bounded; optional identity suspicion persists; summaries resolve votes through hidden response mappings and report rubric applicable counts, pair wins/losses/ties/cannot-judge, evaluator counts and sparse state. Evaluator labels are local labels and this API makes no authentication claim.
- Verification (from `backend/`): `.venv/bin/python -m pytest -q` → **68 passed**, one upstream Starlette/httpx deprecation warning; `.venv/bin/ruff check app tests alembic` → **All checks passed**. Tests use fresh migrated temporary SQLite; pair ordering is forced both ways; reload and full assignment JSON leakage checks pass. No browser flow or live provider execution.
- Limitations: parent must mount `app.api.review.router`; P6.5 browser/API/worker flow and accessibility checks remain. The existing schema has no dedicated identity-suspected vote column, so the flag is persisted in the assignment's private presentation JSON.
- Next concrete action: mount router in parent integration and run fixture-backed browser review/reload flow; Phase 6 gate stays open until then.

### P6.3/P6.4 Human Review frontend / 2026-10-08

- State: **implemented; frontend typecheck and production build passed. No browser verification claimed.**
- Changed files: `frontend/src/HumanReview.tsx`, `frontend/src/main.tsx`, `plan.md`, `docs/BUILD_STATUS.md`.
- Working behavior: `/human-review` creates pairwise/rubric assignments, reloads the active opaque assignment token from session storage, displays assignment content only, submits one vote/rating with 409 handling and repeat-submit protection, and fetches experiment aggregates. Evaluator-label and response self-identification limitations are explicit; pairwise summary omits model slot identifiers. Rubric uses backend v1 anchors and null N/A scores.
- Verification (from `frontend/`): `npm run typecheck` → **passed**; `npm run build` → **passed** (Vite emitted Node `module.register()` deprecation and >500 kB chunk advisory). Evidence: static frontend checks only; no browser run.
- Limitations: P6.5 browser keyboard/accessibility/API/worker flow remains unverified.
- Next concrete action: run the fixture-backed browser review/reload flow as part of P6.5.

## Decisions established by the plan

1. Initial session was planning-only; Phase 1 was implemented on 2026-10-07.
2. Local single-user application, backend-only keys, SQLite persistent queue and separate worker.
3. One global in-flight generation initially; short DB transactions and safe claim/lease fencing.
4. Free-only policy is mandatory; unknown or expired pricing blocks execution.
5. Explicit demo mode uses separate storage and unmistakable fixture provenance.
6. Started experiment configuration and dataset versions are immutable; change configuration by cloning.
7. No universal overall score; report per-task quality, coverage, failures and applicable success criteria.
8. Review identities remain server-side; local evaluator labels are not authenticated independent users.
9. Preserve the survey text; cite it as inspiration rather than claiming full reproduction.
10. Python dependencies are pinned in `backend/requirements.lock` via pip-compile; frontend uses npm's package lock. Local verification used Python 3.14 and Node 26; Python 3.12 and Node 24 LTS are documented targets, not independently tested here.
11. SQLite mode is selected by `EXECUTION_MODE` using distinct live/demo paths; schema migrations are explicit. Demo mode uses fixed synthetic fixture routes; live mode rejects fixture selection and dispatch.
12. Phase 1 schema records identities, provenance and constraints; application-level immutability, status transitions, pricing validation and review blinding belong to later packages. No provider credentials or discovery are persisted.

## Documentation research — not live verification

Planning consulted official documentation through Context7 and direct official-page retrieval:

- OpenRouter official docs (`/openrouterteam/docs`): model pricing, routing price ceilings, key/account schemas.
- https://openrouter.ai/docs/api/reference/limits
- OpenCode official docs (`/anomalyco/opencode`) and https://opencode.ai/docs/zen/

Important implementation checkpoints: account free-request counters may be absent and must remain unknown; Zen models use different endpoint families; pricing and promotional free offers must be rechecked at implementation/execution time. No specific model is declared currently available or eligible by this planning work.

## Verification ledger

### Backend demo fixture execution / 2026-10-08

- State: **backend vertical slice implemented and locally verified; P8.3 and end-to-end demo gates remain open.**
- Changed files: `backend/app/providers/{fixture,catalog,dispatch,common}.py`, `backend/app/main.py`, `backend/app/services/experiment_lifecycle.py`, `backend/app/models.py`, `backend/app/worker/{runner,__main__}.py`, `backend/app/api/experiments.py`, `backend/alembic/versions/4c9f83a1b2d0_response_provenance.py`, `backend/tests/{test_demo_fixture,test_providers,test_worker}.py`, `plan.md`, `docs/BUILD_STATUS.md`. No frontend or export files changed.
- Working behavior: explicit demo-mode model refresh persists only two `DEMONSTRATION`-labeled synthetic routes under `fixture`; it does not construct HTTPX during refresh or invoke live adapters. The existing built-in CC0 dataset remains separate. Start requires a demo-mode experiment and exact fixture route/evidence; claim checks worker execution mode and synthetic snapshot; central dispatch repeats exact route/evidence and request-provenance checks. Demo worker selects only `Fixture`, skips spacing delay, and accepts/persists responses only with synthetic provenance. Live start rejects fixture models; real-provider eligibility still uses unchanged strict free-only policy. Ten dataset items and two fixture models produce 20 jobs.
- Verification (from `backend/`): `.venv/bin/python -m pytest -q` → **70 passed**, one upstream Starlette/httpx deprecation warning; `.venv/bin/ruff check app tests alembic` → **All checks passed**; fresh `DATABASE_PATH=/tmp/opencode/demo-fixture-check.sqlite3 DEMO_DATABASE_PATH=/tmp/opencode/demo-fixture-demo.sqlite3 .venv/bin/alembic upgrade head && ... alembic check` → **No new upgrade operations detected**. Fixture integration uses temporary migrated SQLite and asserts HTTPX is not invoked during demo refresh; no live provider request occurred.
- Limitations: no frontend banner/UX, exports/reports, wrong-answer/malformed/quota/missing-usage/recovery scenario set, browser workflow, or packaged release proof. Backend tests prove fixture-run completion and persisted provenance only. No actual live free route verification is claimed.
- Next concrete action: complete the remaining P8.3 demo presentation/scenarios and browser/API/separate-worker gate when frontend scope is authorized.

### P4.2–P4.6 worker slice / 2026-10-07

- State: **P4.2 locally verified; P4.3–P4.6 partial; Phase 2 and Phase 4 gates open**.
- Changed files: `backend/app/worker/{__init__,__main__,runner}.py`, `backend/app/api/worker.py`, `backend/app/providers/common.py`, `backend/tests/test_worker.py`, `plan.md`, `docs/BUILD_STATUS.md`. No migration, main router, existing lifecycle API or ORM edits.
- Working behavior: separately runnable polling worker (`python -m app.worker`), SQLite `BEGIN IMMEDIATE` reservation/CAS and global lease; UTC account manual cap (env `MANUAL_DAILY_ATTEMPT_CAP`, default 40), experiment lifetime cap, per-job retries, conservative unsent recovery and unknown dispatched expiry, token-fenced response/attempt save, scoring invocation, safe normalized HTTP errors and parsed Retry-After, independent progress router. Dispatch invokes `app.providers.dispatch.dispatch`, which checks the latest persisted price and adapter guard. No demo models are seeded into live catalog.
- Verification from `backend/`: `.venv/bin/python -m pytest -q` → **62 passed**, one Starlette/httpx deprecation warning; `.venv/bin/ruff check app tests alembic` → **All checks passed**; fresh `DATABASE_PATH=/tmp/opencode/p42-worker-check.sqlite3 .venv/bin/alembic upgrade head && DATABASE_PATH=/tmp/opencode/p42-worker-check.sqlite3 .venv/bin/alembic check` → **No new upgrade operations detected**. Tests use synthetic adapter responses/temporary migrated SQLite and include two real child processes for crash/recovery; no authenticated provider calls.
- Limits: the snapshot recorded in an attempt can differ from the later snapshot re-read inside central dispatch if catalog refresh races; Phase 2 gate stays open. Per-experiment `timeout_seconds` is not passed to adapter HTTPX requests (worker CLI uses global timeout). No persisted heartbeat, UI progress controls, browser flow or full concurrent shared-account/HTTP error matrix. No authoritative free-account quota history can be stored in current `ProviderAccountState` (only observation time/source and application day/count); provider-reported quota reconciliation needs additional fields or a separate observation record. Zen remains blocked by pricing policy. P4.6 operational gate is incomplete despite the passing subprocess recovery test.
- Mount integration in parent app: `from app.api import results, worker` then `app.include_router(results.router); app.include_router(worker.router)` (inside `create_app`, after existing routers). Parent owns browser controls/worker process deployment.
- Next: close evidence race and request deadline; expand tests/UI integration before claiming P4/P2 gates.

### P4.5 frontend lifecycle/progress/results / 2026-10-08

- State: **implemented; requested frontend static checks passed. P4 and browser gates remain open.**
- Changed files: `frontend/src/Experiments.tsx`, `docs/BUILD_STATUS.md`.
- Working behavior: saved drafts expose Start; queued/running experiments expose Pause/Cancel and poll progress approximately every two seconds; paused/interrupted experiments expose Resume/Cancel. Resume asks for confirmation before sending `acknowledge_uncertain=true`. Progress includes completed, failed, pending, in-flight, cancelled, consumed/remaining attempts and pause reason. Non-draft saved runs reload their progress; terminal/paused snapshots load partial results. Results show task/metric summaries, quality and scheduled denominators, coverage/failures/pending/cancelled counts, overall-success denominator and common-completed counts. Lifecycle/progress/results errors (including 409 responses) are shown as text and cleared on the next lifecycle attempt. Readiness is labeled advisory, with start authority left to backend.
- Verification (from `frontend/`): `npm run typecheck && npm run build` → **passed** (Vite 7.3.7; Node `module.register()` deprecation warning). Evidence type: frontend static build only.
- Limitations: no browser test or live/provider execution; this does not claim the full P4 acceptance gate or P6 browser gate. Backend evidence race/deadline/matrix items remain open.
- Next concrete action: resolve backend dispatch-evidence race and request deadline; exercise the full workflow with a separate worker and fixture-backed browser test.

### P5.3/P5.4 backend-only / 2026-10-07

- State: **completed in isolation; phase gate remains open pending review**.
- Changed files: `backend/app/services/results.py`, `backend/app/api/results.py`, `backend/tests/test_results.py`, `plan.md`, `docs/BUILD_STATUS.md`. No schema changes.
- Working behavior: scoring saved responses into unique versioned metric rows, rescoring after version changes without mutating answers or attempts, recovery on result/detail reads, `length` truncation, missing-reference nulls, scheduled-job denominators, operational/parse/identity counts, conditional quality and declared binary overall success, classification macro F1, per-model common eligible item/repetition/variant intersections and response-level explanations. Results router is standalone and not mounted by `main.py`.
- Verification (from `backend/`): `.venv/bin/python -m pytest -q` → **52 passed**, one upstream Starlette/httpx deprecation warning; `.venv/bin/ruff check app tests alembic` → **All checks passed**. Evidence: synthetic fixtures against freshly Alembic-migrated temporary SQLite; no live generation.
- Limitations: Phase 4 worker does not exist yet and must invoke `score_response` after saving a response; currently reading either new results endpoint repairs missing scores. Parent must mount `app.api.results.router`. Bad scoring declarations remain unscored and can be retried after correction; no LLM judging or composite metric. Phase 5 gate needs independent review.
- Next concrete action: parent review and mount router; wire worker persistence into scoring when Phase 4 dispatch lands.

### Current integration check / 2026-10-07

- Mounted `/api/datasets` and `/api/experiments` routers in the parent FastAPI app and exposed `execution_mode` to draft persistence.
- Added `/api/datasets/built-in` to install/reuse the original CC0 demo dataset; added version numeric IDs to dataset listing so selected labels resolve to the exact DB version.
- Added `backend/app/providers/dispatch.py`: current persisted exact-route snapshot resolver rejects undiscovered, stale, unsupported, paid, and unconfigured routes before adapter HTTP dispatch; provider adapter repeats pricing validation immediately before the request.
- Frontend Models, Datasets and Experiments pages are integrated. Experiment form supports selected route snapshots, dataset/version, 10-item quick subset or explicit IDs, shared settings, retries/cap estimate and draft creation. It intentionally has no run button until lifecycle/worker UI exists.
- Verification (backend): `cd backend && .venv/bin/python -m pytest -q` → **35 passed**, one upstream Starlette/httpx deprecation warning; `ruff check app tests alembic` → passed; fresh SQLite `alembic upgrade head && alembic check` → no new upgrade operations. New assertions cover latest paid snapshot blocking dispatch, integrated routers and built-in dataset idempotency/30 rows.
- Verification (frontend): `cd frontend && npm run typecheck && npm run build` → passed; Node `module.register()` deprecation warning only. No browser test yet.
- Evidence in this historical P3.4 record is local/static only; it is superseded by P4 start/worker verification and the final integration record below.

### Final local/demo verification and Phase 8 / 2026-10-08

- Integrated current state: FastAPI mounts dataset, experiment, worker progress, results, review, and export routes. `app.state.export_redactions` keeps configured key values private to the process and passes only exact strings to export redaction; no settings export exists.
- Backend export builder uses an explicit report schema for experiment config/hash, model/dataset provenance, selected items, start/finish dates, attempts, responses, scores, aggregates and human feedback. CSV protects formula-leading values, HTML escapes content, Markdown uses dynamic code fences, JSON redacts configured keys. Downloads are available from each experiment results panel.
- `backend/scripts/generate_sample_report.py` generated `docs/sample-report.md` from an isolated temporary demo DB with 30 original items, two synthetic fixture routes, 10 sampled items, and **20 synthetic generation jobs**. The report is prominently labeled demonstration data and asserts no live model result.
- Local Docker Compose demo verification (project `llm-lab-compose-check`): optional `.env`/environment-selected demo mode; migration service, API and separate worker started; loopback port binding; fixture catalog refreshed without provider calls; CC0 dataset installed; 20-job fixture run completed; JSON export contained demo provenance; completed experiment and results survived API restart and Compose down/up on the named volume. Services were stopped. Compose build/config and `Dockerfile` build check passed. A standard-library SQLite backup/restore test also preserved a completed experiment and response. A temporary named test volume may remain, isolated from the default Compose project volume.
- Browser suite: `cd frontend && npm run test:e2e` → **1 passed**. It drives Chromium through fixture catalog/dataset setup, ten-item design and run with two routes, dashboard/answers, exports in all four formats, blinded vote payload redaction, assignment reload, summary, plus a separate large run's pause/resume/cancel controls. The E2E stack starts a migrated temporary demo DB, separate FastAPI and worker processes, and Vite. No live provider call.
- Final backend verification: `cd backend && .venv/bin/python -m pytest -q` → **81 passed**, one upstream Starlette/httpx deprecation warning; `.venv/bin/ruff check app tests alembic scripts` → passed; fresh Alembic upgrade/check → no drift. `docs/sample-report.md` generation and script lint passed.
- Final frontend verification: `npm run typecheck`, `npm run build`, `npm run test:e2e`, `npm audit --audit-level=high` → passed; **0 npm vulnerabilities**. Build still warns about a >500 kB minified JS chunk and Node `module.register()` deprecation.
- Provider documentation rechecked 2026-10-08 in `docs/PROVIDER_NOTES.md`; live OpenRouter account/catalog and Zen public model catalog metadata were observed. No live comparison succeeded. Zen execution remains blocked until the server recognizes `OPENCODE_ZEN_API_KEY`; OpenRouter smoke routes returned 429/invalid-response errors. These are operational tests, not benchmark results.
- Superseded by the live run below: the successful OpenRouter smoke was a small convenience-sample check only, not a research claim.
- Remaining scope: P7 robustness/cluster bootstrap/judge extensions are unimplemented. P8.6 live human review/export and full release security review remain open. Demo fixture routes intentionally return identical synthetic strings.

### Live OpenRouter metadata check / 2026-10-08

- Evidence type: authenticated metadata only. Safe API settings showed `openrouter=true`, `opencode_zen=false` (booleans only). `POST /api/providers/openrouter/check` succeeded and reported free daily requests 0/50 at `2026-10-08T07:32:43Z`. `POST /api/models/refresh` returned 467 OpenRouter models; Zen returned `unconfigured` without a request.
- Eligibility result: 0/467 currently allowed for generation. 16 `:free`-suffixed IDs were present, but their observed pricing had only prompt/completion at zero; required request/cache/reasoning fields were missing and remain unknown. No generation request, experiment, paid route, or fallback was used.
- The API, worker, and frontend remain running in live mode. `.env` is ignored by Git and set to mode 0600; no push was performed. The Zen key must be configured if that gateway should be checked.

### Successful limited OpenRouter run / 2026-10-08

- Verified via API: experiment 4 reached `completed`, 20/20 jobs completed, 0 failed, and 20 attempts consumed. It used one original multiple-choice/other item sample of 10 questions, one repetition, zero retries, two exact OpenRouter free model IDs, and an attempt cap of 40. This is an actual live run; no paid/fallback model was used.
- Provider metadata after the run reported OpenRouter 22/50 free requests used. Experiment-specific dataset settings, model IDs, metrics, operational failures and responses are available in the live app's experiment 4; export/review of this live run has not been performed.
- The run is too small and narrow to support general superiority claims. It contained an instruction-following format failure and a truncated response. Earlier individual route tests (experiments 1–3) remain saved with their HTTP 429/invalid-response/403 outcomes and were not retried.
- Live model page verified 29 price entries (19 OpenRouter with keys, 10 Zen without keys); the experiment selector presents 19 credential-ready routes. Zen `big-pickle` returned 403 unauthenticated, so Zen routes remain price-listed but non-selectable until a valid Zen key is loaded. No further generations were sent.

### P4.1 and P5.1/P5.2 / 2026-10-07

- P4.1 changed `backend/app/services/experiment_lifecycle.py`, `backend/app/api/experiments.py`, `backend/tests/test_experiments.py`. Start validates the saved draft, reloads latest model evidence, blocks stale/unknown/paid/unavailable routes and incompatible settings, freezes hash/provenance/evidence, seeds interleaved unique jobs and queues atomically. Pause/resume/cancel transitions are persisted; resume revalidates and requires uncertain-work acknowledgement. No network dispatch exists yet.
- P5.1/P5.2 added `backend/app/evaluation/scoring.py` and `backend/tests/test_scoring.py`: versioned registry for supported task metrics with parse/explanation/raw values and explicit missing/truncated/malformed/unparseable states. Hand examples cover all task metrics and original dataset references/configs.
- Verification: `cd backend && .venv/bin/python -m pytest -q` → **48 passed**, one upstream Starlette/httpx deprecation warning; `.venv/bin/ruff check app tests alembic` → passed; fresh SQLite migration/check → no new operations. Evidence is synthetic/temporary local DB only.
- Limitation: no worker or persisted per-attempt price evidence yet, so Phase 2 end-to-end and Phase 4 gates remain open. Scorer results are not yet persisted or aggregated; Phase 5 gate remains open.

### P3.4 frontend / 2026-10-07

- State: **completed (frontend static verification); Phase 3 gate remains open**.
- Changed files: `frontend/src/Datasets.tsx`, `frontend/src/Experiments.tsx`, `frontend/src/main.tsx`, `plan.md`, `docs/BUILD_STATUS.md`.
- Working behavior: dataset list/version inventory, idempotent built-in install, raw CSV/JSONL preview and save with row-field errors and duplicate-content acknowledgment; experiment draft form with exact catalog routes and backend eligibility reasons, version item browsing, quick/explicit IDs, shared settings, backend estimate with separate generation/retry/metadata counts and readiness advisory, and saved draft list. Parent app already includes both API routers. No live start control.
- Verification (from `frontend/`): `npm run typecheck && npm run build` → **passed** (Vite 7.3.7; Node `module.register()` deprecation warning). Evidence type: frontend static build only; no browser or live provider verification in this package.
- Limitations: dataset detail/list API lacks numeric `dataset_version_id` required by experiment POST; user must enter it manually, and the UI cannot verify that ID matches the selected dataset/version label. Backend validates item membership for the supplied ID. Backend advisory readiness is not a live-start authorization. Start-time freeze remains P3.5/P4; Phase 3 gate pending.
- Next concrete action: expose version ID in backend dataset API when backend edits are in scope; complete P3.5/P4 start-time checks, then run an integrated browser flow.

### P3.4–P3.5 backend-only / 2026-10-07

- State: **verified in isolation, packages remain open**. Backend API exists but parent application does not include its router; frontend form and start-time immutable freeze are outside this slice.
- Changed files: `backend/app/api/experiments.py`, `backend/app/services/experiments.py`, `backend/tests/test_experiments.py`, `plan.md`, `docs/BUILD_STATUS.md`. No migration.
- Working behavior: standalone `POST /api/experiments/estimate`, `POST /api/experiments`, `GET /api/experiments`, `GET /api/experiments/{id}`, `PUT /api/experiments/{id}` and `POST /api/experiments/{id}/clone`. Shared validation checks dataset membership, distinct provider/model routes, shared max_tokens/optional temperature, bounded settings, conservative context estimate, and initial attempt cap. Null item_ids deterministically selects ten in source order; explicit IDs retain caller order. Draft stores ordered IDs, category counts, dataset content hash, selected snapshot IDs and exact route identities, settings, canonical draft hash, advisory policy decisions and metadata-separated request estimate. Blocked pricing still permits drafts; non-draft updates return 409. Generation messages/references/scoring are not persisted in config. Local seed controls sampling only, not provider generation seed.
- Verification (from `backend/`): `.venv/bin/python -m pytest -q` → **34 passed**, one upstream TestClient deprecation warning; `.venv/bin/ruff check app tests alembic` → **All checks passed**. Evidence: local tests with temporary Alembic-migrated SQLite and direct router import; no live requests.
- Limitations: router must be included by parent; demo provenance requires parent to set `app.state.execution_mode` (standalone defaults to live). Stored eligibility/readiness is advisory as of draft creation or edit; start/resume must refresh pricing and freeze configuration in P4. Context estimate is approximate, not tokenization. P3.4 frontend form and P3.5 immutable-at-start contract remain open.
- Next concrete action: include router from parent when allowed, build form, then implement P4 start validation/freezing; keep Phase 2 and Phase 3 gates open.

### P3.3 / 2026-10-07

- State: **completed in isolation**; Phase 3 gate remains open pending P3.4–P3.5.
- Changed files: `backend/app/services/experiment_design.py`, `backend/tests/test_experiment_design.py`, `plan.md`, `docs/BUILD_STATUS.md`.
- Working behavior: seeded category-balanced selection of up to ten items returns ordered item IDs and counts, redistributes scarce-category slots; messages include only shared system instruction, item prompt/context/choices and separately supplied public task schema. Pure request estimate separates initial work, retry allowance, capped maximum and metadata startup/refresh counts. Shared-setting helper requires distinct gateway/model routes and checks requested parameters.
- Verification (backend): `.venv/bin/python -m pytest -q` → **32 passed**, one upstream TestClient warning; `.venv/bin/ruff check app tests alembic` → **All checks passed**. Evidence: local unit tests and existing synthetic/integration suite; no live generation.
- Limitations: utilities are not wired to experiment persistence or API; P3.4–P3.5 must store selected IDs and validate configuration at start. Phase 3 gate remains open.
- Next concrete action: implement P3.4 experiment form and estimate endpoint; keep Phase 2 and Phase 3 gates open.

### P3.2 / 2026-10-07

- State: **completed in isolation**; Phase 3 acceptance gate remains open pending P3.3–P3.5.
- Changed files: `backend/app/services/datasets.py`, `backend/app/api/datasets.py`, `backend/tests/test_datasets.py`, `plan.md`, `docs/BUILD_STATUS.md`.
- Working behavior: standalone `/api/datasets` router with raw UTF-8 CSV or JSONL preview and atomic save, listing and version detail; bounded 5 MiB/5000 rows, task/scorer declaration validation, row-field errors, duplicate ID rejection and normalized-content acknowledgment flag, stable sorted canonical SHA-256 and version manifest/inventory, unknown item/dataset source/license. CSV JSON-cell examples in router docstring and integration test. No imported evaluation metadata is sent to providers by this code.
- Verification (backend): `.venv/bin/python -m pytest -q` → **25 passed**, one upstream TestClient warning; `.venv/bin/ruff check app tests alembic` → **All checks passed**. Evidence: synthetic fixture, migrated temporary SQLite integration; original 30-row dataset parsed. No live or parent-app route verification; parent must include `app.api.datasets.router` after integration. No schema migration required.
- Limitations: only declared scoring-config shapes are validated; P5 must implement and verify the actual scorers. Inline JSON schema is intentionally restricted to flat primitive object properties. CSV uses raw `text/csv` and JSONL `application/x-ndjson` bodies with query metadata rather than multipart. No provider/generation path was changed; P3.3 must keep reference/scorer fields out of request messages. Concurrent conflicting version writes rely on the existing DB uniqueness constraint and rollback.
- Next concrete action: integrate router from parent when permitted, implement P3.3; keep Phase 2 and Phase 3 gates open.

### P3.1 / 2026-10-07

- State: **completed** (dataset artifact only; Phase 3 gate remains open).
- Changed files: `datasets/original_demo_v1.jsonl`, `plan.md`, `docs/BUILD_STATUS.md`.
- Working behavior: 30 newly authored fictional items, five per planned category, with unique IDs, task-specific references and scoring metadata, per-item original attribution and CC0-1.0 licensing. This is a source artifact, not an imported dataset or a running scorer.
- Verification command and result (local artifact): `python -c '...'` parsed every JSONL row; checked 30 unique IDs and five per category, required fields, per-item attribution/license, choice labels, numeric answer calculations, factual and extraction references, inline extraction schemas and task-specific scoring configuration shapes → **passed**. Reviewed the five summary references against their contexts and instruction checks against their requested output.
- Limitations: backend importer, scorer allowlist/implementation, stable normalized version hash and execution are pending P3.2/P5; scoring metadata is a declarative proposal until those contracts exist. No provider or browser verification performed.
- Next concrete action: resume P2.1 per the phase sequence; implement P3.2 when Phase 3 work resumes.

### Planning

- Inspected the initial repository directory and survey passages on the what/where/how framework, automatic metrics and human evaluation.
- Drafted phase packages, entity/API contracts, worker semantics, scoring denominators, blinding requirements and release gates in `plan.md`.
- Read back the progress record and checked the written plan's phase/package headings against all eight requested phases. Reviewed cross-phase dependencies; fixture execution begins in Phase 2 so browser verification does not depend on Phase 8 packaging. Clarified that local seeds do not guarantee deterministic remote inference.
- Application verification: **not run — application does not yet exist**.
- Live verification: **not performed**. Credential availability has not been inspected and is not assumed.

### P1.1–P1.4 / 2026-10-07

- State: **completed** (local foundation gate).
- Changed files: `.gitignore`, `.env.example`, `README.md`, `plan.md`, `docs/BUILD_STATUS.md`; `backend/pyproject.toml`, `backend/requirements.lock`, `backend/app/{__init__,config,db,main,models}.py`, `backend/alembic.ini`, `backend/alembic/{env.py,script.py.mako,versions/d43689520030_foundation.py}`, `backend/tests/test_foundation.py`; `frontend/{package.json,package-lock.json,index.html,tsconfig.json,vite.config.ts,src/main.tsx,src/style.css}`.
- Working behavior: local-only FastAPI `/api/health` and safe `/api/settings`; env validation and separate SQLite paths; synchronous session scope and initial migration for planned core entities; React navigation with honest unimplemented pages, backend availability, read-only settings and demo-mode label.
- Verification commands and outcomes (local integration, browser smoke; no live or fixture generation):
  - `cd backend && .venv/bin/python -m pytest -q` → **4 passed**, one upstream TestClient deprecation warning. Tests migrate fresh temporary SQLite, restart without data loss, reject duplicate jobs, missing items/model slots, test settings/host/secrets and invalid startup logs.
  - `cd backend && .venv/bin/ruff check app tests alembic` → **All checks passed**.
  - `cd backend && DATABASE_PATH=/tmp/opencode/p1-smoke-v2.sqlite3 .venv/bin/alembic upgrade head && DATABASE_PATH=/tmp/opencode/p1-smoke-v2.sqlite3 .venv/bin/alembic check` → upgrade succeeded; **No new upgrade operations detected**.
  - `cd frontend && npm ci && npm run typecheck && npm run build` → all passed (Vite 7.3.7); `npm audit --audit-level=high` → 0 vulnerabilities.
  - Started `uvicorn app.main:app --host 127.0.0.1 --port 8000` with migrated temporary DB and `npm run dev` on 127.0.0.1:5173; `curl` returned `{"status":"ok","database":"reachable"}` and read-only settings with both providers unconfigured. Headless Chromium `--dump-dom http://127.0.0.1:5173/models` rendered six links and “Not implemented yet.” Both smoke servers were stopped.
- Limitations: no providers, catalog, fixture adapter, dataset, experiment execution or Compose packaging in Phase 1. No live calls. Python 3.12/Node 24 not separately exercised; local runtime Python 3.14/Node 26. `alembic check` on a database created by an earlier, pre-final migration draft detected a difference; the final schema and a fresh database passed. The TestClient deprecation warning originates in installed FastAPI/Starlette.
- Next concrete action: P2.1 typed provider contracts, injected HTTPX transport and current official provider documentation; then adapters and fail-closed free-only policy.

## Blockers and open implementation checks

- No blocker to beginning Phase 2.
- Recheck provider schemas and model-specific pricing/endpoint evidence during Phase 2.
- Determine live eligibility only through actual catalog/evidence checks; never assume two free models will be available.

### P2.1–P2.6 / 2026-10-07

- State: **P2.1–P2.3 backend contracts/adapters implemented; P2.4 partial; P2.5 completed (frontend checks); P2.6 partial. Phase 2 gate not passed.**
- Changed files: `backend/app/providers/{__init__,common,policy,openrouter,zen,catalog,fixture}.py`, `backend/app/main.py`, `backend/tests/test_providers.py`, `docs/{PROVIDER_NOTES,BUILD_STATUS}.md`. No schema revision needed.
- Working behavior: fixed upstream URLs and server-only keys; HTTPX-injected adapters; normalized responses/errors; append-only catalog refresh and latest-model listing; strict zero-price decision and guarded OpenRouter payload; exact Zen Qwen/DeepSeek endpoint mapping; Zen pricing blocked; labeled synthetic fixture adapter.
- Evidence: synthetic `httpx.MockTransport` contracts and temporary SQLite API integration only; **no live provider calls or credential verification**. A changed paid observation replaces the eligibility view without modifying earlier snapshots.
- Verification commands (from `backend/`): `.venv/bin/python -m pytest -q` → **20 passed**, one upstream TestClient deprecation warning; `.venv/bin/ruff check app tests alembic` → **All checks passed**; `DATABASE_PATH=/tmp/opencode/p2-fresh-check.sqlite3 .venv/bin/alembic upgrade head && DATABASE_PATH=/tmp/opencode/p2-fresh-check.sqlite3 .venv/bin/alembic check` → **No new upgrade operations detected** on freshly migrated SQLite. Evidence type: synthetic fixture and local integration only.
- Limitations: dispatch-time current-snapshot lookup/attempt evidence persistence, reviewed Zen allowlist, full HTTP error/unavailable fixture matrix, or start/resume/worker integration (those lifecycle paths do not exist). Strict pricing requirements may block all live catalog entries.
- Next concrete action: wire central decision into future start/resume/attempt dispatcher with a latest-fresh-snapshot lookup; complete contracts, then rerun Phase 2 gate. Do not count the adapter guard alone as an execution gate.

### Parent integration updates / 2026-10-07

- `app.main` now includes both dataset and experiment routers and sets the execution mode on app state. Dataset list returns `{id, version}` objects; built-in installation is idempotent. The experiment form no longer requires a user to guess a numeric dataset version ID.
- Added latest-persisted-snapshot dispatcher and verified that after a formerly free catalog observation is followed by a paid observation, only the original request is sent; the next dispatch fails closed.
- P2.6 provider fixtures and the P2.5 UI are locally tested, but the Phase 2 end-to-end gate stays open until P4 enforces decisions and persists per-attempt evidence.

### P2.5 / 2026-10-07

- State: **completed (frontend implementation and static build; Phase 2 gate open)**.
- Changed files: `frontend/src/main.tsx`, `frontend/src/Models.tsx`, `plan.md`, `docs/BUILD_STATUS.md`.
- Working behavior: Models route reads `/api/models` and `/api/providers`, refreshes via `POST /api/models/refresh` and reloads both views. Displays per-provider connection/credential status and policy links, exact route, endpoint, availability, context, supported parameters, pricing source/check time, backend eligibility reason and live/demo provenance. Loading, empty, request error and partial refresh results are labeled. A card only says eligible when the backend explicitly allows its matching ID and dated evidence/source is present.
- Verification: `cd frontend && npm run typecheck && npm run build` → **passed** (Vite 7.3.7; Node deprecation warning for `module.register()`). Evidence type: static/frontend build; no browser or live provider test for this package.
- Limitations: catalog decisions do not authorize generation; backend dispatch integration still pending. No authenticated provider discovery was performed.
- Next concrete action: complete P2.4 dispatch-time evidence gate and P2.6 remaining contracts; keep Phase 2 gate open.

## Exact resume instruction

Read `plan.md`, this record, and the latest provider notes before any follow-up. Core local/demo workflows and P8.1–P8.5 have been implemented and verified as summarized in “Final local/demo verification and Phase 8.” If continuing, start at optional P7.A or the remaining P8.6 full security/backup restore checks. Do not assert live eligibility or comparison success without fresh authenticated checks and at least two exact verified-zero routes. Keep `plan.md` and this status file synchronized after each work package.
