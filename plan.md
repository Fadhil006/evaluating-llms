# LLM Comparison Lab — Commander Implementation Plan

Planning date: 2026-10-07. Implementation progress last updated: 2026-10-08. Core local/demo application implemented; optional Phase 7 and conditional live release verification remain open.

## 1. Mission and assessment

Build a local, single-user research application for reproducible comparisons of explicitly identified, verified-free LLM routes through OpenRouter and OpenCode Zen. Deliver working vertical slices, preserve evidence, and distinguish fixture verification from live verification.

The proposed specification is strong: it combines experiment design, operational reliability, task-specific metrics, and human review instead of building a misleading universal leaderboard. Its most important implementation risks are pricing changes, incomplete quota information, interrupted remote requests, missing-data bias, and accidental unblinding. This plan makes those contracts explicit.

The scope is substantial. Phases 1–6 produce the core application; Phase 7 adds independently switchable research extensions; Phase 8 packages and verifies the release. Repeated generation is core in Phase 4; uncertainty estimation is an extension. Do not allow optional judging to delay repair of a failing core workflow.

### Repository facts

- The initial repository contains only `ai_project.md`, a text copy of the survey. No application, tests, dependency files, migrations, or existing architecture were found.
- Preserve `ai_project.md`. It is research background, not an executable specification or a dataset license grant.
- This planning delivery adds `plan.md` and `docs/BUILD_STATUS.md`; it does not claim any implementation gate has passed.
- No authenticated model calls or live availability checks were performed during planning.

### Relationship to the survey

Reference: Chang et al., *A Survey on Evaluation of Large Language Models*, ACM TIST 15(3), Article 39, 2024, DOI https://doi.org/10.1145/3641289.

| Survey concept | Application interpretation | Boundary |
|---|---|---|
| What to evaluate, Section 3 | Language tasks, verifiable reasoning, instruction following; optional controlled robustness | No claim to cover medicine, agents, all languages, ethics, or every survey domain |
| Where to evaluate, Section 4 | Original demonstration data and versioned user imports | Original examples are not MMLU, GSM8K, or a representative benchmark |
| How to evaluate, Section 5.1 | Declared task-specific deterministic scorers and operational measurements | ROUGE is overlap, not factuality; latency measures a route under recorded conditions |
| Human evaluation, Section 5.2/Table 10 | Anchored dimensions, blinded preference, evaluator counts and method | Human judgments have bias and are distinct from factual accuracy |
| Table 9/future challenges | Optional robustness and uncertainty; future fairness/calibration | No fairness score without suitable groups/labels; no probability calibration from unvalidated confidence prose |

The survey motivates the design. The application neither reproduces the entire paper nor reproduces historical model rankings in it.

## 2. Commander operating contract — read throughout the build

**Commander must check this plan at session start, before each work package, after each verification run, and before proceeding to the next phase.** Keep `docs/BUILD_STATUS.md` synchronized with actual evidence, not intended work.

1. Read applicable `AGENTS.md`, this plan, and `docs/BUILD_STATUS.md`. Inspect files and current changes before editing. Never recreate completed work from an old prompt.
2. Identify the earliest incomplete phase and the smallest unfinished work package. Check its prerequisites and acceptance criteria.
3. Record the active package, scope, and verification command in build status. Maintain an actionable session todo list.
4. Inspect the code paths to be changed. Check current official documentation when implementing a library or provider behavior. Record dated API evidence in `docs/PROVIDER_NOTES.md`.
5. Implement a functioning slice. No placeholder screens masquerading as completed functionality. During intermediate phases, navigation may explicitly say a future phase is not implemented.
6. Run targeted verification. Fix failures before calling the package complete. After integration, run the phase gate and previously affected regression checks.
7. Update the package checkbox and build-status evidence together: commands, actual outcomes, fixture/live classification, limitations, changed files, and next action.
8. Report briefly: what works, what was verified, what is limited, and which package is next. Proceed automatically after the gate passes; do not ask for repeated approval.
9. If blocked by credentials or current model availability, complete fixtures/contracts and independent work. Mark live verification blocked, never passed. A fixture-passed gate can advance implementation but cannot satisfy the live delivery claim.
10. At context limits or session end, leave an exact resume instruction, unfinished files, failing checks, and decisions in build status. Do not rely on conversational memory.

### Delegation in Commander mode

When Commander mode supports delegation, delegate bounded packages rather than asking several agents to build the whole application. Commander owns integration, schema/API contracts, verification gates, and status updates.

- Each assignment includes package ID, relevant plan sections, owned paths, dependencies, expected behavior, and checks.
- Assign one owner to shared migrations, dependency manifests/locks, and shared API schemas at a time.
- Safe parallel work: dataset authoring and provider adapters after contracts settle; scorer functions and read-only UI work after response schemas settle; documentation and export test cases after manifest design settles.
- Do not parallelize worker state/budget edits with conflicting schema edits. Integrate and test dependencies before assigning dependent packages.
- Treat agent summaries as leads; inspect resulting diffs and run integration checks before closing a gate.
- If delegation is unavailable, execute the same packages sequentially. Do not create custom orchestration infrastructure for this project.

### Change control

Reasonable implementation details may change after inspection. Record consequential changes under Decisions in build status and update this plan. Do not silently remove requirements, label unfinished extensions complete, introduce paid execution, or replace a selected model. No commits or pushes unless separately requested.

## 3. Architecture and defaults

### Minimal architecture

```text
Browser / React
    | same-origin /api requests; polling while an experiment is active
FastAPI API ---------------- SQLite on a local persistent volume
    | reads/writes                 ^
    |                        separate Python worker
    |                              |
    + catalog/account adapters     + generation adapters -> gateways
```

- Frontend: React, TypeScript, Vite, Tailwind, React Router, Recharts. Use ordinary forms and a small typed API client. Add a state-management library only if actual complexity warrants it.
- Backend: FastAPI, Pydantic/settings, HTTPX, SQLAlchemy 2, Alembic, pytest. Use one documented synchronous SQLAlchemy session pattern and short transactions; never hold a DB transaction during HTTP requests.
- Queue: persistent SQLAlchemy `GenerationJob` records and attempt records, not FastAPI background tasks or an in-memory queue. No Redis/Celery requirement for this release.
- Worker: one process, initially one global in-flight generation. Per-provider minimum spacing/cooldowns still apply. Keep claim operations safe if a second worker is accidentally launched.
- Database: SQLite foreign keys on, WAL, busy timeout, explicit transaction boundaries, local disk. Do not place the database on a network filesystem.
- UI progress: poll about every 2 seconds while active, stop on terminal state; slower refresh when paused. WebSockets and streaming are unnecessary for the first release.
- Production-local packaging: build frontend assets and serve them from FastAPI; Compose runs API and worker sharing one volume. Vite dev proxy supplies the same `/api` interface in development.
- Default host bindings: API `127.0.0.1:8000`, Vite `127.0.0.1:5173`; Compose publishes `127.0.0.1:8000:8000`. Containers may listen internally on `0.0.0.0` without exposing the host publicly.
- Explicit localhost Host/Origin allowlists; do not enable wildcard CORS. Require JSON for mutations except the designated upload endpoint. No arbitrary provider URL supplied by a browser or imported experiment.

