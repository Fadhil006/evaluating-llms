# Build plan: reproducible evaluation release

## Target and baseline

Build in this nested `evaluating_llms-2.0/` Git repository, branch `new`, remote
`https://github.com/Fadhil006/evaluating-llms.git`. Baseline: `2769dff`.
Preserve the user's `.env.example` changes, live databases, credentials and sources.
The arena champion is a004 (seed 774418, final 90–87); its recommendation is
the basis for this plan, not evidence that its examples or implementation details
are correct. Commit and push each verified work package. Never stage local run data.

## Research and scope

Use the five sources in `RESEARCH_FOR_ARENA.md`: the original survey for scope,
HELM for comparable multi-metric evidence, IFEval for verifiable constraints,
Dror et al. for design-matched inference, and Zheng et al. for blinded review and
bias awareness. These are adaptations, not benchmark replications.

Ship explicit split/family provenance, bounded instruction checks, immutable
local analysis snapshots, complete-family paired uncertainty, descriptive review
overlap, and matching UI/exports. Reuse the current FastAPI/SQLite/React stack.
Defer LLM judges, executable code, ranking systems, concurrency changes and live
study execution. No model/provider calls are authorized by this build.

## Corrections to the champion before implementation

- Its synthetic example contradicts itself: with F2's variant and both F3 keys
  absent, B has **three**, not four, eligible answers. Tests use explicit rows.
- Preserve historical metric versions and the existing truncated-answer exclusion
  for legacy metrics. The new instruction-check analysis may inspect truncated
  text under its explicitly versioned policy, reporting truncation separately;
  do not silently change all historical task denominators.
- The proposed 40-family suite cannot be honestly called independently reviewed
  by agents inventing reviewer labels. Author it as a **draft** with 12 dev,
  eight calibration and 20 test families; require real review records before a
  held-out live study. Never promote old demo data to held-out status.
- Smoke and pilot requests cannot be assumed reusable across separately frozen
  runs. Budget them separately unless the exact same resumable run is used.

## Ordered work packages and acceptance

### P0 — baseline reliability

Reproduce the backend suite and browser test in the relocated environment. Fix
review assignment metadata to use the chosen item key. Make price-dependent
tests deterministic without extending real pricing expiry. Fix the evidenced
Pause selector problem. Tests must cover multiple item/repetition keys and
expired pricing remaining blocked. Commit after targeted checks pass.

### P1 — dataset and instruction contracts

Extend existing item schema/importer with explicit split, globally namespaced
family ID, variant ID and structured provenance/review metadata. Add an additive
migration; old rows remain `legacy_unknown`. Check known family split crossings
and normalized prompt/context/choices leakage across dataset versions, including
legacy rows. Same-split immutable reimports can remain legal; cross-split reuse
must not be disguised by new IDs/references. Validate family reference/scorer
compatibility and reviewed variants. Keep item text as the actual prompt.

Add strict required/forbidden substring and exact-word-count checks alongside
existing exact-text/JSON checks. Version scorer changes, retain per-check evidence,
and report all-check and pooled-check accuracy distinctly. Validate config types,
Unicode/case semantics, empty checks and boundary counts. Draft dataset generation
must be reproducible and labels must not imply completed independent review.

### P2 — immutable analysis

Add an append-only analysis record containing manifest, result snapshot and hash.
An explicit POST computes local analysis; GET/list/export never rescore or call
providers. Preserve accepted responses and past snapshots. Manifest pins experiment,
dataset, selected model slots, response/metric provenance, scorer/check versions,
family mapping, sampling seed, 10,000 bootstrap draws and software version.

Analyze each task/metric separately. Primary comparison uses identical complete
planned keys for both models in each family, equal-family weighting and paired
resampling. Repeats/variants never increase independent n. Show missing keys,
original-only contrasts and paired original/variant changes separately. Withhold
intervals below ten complete families; mark constant differences degenerate.
Intervals are conditional/exploratory and cannot cure selective missingness.
Do not manufacture family independence for legacy data lacking family metadata.

Tests: explicit missingness example, swapped signs, repeated-key invariance,
zero/one/constant families, historical snapshot stability, no GET writes, and
old-schema migration preserving existing rows.

### P3 — review, UI and reports

Fix selected-row review metadata, retain blinded order and prevent duplicate votes.
Expose descriptive overlap/agreement grouped by actual candidate pair, rubric and
reference condition; normalize A/B choices back to response identities. Show
cannot-judge and identity-suspected counts, local-label limitations and no reliability
claim. Select review item IDs before outcomes in experiment configuration when
creating a review campaign; existing ad-hoc review remains labeled as such.

Add analysis creation/selection/display to ResultsPanel and immutable exports
through the existing API. UI and exported JSON/report must use the same stored
snapshot and expose family n, omissions, conditions and synthetic/live provenance.
Preserve CSV escaping and existing exports. Browser acceptance covers creating,
reloading and exporting an analysis using fixture responses only.

### P4 — verification and handoff

From `backend/`: `.venv/bin/python -m pytest -q` and
`.venv/bin/ruff check app tests alembic scripts`.
From `frontend/`: `npm run typecheck`, `npm run build`, `npm run test:e2e`.
Use disposable test DBs; never migrate the live DB during verification.
Document actual checks, remaining human dataset review, live-study authorization
and current limitations. Push verified commits to `origin/new` without force.

## Live study gate (later, not part of this build)

Independent reference/variant review, frozen protocol, fresh route/access checks
and explicit authorization precede dispatch. Example: 2 models × 20 test families
× 2 variants × 1 repetition = 80 first attempts, plus eight reserved retries.
Dev smoke and pilot are additional unless explicitly resumed within the same run.
All fixture results are synthetic. No general model ranking follows from this
convenience sample; no confidence interval establishes representativeness.
