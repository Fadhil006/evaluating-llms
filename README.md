# Evaluating Large Language Models

An offline, Python-stdlib fixture runner and an explicit opt-in live CLI for a proposed comparison of accuracy, robustness, and response reliability. The active target is [`plan.md`](plan.md); [`BUILD_PLAN.md`](BUILD_PLAN.md) describes an older, narrower roadmap. Neither is evidence of measured model performance. The survey in [`sources/ai_project.md`](sources/ai_project.md) is read-only reference material.

## Intended scope

The proposed categories are General Reasoning, Mathematics, Coding, Knowledge, Summarization, and Instruction Following. The four **candidate** OpenRouter free-tier IDs from `plan.md` are:

| Candidate | Proposed ID |
| --- | --- |
| NVIDIA Nemotron 3 Ultra | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| Google Gemma 4 31B | `google/gemma-4-31b-it:free` |
| Qwen 3.8 27B | `qwen/qwen3.8-27b:free` |
| Cohere North Mini Code | `cohere/north-mini-code:free` |

On 2026-10-05, the official public catalog returned 404 for the plan's former Nemotron ID and listed the replacement above; the other three IDs were listed with zero prompt/completion prices. Catalog listings are **not endpoint tests**: no measured model results are available. Confirm endpoint availability, routing, supported settings, quotas, and actual billing before live requests. Fixed IDs do not guarantee immutable hosted weights; cached responses replay historical outputs, not fresh independent samples.

Official catalog evidence: [Nemotron](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free), [Gemma](https://openrouter.ai/google/gemma-4-31b-it:free), [Qwen](https://openrouter.ai/qwen/qwen3.8-27b:free), [Cohere](https://openrouter.ai/cohere/north-mini-code:free); [public model catalog API](https://openrouter.ai/api/v1/models). Catalog metadata is time-dependent; these links do not establish successful generation requests.

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

Optional local control panel and saved-results viewer (third-party dependency, not needed for the CLI):

```sh
python -m pip install '.[ui]'
streamlit run app.py
```

Choose a dev or held-out dataset, **two different** pinned free-model routes, a shared cumulative request cap (up to 50 attempts), and a local run name. The dev set needs 8 requests for both models; the held-out set needs 48, excluding retries. A smaller cap leaves the comparison partial. The form sends no model requests until you confirm and click; it checks your key's free quota and requires a finite key spending limit first. During a live run, the page shows the latest saved response, progress, reference answer, and scoring explanation; the saved-run viewer retains the full history. Unlike the CLI, the UI can read the ignored project `.env` directly (mode 600), or use an exported `OPENROUTER_API_KEY`. Switching saved runs and downloading an answer-level CSV never sends provider requests. Fixture outputs are synthetic and cannot establish real model accuracy or latency. The comparison shows only questions with objective scores for both models; review, invalid, failed, and pending items remain separate. Reusing a run name requires the same model order, provider routes, and dataset; the quota check currently requires enough remaining quota for the **full selected cap** even on resume.

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

The live **CLI** still handles one model per run (`--max-requests` up to 40); the **website** can compare two models in one saved run (shared cap up to 50). Attempts count cumulatively, including retries, not per invocation. HTTP 429 stops the run; unresolved attempts require manual inspection of saved logs and provider state before any retry, never automatic redispatch. The 12 base pairs are exploratory, not a robust leaderboard; coding and summarization checks are proxies only, not functional correctness scores. **Measured results are pending.** See [`protocol.md`](protocol.md) for the proposed evaluation protocol.