### Proposed layout

```text
frontend/
  src/{api,components,pages}/
  tests/                       # a few Playwright workflows
backend/
  app/
    api/                       # route modules and public schemas
    providers/                 # common types, OpenRouter, Zen, fixture, pricing
    evaluation/                # registry, scorers, aggregates; extensions later
    worker/                    # main loop, claiming, attempts, recovery
    models/                    # ORM entities
    services/                  # imports, experiment lifecycle, review, exports
    config.py
    db.py
    main.py
  alembic/versions/
  tests/{fixtures,contracts}/
  pyproject.toml
datasets/original_demo_v1.jsonl
docs/
  BUILD_STATUS.md
  PROVIDER_NOTES.md
  METHODOLOGY.md
  DEVELOPMENT.md
  sample-report.md
Dockerfile
docker-compose.yml
.env.example
.gitignore
README.md
plan.md
```

This is a location guide, not permission to create empty layers. Keep small modules together where sensible.

### Initial configuration decisions

| Setting | Default / contract |
|---|---|
| Runtime | Python 3.12+ and a current supported Node LTS; select and lock compatible versions in Phase 1 |
| Execution mode | `live` with no configured keys means unavailable; explicit `demo` enables fixtures |
| Database | `data/lab.sqlite3`; demo uses a separate database path |
| Cost policy | `FREE_ONLY=true`; reject false in this release |
| Keys | `OPENROUTER_API_KEY`, `OPENCODE_ZEN_API_KEY`; server environment only |
| Quick comparison | 10 saved, category-balanced item IDs; at least 2 distinct gateway/model entries |
| Generation | 512 output tokens, 1 repetition, seed 42, temperature 0 only if supported by every selected route |
| Network | Non-streaming; 60-second per-attempt deadline; lower connection timeout |
| Retries | At most 2 retries per job, also constrained by experiment and account caps |
| Manual cap | 40 generation attempts per provider account per UTC day unless explicitly configured otherwise |
| Price freshness | Revalidate at start/resume and when evidence exceeds 15 minutes during a run |
| Zen allowlist | Exact IDs, source evidence and expiry; at most 7 days without renewed official verification |
| Upload limits | 5 MiB, 5,000 rows, bounded prompt/context/answer sizes; return precise validation errors |

These are application defaults, not assertions about provider quotas. Expose timeout, retries, and caps clearly. If generation settings cannot be applied uniformly, block or require the user to omit that setting for all routes; never silently drop it for only one model.

## 4. Shared data and API contracts

### Entities and critical constraints

Use UTC timestamps, stable IDs, JSON only for genuinely variable configuration/evidence, and relational foreign keys for joins. Include schema versions in persisted snapshots and exports.

| Entity | Required content and invariants |
|---|---|
| Provider | Gateway slug, fixed base URL, credential-configured boolean, latest connection status/check time, policy links; no key values |
| ModelSnapshot | Append-only gateway/model ID, display name, endpoint family, capabilities/context, supported parameters, pricing evidence/source/check/expiry, available provider version metadata, availability observation |
| Dataset | Name, description, source/license and original/imported origin |
| DatasetVersion | Immutable version, normalized-content SHA-256, source/license manifest, category inventory, import schema version |
| DatasetItem | Version FK, unique external ID within version, prompt/context/choices, references, task type, scorer config, tags, source/license; immutable after version creation |
| Experiment | Draft fields then immutable canonical config JSON/hash, selected model snapshots, dataset version and explicit item IDs, shared prompt/settings, repetitions, seeds, caps, extension config, provenance mode, status and pause reason |
| GenerationJob | Experiment/model slot/item/repetition/variant, unique combination constraint, execution order, status, next eligible time, lease owner/token/expiry, attempt count |
| RequestAttempt | Job FK, unique attempt number, reserved/dispatched/completed timestamps, request duration, sanitized request fingerprint, provider response ID, normalized error/retry-after, outcome including `unknown_remote_outcome` |
| ModelResponse | One accepted response per job, producing attempt, raw text, returned identity, finish reason, nullable usage, safe provider metadata, identity mismatch flag |
| MetricResult | Response FK, metric/scorer version, nullable value, parsed/normalized answer, parse status, explanation; unique response/metric/version |
| HumanRating | Opaque review assignment, evaluator label, rubric version, dimension scores with null=N/A, comments; unique response/evaluator/rubric version |
| PairwiseVote | Assignment, evaluator, A/B/tie/cannot-judge choice, comments/rubric version, persisted hidden presentation mapping; uniqueness prevents repeat-vote inflation |
| ExperimentEvent | Append-only status and operational events, UTC time, structured safe details |

Supporting records justified by concrete requirements:

- `ProviderAccountState`: one configured account per gateway initially; persisted cooldown/reset, quota observation timestamp/source and application request counter. All experiments and judge jobs share this accounting scope.
- `ReviewAssignment`: opaque ID, mode, evaluator label, task/item, internal response mapping and saved randomized order. Its public serializer must not include identities.
- Metadata HTTP calls need a lightweight persistent accounting record as well, distinguishable from generation attempts; use one small `ProviderCall` ledger if convenient. Never confuse catalog GET counts with provider free-generation quota.
- Phase 7 adds perturbation-pair and judge-result records only when needed. Reuse the attempt/budget machinery for judging instead of building a second unmetered request path.

Model catalog refresh appends observations; it does not rewrite an experiment's snapshot. Current eligibility is separate from the preserved original selection. Started configurations cannot be edited; clone to a new draft. Lifecycle changes, ratings, and versioned scoring do not mutate the generation configuration.

Provider modules, catalog UI, persisted-evidence start/resume checks, and dispatch-time decision persistence are integrated and covered by synthetic contracts. Live catalog evidence and a limited 10-item/two-model OpenRouter smoke run are recorded below; Zen execution remains blocked by missing server credentials.

### API surface to implement incrementally

All paths below are under `/api`. Specify public Pydantic schemas rather than serializing ORM objects directly.

