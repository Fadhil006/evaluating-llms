# Build Plan

This is an implementation proposal, not a report of completed work. The
repository currently has documentation only; no commands below are runnable
until the corresponding files and dependencies are created. Files under
`sources/` are read-only reference material.

## Goal

Build the smallest reproducible experiment for the question:

> Does paraphrasing change an LLM's answer accuracy?

Start with one objectively scorable text task, one model, and ten original
questions paired with meaning-preserving variants. Report item-level results,
accuracy on each form, paired accuracy change, request failures, and the exact
conditions used. Treat the result as a small pilot, not evidence of general
model superiority.

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
- Freeze the test set before evaluating models.

Acceptance: every item validates against the protocol, every pair is reviewed,
and development examples are separate from reported test items.

### 3. Build the first executable slice

- Add one small runner that loads the frozen JSONL, calls one provider/model,
  saves raw responses immediately, and records timing, usage when available,
  finish status, and errors.
- Add only the task-specific scorer required by the pilot.
- Keep results in simple JSONL; do not introduce a database yet.

Acceptance: a clean checkout can run ten questions end-to-end, preserve raw
responses and failures, and avoid silently overwriting prior results.

### 4. Validate scoring and robustness analysis

- Test known correct, incorrect, malformed, ambiguous, timeout, and retry cases.
- Calculate original accuracy, variant accuracy, paired accuracy change in
  percentage points, completion rate, and request-failure rate.
- Inspect every pilot response and correct dataset or scorer defects before
  freezing the protocol.

Acceptance: aggregate totals match item-level records; failures are not treated
as ordinary wrong answers; the report distinguishes scoring defects from model
errors.

### 5. Add comparison only if justified

- Add a second model/provider only after the first slice is reproducible and
  budget/access are confirmed.
- Run the same frozen items and common instructions, recording provider
  differences and model identifiers.
- Use paired comparisons and state when differences are inconclusive.

Acceptance: each result is traceable to dataset version, model, settings, date,
and scorer version; no ranking claim exceeds the pilot evidence.

### 6. Document and expand deliberately

- Add reproducibility instructions, dataset provenance, failure analysis, and
  a report separating survey findings, proposed methods, and measured results.
- Expand task categories, repetitions, human review, or visualization only
  after the pilot exposes a concrete need and the budget supports it.

Acceptance: another person can reproduce the documented run, and limitations
cover sample size, contamination, variant validity, scorer reliability, and
provider/model changes.

## First Executable Milestone

The first implementation commit should support one command-line run over ten
paired questions and one model. It must save configuration, raw responses,
scores, timing, and failures, then produce a small summary of original versus
variant accuracy. No dashboard is required for this milestone.

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
- **Research emphasis:** robustness first, or a broader capability comparison.
- **Review requirement:** whether human review is required for the submission.

## Explicit Deferrals

- Streamlit dashboard: defer until command-line results are reliable and users
  need interactive inspection.
- SQLite/results database: defer while JSONL is sufficient for the pilot.
- Multiple adapters and third models: defer until provider choice and budget
  are settled.
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
