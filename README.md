# Evaluating Large Language Models

An evaluation framework for controlled comparisons on project-authored question sets. It provides validated development/held-out datasets, synthetic offline fixtures, explicit opt-in live execution, deterministic/proxy scoring, saved run records, paraphrase analysis, a local-only Flask dashboard, a CLI, history, and CSV export. It is not a generic chatbot. Inspired by the survey's **what to evaluate, where to evaluate, and how to evaluate** dimensions, this small project does **not** implement the entire survey (see [References](#references)).

**Measured results pending.** Existing offline runs are synthetic fixtures, not actual model outputs. The repository currently contains no completed successful live comparison, so it makes no measured accuracy, latency, or model-winner claim. See [`protocol.md`](protocol.md) for the implemented evaluation rules and limitations.

## Implemented scope and current status

The datasets cover reasoning, mathematics, coding, knowledge, summarization, and instruction following. The held-out v1.0 dataset contains 12 base questions plus 12 paired paraphrases (24 items); the separate dev dataset is for development only. Current live OpenRouter choices are allowlisted exact IDs, not verified benchmark results:

| Candidate | Proposed ID |
| --- | --- |
| NVIDIA Nemotron 3 Ultra | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| Google Gemma 4 31B | `google/gemma-4-31b-it:free` |
| Qwen 3.8 27B | `qwen/qwen3.8-27b:free` |
| Cohere North Mini Code | `cohere/north-mini-code:free` |

Catalog listings are **not endpoint tests**. Confirm endpoint availability, routing, supported settings, quotas, and billing before live requests. Fixed IDs do not guarantee immutable hosted weights. The live CLI runs one model per run; the local dashboard compares exactly two models. The OpenCode route has different controls and is not provider-equivalent to OpenRouter.