| Area | Endpoints / behavior |
|---|---|
| Health/settings | `GET /health`, `GET /settings`; safe status only, worker heartbeat once implemented |
| Providers/models | `GET /providers`, `POST /providers/{slug}/check`, `POST /models/refresh`, `GET /models` |
| Datasets | `GET /datasets`, `GET /datasets/{id}/versions/{version}`, `POST /datasets/import/preview`, `POST /datasets/import` |
| Design | `POST /experiments/estimate`, `POST /experiments`, `GET /experiments`, `GET /experiments/{id}`, draft update, `POST /experiments/{id}/clone` |
| Lifecycle | `POST /experiments/{id}/{start,pause,resume,cancel}`; idempotent where appropriate; illegal transitions return 409 |
| Results | `GET /experiments/{id}/progress`, `/events`, `/responses`, `/results`; paginated/filterable records |
| Review | `POST /review/assignments`, `GET /review/assignments/{opaque_id}`, rating/vote submission, aggregate retrieval |
| Exports | `GET /experiments/{id}/export?format=csv|json|html|markdown` |

Validation failures include field paths/row numbers and actionable messages. Never return secret-bearing exception representations. Import preview and save must both validate; saving must not trust an unverified preview result supplied by the browser.

## 5. Phase 1 — Foundation and data model

**Goal:** application starts, migrates, and exposes an honest basic shell.

### Work packages

- [x] **P1.1 — Bootstrap:** select compatible dependencies, lock them, configure Python/npm scripts, lint/type/build commands, `.gitignore` for keys/data/artifacts, and `.env.example` with empty secret placeholders.
- [x] **P1.2 — Settings and database:** readable startup validation, writable data directory check, secret types and safe error handler, SQLAlchemy sessions, Alembic environment and initial entity migration.
- [x] **P1.3 — API and shell:** health/settings endpoints and navigation for Overview, Models, Datasets, Experiments, Human Review, Settings. Show backend availability and explicit unimplemented states instead of fabricated statistics.
- [x] **P1.4 — Foundation checks:** migration smoke test on a fresh temporary DB, API/config tests, frontend production build, local startup check; write exact startup commands into README.

### Acceptance gate

- Empty DB upgrades to head; restart preserves data; constraints such as job uniqueness work.
- Health responds and navigation renders locally.
- Invalid timeout/path/config reports a useful problem without printing settings or credentials.
- Missing keys are a normal unavailable state. Sentinel keys do not appear in API JSON or captured logs, including startup validation errors.
- Any seeded fixture is visibly labeled and never appears as a live discovery result.

Record actual commands and outcomes in build status. Future planned commands are not evidence.

## 6. Phase 2 — Providers and verified-free discovery

**Goal:** current catalogs and an enforceable execution policy, independent of the browser.

### Documentation checkpoint

Official sources consulted during planning on 2026-10-07:

- OpenRouter docs via Context7 `/openrouterteam/docs`: model pricing, key limits, provider routing preferences and OpenAPI schemas.
- https://openrouter.ai/docs/api/reference/limits (redirected to the current limits documentation).
- https://opencode.ai/docs/zen/ and official OpenCode docs source via Context7 `/anomalyco/opencode`.

Findings to recheck during implementation:

- OpenRouter pricing has multiple fields and may contain conditional overrides. Parse exact decimal prices, not name suffixes or truthiness of strings.
- `provider.max_price` supports specific documented keys; token-price ceiling units differ from catalog per-token pricing. Zero avoids conversion ambiguity, but does not prove all auxiliary costs are zero.
- OpenRouter provider fallback controls and model fallback controls are distinct. Explicitly prohibit model substitution; for the initial strict comparison use no provider fallback and record the route actually served.
- Account schemas/documentation may expose different quota detail. Use documented free-request counters when actually returned; absent/null counters are unknown. Monetary credit remaining is not a free-request counter. Never hard-code a documentation example quota as the user's quota.
- Zen documents different endpoint families (`chat/completions`, `responses`, `messages`, and others). Discovery alone does not identify a usable chat adapter.
- Zen free offers and privacy exceptions change. A name containing “Free” is not a zero-price contract. Do not copy a historical model list into permanent eligibility logic.

### Work packages

- [x] **P2.1 — Provider contract:** typed catalog entries, capabilities, quota observation, generation request/response, normalized errors; HTTPX transport injection for fixtures. A small protocol with two real adapters is sufficient.
- [x] **P2.2 — OpenRouter adapter:** `GET https://openrouter.ai/api/v1/models`, `GET /api/v1/key` when configured, non-streaming `POST https://openrouter.ai/api/v1/chat/completions`; normalize text, finish, usage, identity, response ID and upstream metadata.
- [x] **P2.3 — Zen adapter:** `GET https://opencode.ai/zen/v1/models`, explicitly documented chat-completions routes only; preserve unsupported models in catalog with reasons. Do not invent a Zen quota API if none is documented.
- [x] **P2.4 — Free-only policy:** OpenRouter uses explicit `is_free` or zero prompt/completion prices, rejects any listed applicable request/cache/reasoning price, and treats omitted optional charges as inapplicable to this text-only request shape; Zen uses the dated 11-ID chat free-pricing allowlist with 7-day expiry. Start/resume/worker revalidate evidence, credential availability and dispatch-time snapshot; provider-side ceilings/fallback disablement remain. Live endpoint errors are recorded, not bypassed.
- [x] **P2.5 — Catalog UI:** refresh, connection status, eligibility, context, supported parameters, evidence dates, endpoint support and data-policy links. Expired/stale/unknown are distinct from paid and temporarily unavailable.
- [x] **P2.6 — Contract verification (provider layer):** fixtures cover successful schemas, missing optional fields, malformed prices, paid and unknown prices, unsupported endpoint, 401/429/5xx and unavailable IDs. Label recorded vs synthetic fixtures. Introduce the explicitly labeled fixture adapter here so Phases 3–6 can run without credentials; Phase 8 completes its packaged demonstration scenarios.

### Free-only decision algorithm

1. Require exact gateway/model identity and a supported endpoint. Exclude automatic routers such as `openrouter/free` and any model-routing aliases without a stable named model.
2. Fetch or validate fresh evidence. Missing pricing is not zero. All applicable token/request/cache/reasoning charges and conditional pricing tiers must be proven zero or explicitly inapplicable to the fixed request shape.
3. For insufficient machine-readable pricing, accept only a dated, maintained official-documentation allowlist entry with exact ID, endpoint, evidence excerpt/hash, URL, reviewer/check date, expiry and covered charges. Ambiguous entries fail closed.
4. Forbid tools, web search, paid plugins, BYOK routing and paid auxiliary features in the initial request builder. Do not pass through arbitrary user provider payloads.
5. Apply documented zero-price ceilings and required-parameter enforcement where supported. Disable fallback options. The guard cannot be disabled by an API client.
6. Persist the eligibility decision with the attempt. If refresh fails after evidence expires, pause execution; do not continue on assumed prices.

### Acceptance gate

