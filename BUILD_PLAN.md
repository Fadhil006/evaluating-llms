# Build Plan

## Active Scope: Credible Demo in Seven Days

This section supersedes the longer release schedule below. The remaining sections
are a future roadmap, not requirements for the one-week demo.

**Deliverable:** a local dashboard comparing two named text/instruction models on
numerical reasoning and objectively checkable instruction following, including
paraphrase robustness, saved raw answers, scoring explanations, and JSONL/CSV
exports. No training or fine-tuning is needed.

### Experiment size and credibility

- Prepare 10 separate development examples and 30 evaluated base questions
  (15 per category), each with one reviewed paraphrase: 60 evaluated prompts.
- Two models and one repetition require 120 evaluated requests, excluding
  development, smoke tests, and retries. This is a small exploratory evaluation,
  not a statistically strong general ranking.
- Freeze evaluation questions and scoring rules before inspecting their model
  outputs. Keep development examples separate. Log changes as new versions.
- Verify reference answers and pair meaning manually. Have a second person check
  them if available; accurately report who reviewed them.
- Numeric answers use declared normalization and tolerances. Instruction checks
  cover explicit rules such as required JSON fields or forbidden terms; do not
  equate format compliance with general intelligence or factual correctness.
- Report category scores, paired original-minus-paraphrase accuracy in percentage
  points, complete-pair counts, request failures, and end-to-end latency separately.
- Save prompts, raw answers, errors, dataset hash, model identifiers, routing,
  settings, timestamps, scorer version, and code commit. Explain that one run does
  not measure output variability and temperature zero is not determinism.
- Manually inspect all 120 evaluated outputs. Keep original automatic scores and
  record review notes separately; do not silently repair scores after seeing results.
- Demonstrate 2–4 live requests plus the full saved real run. Label saved results
  and offline mock data clearly; never present mock responses as measured evidence.

### Provider decision

**Recommended:** two fixed, inexpensive instruction/chat models through OpenRouter,
ideally from different model families. Select exact available IDs and endpoints on
day 1, after checking prices and output quality on development items. Do not use
an automatic model selector for comparison runs. Set one provider per model,
disable fallback, require supported parameters, and record actual routing where
available. A model alias is not a guarantee of immutable hosted weights.

Strictly free alternative: two explicitly named OpenRouter `:free` models, with
availability checked first and a multi-day request schedule. Official limits at
planning time are 20 requests/minute and 50 free requests/day for accounts with
less than $10 purchased credits, or 1,000/day after at least $10 purchased credits.
The 120-request evaluation alone needs at least three daily quotas on the lower
tier; development and retries need additional capacity. Recheck account limits.

OpenCode is the development assistant, not the evaluation runner. OpenCode Zen
also exposes model APIs and could be integrated directly, but a coding-agent run
adds system prompts, tools, and context that change what is being evaluated. Do
not assume access in the editor implies a reusable API entitlement or stable free
capacity. A Zen integration is not needed for this deadline.

Local inference through Ollama is an alternative if suitable hardware and models
are already available. Otherwise downloads, memory limits, and inference speed
add deadline risk. Select local model sizes only after checking RAM/VRAM; record
model digest, quantization, runtime, and hardware. Do not present local-versus-cloud
latency as a pure model-speed comparison.

Use a user-approved spend cap for hosted requests; estimate it from measured pilot
tokens and current prices before the full run. No exact model price or dollar
budget is assumed. Zero-budget access is a constraint, not evidence of poorer
scientific validity: fixed inputs, traceable outputs, and honest claims matter.

### Seven-day execution plan

| Day | Build | Done when |
|---|---|---|
| 1 | Confirm provider/budget; write protocol, minimal Python setup, ignore rules, dataset schema, development examples | Offline validation works; two model IDs selected; small live access check succeeds |
| 2 | Author and verify 30 base items plus paraphrases; implement numeric and rule scorers | All references and pairs reviewed; known correct/wrong/malformed outputs tested; evaluation data frozen |
| 3 | Implement sequential runner, bounded retry, per-response persistence, resume, and offline provider stub | Interrupted run resumes without duplicating completed records; errors and truncations remain visible |
| 4 | Add paired analysis and run real evaluation | Summary matches hand-calculated examples; real responses saved; free-tier runs begin earlier if required by quotas |
| 5 | Build a small Streamlit dashboard: overview, model comparison, answer inspection, export | Dashboard reproduces saved summaries without calling a model on refresh |
| 6 | Inspect outputs, record scoring disagreements, finish evaluation and documentation | Every output reviewed; limitations documented; clean setup and offline checks pass |
| 7 | Freeze demo version, rehearse live smoke run, prepare report and saved-result fallback | Another person can inspect or reproduce the workflow; real saved results remain usable without network |

