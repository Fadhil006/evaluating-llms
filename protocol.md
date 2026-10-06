# Preliminary offline evaluation protocol

**Status:** Day 1 design freeze, not an executed experiment. This document records initial rules to implement and test before inspecting held-out model outputs. Dataset, provider access, key, model availability, and any live run remain pending. The active scope comes from [`plan.md`](plan.md); see [`README.md`](README.md) for the six intended categories and four unverified candidate IDs.

## Research question and comparison

Compare model performance across General Reasoning, Mathematics, Coding, Knowledge, Summarization, and Instruction Following on identical items. Report paraphrase sensitivity where reviewed original/variant pairs exist. Use fixed, explicitly named models after availability checks; never use a rotating model selector for comparative results. Apply the same prompt template, system instruction, generation settings, scoring version, and item set to each model when supported; record unsupported settings and actual routing rather than assuming identical provider behavior. Fixed IDs do not guarantee immutable hosted weights, and temperature 0 does not ensure deterministic outputs. A cached response is historical replay, not a fresh independent sample; repetitions must make new requests and record their conditions.

## Split and item policy (frozen preliminarily)

- Keep separate development and held-out evaluation sets. Debug prompts, scorers, and parser behavior only on development items; do not move inspected development items into the held-out set.
- Keep each base question and all paraphrase/typo variants together in one split. Give every item a stable ID, pair/base ID, category, source/license, reference answer, scorer/rubric version, and dataset version. Check references and variant meaning manually before freezing the evaluation set.
- Freeze held-out items, answers, variants, split assignment, scoring rules, and prompt/settings before viewing their model outputs. Corrections afterward require a new dataset/protocol version and an explicit change log; preserve prior records. Planned sizes are not yet committed or achieved.
- Compare only matched successfully answered items across models; report missing pairs, request failures, refusals, and truncations separately, never as automatically wrong answers. Calculate original-minus-variant accuracy in percentage points only on complete pairs, with denominators shown.

## Preliminary scoring rules (frozen before data collection)

| Category | Initial rule | Boundary |
| --- | --- | --- |
| General Reasoning and Knowledge | For predeclared multiple choice, compare one unambiguous extracted A/B/C/D choice; for short answer, compare case/whitespace-normalized text with predeclared accepted forms. | Ambiguous or multiple choices are not guessed; short-answer equivalence needs review. |
| Mathematics | Compare a single final numeric answer after predeclared unit/format normalization; accept absolute difference at most `1e-4` unless an item declares a different tolerance in advance. | Ambiguous multiple numbers or incompatible units go to review; no post-hoc tolerance tuning. |
| Coding | Parse generated Python as text with `ast.parse`, check the required function name/signature, and flag for manual rubric review. | **Never execute untrusted generated code on the host**, including via `exec`, `eval`, imports, or unit tests. AST validity alone is not functional correctness; any future execution requires an independently designed isolation policy. |
| Summarization | Check predeclared word-count limits and required key entities; review faithfulness/unsupported claims manually. | Keyword coverage is a proxy, not semantic accuracy or hallucination proof. |
| Instruction Following | Validate predeclared machine-checkable constraints (e.g. JSON parse/required keys, forbidden strings, bullet count). Report both fraction of constraints passed and all-constraints-passed rate. | Compliance does not establish factual correctness. |

Keep raw responses and scorer explanations separately from any later human ratings; do not silently overwrite an automatic score after review. Optional blinded human review can label borderline or subjective cases; a second reviewer and LLM judging are not prerequisites. Scoring details that cannot be settled until items exist must be declared per item before evaluation, not invented after viewing outputs.

## Reporting and limits

Record the dataset hash/version, prompt, settings, scorer version, requested and returned model IDs, provider/routing where known, timestamps, raw answers, latency, token usage when available, and errors without credentials. Report category metrics and operational failures separately; no overall ranking without shared denominators and an uncertainty/limitations statement. Small samples, public-item contamination, imperfect paraphrases, heuristic scorers, model updates, and one-shot sampling limit generalization. Mock/offline responses must never be presented as measured model results.

Live work requires a real key supplied outside version control, confirmed candidate availability and limits, and explicit approval before requests. Pause at rate limits; do not rotate accounts, keys, or IPs to bypass quotas. Nothing in this protocol asserts that access, the four-model comparison, or any score has been verified.