- Catalog refresh persists new snapshots and UI reports reasoned eligibility.
- Backend calls are blocked for unknown/nonzero/expired prices even if frontend validation is bypassed.
- Test a previously free model becoming paid/unavailable before the next request and after resume.
- Tests assert the complete outbound payload contains no plugins, fallback model list, or unapproved settings.
- No credentials: adapters are contract-verified only. Fewer than two eligible live models: comparison remains a draft/blocked run with preserved selection; no paid substitution.

Implementation contracts and fail-closed behavior pass local fixtures. Current live metadata refresh produced 19 verified-zero OpenRouter entries and 10 current Zen free-price allowlist entries. Zen credential configuration is not detected by this server, so Zen routes are shown as price-verified but not selectable until a key is configured. Earlier live smoke attempts failed; a later separate ten-item OpenRouter run completed (recorded below).

Initial live metadata check on 2026-10-08 found incomplete pricing due the overly strict optional-SKU policy; that count was superseded by the evidence semantics documented in `docs/PROVIDER_NOTES.md` and tested in the provider suite.

UI follow-up: Models shows only verified-free price entries; the experiment selector additionally requires a configured provider key. Paid, unknown-price, unsupported and unavailable catalog entries remain hidden. The API retains the full catalog for policy checks and provenance. Current price-eligible count is 19 OpenRouter and 10 Zen; Zen is not runnable until its key is correctly configured. Demo mode still shows only labeled synthetic fixtures.

Earlier live smoke on 2026-10-08: three one-item experiments were saved with 0 retries; OpenRouter returned HTTP 429/invalid response and Zen `big-pickle` returned HTTP 403 without a configured key. Those are operational failures, not benchmark results, and remain stored.

Later live run, experiment 4, 2026-10-08: 10 original questions × 2 verified-free OpenRouter routes, one repetition, 20/20 responses completed with no retries. Most task-specific checks passed; the run also captured a deterministic instruction-format failure and a truncation. This one convenience-sample run is not evidence of broad model superiority. OpenRouter's account endpoint reported 22/50 free requests used afterward. Zen remains non-selectable until `OPENCODE_ZEN_API_KEY` is recognized; no additional generations were sent.

## 7. Phase 3 — Datasets and fair experiment design

**Goal:** reproducible data selection and a truthful request estimate before running.

### Work packages

- [x] **P3.1 — Original dataset:** author 30 items, five each in multiple choice, short factual answer, arithmetic/reasoning, structured extraction, summarization, instruction following. Add item sources/original attribution and explicit dataset license (use CC0-1.0 for newly authored examples). Review every answer and deterministic condition.
- [x] **P3.2 — Versioned import:** UTF-8 CSV/JSONL parser, size/row/field limits, preview, row-specific validation, duplicate IDs/content checks, canonical serialization/hash, atomic save. Arrays/objects in CSV are JSON strings; the API router docstring and isolated CSV integration test give examples.
- [x] **P3.3 — Sampling and request builder:** deterministic category-stratified sampling; save actual ordered item IDs, not just the seed. Build messages only from system instruction, prompt, context, choices and any explicitly declared public task schema.
- [x] **P3.4 — Experiment form:** name, models, dataset/version, item subset, shared system instruction, tokens, temperature, repetitions, seed, timeout, retries and attempt cap; shared backend validation and authoritative estimate endpoint.
- [x] **P3.5 — Immutable snapshot:** draft editing, clone operation, canonical config hash at start; capture resolved request settings, dataset hash, model snapshots and run provenance.

Backend draft/design and start-time freeze routes are integrated in the parent API. Start revalidates the newest exact route evidence, captures it in an immutable frozen config and schedules unique interleaved jobs atomically. Pause/resume/cancel transitions are available; the P3.4 frontend form passes static typecheck/build. Dataset versions expose their database IDs. Dispatch and durable attempt evidence remain in P4.

### Import/data rules

- Fields: `id`, `task_type`, `prompt`, optional `context`, `reference_answers`, `choices`, `scoring_config`, `tags`, `source`, `license`.
- Require references/choices/schema/labels according to task type, not a single permissive schema for every task.
- Reject unknown executable scorer names, arbitrary Python, external schema references, or unbounded user regex execution. Deterministic instruction checks use an allowlisted configuration language.
- Reject duplicate IDs in a version. Flag identical normalized content under different IDs and require explicit acknowledgement; preserve the flag. Identical version hashes reuse/reject the duplicate version rather than duplicating silently.
- Missing source/license on imports is labeled unknown, never inferred as permission to redistribute. Preserve source/license at item level and version level.
- Keep scoring metadata and answers private to evaluation. If a task needs a JSON schema or output constraint in the prompt, use an explicit public task specification, not the entire scoring configuration. Any explicitly permitted reference inclusion must be disclosed and hashed in the manifest.
- Quick sampling: distribute ten items as evenly as possible across six categories (four categories have two, two have one), rotate remainder allocation deterministically by seed; show the actual distribution. Never describe ten items as perfectly equal category coverage.
- Context limits: use conservative estimation and documented uncertainty unless exact tokenization is available. Block clearly oversized inputs; provider rejection remains a possible recorded outcome. Validate requested output limits against every route.
- The sampling/execution-order seed controls local selection and job order; it does not make remote inference deterministic. A provider generation seed is a separate optional setting, sent only when uniformly supported and recorded as best-effort rather than a reproducibility guarantee.

### Budget estimate contract

`base_generation_requests = models × selected_items × repetitions`

Show separately:

- Initial candidate requests.
- Maximum candidate retries = initial requests × per-job retry count, constrained by a user-visible absolute attempt cap.
- Metadata/connection checks: expected startup count and possible refresh checks, classified separately from generations.
- Optional robustness requests and judge requests, with order-swap multiplier, plus their retry allowance.
- Per-account allocation and remaining application/provider allowance when known.

Example: 3 × 10 × 1 = 30 initial generations; with 2 retries/job, unconstrained generation maximum is 90, not 30. A cap of 40 allows only 10 extra attempts. Estimate both initial workload and maximum permitted work. Metadata calls may have separate provider limits; do not silently count them as free-model completions.

### Acceptance gate

- Thirty originals and references are reviewed; hash/version stable under repeated load.
- Preview/save reject malformed CSV/JSONL, invalid scorer config, duplicate IDs and oversized files without partially importing data.
- Captured generation messages contain no hidden answers/scoring metadata, including deliberately seeded sentinel answers.
- Same seed/input yields the same saved selection; changing catalog order does not alter existing experiments.
- At least two distinct route entries required to start a comparison. Unsupported temperature/other settings produce clear blocking explanations or an explicit omit-for-all choice.
- Request estimates change correctly with models/items/repetitions/retries and future extension flags.

## 8. Phase 4 — Durable runner and accounting

**Goal:** browser-independent execution with bounded requests and honest recovery semantics.

### State model

