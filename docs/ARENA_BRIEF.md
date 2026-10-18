# Arena brief: make LLM Comparison Lab 2.0 a credible evaluation tool

Prepared: 2026-10-17. Status: **input to a future planning tournament; four contenders recommended for a five-hour usage window**. No tournament winner or implementation is claimed by this document.

## 1. User objective and handoff

The user wants to improve `evaluating_llms-2.0` through an in-depth research-backed plan, with clear attribution of which research papers contribute which methods. The original request envisioned ten competitors; the revised recommendation is four to conserve a five-hour subscription allowance, with a reduced five-paper reading list. Competitors independently construct proposals, attack and defend them, and yield one winning proposal. The winner is then expanded into the plan used for implementation.

**This tournament produces design artifacts, not competing application rewrites.** Each contender constructs a complete solution proposal: scope, scientific protocol, architecture delta, worked analysis example, verification plan and phased delivery. Source changes happen only in the later build stage.

The contenders are planning agents, not a requirement for the application's number of benchmark endpoints. The existing arena harness normally uses instances of one configured model with different strategy cards, not distinct model families. Record the actual model/configuration used. Different model IDs require explicit orchestration support rather than claiming diversity that was not used.

### Copy/paste launch request for later

Run from `/home/fadhil/Projects/evaluating_llms-2.0`:

```text
/arena --agents 4
Use docs/ARENA_BRIEF.md as the complete task and docs/RESEARCH_FOR_ARENA.md
as its required research companion. Read both before constructing the common
task. Run a planning-only tournament: four independent proposals, adversarial
critique, defense/revision and independent judging. No application edits,
live model evaluation calls, provider-account checks, or Graphify runs.
After selecting the champion, have the winner produce the build-plan handoff
specified in section 10. Do not implement the plan in this tournament.
```

The orchestrator must embed this brief and the research companion in the common task or attach identical immutable copies, preserving the same requirements for every contender. Record the target repository commit and dirty-tree state before the tournament. If this brief becomes stale, record baseline changes in a shared addendum before spawning competitors.

### Subscription-window sizing

For the installed workflow, N initial proposals plus two attacks, two defenses and one judge per elimination match gives **6N − 5 agent invocations**, excluding failures/retries and the winner's final build-plan expansion. Four contenders require 19 calls; six require 31; ten require 55. These are orchestration counts, not billable-message or token estimates. Reserve allowance for the final plan and verification. Four is a conservative recommendation, not a guarantee of fitting the remaining quota or finishing within five hours.

OpenAI's plan documentation says usage varies with model, task complexity, context and other factors: <https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan>. No verified GPT-6 Luna-specific quota is assumed here. Check the actual account usage dashboard and the authentication path used by the harness; API-key usage is not the same allowance as subscription-backed usage. Do not infer that a reset window is five hours of continuous compute.

## 2. Project, constraints and baseline evidence

**Target:** `/home/fadhil/Projects/evaluating_llms-2.0`.

**Reference only:** `/home/fadhil/.codex/.chatgpt-projects/evaluating_llms` is the older/simpler working copy. Do not accidentally implement there or treat root legacy prototype features as current-backend features.

- Inspected baseline: branch `new`, commit `2769dffe4d717ec355e8a6919b46cd28afaf6ef3`.
- Pre-existing user change: `.env.example`. Preserve it. Do not inspect credential values or modify live databases.
- Read `AGENTS.md`. Keep `sources/` read-only. Root `app.py`, `evaluation/`, and root `protocol.md` describe the preserved Flask/CLI prototype; the active app uses `backend/`, `frontend/`, and `docs/METHODOLOGY.md`.
- Current stack is sufficient: FastAPI, SQLAlchemy/Alembic, SQLite durable worker, React/TypeScript/Vite. Reuse it unless a concrete demonstrated limitation requires a narrowly justified change.
- Keep fixture/demo mode useful without network access. Do not authorize live requests implicitly through a test or research task.
- Maintain free-route enforcement, quota checks, request caps, identity checks, failure visibility and uncertain-attempt handling. Do not disable guards to make a demonstration pass.
- Earlier inspection found a local 20-response live smoke experiment over ten convenience items, with a format failure and truncation. It is not a broad benchmark or evidence that all routes currently work.
- Previous comparison in the user conversation reported backend 78 passed / 3 failed, frontend build/typecheck passed, and an E2E failure. Its full command-output record is not stored in this repository. These are dated external reports, not results from this planning pass. Reproduce them before fixing them.