Official catalog links: [Nemotron](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free), [Gemma](https://openrouter.ai/google/gemma-4-31b-it:free), [Qwen](https://openrouter.ai/qwen/qwen3.8-27b:free), [Cohere](https://openrouter.ai/cohere/north-mini-code:free); [public model catalog API](https://openrouter.ai/api/v1/models). Catalog metadata is time-dependent; these links do not establish successful generation requests.

## Offline fixture run (Python 3.11+)

From the repository root, create a **synthetic** fixture for the four items in [`datasets/v1.0/dev.jsonl`](datasets/v1.0/dev.jsonl). These answers are typed examples, **not model responses or measured results**. `runs/` is ignored by Git.

```sh
python3 -m venv .venv
. .venv/bin/activate
mkdir -p runs
printf '%s\n' '{"fixture-a":{"dr1-o":"B","dr1-p":"B","dm1-o":"7","dm1-p":"7"}}' > runs/fixture-dev.json
python -m evaluation --dataset datasets/v1.0/dev.jsonl --fixtures runs/fixture-dev.json --run-dir runs/dev-synthetic --models fixture-a
```

The fixture file is JSON mapping each model label to item IDs and answer strings (or objects with `status` and `answer`/`error`). The CLI uses only the standard library; it saves a frozen dataset, config, responses, scores, `summary.json`, and `results.csv` in `runs/dev-synthetic/`. Reusing a run directory requires the same dataset, fixture path, and model labels. To rebuild the derived scores, summary, and CSV from the saved responses without making requests:

```sh
python -c 'from evaluation.runner import reanalyze; reanalyze("runs/dev-synthetic")'
python -m json.tool runs/dev-synthetic/summary.json
# CSV: runs/dev-synthetic/results.csv
python -m unittest discover -s tests
```

Optional local-only Flask dashboard and saved-results viewer (third-party dependency, not needed for the CLI; no deployment):

```sh
python -m pip install '.[ui]'
python app.py
```

Open `http://127.0.0.1:8501` on the same machine. The offline demo uses synthetic answers and sends no provider requests.

The Flask form selects a dev or held-out dataset, one or more **complete original/paraphrase pairs**, a backend, two different exact allowlisted model IDs, a shared cumulative request cap (up to 50 attempts), and a local run name. Each selected pair includes both wordings, and both models receive both items. A selected pair therefore means four first attempts total; selecting every dev pair takes 8 and every held-out pair takes 48. A smaller cap leaves a partial run. The local synthetic demo is separate from live comparison: it uses two synthetic fixture labels, performs no provider calls, and is not measured model performance. OpenRouter provider routes are pinned by the app's model mapping; there is no provider-slug selector in the UI. Generation controls are not editable in the UI: OpenRouter uses the fixed system prompt/template, temperature 0, and 512 max tokens, while OpenCode uses separate recorded CLI controls. New runs record selected pair/item IDs, schema/protocol/software versions, `generation_conditions`, and `unsupported_controls` in `config.json`; the saved-run UI displays the raw frozen config as well as provenance. Live requests require explicit confirmation; OpenRouter also runs an access check, and a paid or unverified OpenRouter account requires a positive finite key spending cap. The dashboard can use an exported `OPENROUTER_API_KEY` or the ignored local `.env` (mode 600). Browsing saved runs and downloading CSV does not make provider requests. Fixture outputs cannot establish real model accuracy or latency. Only shared rule-scored items enter the matched comparison; review, invalid, failed, unscored, and pending items remain separate. Reusing a run name requires the same frozen config and selected dataset snapshot; the quota check requires enough remaining quota for the **full selected cap** even on resume.

The dashboard also offers **OpenCode (free-labeled)** for two configured OpenCode models. This uses your installed OpenCode CLI and its existing provider login instead of an OpenRouter key. Do not reuse an OpenRouter run name. A model's “free” label is **not a billing guarantee**: OpenCode has no verified spend-cap preflight here, so check provider/account terms yourself before confirming outbound requests. Timeouts or uncertain CLI failures pause the run for manual inspection; they are never retried automatically.

## Opt-in live run

Live mode requires `--live`, one exact allowlisted `:free` model ID, and one pinned provider slug; provider fallback is disabled. Check the provider route and your account's **free-tier daily quota in the account UI** before opting in. Catalog listings do not guarantee a successful request or free billing. The live CLI reads `OPENROUTER_API_KEY` from the environment, **not automatically from `.env`**. Enter the key only on your own machine (never paste it into chat):

```sh
read -rs -p 'OpenRouter key: ' OPENROUTER_API_KEY; printf '\n'; export OPENROUTER_API_KEY
```

Alternatively, populate an ignored `.env` locally from `.env.example` and explicitly load the trusted, shell-compatible file with `set -a; . ./.env; set +a`. Never commit, log, or save a key in runs/reviews. After checking the local key, exact model ID and provider slug, start with at most two dev requests:

```sh
python -m evaluation --live --dataset datasets/v1.0/dev.jsonl --run-dir runs/gemma-dev-live --model google/gemma-4-31b-it:free --provider google-ai-studio --max-requests 2
```

Only after inspecting that separate dev run and confirming quota/route again, opt into a **new production run** on the held-out set (24 items = 12 base pairs):

```sh
python -m evaluation --live --dataset datasets/v1.0/benchmark.jsonl --run-dir runs/gemma-benchmark-live --model google/gemma-4-31b-it:free --provider google-ai-studio --max-requests 24
```

The live **CLI** still handles one model per run (`--max-requests` up to 40); the local dashboard can compare two models in one saved run (shared cap up to 50). Attempts count cumulatively, including retries, not per invocation. HTTP 429 stops the run; unresolved attempts require manual inspection of saved logs and provider state before any retry, never automatic redispatch. The 12 base pairs are exploratory, not a robust leaderboard; coding and summarization checks are review-only proxies, not functional correctness or faithfulness scores. Instruction-rule scores check declared constraints, **not factual correctness**. **Measured results are pending.** See [`protocol.md`](protocol.md) for the implemented protocol and deferred methods.

# References

These sources inform evaluation design and interpretation. The dataset items, prompts, reference answers, and scoring rules here are project-authored. MT-Bench, Chatbot Arena, PandaLM, HELM, and AlpacaEval are **related work, not implemented or imported benchmarks**; no LLM-as-a-judge, human-preference voting, or calibrated judging workflow is implemented. Their results do not establish performance of any model in this repository. Such methods remain deferred, not implicit capabilities of the two-model UI.

1. Chang et al. (2024), [“A Survey on Evaluation of Large Language Models”](https://doi.org/10.1145/3641289) ([local text](sources/ai_project.md)). Broad overview of tasks, methods, and evaluation benchmarks; motivates reporting task and method explicitly.
2. Zheng et al. (2023), [“Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena”](https://arxiv.org/abs/2306.05685). Introduces MT-Bench and studies model-based judging and its biases. This project does not implement an LLM judge; the work is cited as relevant context, not an implemented method.
3. Chiang et al. (2024), [“Chatbot Arena: An Open Platform for Evaluating LLMs by Human Preference”](https://arxiv.org/abs/2403.04132). Human preference evaluation context; this project instead applies item-level objective/proxy scoring and does not claim Arena-style preference judgments.
4. Liang et al. (2023), [“Holistic Evaluation of Language Models” (HELM)](https://arxiv.org/abs/2211.09110). Supports transparent, multi-metric reporting and explicit scenario coverage; this project is much smaller and does not reproduce HELM.
5. Wang et al. (2023), [“PandaLM: An Automatic Evaluation Benchmark for LLM Instruction Tuning Optimization”](https://arxiv.org/abs/2306.05087). Relevant to automatic evaluation of instruction-following systems; this project does not use PandaLM or its judge.
6. Dubois et al. (2024), [“Length-Controlled AlpacaEval: A Simple Way to Debias Automatic Evaluators”](https://arxiv.org/abs/2404.04475). Illustrates sensitivity/bias in automatic preference evaluation; no AlpacaEval method or judge is implemented here.
7. [OpenRouter API documentation](https://openrouter.ai/docs/api-reference/overview) and [model catalog API](https://openrouter.ai/api/v1/models). Provider integration and dynamic model-catalog information; catalog presence does not guarantee successful requests, fixed weights, or zero billing.

For implemented scoring and limitations, see [`protocol.md`](protocol.md). For the survey's project-specific interpretation, see [`project_overview.md`](project_overview.md).