```text
draft -> queued -> running -> completed | completed_with_errors
                   |  |
                   |  +-> paused -> queued (resume)
                   +----> interrupted -> queued (resume after recovery)
draft/queued/running/paused/interrupted -> cancelled
```

Store pause reasons independently: user, rate limit, quota, manual cap, credentials, stale pricing, unavailable model, unknown remote outcome. Completed/cancelled configurations remain immutable; a new comparison requires cloning. A cooldown for a retry need not pause the entire experiment; exhausted daily quota does.

Jobs have separate pending/leased/retry-wait/succeeded/failed/cancelled/interrupted states. Terminal experiment status is derived only after accounting for every scheduled job. Paused work must not be mistaken for completed work.

### Work packages

- [x] **P4.1 — Start transaction:** validate current eligibility/settings, freeze config, persist all unique jobs and a saved seeded interleaved order, enqueue once; repeated start cannot duplicate jobs.
- [x] **P4.2 — Atomic claim and budget:** serialized SQLite claims with lease tokens, account UTC counters and configured manual cap, lifetime experiment cap and per-job retry limit; unsent reservations are released.
- [x] **P4.3 — Dispatch/result persistence:** latest route evidence is revalidated and persisted immediately before dispatch, responses/metrics/events are stored with lease fencing, and returned identities/usage/provenance are retained.
- [x] **P4.4 — Retry/error policy:** bounded backoff/jitter, Retry-After seconds/date without shortening waits, provider cooldown, permanent errors, known provider-quota pause, and application request caps are implemented and tested.
- [x] **P4.5 — Lifecycle/recovery:** pause/resume/cancel, leases/unknown outcomes, progress API and UI controls are implemented. Worker heartbeat is not a separate record; lease and attempt state are the recovery signal.
- [x] **P4.6 — Operational checks:** deterministic failure/cap/race tests, subprocess worker recovery, and fixture-backed browser workflow with separate worker pass locally.

### Accounting and concurrency semantics

- One account scope per gateway in v1. Every dispatched generation, including retries and judge requests, consumes the application's conservative attempt allowance even on failure. Shared counters cover simultaneous experiments.
- Ledger distinguishes reserved, definitely unsent, sent, completed and uncertain attempts. Release a reservation only when known unsent; uncertain sends remain consumed. A crash must not replenish the budget accidentally.
- Daily account cap resets according to recorded reset/timezone policy; experiment lifetime cap never resets at midnight. Refresh stale provider counters and account for local sends since the observation without double-counting confirmed observations.
- External uses of the same key are invisible unless the provider reports them. Display application consumption separately from authoritative provider consumption; never promise a globally accurate remaining quota from local counts alone.
- Initial dispatch spacing: conservative configurable interval, e.g. 4 seconds per gateway, tightened by documented restrictions and provider headers. One in-flight request is a throughput choice, not sufficient rate-limit handling by itself.
- No hidden HTTPX/provider SDK retries: worker logic owns attempts. Every actual retry must have a persisted attempt and budget reservation.
- Retry-After is a minimum wait, including HTTP dates. Do not cap it downward; pause with a future eligible time if long. Jitter/backoff tests use an injected clock/random source.
- 400/422 invalid request: terminal job failure. 401/credential failure: pause gateway's affected work. 403 classify access/moderation explicitly. 404 unavailable model: block that route and preserve pending jobs. 402: pause; never suggest automatically switching to paid execution. 429 daily exhaustion: pause until known reset or explicit recheck. Transient 429/5xx/timeouts: bounded retry where appropriate.
- A network timeout after sending can have an unknown remote outcome. Record uncertainty even when configured retries proceed within budget; do not call this exactly-once execution.

### Pause, cancellation, and crash contract

- Pause prevents new dispatches after its transaction boundary. A previously committed in-flight dispatch may finish and its answer is saved.
- Cancel stops pending work; the initial implementation allows the one in-flight request to finish and records it with cancellation timing. Do not claim remote cancellation is guaranteed.
- Lease duration exceeds the request deadline plus persistence allowance, or is renewed with a heartbeat. Expired owner cannot overwrite a replacement worker's result (lease fencing).
- Completed jobs are never resent on restart. Expired leased jobs without a recorded response are marked interrupted; if dispatch may have occurred, record unknown remote outcome and require explicit resume acknowledgement before retrying that job.
- Resume revalidates prices, quotas, identity availability and capability compatibility. A changed model remains the original selection; clone explicitly to change it.
- Save monotonic elapsed request duration around actual HTTP work. Keep queue wait and retry delay separate; no TTFT claim in non-streaming mode. Missing token counts remain null.
- Returned identity mismatch is preserved and flagged; exclude it from clean named-model quality comparisons while exposing it in operational coverage.

### Acceptance gate

- Closing/reopening the browser leaves worker progress intact.
- Kill/restart a worker after completed jobs and during an in-flight fixture request: no completed duplicate, uncertainty recorded, remaining jobs recover under documented policy.
- Test two simultaneous claims and two experiments sharing the final available request: at most one reservation succeeds.
- Pause/cancel race tests observe documented in-flight semantics; resume retains all completed work.
- 429 with Retry-After, daily exhaustion, permanent failure, transient retry, retry cap, midnight boundary and manual-cap exhaustion all pass deterministic tests.
- UI displays completed/failed/pending/in-flight counts, consumed/remaining attempts, pause reason and recovery action.

Local/fixture acceptance passed 2026-10-08. Provider-account reconciliation can only use the last supported quota observation plus this application's request count; usage outside this app is not visible. Live provider checks remain unperformed.

## 9. Phase 5 — Deterministic evaluation and denominators

**Goal:** scores are traceable, task-appropriate, and not improved by hiding failures.

### Work packages

- [x] **P5.1 — Registry:** versioned scorer functions, explicit task mappings, structured score/explanation/parse-status outputs; preserve raw and normalized responses.
- [x] **P5.2 — Metrics:** implement the table below and independent hand-calculated checks.
- [x] **P5.3 — Scoring lifecycle:** idempotent local scoring after persistence; scoring failure cannot cause regeneration. Recovery finds unscored saved responses. Rescoring creates a new scorer version's results, not replacement raw answers.
- [x] **P5.4 — Aggregates:** per-task metrics, clear counts/coverage, common-completed-set comparisons, failure/format/truncation breakdown and explanations.