### Existing implementation map

| Concern | Existing locations | Existing capability / relevant gap |
|---|---|---|
| Dataset import | `backend/app/services/datasets.py`, `backend/app/models.py` | CSV/JSONL validation, canonical hashes, bounded imports and versions; current schema lacks explicit split/base-family contracts |
| Design and lifecycle | `backend/app/services/experiments.py`, `backend/app/services/experiment_lifecycle.py` | Frozen configuration, model slots, selected items, repetitions, bounded attempts, interleaved jobs, lifecycle controls |
| Durable execution | `backend/app/worker/runner.py` | Leases, single-flight dispatch, recovery, retries and pauses; do not rebuild this as a new queue |
| Scoring | `backend/app/evaluation/scoring.py` | Versioned deterministic task scorers; instruction checks currently exact text / exact JSON |
| Results | `backend/app/services/results.py` | Scheduled/eligible/common-completed denominators, quality, failures, route latency and usage; no uncertainty estimates or family robustness analysis |
| Human evaluation | `backend/app/services/review.py` | Blinded assignments, A/B order, rubric and pairwise submissions, raw-count summaries; no review reliability campaign or agreement analysis |
| Reports | `backend/app/services/exports.py` | JSON/CSV/HTML/Markdown with provenance and output escaping; extend existing formats |
| Data / migrations | `backend/app/models.py`, `backend/alembic/versions/` | Preserve existing experiments and metric history with additive migrations |
| UI | `frontend/src/Experiments.tsx`, `frontend/src/ResultsPanel.tsx`, `frontend/src/HumanReview.tsx` | Existing design/results/review workflows to extend |
| Verification | `backend/tests/`, `frontend/tests/e2e/demo.spec.ts` | Existing offline unit/integration/browser coverage |
| Documentation | `docs/METHODOLOGY.md`, `docs/BUILD_STATUS.md`, `docs/PROVIDER_NOTES.md`, `docs/DEVELOPMENT.md` | Separate implemented behavior, historical observations, proposals and measurements |

### Baseline issues to investigate first

1. `backend/app/providers/zen_pricing.py` has evidence expiring 2026-10-15. On the planning date it is stale. Stale production evidence should fail closed; deterministic tests need controlled evidence/time. Do not simply move a production expiry into the future.
2. The earlier browser run reported an ambiguous Pause selector. Reproduce the failure and distinguish selector ambiguity from queued-worker/lifecycle behavior. Fix only the evidenced cause.
3. In `backend/app/services/review.py`, inspect assignment metadata: the selected `item_key` is used for the item, but `presentation` uses loop variable `key` for repetition/variant. Verify with multiple families/repetitions before classifying or fixing the suspected mismatch.
4. Results currently select the current scorer version, and local score recovery can add scores while reading. Plan an explicit analysis/scorer-version selection policy so future scorer upgrades cannot silently change the apparent historical conclusion.

## 3. Target outcome and priorities

The next release should let a user conduct a **small, reproducible, statistically honest, task-specific comparison** and explain exactly what its evidence supports. Success is not adding every benchmark or making the UI look like a public leaderboard.

Required outcomes of every proposal:

1. Repair/reproduce baseline regressions without weakening production protections.
2. Make dataset split, item-family grouping and source/version provenance explicit in the current backend.
3. Make comparisons reproducible under declared scorer/analysis versions, with independent sample counts and uncertainty/missingness policies.
4. Offer a justified research-backed evaluation improvement beyond infrastructure. Strong candidates are richer verifiable instruction checks, controlled prompt perturbations and review reliability; choose a feasible combination.
5. Make the new evidence understandable in the existing UI and exports.
6. Specify the path from offline acceptance to a separately authorized live pilot and a final held-out study.

Recommended sequence: **reliable baseline → data/analysis contracts → one objective evaluation track plus robustness/review → optional calibrated judging**. This is a starting recommendation, not the winning answer. Contenders may propose a better sequence with explicit dependency and validity arguments.

### Scope decisions the arena must make

- Which first benchmark subset has the strongest fit with existing scorers, licensing, budget and user value? Name a concrete candidate and alternative; verify before selecting.
- What new original held-out data are needed, and who reviews references/perturbations?
- How many independent base items, variants and repetitions are affordable? Show a cost/precision tradeoff rather than a magical sufficiency threshold.
- Which uncertainty method is appropriate for each metric? Which cases should be descriptive only?
- How much review coverage is feasible, and when can reviewer agreement be estimated honestly?
- Should an LLM judge be in this release, optional afterward, or deferred? Explain using calibration quality and request cost.
- What evidence would justify a later executable coding track? Keep it deferred in this bounded release.

## 4. Scientific and data contracts to design

Sections 4.1–4.3 are core contracts. For the evaluation tracks in 4.4–4.7, fully specify those selected for the release; for unselected tracks, provide a clear deferral reason and future entry criterion. The presence of a section does not require implementing every track.

### 4.1 Dataset manifests and split protection

Define explicit semantics for dataset version/hash, external source item ID, source URL/revision, license, acquisition date, task, references, scorer configuration, base-family ID, variant ID/type, split and review status. Reuse existing fields before adding new ones; provide a field-level delta.

- Use separate dev, judge-calibration (if needed), and held-out test assignments. All variants/near-duplicates belonging to one known family remain in the same split.
- Preserve imported benchmark IDs, exact subset selection and upstream scorer/version compatibility. Distinguish project-authored, adapted and imported items.
- Check exact/normalized duplicate leakage across applicable dataset versions, not only inside one uploaded file. Define the limits of detecting paraphrase/semantic leakage.
- For existing rows without provenance/split/family metadata, preserve an explicit legacy/unknown status. Never retroactively label already inspected data “held-out.”
- Review item/reference correctness before target-model evaluation. Freeze selection and exclusions before looking at held-out outcomes.
- No giant data ingestion platform is required: a manifest plus the existing importer may suffice.

### 4.2 Experiment, response and analysis identity

Separate generation identity from analysis identity. Reanalysis must not trigger generation, mutate the original response, erase old metric versions, or silently replace an earlier published report.

Describe how an analysis identifies: frozen experiment config/dataset/selected items, scorer and normalization versions, metric, selected model slots, eligible/common keys, family mapping, repeated-generation policy, uncertainty settings and software revision. Pin a hash or immutable analysis record. Define compatibility with old experiments.

Do not assume a hosted model ID freezes its weights. Preserve route identity, supported/unsupported generation controls, request dates and returned provenance. The local random seed governs selection/resampling/order only where implemented; it is not a guarantee of remote deterministic generation.

### 4.3 Metrics, missingness and paired inference

For each metric specify the numerator, denominator, range/direction, unit of analysis, eligibility rules and claim limits. Distinguish:

- Conditional task quality among eligible answers.
- Scheduled-job operational success/coverage and failures.
- Matched/common-completed comparisons and omitted keys.
- Robustness deltas across variants within base families.
- Human preference, rubric ratings and judge preference as different outcomes.