**Demo architecture:** Python runner + JSONL run artifacts + a Streamlit viewer.
Use one run directory with immutable configuration, append-only response records,
and generated summary/export files. No SQLite, hosted deployment, accounts,
background service, model training, LLM judge, or UI-launched jobs in this week.
Keep manual review notes in CSV. Knowledge and evidence-based answering move to
the later release; the runnable two-category experiment is the week-one goal.

**Immediate decisions:** zero budget or a small paid allowance; hosted or already
working local inference; availability of a second reviewer. If undecided, proceed
with offline runner development and OpenRouter as the proposed live integration.

Provider references (limits and availability must be rechecked before execution):
- https://openrouter.ai/docs/api/reference/limits
- https://openrouter.ai/docs/guides/routing/provider-selection
- https://opencode.ai/docs/zen/
- https://docs.ollama.com/api/introduction

## Longer-Term Roadmap

This is an implementation proposal, not a report of completed work. The
repository currently has documentation only; no commands below are runnable
until the corresponding files and dependencies are created. Files under
`sources/` are read-only reference material.

## Goal

Build the evaluation application described in `implementation_plan.md`, beginning
with the smallest reproducible experiment for the question:

> Does paraphrasing change an LLM's answer accuracy?

Start with one objectively scorable text task, one model, and ten original
questions paired with meaning-preserving variants. Report item-level results,
accuracy on each form, paired accuracy change, request failures, and the exact
conditions used. Treat the result as a small pilot, not evidence of general
model superiority.

The target first release compares **two models across knowledge, reasoning,
instruction following, and evidence-based answering**, with paraphrase robustness,
a results dashboard, and human review. The ten-pair pilot is the first milestone,
not the final deliverable. `implementation_plan.md` provides the broader research
rationale; this document sets the implementation order.

## Working Assumptions and Architecture

- Start as a single-user local Python application; no accounts, hosted service,
  task queue, or separate web backend is needed for the first release.
- Run experiments through a command-line entry point independent of the UI.
  Initially the dashboard reads saved runs; refreshing it cannot trigger model calls.
- Use JSONL for datasets and initial run records. Introduce SQLite when building
  persistent answer review and experiment browsing, with JSONL export retained.
- Use the proposed Streamlit dashboard after the runner is verified. Validate
  current framework/provider documentation when implementing those integrations.
- Keep credentials in environment variables, never datasets, saved configurations,
  logs, or Git. Add ignore rules before any real provider run.
- Use standard-library validation, persistence, and tests where sufficient. Add
  a provider SDK only after choosing the first provider.
- A mock response path allows offline development; it never counts as model evidence.

Data flow: **dataset → validated run configuration → provider → saved response →
task scorer → paired analysis → dashboard/review → report**.

## Sequential Phases

### 1. Freeze scope and protocol

- Select the initial task category, preferably knowledge or reasoning with
  verifiable answers.
- Define the prompt, generation settings, scorer, retry policy, and failure
  categories.
- Decide how variants are authored and manually checked.
- Record provider, model version, date, and any unsupported settings.

Acceptance: `protocol.md` states the question, dataset split, scoring rules,
variant policy, exclusions, and limits on claims.

### 2. Prepare the pilot dataset

- Create ten project-authored original questions and one paraphrase per item.
- Store stable IDs, pair IDs, category, reference answer, scorer name, source,
  license/provenance, and dataset version in JSONL.
- Verify every answer independently, remove duplicates, and review that each
  variant preserves meaning and difficulty as far as practical.
- Version the pilot dataset before each run. Reserve a separate final test set;
  pilot examples used for debugging must not become final held-out evidence.

Acceptance: every item validates against the protocol, every pair is reviewed,
and development examples are separate from reported test items.

