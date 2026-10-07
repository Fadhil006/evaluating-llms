# Evaluation protocol (implemented)

**Status:** The software and offline fixture workflow are implemented. Completed measured model results are still pending: no successful live model responses have been verified here. Offline fixture runs are synthetic demonstrations and must not be reported as benchmark measurements. This limited protocol is inspired by the survey's what/where/how evaluation dimensions, not an implementation of the entire survey ([survey](sources/ai_project.md), [references](README.md#references)).

## Dataset and split

Datasets are UTF-8 JSONL. `datasets/v1.0/dev.jsonl` is for development/debugging; `datasets/v1.0/benchmark.jsonl` is the held-out `test` split and is reserved for final evaluation. Each file is validated before a run. Do not tune prompts, rules, or references using held-out outputs. Each base item and its paraphrase share pair ID, split, category, scorer, reference answer, rules, source, and version. The held-out v1.0 set contains 12 base questions and 12 paraphrases (24 items), two base pairs in each of six categories. This is a small exploratory set, not a leaderboard-grade sample.

The validator rejects malformed/duplicate IDs and prompts, unsupported category/scorer combinations, invalid rules, mixed versions, missing or duplicate pair variants, and inconsistent pairs. A run uses one split only. The shared runner's optional `pair_ids` selects nonempty, unique existing pair IDs; both variants are retained in dataset order, and omitting the argument selects all pairs. The CLI does not expose `pair_ids`; the Flask form accepts one or more valid pair IDs and the runner freezes both IDs for every selected pair. A request cap may leave selected pairs incomplete but does not select pairs itself. The **selected** items are copied to `dataset.jsonl` and SHA-256 hashed in `config.json`; reusing a run directory with different inputs is rejected.

## Run configuration and prompts

Run configuration is written once and cannot be changed in place; use a new run directory for changed settings. New runs record synthetic/live source, models, hash of the selected dataset snapshot, dataset version and split, scorer source hash, creation time, `selected_pair_ids`, `selected_item_ids`, `schema_version` (1), `protocol_version` ("1"), `software_version` ("0.1.0"), backend-specific `generation_conditions`, and `unsupported_controls` (`seed`, `top_p`, `stop_sequences`). These are provenance labels, not evidence of controlled hosted model weights or supported seed/top-p/stop settings. Live OpenRouter configuration also records exact provider route(s), system prompt, prompt template, temperature, max tokens, and application version. The fixed system prompt is `Answer the question accurately and concisely.` The prompt template is `Question: {prompt}\nAnswer:`. OpenRouter uses temperature `0` and `max_tokens=512`; a seed, `top_p`, and stop sequences are not sent or claimed as controlled. The CLI supports a one-model live run with an explicit provider slug; the local Flask dashboard targets exactly two distinct allowlisted models from one chosen backend, with OpenRouter provider slugs pinned by the app rather than user-editable. Provider fallback is disabled. Returned model/provider slug (when supplied) and reported cost are checked against the requested route; mismatches or positive cost pause the run. The saved-run UI exposes frozen config JSON and derived run status (partial/paused/complete); generation controls cannot be edited there.

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
- Instruction: declared JSON keys/exact string values, case-insensitive forbidden strings, and/or bullet count; reports constraint fraction and all-constraints pass. This is a scored **rule-compliance** result, not factual correctness.
- Coding: Python AST syntax/function signature checks only. Generated code is never executed; the outcome remains review-only and is not correctness.
- Summarization: whitespace-separated word-range and case-insensitive required-term presence proxies only; faithfulness is not determined and outcome remains review-only.

MCQ accepts only a single bare or `answer:`/`choice:`-labeled A–D choice; numeric answers must be a single finite number (optional `Final answer:` prefix). Units/text require review or are invalid; no unit conversion is performed. Short-answer equivalence beyond declared forms is not inferred. There is no LLM-as-a-judge implementation. Subjective/review cases do not enter scored accuracy. Automatic results are not silently replaced by human judgments.

**Deferred, not implemented:** MT-Bench multi-turn evaluation, Chatbot Arena voting, PandaLM judging, HELM's holistic scenario/metric suite, AlpacaEval preference evaluation, LLM-as-a-judge, human adjudication workflow, executable coding tests, and summary faithfulness scoring. These are related work, not alternate modes of this app (see [References](README.md#references)).

## Comparison and aggregation

Both models receive the same item prompt and scoring rule in a comparison run. Reports retain each model's planned, answered, objective-scored, correct, incorrect, review, invalid, unscored, failed, truncated, rate-limited, and pending counts. Per-model accuracy is correct/objectively scored; show the denominator. The `matched_comparison` summary uses only item IDs objectively scored for every selected model and reports shared-denominator accuracy, percentage-point difference for two models, and category breakdown on those same matched IDs. Coverage/failures remain visible separately. If there are no shared scored items, matched accuracy and delta are unavailable, not zero. Live latency summaries report count, mean and median only from successful nontruncated responses with finite nonnegative measured durations; provider/network effects remain part of these observations. Fixture latency is excluded from model-latency summaries. Time-to-first-token and tokens/second are unavailable in current adapters.

Original/paraphrase analysis is per model and uses only complete pairs with objective scores for both variants. It reports complete-pair denominator, original/variant correct counts, and original-minus-paraphrase percentage-point difference. A paraphrase drop is an observed result on this set, not proof of general robustness failure. Scores are descriptive; small samples and no repeated trials do not support strong rankings or stable latency claims.

## Reproduction, export, and limitations

Use `python -m evaluation` for fixtures or explicit one-model live CLI runs, and `python app.py` for the local-only two-model Flask interface at `http://127.0.0.1:8501`. Saved runs are browsable in history and export one row per planned model/item to CSV; a stale or incomplete CSV is withheld. Saved-run inspection uses persisted scores and does not rescore with changed code; scorer-version mismatch is noted in metadata. Live average/median latency is derived only from successful, finite, nonnegative live response timings; fixture timing is excluded. To reproduce offline scoring without provider calls, explicitly run `reanalyze(run_dir)`; scorer source hash and dataset hash prevent reanalysis after relevant inputs change. Hosted model IDs do not freeze model weights, temperature zero is not deterministic, providers may differ in routing/settings, and network/queue/rate-limit conditions influence latency. Other limitations: only 24 held-out items, possible benchmark contamination, single-author item/paraphrase review, imperfect heuristic scoring, proxy measures for coding/summarization, rate limits, changing model availability, and no repeated-trial reliability or calibrated confidence measure. No confidence claim is inferred from a model self-report.