Retain incomplete, truncated, malformed, identity-mismatched and unscored cases with explicit policies. Do not improve apparent accuracy by hiding malformed completed answers. Do not turn transport failures into invented factual errors. Keep the existing distinction between conditional quality and scheduled-job success.

**Recommended inference candidate:** paired cluster resampling at independent base-family level, with repeats/variants kept inside each cluster. Contenders must define weighting (equal-family vs equal-item), repeated-generation aggregation, stratification, missing families and estimand. Use the same sampled families for both models. Preserve pairing; do not independently bootstrap model A and B.

If macro-F1 is included, compute it from resampled confusion information over the declared label set. A mean of row-level F1 is not macro-F1. Do not automatically pool incompatible tasks or scorers into an overall quality score.

Specify confidence level, reproducible resampling seed/count, degenerate cases, small independent sample warnings, and conditional interpretation. Repeated generations do not create new independent questions. A matched CI does not remove selection bias from failed routes. No universal “winner” badge based on an arbitrarily narrow interval. If testing many contrasts, preregister a primary contrast or give a multiple-comparison policy.

### 4.4 Instruction-following evaluation

Use R2 to propose a bounded allowlist of verifiable constraints appropriate to the existing scorer. For each, define exact checking semantics and retained per-check evidence.

Report prompt all-check pass rate separately from pooled instruction-level pass rate and per-type results. A mean of per-prompt fractions gives different weighting from pooled instruction accuracy; name the statistic actually used. Define how missing responses affect each conditional/scheduled denominator.

Official IFEval replication is optional. A small adapted suite must carry its own name and protocol version. Keep strict and any loose evaluation separate.

### 4.5 Robustness families

Use R1's robustness motivation and R3's statistical-design principles for a small local set of meaning-preserving perturbations. Explain how task/reference equivalence is reviewed and stored. At minimum report original quality, variant quality, paired delta, correct→incorrect and incorrect→correct changes, complete-family count and omissions. Keep lexical stability distinct from answer correctness; do not claim a named robustness benchmark replication.

The existing generation job's `variant` field is not proof that semantically reviewed prompt variants already exist. Trace actual prompt construction and family provenance; reuse fields only when their semantics match.

### 4.6 Human-review reliability

Extend the existing service rather than replacing it. Define review campaign sampling, task-specific anchors, overlapping assignments, reference visibility, stable stored A/B mapping, repeated-rater handling, tie/cannot-judge handling and identity-suspicion handling.

Select an agreement statistic appropriate to the design or explicitly use descriptive agreement until enough overlap exists. Report sample counts and uncertainty/limitations; raw percentage agreement is not chance-corrected reliability. Independent local labels are not verified independent humans. No public authentication system is required for this local research workflow.

Show how review remains auditable after refreshing the page and exporting results. Prevent mixing rubric versions or reference-visible and reference-hidden conditions in a single unlabeled average.

### 4.7 Optional LLM judge and coding tracks

An LLM judge proposal must address R4: immutable candidate responses; versioned judge model/rubric/reference policy; swapped order; inconsistent versus tie versus cannot-judge; length and self-preference diagnostics; untrusted-answer injection; malformed output; separate judge call budget and attempts; independent human calibration and a go/no-go criterion fixed before test outcomes. Regression-based length adjustment is deferred.

Calibrate on disjoint families from the final judged evaluation; show calibration agreement by task and uncertainty, not only an aggregate. A default “80% agreement” copied from a paper is not a justified threshold. If judge suitability cannot be established, ship human review/objective scoring and report judging as unavailable.

Executable coding evaluation is deferred from this release. Retain any coding proxies as proxies and make no functional-correctness claims from syntax checks. A later execution track needs a separately researched test/isolation design.

## 5. Work packages and expected integration points

Each contender must turn these into a dependency-ordered release plan with concrete file-level changes, acceptance criteria, effort ranges and evidence gates. Do not add files just to match this table.

