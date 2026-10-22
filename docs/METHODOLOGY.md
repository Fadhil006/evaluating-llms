# Methodology and interpretation

Last checked: 2026-10-22 (starter datasets and their scoring/selection contracts; older verification dates below remain specific to those features). This describes implemented code where verified and labels incomplete integration or verification as provisional. It is not a report of a new broad live study. Fixture results are synthetic; the existing small live run is a sampled smoke, not broad performance evidence.

## Scope and paper-to-feature attribution

The five sources and their intended relationships are recorded in [RESEARCH_FOR_ARENA.md](RESEARCH_FOR_ARENA.md). These are adaptations or motivations, not benchmark replications:

| Source | Implemented or planned local feature | Relationship and caveat |
|---|---|---|
| Chang et al., *A Survey on Evaluation of Large Language Models* (2024; R0) | Task/split/provenance and metric interpretation documented here. | Borrowed what/where/how organization; motivation, not a full survey checklist or reproduction. |
| Liang et al., HELM (2022/2023; R1) | Distinct task metrics, operational coverage, family-based original/variant summaries. | Adaptation/motivation. The local convenience dataset and checks are not HELM scenarios or its robustness suite. |
| IFEval (2023; R2) | Versioned deterministic exact-text, exact-JSON, required/forbidden substring, and exact-word-count checks. | Bounded adaptation only; not official IFEval compatibility or a truthfulness/helpfulness measure. |
| Dror et al. (ACL 2018; R3) | Paired resampling over complete independent families, with repeats/variants retained within family. | Project-specific adaptation motivated by design-matched inference; not a method/formula prescribed by that paper. |
| Zheng et al., MT-Bench/Chatbot Arena (2023; R4) | Blinded pairwise/rubric review and descriptive overlap, with A/B mapping retained. | Adaptation. Local evaluator labels are not verified independent raters; no judge replication or transferred agreement claims. |

Split enforcement, immutable snapshots, threshold choices, and API/UI mechanics are local engineering decisions, not paper-attributed methods. No upstream benchmark data or evaluator is claimed to be replicated.

## Imported data and split/family validation

The current importer (`backend/app/services/datasets.py`) accepts `dev`, `calibration`, `test`, or `legacy_unknown`; missing split metadata remains `legacy_unknown`. Known-split items require a family ID. A family cannot cross splits within an import or across saved dataset versions, and family variants must agree on split, task, scorer configuration, references, and applicable multiple-choice choices. Normalized task/prompt/context/choices content is checked within an import and across versions for cross-split reuse. Duplicate normalized content within one split is surfaced and requires explicit acknowledgement to save. CSV provenance is parsed as JSON; version detail and exports expose split/family/variant/review metadata. Dataset versions retain canonical content hashes and metadata.

These checks establish declared provenance/consistency, not independent family review, semantic paraphrase validity, or absence of contamination. Review status is uploader-declared metadata. `datasets/instruction_following_draft_v1.jsonl` contains only 5 dev families / 10 draft items; the proposed 40-family suite is incomplete. None are independently reviewed or used in a held-out study.

## Local 5-, 10-, and 20-question starter datasets

The starter datasets are overlapping, nested subsets of `datasets/original_demo_v1.jsonl`, not new independently sampled benchmarks. Their sizes and selection recipe are local usability choices, not requirements from the survey. The original 30-question dataset remains available and unchanged.

Selection cycles through arithmetic, multiple choice, short factual, structured extraction, instruction following, and summarization, taking the next source item in each category until the requested size is reached. The 5-question set covers the five deterministic/reference-check task categories; the 10- and 20-question sets also include summarization. Source prompts, references, scoring configurations, licenses, and declared split/review/family metadata are retained. Legacy-unknown metadata is not promoted to reviewed, held-out, or independent-family status. Dataset provenance records the source and selected IDs.

This is a limited application of Chang et al.'s [what/where/how framing](https://doi.org/10.1145/3641289): task coverage is **what**, versioned locally authored examples and their provenance are **where**, and task-specific automatic checks plus separate human review are **how**. The primary paper's Section 5.1 and Table 9 discuss task-dependent exact-match, F1, and ROUGE metrics; Section 5.2 discusses human evaluation. They do not prescribe these subsets, this app's exact checks, or a single overall scoring formula.

Arithmetic uses numeric comparison, multiple choice uses label accuracy, short factual uses normalized exact match, structured extraction uses JSON/schema/field checks, and instruction following uses the declared versioned checks. Summarization uses ROUGE-L overlap, **not factual correctness**. Report each task/metric and its scored denominator separately; do not turn unlike metrics into an overall winner. The subsets overlap and are tiny convenience samples, not independent replications or evidence of statistical superiority. Existing paired-family analysis safeguards still apply; these legacy-unknown items do not acquire independent families just because a set has 20 questions.

