# Methodology and interpretation

Last checked: 2026-10-08. This document describes the implemented limited application and its intended interpretation; it is not a report of a live model comparison.

## Relation to Chang et al.

Chang et al., [*A Survey on Evaluation of Large Language Models*](https://doi.org/10.1145/3641289), ACM TIST 15(3), Article 39 (2024), organize evaluation around **what** is evaluated, **where** it is evaluated, and **how** it is evaluated. This application borrows that organizing framework:

| Survey question | This application | Deliberate boundary |
|---|---|---|
| What (Section 3) | Small language-task comparisons: multiple choice, short factual answers, extractive QA, arithmetic, classification, structured extraction, summarization, and explicit instruction checks. Results can also show route failures and request latency. | This is not broad coverage of the survey's domains. It does not assess all language abilities, agents, medicine, safety, fairness, or calibration. |
| Where (Section 4) | A 30-item, newly authored convenience dataset (`datasets/original_demo_v1.jsonl`) and versioned user CSV/JSONL imports with recorded provenance. | The original items are not MMLU, GSM8K, or a representative sample of users or real-world tasks. Imported data quality and rights depend on the importer. |
| How (Section 5) | Versioned task-specific deterministic parsers/scorers, operational attempt records, explicit scheduled/response/eligible counts, and optional human ratings and pairwise preferences. | Overlap scores do not establish factuality; route timing is conditional on the recorded provider, endpoint, settings, and run conditions. |
| Human evaluation (Section 5.2/Table 10) | Opaque assignments, stored A/B order, six anchored rubric dimensions, and separate pairwise preference. | Local evaluator labels are not verified independent people; blinding is interface-level, not protection from the operator or self-identifying answers. |
| Future directions (including Table 9) | Robustness, uncertainty estimation, and LLM judging are planned extensions. | They are unfinished. There is no fairness result without suitable group labels/design or calibration result without validated probabilistic predictions. |

**The application does not reproduce the whole paper, its protocols, datasets, or historical rankings. It is not equivalent to any benchmark discussed in that survey.** Do not infer general model superiority, universal capability, safety, or deployment fitness from these comparisons. The purpose of the survey is methodological context, not a claim of replication.

## Tasks, parsers, and scores

Each task uses the dataset item's declared accepted references and validated scorer configuration. Scorer version is currently `1`; normalization is `unicode-nfc-casefold-whitespace-v1`; tokenization is `unicode-word-casefold-v1`. The implementation is in `backend/app/evaluation/scoring.py`. A completed but unparseable answer is a format/correctness failure where a correctness metric applies. Missing responses and truncated answers have null quality scores, not invented zeroes; they remain visible in operational coverage. Missing references cannot be graded.

| Task / metric | Parsing and calculation | Important interpretation |
|---|---|---|
| Multiple choice — `label_accuracy` | Accept exactly one configured label, either the whole trimmed response or a single final `Answer: X` line. Conflicting/multiple declared answers and out-of-set labels are unparseable. Compare to accepted labels. | Completed invalid/ambiguous output scores 0; absent/truncated response is null. |
| Short factual — `raw_exact_match`, `normalized_exact_match` | Raw response equality, plus exact match after Unicode NFC, casefolding, and whitespace collapse. Punctuation is retained. Match any accepted reference. | Normalized match is not semantic equivalence; no substring matching. |
| Extractive QA — `token_f1` | Unicode `\w+` tokens after NFC/casefold; multiset overlap precision/recall F1, maximum over references. Two empty token sequences score 1. | Token overlap is not a factuality or entailment measure. |
| Arithmetic — `numeric_exact` | A single finite Decimal value, either the whole response or one final `Answer: ...` line; multiple answer lines are rejected. Match if absolute error is at most `max(abs_tolerance, rel_tolerance × |reference|)`. | Current scorer requires `units=none`; units are not converted. Unsupported unit policy blocks scoring. |
| Classification — `label_accuracy`, aggregate `macro_f1` | One configured label parsed as above. Macro F1 is computed over the declared class set from pooled confusion counts, not averaged item-level F1. | Completed invalid predictions count as false negatives for the true class. Missing/truncated rows have no confusion entry and are reported separately. |
| Structured extraction — `json_valid`, `schema_valid`, `field_exact` | Parse strict JSON (reject duplicate keys and non-finite numbers); validate the supported flat object schema; then compare typed values/fields exactly with any accepted reference. | Extra/missing fields or wrong types fail schema; malformed JSON and schema failure are separately flagged. No remote schema references. |
| Summarization — `rouge_l_f1` | Longest common subsequence F1 over the versioned Unicode-word tokens; maximum over references. | Lexical sequence overlap only, not factuality, coverage, or summary quality by itself. Pair with human review when relevant. |
| Instruction following — `instruction_checks` | Fraction of allowlisted declared checks passed (currently exact text or exact JSON). Also report `checks_passed`. | This measures only those explicit checks, not subjective helpfulness or complete instruction compliance. |

For an item with no reference, no metric is gradeable, even if a response is present. A scorer/configuration error leaves that response saved and unscored; reading results may retry local scoring, but it never regenerates the answer. Raw answer and parse explanation are retained for audit.

## Denominators, missingness, and comparisons

For every model/task/metric, report these counts from scheduled jobs and persisted records:

- **Scheduled**: all selected `(item, repetition, variant)` jobs for that route, including jobs not yet run.
- **Responses**: jobs with a recorded response; returned-identity mismatches remain visible here but do not enter clean quality comparisons.
- **Complete**: recorded responses not marked truncated (`finish_reason=length`). Truncated responses are counted separately and have null score.
- **Parseable / format failures**: scorer parse status among completed responses; invalid format is not silently discarded from correctness.
- **Metric eligible / quality denominator**: completed, scored responses with a reference and no identity mismatch. A completed invalid-format response with a reference is metric-eligible and receives the task scorer's failure value. Missing/unscored references or identity mismatch are excluded and explicitly counted.
- **Operational failures, pending, cancelled, missing reference, unscored, and identity mismatch**: separate counts; these are not conflated with wrong answers.

Quality is the mean over the exact metric-eligible denominator. For binary metrics, the separately labeled scheduled-job success rate uses successful eligible binary outcomes divided by **all scheduled jobs**, so missing/failed work cannot improve it. It is provisional during a run; pending jobs are counted, not represented by fabricated score rows. Continuous overlap scores have no default pass threshold: report conditional quality and coverage, not a made-up binary success rate.

Direct comparisons also show the intersection of eligible `(item_id, repetition, variant)` keys across the selected models, with common-set count, each model's full eligible count, and omitted keys/counts. Common-set scores help control item mix but do not replace full scheduled-set coverage. Repetitions of the same item are not independent questions. A small or selective common subset can be misleading and must be read alongside omissions and operational failures.

### Latency and usage

Latency is elapsed duration for a successful persisted request attempt that produced the accepted response; summaries report sample count, median, and p95. It is an **end-to-end model/provider route measurement under this run's conditions**, not intrinsic model speed. It includes route/network/service effects and depends on load, region, request size, settings, and time. It is not time-to-first-token (requests are non-streaming), not a controlled hardware benchmark, and not comparable across unrecorded conditions. Failed attempts and queue/retry waiting are not included in this latency sample. Token totals are nullable and reflect provider-reported usage only where present; missing usage is not zero.

## Human review

Rubric v1 uses scores 1–5 (2 and 4 are intermediate) and N/A for dimensions not supported by the task evidence:

| Dimension | 1 — low | 3 — middle | 5 — high |
|---|---|---|---|
| Accuracy | Materially incorrect against evidence | Mixed correctness or important omission | Correct on assessable requirements |
| Relevance | Does not answer the task | Partly relevant, with distractions | Directly addresses the task |
| Fluency | Difficult to understand | Understandable, noticeable issues | Clear and readable |
| Transparency | Misrepresents evidence/limitations | Some appropriate evidence or uncertainty | Communicates relevant support and limits without unsupported certainty |
| Safety | Task-relevant harmful issue | Some relevant concern | Meets safety criteria applicable to this task |
| Task alignment | Violates central instructions | Partly follows instructions | Meets stated user constraints |

Transparency is not a request to expose hidden chain-of-thought. Safety may be N/A when not tested; these ratings are not a safety benchmark. Pairwise choice is A, B, tie, or cannot judge. Report outcomes separately, with comparison/evaluator counts; preference is not accuracy. Rubric summaries use dimension-specific applicable rating counts.

Assignments store randomized A/B presentation and the private mapping before display. The public review payload omits model identities, but responses may self-identify and the local operator can inspect the database and results. Evaluator labels are local labels, not authentication or proof of independent raters. Report the number of distinct labels, avoid calling them independent reviewers, and permit cannot-judge/identity-suspected responses. Sparse ratings are descriptive, not population estimates.

## Sample and claim limits

The original sample has 30 fictional, newly authored items across six categories (five each); the quick run selects ten with category-balanced allocation that is not perfectly equal across six groups. This is a small convenience sample. User imports may have different size, provenance, selection bias, licensing, difficulty, or contamination. Repeated generations do not increase independent item count. Remote model versions and provider routing can change; a fixed local seed does not make remote inference deterministic. Pricing, quotas, and availability are time-dependent. Failures, retries, truncation, and route identity changes can create non-random missingness.

Therefore, report observed items, settings, route identity/evidence date, scorer versions, denominator and missingness for each result. Avoid broad claims and causal explanations. There is no overall composite score and no fairness, calibration, robustness, uncertainty-interval, or LLM-judge result in the current core application. The richer fixture scenarios and full demo release remain unfinished; synthetic fixture outcomes are workflow tests, never model measurements.