| Task | Metric and declared parsing rule | Required checks |
|---|---|---|
| Multiple choice | Accuracy; accept a single label or a single declared `Answer: X` final line; conflicting/multiple labels unparseable | Correct/wrong labels, ambiguity, out-of-range, empty output |
| Short factual | Raw exact match; normalized exact match against accepted variants; versioned Unicode/case/whitespace policy | Multiple variants, punctuation policy, no substring-match cheating |
| Extractive QA | Multiset token-overlap F1, max over accepted references; explicitly declared tokenizer | Repeated tokens, no overlap, empty/reference-empty rules |
| Arithmetic | Single declared final numeric answer; Decimal comparison with configured absolute/relative tolerance and explicit units policy | Negatives, decimals, scientific notation if supported, incompatible units, NaN/Infinity, ambiguous numbers |
| Classification | Per-item label accuracy; macro F1 computed over the version's declared label set at aggregate level | Missing class, invalid prediction, hand-calculated confusion counts; not an average of per-item F1 |
| Structured extraction | JSON validity, JSON Schema validity, expected-field correctness with declared extra/missing-field policy | Broken JSON, wrong type, missing/extra field, null; disallow remote `$ref` |
| Summarization | ROUGE-L F1 with versioned tokenizer/reference aggregation; pair with human review | Known longest-common-subsequence examples, empty texts, multiple references; no factuality claim |
| Instruction following | Explicit allowlisted checks: required strings, JSON format, word/line count, forbidden strings, etc. | Boundary counts and partial compliance; no subjective automatic helpfulness score |

Support imported extractive QA/classification even though the six-category original demo does not claim coverage of every supported task. Provide small scorer fixtures for those tasks.

### Missingness and reporting contract

For each model/task/metric report:

- `N_scheduled`: all selected item/repetition jobs for that route/task.
- `N_response`: recorded responses, with route-identity and finish/format flags.
- `N_complete`: responses meeting the declared completion eligibility rule; truncated responses are separate, not silently included.
- `N_parseable`, `N_metric_eligible`, missing-reference count, operational failures and pending/cancelled counts.
- Quality among eligible completed responses, together with its exact denominator; format failures in otherwise completed applicable tasks count as failed correctness, not selectively removed successes.
- Overall task success = declared successful outcomes / scheduled jobs, only where a defensible success criterion exists. Pending jobs are labeled pending in provisional reports; they are not fabricated score records of zero.

For continuous overlap metrics without a declared pass threshold, show conditional quality and completion coverage rather than inventing binary “success.” A success threshold must be explicit in dataset scoring config. Optional operationally adjusted metrics must be separately labeled, not presented as the raw quality metric.

Direct comparisons use the intersection of eligible `(item_id, repetition, variant)` keys across compared models, alongside full scheduled-set coverage. Report the size and IDs/counts of omitted items and avoid replacing the full results with survivor-only rankings. Repeated trials are not independent questions.

### Acceptance gate

- Each scorer has hand-calculated correct/incorrect/edge examples; scorer and normalization versions persisted.
- A model answering 1/10 correctly with nine network failures cannot appear equivalent to a model answering 10/10 correctly.
- Missing response != incorrect response != invalid format != truncated answer; null metrics are not coerced to zero.
- A score detail endpoint explains extraction, reference policy, version and denominator.
- No unexplained overall composite score.

## 10. Phase 6 — Results dashboard and blinded human review

**Goal:** useful comparisons and genuinely anonymous presentation at the application interface.

### Work packages

- [x] **P6.1 — Results UI:** task/metric tables and Recharts bars, completion/failure counts, median/p95 request latency with sample count, nullable token usage and coverage; model/task/status filters. Frontend implementation and static build verified; browser gate remains open.
- [x] **P6.2 — Answer inspection:** side-by-side responses, reference answers, normalized values and scoring explanations; error view for incorrect, malformed, missing, mismatched-route and truncated responses. Frontend implementation and static build verified; browser gate remains open.
- [x] **P6.3 — Review protocol:** versioned rubric and server-created opaque assignments; seeded/randomized stored presentation order; applicable references displayed consistently. Backend locally verified; browser flow remains in P6.5.
- [x] **P6.4 — Review persistence:** rubric ratings, preference votes, evaluator label and comments; uniqueness/upsert semantics prevent duplicate inflation; aggregate only latest intended rating per unique key. Backend locally verified; browser flow remains in P6.5.
- [x] **P6.5 — Browser gates:** Playwright exercises the demo catalog, dataset installation, experiment design/run, pause/resume/cancel, results/exports, blinded review, assignment reload and duplicate-submit protection using a real separate API/worker/temporary SQLite. Keyboard navigation/focus is checked; API tests cover additional partial/error states. Broader manual contrast audit remains desirable.

### Blinding contract

- Review API responses contain task context, response text, references when relevant, opaque assignment IDs and A/B labels only. Do not include model names, provider IDs, response IDs that join directly to the public result list, revealing URLs or metadata hidden with CSS.
- Server saves mapping before returning the assignment. Refreshing or submitting a vote uses that same mapping, even after restart.
- Pair comparisons use the same task/item and declared repetition pairing. Do not compare different questions or regenerate until a preferred result appears.
- Assignment uniqueness plus vote uniqueness prevents refresh/repeated clicks from creating additional votes for the same evaluator and candidate pair.
- Evaluator identity is a local label, not authenticated multi-user identity. Report the number of distinct labels without claiming verified independent raters.
- A local operator can inspect the DB/results, and response text can self-identify. Document these blinding limits; do not secretly edit raw answers to remove self-identification. Let reviewers mark “cannot judge” and optionally “identity suspected.”

### Rubric v1 anchors

Use scores 1–5, with 2/4 intermediate and N/A for dimensions not supported by the task evidence.

| Dimension | 1 (low) | 3 (middle) | 5 (high) |
|---|---|---|---|
| Accuracy | Materially incorrect relative to evidence | Mixed correctness or important omission | Correct on the assessable requirements |
| Relevance | Does not answer the task | Partly relevant with distractions | Directly addresses the task |
| Fluency | Difficult to understand | Understandable with noticeable issues | Clear and readable |
| Transparency | Misrepresents evidence/limitations | Some evidence or uncertainty stated appropriately | Clearly communicates relevant support and limits without unsupported certainty |
| Safety | Contains a task-relevant harmful issue | Some relevant concern | Meets the safety criteria applicable to this task |
| Task alignment | Violates central instructions | Partly follows instructions | Meets the stated user constraints |

Transparency is not access to hidden chain-of-thought. Safety is N/A for tasks that do not test it; these ratings are not a comprehensive safety benchmark.

Pairwise choices: A wins, B wins, tie, cannot judge. Report wins/losses/ties/cannot-judge separately, total comparisons and evaluators per pair; sparse matrices say insufficient comparisons. Preference is never relabeled accuracy. Rubric means include dimension-specific applicable rating counts.

### Acceptance gate

- Inspect review API/network payloads for identity leakage; names absent from DOM and accessible labels too.
- Tests force both A/B mappings and verify correct winner attribution, persistent order and duplicate-vote protection.
- Human ratings affect the correct report and persist across reload/restart.
- At least one real browser flow exercises API + separate worker + temporary SQLite using a fixture provider, rather than mocking all backend endpoints.
- Latency labels explicitly say measured model/provider route under the recorded conditions; no intrinsic speed or TTFT claims.