| Package | Likely integration points | Acceptance evidence |
|---|---|---|
| P0: establish stable baseline | Provider tests/`zen_pricing.py`, worker tests, `review.py`, `frontend/tests/e2e/demo.spec.ts` | Reproduced causes, deterministic tests, expired evidence still blocked; selected review item/repetition/variant remain aligned on a multi-family, multi-repetition fixture; no undocumented provider calls |
| P1: provenance/family/split contract | `models.py`, Alembic migrations, `services/datasets.py`, importer tests, experiment validation | Old DB migrates safely; duplicate/family leakage rejected; old data stays explicitly legacy/unknown |
| P2: pinned analysis and uncertainty | `services/results.py`, scorer/version policy, a small analysis helper if needed, result/export tests | Hand-checkable paired examples, stable analysis manifest, honest null/degenerate behavior |
| P3: selected evaluation tracks | `evaluation/scoring.py`, dataset manifest/content, experiment prompt construction, review service | Constraint boundaries, validated variants, matched denominators, review audit/overlap checks |
| P4: UI and report integration | `ResultsPanel.tsx`, `Experiments.tsx`, `HumanReview.tsx`, `services/exports.py` | UI/export agree on sample units, values, intervals, exclusions and provenance |
| P5: offline release and study protocol | Existing fixture/demo system, backend/browser tests, methodology/build/provider docs | Reproducible offline walkthrough plus a separately budgeted and authorized live-study protocol |
| Optional: calibrated judge | Existing provider/worker conventions and separate result records | Calibration gates pass before any corresponding quality claim |

SQLite and global single-flight may remain adequate. The planning tournament's contender count does not justify expanding backend concurrency. Any proposal for concurrency must quantify the actual workload and show quota/lease correctness, not introduce Redis/Celery or another database speculatively.

## 6. Request budget and study stages

Every proposal includes at least one fully worked request budget:

```text
generation first attempts = models × base items × variants per base × repetitions
judge first attempts = judged response pairs × orderings × judge repetitions
total maximum dispatches = generation first attempts + judge first attempts
                          + explicitly reserved retry attempts
```

These are generation/judging dispatches. Budget catalog refreshes, account checks and other metadata requests separately using the existing estimator where applicable. If variants/items vary, compute the sum from the actual selected manifest. Human review is measured in assignments/rater time, not provider calls. Token limits, provider daily quotas, context limits and route availability are additional constraints; a free label does not guarantee capacity.

Illustrative arithmetic, not a mandated sample size: 2 models × 30 base items × 2 variants × 2 repetitions = **240 generation requests**. Judging every corresponding model pair in both orders adds 30 × 2 × 2 × 2 = **240 judge requests**, before retries. A judge is not free operationally just because its price is zero.

Require separate stages:

1. **Offline fixtures:** scorer, analysis, lifecycle and report correctness; no model-performance claim.
2. **Dev smoke:** smallest explicitly authorized dispatch to verify routes and persisted provenance; excluded from held-out conclusions.
3. **Calibration/pilot:** estimate feasible workload, refine rules/rubrics on non-test families; freeze the final protocol afterward.
4. **Held-out study:** fixed selection/settings/analysis and explicit maximum attempts; preserve incomplete outcomes and resumable state.
5. **Reanalysis/report:** no new requests; publish observed limits, exclusions and evidence classification.

Give small/medium budget options with tradeoffs, not a claim that a fixed number of items is universally enough. Under a tiny quota, prefer fewer methods evaluated honestly over many underpowered feature demonstrations.

## 7. Required contender artifact

Each independent proposal must include:

1. Executive decision: intended user outcome, recommended scope and non-goals.
2. Verified current-state map and assumptions/unknowns, including drift from this brief.
3. Paper-to-feature matrix using the five sources R0–R4, distinguishing replication/adaptation/motivation. Keep the reading list bounded; identify new research needs as deferred work rather than adding papers during the tournament.
4. Dataset/split/family design, benchmark selection, licensing check and sample-budget options.
5. Precise metrics/inference/review protocol, including missingness and honest interpretation.
6. Minimal architecture delta, field/API/export changes, migration/backward-compatibility strategy and alternatives rejected.
7. A worked synthetic example with at least two models, unequal completion and repeated/variant items. Show independent-family count, a matched difference and exclusions. Label it synthetic; it is a proof of analysis logic, not model evidence.
8. Dependency-ordered phases, rough effort ranges and scope-cut order; no fabricated calendar deadline.
9. Meaningful offline acceptance tests and separate live-study protocol/cost estimate.
10. At least five concrete failure modes, mitigations and unresolved decisions.

Unexecuted code snippets/diffs may illustrate a contract; mark them untested. Do not replace precise behavior with a large speculative implementation dump.

## 8. Tournament procedure

Use the installed arena harness's bookkeeping and generated strategy cards. All proposals start from the same frozen brief, research companion and baseline evidence. Do not hand one contender a preferred answer or unequal private context.

- Independence: four first-pass artifacts before cross-examination under the recommended configuration. Record actual agent/model identity, strategy assignment and seed when supported.
- Bracket: four contenders produce three elimination matches over two rounds. If explicitly changed to ten, there are nine matches over four rounds with byes. Follow harness scheduling rather than inventing results or changing pairings to favor a proposal.
- Each match: both sides attack the other's artifact; both defend/revise; an independent judge scores the revised artifacts. The orchestrator does not pick the winner.
- Attacks must identify a factual error, missing requirement, counterexample or ambiguity with a source/path/quotation. No points for stylistic hostility.
- Defenses fix the artifact or explicitly concede/defer the issue. Preserve a short change log and surviving risks.
- Judges evaluate evidence, feasibility and the rubric below; proposal verbosity and citation count earn no independent points.
- If both proposals fail critical gates, neither is build-ready. The procedural winner must repair the gap and receive independent re-review before the final build plan is accepted. A tournament cannot manufacture a valid solution by elimination alone.
- Arena writes remain in its designated `.arena/` directory, to be created by the harness during the future tournament; it is not an existing application directory. No application modifications, shared mutable prototypes or live benchmark calls. After completion, copy only approved planning artifacts into `docs/` if requested.

### Weighted judging rubric: 100 points

| Criterion | Points | What earns the score |
|---|---:|---|
| Scientific validity | 25 | Correct estimands/units, paired comparisons, dependence/missingness handling, honest conclusions |
| Grounding in the actual repo | 20 | Reuses working modules, distinguishes legacy/current behavior, addresses evidenced gaps |
| Research fidelity | 15 | Accurate primary citations, explicit adaptations, no borrowed performance claims |
| Implementation feasibility | 15 | Concrete migrations/contracts, dependencies, budget and bounded release scope |
| Verification and reproducibility | 15 | Hand-checkable examples, failure tests, versioned artifacts and offline/live separation |
| User clarity and maintainability | 10 | Understandable reports, minimal architecture, explicit omissions and upgrade triggers |

Critical gates: fabricated evidence/citations, counting correlated repeats as independent questions, silently mixing unmatched populations or metric versions, treating synthetic scores as measured, modifying held-out rules after seeing outcomes, or bypassing live dispatch protections prevents build-ready status regardless of total score. Judge severity based on the actual proposal, not a keyword checklist.

Tie-break order: scientific validity, repository grounding, verification, then lower justified maintenance/request cost. An unresolved substantive tie requires an independent tie-break judgment, not an orchestrator preference.

### Required adversarial scenarios

Judges and attackers should test relevant proposals against these concrete cases:

1. A responds to 100 items; B responds only to its easiest 20. An apparent common-set win must not imply a full-sample win.
2. Five base questions each have 20 repeats and two variants. This is five independent item families, not 200 independent questions.
3. A “paraphrase” changes a number, negation or answer-label mapping. It cannot be treated as an invariant perturbation without validation.
4. A held-out family arrives via a second dataset import under new IDs; its normalized text duplicates dev data.
5. One prompt has ten checks and another has one; pooled check accuracy and mean prompt fraction differ.
6. A scorer upgrade changes normalization; viewing/exporting an old experiment must disclose which analysis/version is shown.
7. A reviewer refreshes, submits twice, or rates under two labels; order and vote provenance must remain auditable. Selecting a candidate other than the final iterated family must retain that selected candidate's item/repetition/variant metadata.
8. Swapped-order judge results disagree; a longer wrong answer wins; answer text instructs the judge to vote for itself.
9. Price evidence expires halfway through a resumable run; an HTTP timeout occurs after remote dispatch but before response persistence.
10. An old database lacks splits/families, a sample has zero common items or one family, or all binary answers are identical. Migration/statistical behavior must be defined.

## 9. Verification the eventual build plan must require

Existing commands (confirm against repository instructions at execution time):

| Working directory | Command |
|---|---|
| `backend/` | `.venv/bin/python -m pytest -q` |
| `backend/` | `.venv/bin/ruff check app tests alembic scripts` |
| `frontend/` | `npm run typecheck` |
| `frontend/` | `npm run build` |
| `frontend/` | `npm run test:e2e` |

Use disposable test databases and fixture adapters. Define migration upgrade/compatibility checks on an old-schema copy, not the live study database. Run preserved root prototype tests only if shared/prototype code is affected.

New tests should prove new contracts, not mirror implementation: leakage across versions, family-preserving resampling, unequal-check denominators, scorer-version preservation, blinded review metadata, expired evidence, missingness and UI/export agreement. Use tiny hand-computable inputs; no framework replacement.

The build report must distinguish commands actually run, their results, skipped/blocked checks, test-generated synthetic artifacts and any separately authorized live measurements. A historical passing test count is not current verification.

## 10. Winner's final build-plan handoff

After the bracket, the champion must turn its revised solution into a standalone **BUILD_PLAN_NEXT.md** in the arena output directory. It must incorporate valid surviving critiques from all rounds and clearly choose one coherent design rather than concatenate losing proposals.

Required structure:

1. **Decision summary and scope:** what ships, what is deferred, and why.
2. **Baseline:** exact commit/dirty state, inspected modules, known failures, assumptions needing recheck.
3. **Research traceability:** paper → method → adapted requirement → target files → acceptance test → limitation.
4. **Protocol specification:** data selection, split/family policy, model conditions, scoring, missingness, uncertainty, review and optional judge.
5. **Data/API contracts:** field-level changes, defaults, constraints, versioning, compatibility, import/export examples; mark newly proposed files explicitly.
6. **Ordered work packages:** for each, rationale, files, concrete changes, dependencies, failure cases, acceptance checks, effort range and stop/go gate.
7. **Migration/recovery:** preservation of old runs, explicit legacy metadata, safe upgrade testing, non-destructive recovery strategy and scorer/report compatibility.
8. **Validation plan:** offline examples/tests first, then opt-in dev/calibration/held-out stages with budget arithmetic and stopping rules.
9. **Reporting contract:** visible metrics, denominators, independent sample count, uncertainty/limitations, provenance and truthful claim examples.
10. **Risks and deferred work:** minimum useful release, cut order, requirements for later judge/coding/large-scale ranking work.
11. **Builder checklist:** ordered actionable steps and exact finish criteria, suitable for a separate implementation agent without reconstructing the tournament.
12. **Resolved debate log:** major attacks, accepted corrections and remaining limitations; include independent final acceptance verdict.

The tournament winner is the preferred **design under this rubric**, not proof that a particular evaluated LLM is superior. Implementation begins only in a separate build invocation. No benchmark result, paper replication or capability claim becomes true merely because the plan won.