### 3. Build the first executable slice

- Add one small runner that loads the frozen JSONL, calls one provider/model,
  saves raw responses immediately, and records timing, usage when available,
  finish status, and errors.
- Add only the task-specific scorer required by the pilot.
- Keep results in simple JSONL; do not introduce a database yet.

Acceptance: a clean checkout can run ten originals plus ten paraphrases (20
requests per model per repetition) end-to-end, preserve raw
responses and failures, and avoid silently overwriting prior results.

### 4. Validate scoring and robustness analysis

- Test known correct, incorrect, malformed, ambiguous, timeout, and retry cases.
- Calculate original accuracy, variant accuracy, paired accuracy change in
  percentage points, completion rate, and request-failure rate.
- Inspect every pilot response and correct dataset or scorer defects before
  freezing the final protocol and held-out dataset. Retain earlier pilot versions
  rather than silently modifying the inputs behind saved results.

Acceptance: aggregate totals match item-level records; failures are not treated
as ordinary wrong answers; the report distinguishes scoring defects from model
errors.

### 5. Add the second model and remaining task categories

- Add a second model after the first slice is reproducible and
  budget/access are confirmed.
- Prefer a second model from the same provider initially if it meets the research
  objective. Add a separate provider integration only when needed.
- Implement multiple-choice and numeric scoring, explicit instruction checks,
  and passage-answer scoring with abstention checks. Route uncertain passage
  assessments to human review rather than claiming exact match establishes truth.
- Run the same frozen items and common instructions, recording provider
  differences and model identifiers.
- Use paired comparisons and state when differences are inconclusive.

Acceptance: each result is traceable to dataset version, model, settings, date,
and scorer version; no ranking claim exceeds the pilot evidence.

### 6. Build the dashboard and human review workflow

- Add dataset preview, saved experiment browsing, results, and answer review views.
- Show category accuracy, paired robustness changes, completion rate, latency,
  cost when known, and links to raw answers. Always show model and dataset versions.
- Store reviewer IDs, rubric version, and independent ratings. Hide model identity
  during review; retain original ratings when disagreements are resolved.
- Use SQLite for experiments, responses, and reviews once this workflow is added.
  Persist each response transactionally and export records without credentials.
- Keep execution in the CLI for the first UI release; display its saved progress.
  Add UI launch/cancellation only with explicit duplicate-run protection.

Acceptance: dashboard totals match exported records, reviews survive a restart,
and page refreshes do not send requests or overwrite another reviewer's ratings.

### 7. Run the controlled experiment and produce the report

- Add reproducibility instructions, dataset provenance, failure analysis, and
  a report separating survey findings, proposed methods, and measured results.
- Freeze the protocol, scorer version, held-out dataset, and model settings after
  pilot corrections. Record any subsequent changes as a new experiment version.
- Use the detailed proposal's 160 base questions plus 120 variants as a target,
  subject to answer verification and budget. Keep the 40 development questions
  outside the final results. Start with one repetition, then assess repeat costs.
- For two models, 280 prompts and three repetitions mean 1,680 generation
  requests before retries; approve the budget after measuring the pilot.
- Review a stratified sample of roughly 60 responses with two independent
  reviewers if available. Report agreement and automatic-scoring disagreements.
- Compute uncertainty using base-question groups: originals, variants, and
  repetitions belong together, not as independent samples.

Acceptance: another person can reproduce the documented run, and limitations
cover sample size, contamination, variant validity, scorer reliability, and
provider/model changes.

## First Executable Milestone

The first implementation commit should support one command-line run over ten
paired questions and one model. It must save configuration, raw responses,
scores, timing, and failures, then produce a small summary of original versus
variant accuracy. No dashboard is required for this milestone.

## Proposed Files and Commit Sequence

Create files only as their phase starts; this is not an existing directory tree.

