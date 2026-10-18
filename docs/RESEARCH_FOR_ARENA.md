# Research basis for the next LLM Comparison Lab

Prepared 2026-10-17; reduced to **five core papers**, including the project's original survey. Status: design inputs, not implemented features or project measurements.

Read alongside [ARENA_BRIEF.md](ARENA_BRIEF.md). This is a deliberately bounded reading list, not a systematic literature review. The arena should use these five sources rather than expand the bibliography. Each has a distinct role: scope, comparable evaluation, objective instruction checks, statistical validity, and judging/review bias.

## Attribution rules

For each feature, identify the paper, method, reused idea, local changes, target module, acceptance test and limitation. Label it **replication**, **adaptation**, or **motivation only**.

- Replication requires pinned data/protocol/scorer versions and compatibility checks. A local subset must be labeled as a subset.
- Adaptations use local names: an IFEval-inspired checker is not an official IFEval result.
- Split enforcement, immutable analysis records, migrations and request budgeting are project engineering decisions. Do not attribute their exact implementation to a paper.
- Published agreement rates or rankings do not transfer to this project.
- Check code/data licenses and pin upstream revisions before reuse.

## R0 — Survey: evaluation scope

**Chang et al., “A Survey on Evaluation of Large Language Models,” ACM TIST, 2024.**

- Source: <https://doi.org/10.1145/3641289>; local text: `sources/ai_project.md` (read-only).
- Borrow: Sections 3–5 organize **what**, **where**, and **how** to evaluate.
- Apply: a coverage matrix connecting tasks, datasets, metrics and supported claims. Declare unsupported domains explicitly.
- Target: dataset manifests, experiment metadata, methodology and exported reports.
- Verify: every displayed metric identifies its task, denominator, version and interpretation.
- Limit: the survey is not a feature checklist. Do not optimize an invented “percentage of the paper completed.”

## R1 — HELM: standardized, multi-metric comparison

**Liang et al., “Holistic Evaluation of Language Models,” arXiv 2022; TMLR 2023.**

- Source: <https://arxiv.org/abs/2211.09110v2>.
- Borrow: scenario taxonomy, standardized conditions, multiple metrics and transparent prompts/completions. HELM includes robustness alongside accuracy and other dimensions.
- Apply: separate task quality, coverage, operational failures, route latency and applicable robustness results; link each to frozen inputs/settings and saved outputs.
- Local adaptation: a small reviewed original/paraphrase family comparison. Define meaning preservation, family membership and paired correctness deltas explicitly; this is not a replication of HELM's robustness suite.
- Target: existing dataset/experiment services, `services/results.py`, report exports and result UI.
- Verify: unequal completion cannot silently alter comparison claims; all common/eligible/scheduled denominators and omissions remain recoverable.
- Limit: no composite average combining accuracy, overlap, latency and preferences. Calibration/fairness require appropriate data and designs; their names alone do not implement them.

## R2 — IFEval: verifiable instruction following

**“Instruction-Following Evaluation for Large Language Models,” 2023.**

- Source: <https://arxiv.org/abs/2311.07911v1>.
- Official implementation: <https://github.com/google-research/google-research/tree/master/instruction_following_eval>, especially `evaluation_lib.py` and `instructions_registry.py`.
- Borrow: deterministic checks for verifiable instructions, and the distinction between instruction-level and prompt-level success. The official implementation separates strict and loose checking.
- Apply: expand current exact-text/exact-JSON checks with a bounded set such as explicit word/keyword constraints; retain individual check outcomes.
- Target: `backend/app/evaluation/scoring.py`, validated scorer configurations and result aggregations.
- Verify: counting/Unicode/case/boundary behavior; reject empty check lists; distinguish pooled check accuracy from all-check prompt accuracy when prompts contain unequal numbers of constraints.
- Limit: use strict checks first. Any loose normalization must be separately versioned. Claim official IFEval compatibility only after comparison against a pinned official evaluator. Constraint compliance is not truthfulness/helpfulness.

## R3 — Statistical testing: align inference with the design

**Dror, Baumer, Shlomov and Reichart, “The Hitchhiker’s Guide to Testing Statistical Significance in Natural Language Processing,” ACL 2018.**

- Source: <https://aclanthology.org/P18-1128/>; DOI: <https://doi.org/10.18653/v1/P18-1128>.
- Borrow: statistical method selection must reflect the task, metric, assumptions and experimental setup.
- Local adaptation, not a formula prescribed by this paper: paired cluster resampling by independent base-item family, retaining its repeats/variants together. Define weighting, missingness and the estimand before selecting an interval method.
- Target: pinned analysis policy and a small helper used by existing results/exports.
- Verify: identical models have zero paired difference; swapping models reverses the difference; repeated generations do not inflate independent item count; macro-F1 is recomputed from resampled confusion data, not averaged per-item F1.
- Limit: conditional/convenience-sample intervals do not establish representativeness or correct selective missingness. Define small-sample and degenerate behavior. P-values are optional and require a justified multiple-comparison policy when applicable.

## R4 — MT-Bench / Chatbot Arena: preference and judge bias

**Zheng et al., “Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena,” NeurIPS 2023.**

- Source: <https://arxiv.org/abs/2306.05685v4>; relevant sections: 2 and 3.3–3.4.
- Borrow: human preference evaluation and study of position, verbosity and self-enhancement biases; swapped-answer-order checks and reference-guided judging.
- Apply first: strengthen the existing blinded review workflow, preserve A/B mapping, keep preference separate from correctness, and inspect response-length confounding.
- Optional extension: judge already persisted responses with versioned rubric/model/reference policy; retain both swapped-order verdicts and calibrate against separate human-reviewed families.
- Local adaptation: inconsistent swapped verdicts become **inconsistent/needs review**, distinct from genuine ties. This differs from the paper's conservative tie treatment. Review campaign assignment/overlap policies are local design, not replicated paper protocols.
- Target: existing review service/UI; separate judge records and budget only if the optional track is selected.
- Verify: duplicate submissions, identity leakage, swapped-order disagreement, verbosity stress cases, malformed verdicts and candidate-answer prompt injection.
- Limit: local evaluator labels are not verified independent people. The paper's agreement findings do not validate a different/free judge. Length diagnostics are not statistical length correction. Do not import a leaderboard or executable coding track into this release merely to add scope.

## Bounded release mapping

| Workstream | Source / relationship | Priority |
|---|---|---|
| Scope and interpretable report cards | R0, R1 adaptation | Core |
| Provenance, held-out splits, immutable analysis | R0/R1 motivation plus local engineering | Core |
| Paired uncertainty and independent-family counts | R3 motivation plus specified local statistical design | Core |
| Verifiable instruction checks | R2 adaptation | Preferred objective track |
| Reviewed paraphrase robustness | R1 motivation, R3 analysis principles | Small optional track |
| Blinded review and bias diagnostics | R4 adaptation | Reuse/strengthen existing feature |
| Calibrated LLM judge | R4 adaptation | Conditional, after core acceptance |

Deferred from the reading list and initial scope: dedicated contamination-refresh benchmarks, regression-based length adjustment, large-scale ranking systems and executable code benchmarks. Keep provenance, length visibility and honest coding-proxy labels as engineering safeguards without claiming those deferred methods are implemented.
