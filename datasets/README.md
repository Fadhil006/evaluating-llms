# Authored evaluation dataset (v1.0)

`v1.0/benchmark.jsonl` contains 12 held-out base questions, two per category,
each with one manually checked meaning-preserving paraphrase (24 test items).
`v1.0/dev.jsonl` contains separate development pairs; debug only with dev items.
Load each file with `evaluation.dataset.load_dataset`; validate a combined list
to check that IDs, prompts, and pairs do not collide across files.

All items are original short prompts authored for this project (`source`:
`original:project-authored`); there are no imported benchmark questions or
third-party license claims. Answers, paired meanings, and deterministic rule
constraints were checked by the author before any held-out model outputs were
inspected. This is a single-author check, not independent adjudication; small
sample size, possible public knowledge contamination, subjective paraphrase
equivalence, and proxy scoring limit conclusions. In particular, code rules
check Python AST syntax/signature only (never execute generated code), and
summary rules check word limits and named terms only, not faithfulness.

Pre-output v1.0 correction: both `i1` variants now declare
`required_json_values` for `city: Oslo` and `color: blue`. The earlier
key-only rule could accept incorrect values. No held-out responses had been
inspected; the version remains v1.0. The scoring engine must enforce this
declared rule before these items are scored.

Do not tune prompts, answers, tolerances, or rules on held-out outputs. Any
post-freeze correction needs a new version and a documented change log;
preserve old records and distinguish offline tests from measured model results.