| Phase | Files or modules | Suggested commit boundary |
|---|---|---|
| 1 | `protocol.md`, `README.md`, `.gitignore`, `pyproject.toml` | Document scope and establish minimal Python setup |
| 2 | `datasets/pilot.jsonl`, `evaluation/dataset.py` | Add reviewed pairs and input validation |
| 3 | `evaluation/runner.py`, `evaluation/provider.py`, `evaluation/__main__.py` | Save an offline run, then integrate one provider |
| 4 | `evaluation/scoring.py`, `evaluation/analysis.py`, `tests/` | Verify scoring, error handling, and paired totals |
| 5 | Dataset versions and targeted additions to existing modules | Add second model and remaining task scorers |
| 6 | `app.py`, `evaluation/storage.py` | Add persistent browsing, followed by blinded review |
| 7 | `reports/`, reproduction instructions | Record frozen experiment and measured findings |

Run outputs belong under `runs/` and should be ignored by default. Publish only
explicitly selected, sanitized experiment artifacts. Do not create a provider
class hierarchy or split modules further until actual complexity requires it.

## Verification Gates

- **Dataset:** reject missing IDs, duplicate IDs, invalid pair references, missing
  answers, invalid categories, and original/variant leakage between splits.
- **Runner:** use offline responses to exercise success, timeout, rate limiting,
  bounded retries, interrupted writes, and restart without duplicate completed
  records. Keep unique run/item/model/repetition keys.
- **Scoring:** check correct, wrong, malformed, ambiguous, and valid alternative
  answers; independently calculate a small reference summary.
- **Analysis:** report denominators explicitly. Compute paired changes on pairs
  with both responses available, and separately disclose incomplete pairs and
  request failures. Never compare different response subsets silently.
- **Reproducibility:** record dataset hash, code commit, scorer version, prompt,
  generation settings, requested/returned model identifiers, timestamps, and errors.
- **Live integration:** after offline checks, run a small paid smoke test only once
  provider access and spend limits are known; save observed usage and failure rates.
- **Release:** reproduce one saved report from raw records without another model
  call, check UI/export agreement, and document the commands actually verified.

## Approximate Schedule

Use the original 6–8 week estimate as a planning assumption, not a commitment:
week 1 protocol and data; week 2 first runner; week 3 scoring and second model;
week 4 dashboard and review; weeks 5–6 pilot corrections and final experiments;
weeks 7–8 report, reproduction checks, and contingency. Each acceptance gate,
rather than the calendar, determines when to move on.

## Proposed Verification Commands

These are future commands only; no runnable build or dependency setup exists
yet:

```text
python -m <package>.validate_dataset <dataset.jsonl>
python -m <package>.run_experiment --dataset <dataset.jsonl> --model <model>
python -m <package>.analyze <results.jsonl>
python -m unittest discover
```

The eventual checks should cover scorer edge cases, dataset validation,
request failures and retries, resume/duplicate behavior, credential exclusion,
and agreement between item-level records and summaries.

## Open Decisions

- **Provider/model:** hosted API or local Ollama; exact model versions remain
  undecided until access and hardware are known.
- **Budget:** maximum API spend, token limits, and whether local inference cost
  is acceptable.
- **Deadline:** determines whether the deliverable is only the pilot or also a
  second model, human review, and a report.
- **Research emphasis:** use robustness plus four-category comparison as the
  default; confirm whether submission requirements call for a different scope.
- **Review availability:** who can independently verify answers and review outputs?

These decisions do not block writing the protocol or building the offline path.
Provider and budget decisions do block live requests and final model selection.

## Explicit Deferrals

- Streamlit dashboard and SQLite: scheduled for phase 6, after the command-line
  pipeline is reliable; they are part of the intended application release.
- Additional provider adapters and a third model: defer beyond the two-model
  release unless required by model access.
- LLM judging: defer until human or automatic scoring exposes a specific gap;
  never treat an LLM judge as ground truth without validation.
- Comprehensive safety, multilingual, multimodal, agent, and benchmark-harness
  support: out of the first slice.

## Claim and Evaluation Risks

- Ten paired questions cannot establish statistically strong or general claims.
- A paraphrase can change difficulty or meaning; manual pair review is required.
- Exact-match and parsing rules may reject valid answers, so scorer limitations
  must be reported.
- Public questions may be contaminated; adapted subsets are not official
  benchmark results.
- Consistency does not imply correctness, and “hallucination” must not hide
  distinct errors such as unsupported claims, refusals, or format failures.
- Provider defaults, model updates, truncation, rate limits, and unavailable
  token pricing can make comparisons unfair unless recorded explicitly.