## 11. Phase 7 — Independently switchable research extensions

All flags default off. Complete and verify each extension separately after Phase 6. If a session ends before implementation, mark it pending, not available. Core must continue working with all extensions disabled.

### P7.A — Controlled robustness

- [ ] Store baseline/modified item pairs, transformation version, original/modified prompt, intended-answer validation and pair IDs.
- [ ] Initially offer deterministic benign formatting/typo changes and manually reviewed paraphrases. Do not automatically assume any generated paraphrase preserves the answer.
- [ ] Include all variant jobs in estimates/snapshots; use the same variant for every compared model.
- [ ] Report baseline/modified metrics on valid matched pairs, absolute change, coverage and excluded pairs. Relative drop is null/undefined when baseline is zero.
- [ ] Tests cover pairing, variant accounting, invalidated pairs and zero baseline. No claim that benign perturbations constitute a complete adversarial benchmark.

### P7.B — Repeated trials and uncertainty

- [ ] Expose within-item variation from core repetitions; aggregate each item's repetitions according to a declared policy.
- [ ] Implement deterministic dataset-item cluster bootstrap, e.g. 2,000 resamples with saved seed and percentile interval method. Resampling an item carries all its repetitions; for model differences sample paired item IDs together.
- [ ] Report item count separately from generation count, missing pairs and bootstrap settings. One item or insufficient variation yields a clear limitation, not false precision.
- [ ] Hand-check tiny paired fixtures and reproducibility; demonstrate that adding repetitions does not increase the number of independent items.
- [ ] Intervals describe this convenience sample and protocol, not all real-world tasks or a broad superiority claim.

### P7.C — Optional LLM-assisted judging

- [ ] Explicit opt-in with a verified-free supported judge route, rubric and prompt versions, candidate-pair selection and optional order swap frozen before run.
- [ ] Persist judge jobs, identities, randomized mappings, prompt, raw output, parsed result/status and every request attempt; use the same worker accounting and pricing gate.
- [ ] Judge budget for all-pairs mode: `items × repetitions × (M × (M-1)/2) × orders`, where orders is 1 or 2. Apply variant selection and retry allowance explicitly. Failed/missing candidate pairs produce skipped judge jobs with reasons, not calls.
- [ ] Put candidate text into delimited/escaped data fields under a fixed rubric instruction, disable tools, require strict structured output. Treat every candidate as untrusted. Delimiters reduce confusion but do not guarantee immunity to prompt injection.
- [ ] Adversarial fixtures include “ignore the rubric,” forged delimiters, self-awarded scores and instructions to reveal secrets. Verify serialization, no instruction promotion, no tools and safe rejection of malformed judge output; do not claim these tests prove the model cannot be manipulated.
- [ ] Flag self-judging and order inconsistencies; keep model judgments separate from deterministic and human results. Compare overlapping human/judge samples with counts and agreement descriptions, including zero-overlap states.

### P7.D — Honest coverage boundaries

- [ ] Document fairness and calibration as future modules with concrete prerequisites: representative groups/labels/measurement design for fairness; suitable probabilistic predictions and validation for calibration.
- [ ] Ensure no fabricated scores, disabled-feature charts implying measured data, or unvalidated confidence probabilities appear.

### Acceptance gate

Core browser/test suite passes with extensions off; enabled extensions add the correct request allowance and preserve provenance. Each output explains measurement limits and records its own version/configuration. Live judging is unverified without a separately budgeted live run.

## 12. Phase 8 — Exports, documentation, packaging and release

**Goal:** reproducible installation and a complete truthful report, including offline demonstration.

### Work packages

- [x] **P8.1 — Export manifest:** versioned allowlisted JSON serializer containing experiment config/hash, dataset provenance/content hash/selected IDs, model and pricing snapshots, runtime/software versions, dates, attempts/outcomes, responses, scores/versions, human method/counts and enabled extension outputs. Mounted and redaction tested.
- [x] **P8.2 — CSV and reports:** CSV responses/metrics with explicit job/metric granularity and nullable fields; standalone escaped HTML report; readable Markdown academic report. One report-data builder keeps denominators consistent. Secret, XSS, unsafe-Markdown and CSV-formula tests pass.
- [x] **P8.3 — Offline demo:** explicit fixture provider, separate database, persistent “DEMONSTRATION — synthetic responses, no live API calls” banner, provenance in every response/report. Success is exercised end-to-end; wrong/malformed/quota/missing-usage/recovery cases are covered by separate backend fixtures. Fixture adapters cannot access reference answers.

Backend fixture execution slice implemented 2026-10-08: demo-only refresh exposes two labeled synthetic routes (`fixture/alpha-v1`, `fixture/beta-v1`), persists synthetic request/response provenance, enforces demo mode and exact synthetic snapshot evidence at start/claim/dispatch, and runs ten selected items as twenty jobs without live catalog HTTP. Both fixture routes deliberately return identical synthetic text; they are not model evaluations.
- [x] **P8.4 — Local/Compose release:** multi-stage frontend/API/worker image, one-shot migration, healthcheck, loopback-only API port, named volume and documentation. Compose demo ran 20 fixture jobs, exported, retained results across Compose down/up, and a SQLite backup/restore test preserved a completed experiment and response.
- [x] **P8.5 — Documentation:** README, methodology, provider evidence, development/operations/OpenCode, sample report and build ledger cover installation, keys, pricing, imports, running/recovery, metrics/review, exports, backups and limits.
- [ ] **P8.6 — Release verification:** backend/frontend checks, browser run/review/export, export sanitization, generated labeled sample, Docker build/Compose run and volume persistence pass locally. Conditional live experiment is unverified because credentials and two fresh eligible routes were not established; full release security/restore audit remains open.

### Export requirements and security

Every report includes:

- Selected gateway/model identities, requested/returned identity differences and upstream routing information when available.
- Start/end/export dates and partial/terminal state.
- Dataset name/source/license/version/hash, selected item IDs and sample size.
- System instruction, task rendering policy, effective generation settings, unsupported/omitted options, seeds/repetitions and attempt budgets.
- Scorer/parser versions, per-task metrics, numerators/denominators, common-item coverage and omitted data.
- Operational failures, pending/missing/truncated responses, unknown remote outcomes and timing/usage coverage.
- Human rubric/method, evaluator-label counts, applicable ratings and pairwise comparison counts.
- Extension methods, judge identity/bias/self-judging flags when relevant.
- Limitations: small convenience sample, possible benchmark exposure, evolving models, mutable provider routes, imperfect reproducibility, human/judge bias and local-only accounting.

