# Evaluation protocol (implemented)

**Status:** The software and offline fixture workflow are implemented. Completed measured model results are still pending: the repository contains no successful live model responses. Offline fixture runs are synthetic demonstrations and must not be reported as benchmark measurements.

## Dataset and split

Datasets are UTF-8 JSONL. `datasets/v1.0/dev.jsonl` is for development/debugging; `datasets/v1.0/benchmark.jsonl` is the held-out `test` split and is reserved for final evaluation. Each file is validated before a run. Do not tune prompts, rules, or references using held-out outputs. Each base item and its paraphrase share pair ID, split, category, scorer, reference answer, rules, source, and version. The held-out v1.0 set contains 12 base questions and 12 paraphrases (24 items), two base pairs in each of six categories. This is a small exploratory set, not a leaderboard-grade sample.

The validator rejects malformed/duplicate IDs and prompts, unsupported category/scorer combinations, invalid rules, mixed versions, missing or duplicate pair variants, and inconsistent pairs. A run uses one split only. Dataset content is copied to `dataset.jsonl` and SHA-256 hashed in `config.json`; reusing a run directory with different inputs is rejected.

## Run configuration and prompts

Run configuration is written once and cannot be changed in place; use a new run directory for changed settings. It records synthetic/live source, models, dataset hash and version, split, scorer source hash, and creation time. Live OpenRouter configuration also records exact provider route(s), system prompt, prompt template, temperature, max tokens, and application version. The fixed system prompt is `Answer the question accurately and concisely.` The prompt template is `Question: {prompt}\nAnswer:`. OpenRouter uses temperature `0` and `max_tokens=512`; a seed and `top_p` are not sent or claimed as controlled. The CLI supports a one-model live run; the local Flask dashboard supports exactly two distinct models. OpenRouter comparison requires explicitly selected, pinned provider slugs and disables provider fallback. Returned model/provider and reported cost are checked against the requested route; mismatches or positive cost pause the run.

The OpenCode path is also available in the local dashboard, but is a distinct execution path. Its agent, tool-denial policy, and timeout are recorded; it does not share all OpenRouter generation controls and must not be treated as a perfectly controlled provider-equivalent comparison. Provider/network conditions affect latency. No model-order judge is used: current scoring is per-answer objective/proxy scoring, so pairwise position randomization is not applicable.

## Execution modes and confirmation

### Offline fixture

The local JSON fixture maps model labels to item IDs and typed answers/errors. The runner tags every response, score, summary, and CSV row `synthetic: true`, source `offline_fixture`. These hand-authored outputs exercise the pipeline only; they are not from a model and are never measured performance. Fixture latency is local processing time and is not model latency.

### Live

Live execution requires an explicit CLI `--live` invocation or local dashboard confirmation before dispatch. The UI displays the selected data/models and requires confirmation; the CLI requires the explicit live flag. OpenRouter requests require a key, an allowlisted exact `:free` ID, pinned provider, and bounded cumulative request cap. A free label/catalog price is not a billing guarantee; verify current account/provider terms first. OpenCode requires separate provider/account checks. No live request is made by fixture mode or result browsing.

## Persistence, failures, and retries

Each run stores immutable `config.json` and `dataset.jsonl`, append-only `responses.jsonl`, and for live runs `attempts.jsonl` (durable attempt intent before dispatch). Derived `scores.jsonl`, `summary.json`, and answer-level `results.csv` can be rebuilt from saved records. Responses retain answer/raw response when available, status/error, timestamps, latency, returned identity/routing, finish reason, generation ID, and token usage where provider supplies it. Errors, rate limits, truncations, and pending work remain visible and are not scored as incorrect. A timeout/transport failure after durable intent is ambiguous; the runner pauses and refuses automatic redispatch until manually investigated. HTTP 429 pauses and can be resumed later; attempts count against the cumulative run cap. Retries are bounded by that cap; there is no infinite retry loop. Never delete or alter attempt logs to force a retry.

## Scoring

Each item declares a scorer and rule data before evaluation. The deterministic scorer supports:

- MCQ: one unambiguous A-D choice must match the reference.
- Numeric: one finite final number compared to the reference using the declared absolute tolerance (default `1e-4`). Units/text and ambiguous outputs go to review/invalid, not guessed.
- Short answer: case/whitespace-normalized exact match against predeclared accepted forms.
- Instruction: declared JSON keys/values, forbidden strings, and/or bullet count; reports constraint fraction and all-constraints pass. This does not measure factual correctness.
- Coding: Python AST syntax/function signature checks only. Generated code is never executed; the outcome remains review-only and is not correctness.
- Summarization: word-range and required-term proxies only; faithfulness is not determined and outcome remains review-only.

There is no LLM-as-a-judge implementation in this release. Subjective/review cases do not enter objective accuracy. Automatic results are not silently replaced by human judgments.

## Comparison and aggregation

Both models receive the same item prompt and scoring rule in a comparison run. Reports retain each model's planned, answered, objective-scored, correct, incorrect, review, invalid, failed, truncated, rate-limited, and pending counts. Per-model accuracy is correct/objectively scored; show the denominator. The `matched_comparison` summary uses only item IDs objectively scored for every selected model and reports shared-denominator accuracy, percentage-point difference for two models, and category breakdown on those same matched IDs. Coverage/failures remain visible separately. If there are no shared scored items, matched accuracy and delta are unavailable, not zero.

Original/paraphrase analysis is per model and uses only complete pairs with objective scores for both variants. It reports complete-pair denominator, original/variant correct counts, and original-minus-paraphrase percentage-point difference. A paraphrase drop is an observed result on this set, not proof of general robustness failure. Scores are descriptive; small samples and no repeated trials do not support strong rankings or stable latency claims.

## Reproduction, export, and limitations

Use `python -m evaluation` for fixtures or explicit one-model live CLI runs, and `python app.py` for the local-only two-model Flask interface at `http://127.0.0.1:8501`. Saved runs are browsable in history and export one row per planned model/item to CSV. To reproduce offline scoring without provider calls, run `reanalyze(run_dir)`; scorer source hash and dataset hash prevent reanalysis after relevant inputs change. Hosted model IDs do not freeze model weights, temperature zero is not deterministic, providers may differ in routing/settings, and network/queue/rate-limit conditions influence latency. Other limitations: only 24 held-out items, possible benchmark contamination, single-author item/paraphrase review, imperfect heuristic scoring, proxy measures for coding/summarization, rate limits, changing model availability, and no repeated-trial reliability or calibrated confidence measure. No confidence claim is inferred from a model self-report.