The experiment wizard explicitly selects all items for a starter dataset: with two model routes and one repetition, the 5-, 10-, and 20-question sets require 10, 20, and 40 initial requests respectively. Other datasets retain the existing quick-sample default unless explicitly configured otherwise. An estimate or dataset installation does not start generation. No HELM, official IFEval, MT-Bench, Chatbot Arena, or AI judge is run by choosing these datasets.

## Scorers and instruction checks

Task scorers use `SCORER_VERSION = 1`; normalization is `unicode-nfc-casefold-whitespace-v1` and tokenization is `unicode-word-casefold-v1`. Instruction-check scoring is separately versioned as `INSTRUCTION_CHECK_SCORER_VERSION = 2`, with check policy `instruction-checks-v1`. Its allowed check types are exact text, exact JSON, required substring, forbidden substring, and exact Unicode-word count. Substrings use NFC plus casefold; exact word count uses the Unicode `\w+` tokenizer. Import validation requires 1–20 valid checks and bounds word counts. Each check's type/pass evidence is retained.

Instruction results distinguish:

- **All-check prompt success** (`instruction_all_checks@2`): whether every declared check on that prompt passed.
- **Pooled check accuracy**: total passed checks divided by total declared checks, aggregated across responses. This is not the mean of prompt-level all-check success and may weight prompts with more checks more heavily.

Metric identities include scorer versions so incompatible versions are not silently pooled. Truncated answers currently have null quality values and remain visible as truncated rather than being graded, including for instruction checks. These checks are objective only relative to their declared constraints; they do not grade factuality or general instruction-following quality.

## Explicit analysis snapshots and paired uncertainty

Analysis is an explicit local operation: `POST /api/experiments/{id}/analyses` computes and stores an append-only content-hashed snapshot. Analysis list/detail GET endpoints retrieve saved snapshots. The snapshot records experiment/dataset/config and model-slot provenance, observed scorer versions, family mapping, planned keys, observations, sampling seed, analysis version, 10,000 draws, and results. Its analysis version is `paired-family-v1`. GET results, response and export endpoints are read-only; they do not rescore or call providers. Creating an analysis can locally recover missing score rows before freezing the snapshot; it does not regenerate answers or call providers.

Each task/metric is analyzed separately. The paired comparison includes only families for which both selected model slots have scores for every planned key in that family; repeats and variants are averaged within family, so they do not increase independent `n`. Families are equally weighted. The reported delta is slot 2 minus slot 1. A 95% percentile interval uses 10,000 paired family bootstrap draws; it is withheld below 10 complete families and marked degenerate when all observed family differences are identical. Legacy data without family metadata is not assigned artificial family independence.

Missingness is part of the result: incomplete/unpaired families are listed as omitted, and no imputation is performed. Original-only and per-variant deltas are descriptive contrasts. Intervals are conditional on complete observed families and do not repair selective missingness or establish representativeness. The implementation is available in `backend/app/services/analysis.py` and `analysis_store.py`.

Snapshot API/export and fixture-browser integration passed local tests on 2026-10-18. The unpinned dashboard remains a current-score view. The saved analysis payload retrieved by its ID is frozen; experiment exports containing it also include current job/review state and are not byte-for-byte immutable reports.

## Human review and overlap

Review assignments hide model identity in the public payload, store randomized A/B mapping privately, and prevent duplicate submissions. Pairwise choices are A, B, tie, or cannot-judge; identity-suspected responses are recorded. Summary code maps A/B choices back to response identities and reports descriptive same-pair overlap, ties, cannot-judge, and identity-suspected counts. Rubric overlap is descriptive and grouped by reviewed response/reference condition. UI language correctly notes that local evaluator labels do not verify independence; no inferential reliability statistic is reported.

This is overlap/agreement description, not a reliability estimate or population claim. The reviewed pair sample is selected from completed responses, and response self-identification or operator access can defeat practical blinding. Pre-outcome review-item selection and a complete acceptance-tested campaign workflow remain provisional unless verified separately.

## Evidence and claim limits

Backend tests use synthetic fixtures and temporary databases; they do not establish model performance. The existing successful live run described in `AGENTS.md` is a 10-item, two-route convenience-sample smoke only. It is not a broad comparison, the proposed 40-family study, or evidence of general superiority. No new live generation was performed for this documentation update.

No overall composite score, official IFEval result, HELM replication, LLM-judge result, fairness/calibration result, or representative benchmark estimate is claimed. Report task, metric/scorer version, split/family provenance, denominators, omissions, run conditions, and synthetic/live provenance with any result.