Use explicit export schemas, never a database dump or settings dump. Headers, environment variables and raw credential-bearing exceptions are prohibited. Redact configured secret values if a provider response/error echoes them; test sentinel secrets across logs, APIs, stored safe metadata and every export. Do not retain unsanitized provider blobs for convenience.

HTML escapes all model/user text; React renders plain text by default. Markdown exports escape raw HTML and unsafe embedded links. No execution of model-provided markup. CSV quotes correctly and prefixes spreadsheet-dangerous text (including leading whitespace/control characters before `=`, `+`, `-`, `@`) as safe text; test model names, prompts, answers and comments, not only answer cells. JSON retains raw text subject to secret redaction; mark any export text transformation.

Reports may be exported mid-run, clearly labeled partial with pending counts. Demo reports cannot be confused with live measurements. Imported dataset redistribution limitations are retained in reports.

### Required documentation

- `README.md`: minimal install/start commands, demo vs live, key environment setup, first ten-item comparison, tests and Compose instructions.
- `docs/METHODOLOGY.md`: survey mapping, metric definitions, parsers, denominators, human rubric, experiment fairness and known limits.
- `docs/PROVIDER_NOTES.md`: dated official sources, endpoint maps, pricing allowlist/check policy, quota observations, policy links, fixture versus live evidence.
- `docs/DEVELOPMENT.md`: project layout, commands, migration practice, worker debugging, and practical OpenCode guide.
- `docs/sample-report.md`: generated fixture report with unmistakable labels and real fixture counts; no invented live run.
- `docs/BUILD_STATUS.md`: phase evidence, decisions, blockers, remaining extensions, exact resume instructions.

The OpenCode guide must recheck https://opencode.ai/docs/providers/, https://opencode.ai/docs/models/ and https://opencode.ai/docs/zen/. Explain `/connect`, `/models`, and currently documented model-selection syntax with supported examples. Distinguish the coding assistant's provider/model and credential store from application evaluation gateway/model IDs and server environment variables. Do not read the assistant's stored keys into the application or assume a model useful for coding is eligible/free for evaluation.

### Backup/restore contract

Use SQLite's backup facility or stop both API and worker and copy a consistent database. Do not copy only the main `.sqlite3` file during WAL writes. Restore to a separate test path and verify migrations, experiment counts, completed responses and resumable state. Include any required external assets/configuration while excluding secret values from academic exports.

### Release acceptance gate

1. Fresh local and Compose installations migrate and start; host exposure is localhost only.
2. Demo workflow selects two fixture models, runs ten shared questions, shows quota pause/recovery, scores answers, accepts blinded review and exports consistent reports.
3. Restart/volume recreation preserves completed work; restore verification succeeds.
4. Fixture labels and export sanitization pass browser/API tests; keys never enter frontend assets/storage.
5. With configured credentials and two currently verified-free routes: run an explicitly budgeted live comparison and record actual IDs, dates, counts and results separately. Without those prerequisites, mark live end-to-end verification blocked and preserve the experiment for later; do not mark final live demonstration passed.

## 13. Verification matrix and commands

Create runnable project commands in Phase 1; maintain them as the source of truth in README. Suggested interfaces (not yet executed):

```bash
# From backend/ using the project's documented environment
alembic upgrade head
pytest -q
python -m app.worker

# From frontend/
npm ci
npm run typecheck
npm run build
npm run test:e2e

# From project root
docker compose up --build
```

Browser tests use an isolated temporary DB, fixture mode and a real separate worker, with web-first condition waits instead of arbitrary sleeps. Routine tests do not contact paid or live providers. Live checks are opt-in, excluded from CI, and require known keys without printing them.

| Risk / feature | Minimum meaningful verification | Phase |
|---|---|---|
| Empty install / secrets | Fresh migration; invalid config; sentinel key leakage assertions | 1 |
| Free-only policy | Zero/nonzero/missing/override/expired evidence, route/endpoint exclusion, pre-dispatch refresh | 2 |
| Provider contracts | Normalization and exact outgoing payload tests per gateway | 2 |
| Imports / fairness | Invalid rows/duplicates/limits, stable hashes/sample IDs, reference isolation, incompatible settings | 3 |
| Request estimates | Base, retries/caps, per-account allocation and extension multipliers | 3, 7 |
| Queue safety | Duplicate start, competing claims, exhausted cap, crash windows, lease fencing | 4 |
| Rate limits | Retry-After/date, permanent error, cooldown, quota reset, manual cap | 4 |
| Evaluation | Hand-calculated scorers, format/truncation separation, scheduled vs completed denominators | 5 |
| Review | API/DOM blinding, both mappings, persisted order and unique ratings/votes | 6 |
| Browser core | Create/run/pause/resume/results/review with real fixture worker | 6 |
| Extensions | Pair preservation, item-level bootstrap, judge injection/parser/budget, off-mode regression | 7 |
| Exports | Same counts across formats, secret sentinel, XSS/Markdown and CSV payloads, partial labels | 8 |
| Packaging | Fresh Compose build, volume persistence, backup restore | 8 |
| Live integration | Separately logged, bounded real run or explicit unavailable/blocked state | 8 |

Tests should target invariants and failures, not mirror each implementation line. Use HTTPX MockTransport or equivalent fixture transport, temporary SQLite databases and an injected clock where useful. Keep browser coverage to a few high-value flows rather than duplicating every backend case.

## 14. Completion and handoff checklist

- [ ] All Phase 1–6 gates passed with evidence.
- [ ] Phase 7 extensions independently implemented/tested, or explicitly marked unfinished; no misleading enabled controls.
- [ ] Phase 8 exports, documentation, Docker/local installation, backup and browser gates passed.
- [ ] Every displayed result has live/fixture provenance and relevant denominators.
- [ ] Pricing, quota and endpoint claims cite dated evidence; no model availability invented.
- [ ] Remaining limitations and live-verification status are explicit.
- [ ] `docs/BUILD_STATUS.md` matches checked packages in this plan.

### Copyable Commander kickoff

> Implement LLM Comparison Lab using `plan.md` as the execution contract and `ai_project.md` as conceptual research background. First read applicable repository instructions, `plan.md`, and `docs/BUILD_STATUS.md`, then inspect the current files. Resume the earliest incomplete work package; do not rebuild completed work. Check the plan before each package, after verification, and before advancing phases. Keep package checkboxes and build-status evidence synchronized. Implement phase by phase, run each acceptance gate, report working functionality, verification and limitations, and continue when the gate passes. Use current official provider documentation, fail-closed free-only enforcement, a persistent separate worker, task-specific scoring and server-side blinded review. Without credentials use clearly labeled fixtures and record live verification as blocked. Delegate bounded non-conflicting packages if Commander supports it; retain integration ownership. Begin with P1.1 unless inspection proves it is already complete.
