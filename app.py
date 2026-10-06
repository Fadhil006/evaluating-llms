"""Opt-in local run controls and read-only viewer. Start with: streamlit run app.py"""

import csv
import hashlib
import io
import json
import re
from uuid import uuid4
from collections import Counter
from pathlib import Path

import streamlit as st


RUNS = Path(__file__).resolve().parent / "runs"
DATASETS = Path(__file__).resolve().parent / "datasets" / "v1.0"
MODEL_NAMES = {
    "nvidia/nemotron-3-ultra-550b-a55b:free": "Nemotron 3 Ultra",
    "google/gemma-4-31b-it:free": "Gemma 4 31B",
    "qwen/qwen3.8-27b:free": "Qwen 3.8 27B",
    "cohere/north-mini-code:free": "North Mini Code",
}
MODEL_PROVIDERS = {
    "nvidia/nemotron-3-ultra-550b-a55b:free": "nvidia",
    "google/gemma-4-31b-it:free": "google-ai-studio",
    "qwen/qwen3.8-27b:free": "modelrun/fp4",
    "cohere/north-mini-code:free": "cohere",
}
OPENCODE_MODELS = {
    "opencode/ling-3.1-flash-free": "Ling 3.1 Flash",
    "opencode/nemotron-3-ultra-free": "Nemotron 3 Ultra",
}
FILES = ("config.json", "dataset.jsonl", "responses.jsonl", "scores.jsonl", "summary.json")
PROXY = {"code_syntax": "Syntax/signature proxy · human review needed",
         "summary_constraints": "Length/term proxy · human review needed"}


def safe_run_path(name):
    """Permit only a single plain directory name under the local runs root."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Use 1–64 letters, digits, dashes or underscores; start with a letter or digit.")
    folder = RUNS / name
    if RUNS.is_symlink() or folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError("That run name is not a safe directory.")
    return folder


def control_panel():
    with st.container(border=True, key="workbench"):
        st.caption("01  /  RUN WORKBENCH")
        st.header("Compare two models.")
        st.write("Start with the four-answer offline demo above. For a live run, choose one dataset and two models; nothing is sent until you confirm.")
        backend = st.selectbox("How will you connect?", ["OpenRouter", "OpenCode (free-labeled)"])
        opencode = backend == "OpenCode (free-labeled)"
        choices = OPENCODE_MODELS if opencode else MODEL_PROVIDERS
        st.caption("OpenCode uses your existing provider login; 'free' labels may still use billable quota and there is no verified spend-cap check." if opencode else
                   "OpenRouter uses a local key and checks free-request quota and your key's spend limit before starting. A free listing is not a billing guarantee.")
        with st.form("live_run", clear_on_submit=False):
            a, b = st.columns(2)
            dataset = a.selectbox("Dataset", ["dev.jsonl", "benchmark.jsonl"],
                                  format_func=lambda name: "Development · 4 questions" if name == "dev.jsonl" else "Held-out · 24 questions")
            a.caption("Start with development; inspect saved answers before trying held-out.")
            if opencode:
                models = list(OPENCODE_MODELS)
                b.write("**Models · fixed pair**")
                b.write("Ling 3.1 Flash + Nemotron 3 Ultra")
            else:
                models = [b.selectbox("First free model / pinned route", list(choices),
                                      format_func=lambda name: f"{MODEL_NAMES[name]} · {MODEL_PROVIDERS[name]}"),
                          b.selectbox("Second free model / pinned route", list(choices), index=1,
                                      format_func=lambda name: f"{MODEL_NAMES[name]} · {MODEL_PROVIDERS[name]}")]
            with st.expander("Show exact model IDs"):
                for model in models:
                    st.code(model, language="text")
            c, d = st.columns(2)
            run_name = c.text_input("Local run name", value="pilot-opencode" if opencode else "pilot-dev",
                                    key=f"run_name_{backend}",
                                    help="Reuse a name only to resume the same backend, two models, their order, and dataset; otherwise choose a new name.")
            cap = d.number_input("Total attempt cap for both models", min_value=1, max_value=50, value=8, step=1,
                                 help="One shared cap across both models; earlier attempts and retries count when resuming. Not a per-click allowance.")
            workload = 8 if dataset == "dev.jsonl" else 48
            st.caption(f"{'Development: 4' if dataset == 'dev.jsonl' else 'Held-out: 24'} questions × 2 models = {workload} planned answers. "
                       + (f"Cap {int(cap)} is below {workload}: this comparison will be partial." if cap < workload else
                          f"Cap {int(cap)} covers planned answers; retries also use the shared cap."))
            if opencode:
                confirmed = st.checkbox("I agree to send requests via OpenCode to both models, up to the shared cap. Free labels may use billable provider quota; there is no verified spend-cap check.")
            else:
                confirmed = st.checkbox("I agree to send requests via OpenRouter to both models, up to the shared cap, after the local key and quota check.")
            submitted = st.form_submit_button("Start comparison" if opencode else "Check access & start comparison", type="primary")
    if not submitted:
        return
    if len(set(models)) != 2 or any(model not in choices for model in models):
        st.error("Choose two different models before starting. Nothing was sent.")
        return
    if not confirmed:
        st.warning("Confirm outbound requests before starting. Nothing was sent.")
        return
    try:
        folder = safe_run_path(run_name)
    except (TypeError, ValueError):
        st.error("Invalid run name. Use 1–64 letters, digits, dashes or underscores, starting with a letter or digit.")
        return
    if not opencode:
        try:
            # Import only after explicit confirmation; the saved-run viewer never touches providers.
            from evaluation.access import preflight
            access = preflight(max_requests=int(cap))
            if not isinstance(access, dict) or access.get("allowed") is False or access.get("ok") is False:
                raise ValueError("preflight denied")
        except Exception:
            st.error("OpenRouter access check blocked this run; no model request was started. Check your local key, remaining free requests and key spend limit in your OpenRouter account. A missing spend limit can block the check. You can lower the shared cap or try the offline demo; only retry after checking your account.")
            return
        st.success(f"OpenRouter access check passed · shared cap {int(cap)} attempts for both models, including prior attempts · pinned routes: "
                   + " · ".join(f"{MODEL_NAMES[model]} → {MODEL_PROVIDERS[model]}" for model in models) + ".")
        # Whitelist only numerical quota/cap fields; never render arbitrary backend data or credentials.
        labels = {"free_remaining": "Free requests remaining", "free_limit": "Daily free limit",
                  "spend_limit": "Key spend cap", "spend_remaining": "Spend cap remaining"}
        metadata = [f"{label}: {access[key]}" for key, label in labels.items()
                    if type(access.get(key)) in (int, float)]
        if metadata:
            st.caption(" · ".join(metadata))
    else:
        st.info("OpenCode · no verified quota or spend-cap preflight. Requests start only after your confirmation above.")
    progress_area = st.empty()

    def show_saved_response(event):
        """Render only fields from a saved-response event, never provider metadata."""
        if not isinstance(event, dict) or event.get("model") not in models:
            return
        completed, planned, attempts = (event.get(key) for key in ("completed", "planned", "attempts"))
        if (any(type(value) is not int for value in (completed, planned, attempts)) or
                not 0 <= completed <= planned or planned < 1 or attempts < 0):
            return
        status = event.get("status")
        statuses = {"ok": "Answer saved", "rate_limited": "Rate limited · awaiting retry",
                    "error": "Request failed", "truncated": "Answer truncated"}
        score = event.get("score_status")
        with progress_area.container(border=True):
            st.caption(f"02  /  {backend.upper()} · LATEST SAVED RESPONSE")
            st.subheader(f"{choices[event['model']] if opencode else MODEL_NAMES[event['model']]} · {str(event.get('item_id', ''))}")
            a, b = st.columns(2)
            a.metric("Saved outcomes", f"{completed}/{planned}")
            b.metric("Cumulative attempts", attempts)
            st.progress(completed / planned, text=f"{completed}/{planned} planned model answers saved")
            st.caption("Latest response only · full history appears in the saved-run viewer below.")
            st.write("Question")
            st.code(str(event.get("prompt") or "Not recorded"), language="text")
            if status == "ok":
                st.write("Model answer")
                st.code(str(event.get("answer") if event.get("answer") is not None else "No saved answer"), language="text")
            else:
                st.warning(statuses.get(status, "Request did not produce a scored answer"))
            st.write("Expected answer")
            st.code(str(event.get("reference_answer") or "Not recorded"), language="text")
            if status == "ok":
                if score == "scored" and type(event.get("correct")) is bool:
                    st.write(f"Objective score: {'Correct' if event['correct'] else 'Incorrect'}")
                elif score == "review":
                    st.info("Needs human review · not an objective correctness score.")
                else:
                    st.warning("Invalid or unscored answer · not an objective correctness score.")
                if score in ("scored", "review", "invalid"):
                    st.caption(f"Score status: {score}")
                if isinstance(event.get("explanation"), str) and event["explanation"]:
                    st.write("Scoring explanation")
                    st.code(event["explanation"], language="text")

    try:
        with st.spinner("Waiting for saved responses from both models within the shared cap…"):
            if opencode:
                from evaluation.runner import run_opencode_comparison
                result = run_opencode_comparison(DATASETS / dataset, folder, models, int(cap),
                                                 on_progress=show_saved_response)
            else:
                from evaluation.runner import run_live_comparison
                result = run_live_comparison(DATASETS / dataset, folder, models,
                                             {model: MODEL_PROVIDERS[model] for model in models}, int(cap),
                                             on_progress=show_saved_response)
    except Exception:
        st.error("Run paused or failed. No automatic retry was started. Check this run's saved attempts and responses locally, then check your provider account before trying again; an uncertain request may have reached the provider.")
        return
    st.session_state["selected_run"] = folder.name
    level, message = run_feedback(result, models)
    getattr(st, level)(message)
    if opencode and result.get("paused"):
        st.info("OpenCode paused: inspect attempts.jsonl and responses.jsonl in this run and check your provider account before trying again. An unresolved attempt may have reached the provider even if no answer was saved.")


def create_demo_run():
    """Create a clearly labeled synthetic development run through the ordinary runner."""
    from evaluation.runner import run

    name = f"demo-{uuid4().hex[:10]}"
    folder = safe_run_path(name)
    RUNS.mkdir(parents=True, exist_ok=True)
    fixture_path = RUNS / f"{name}.fixtures.json"
    fixture_path.write_text(json.dumps({"demo-fixture": {
        "dr1-o": "B", "dr1-p": "B", "dm1-o": "7", "dm1-p": "7",
    }}), encoding="utf-8")
    run(DATASETS / "dev.jsonl", fixture_path, folder, ["demo-fixture"])
    return folder


def load_run(folder):
    """Load only the five expected local files; never invoke the evaluation runner."""
    if folder.is_symlink() or folder.parent != RUNS or not folder.is_dir():
        raise ValueError("Choose a directory directly under runs/.")
    for name in FILES:
        path = folder / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or unsafe run file: {name}")

    def lines(name):
        with (folder / name).open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def document(name):
        with (folder / name).open(encoding="utf-8") as stream:
            return json.load(stream)

    return (document("config.json"), lines("dataset.jsonl"),
            lines("responses.jsonl"), lines("scores.jsonl"), document("summary.json"))


def csv_cell(value):
    """Keep downloaded spreadsheet cells from becoming formulas on open."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def export_csv(rows):
    stream = io.StringIO()
    fields = ("model", "item_id", "pair_id", "variant", "category", "scorer",
              "prompt", "reference_answer", "raw_answer", "response_status",
              "score_status", "correct", "explanation", "checks")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows({field: csv_cell(row.get(field)) for field in fields} for row in rows)
    return stream.getvalue().encode("utf-8-sig")


def joined_rows(items, responses, scores, models):
    """Preserve unanswered items and prefer terminal attempts to interim 429s."""
    answer_by_key = {}
    for response in responses:
        key = (response.get("model"), response.get("item_id"))
        if key not in answer_by_key or response.get("status") != "rate_limited":
            answer_by_key[key] = response
    score_by_key = {(row.get("model"), row.get("item_id")): row for row in scores}
    rows = []
    for model in models:
        for item in items:
            response = answer_by_key.get((model, item["id"]), {})
            score = score_by_key.get((model, item["id"]), {})
            rows.append({"model": model, "item_id": item["id"], "pair_id": item.get("pair_id"),
                         "variant": item.get("variant"), "category": item.get("category"),
                         "scorer": item.get("scorer"), "prompt": item.get("prompt"),
                         "reference_answer": item.get("reference_answer"),
                         "rules": item.get("rules"), "raw_answer": response.get("raw_answer"),
                         "response_status": "truncated" if response.get("finish_reason") == "length"
                         else response.get("status", "pending"),
                         "error": response.get("error"), "latency_ms": response.get("latency_ms"),
                         "score_status": score.get("status"), "correct": score.get("correct"),
                         "explanation": score.get("explanation"), "checks": score.get("checks")})
    return rows


def tally(rows):
    counts = Counter()
    for row in rows:
        counts["total"] += 1
        if row["response_status"] == "ok":
            if row["correct"] is True:
                counts["correct"] += 1
                counts["scored"] += 1
            elif row["correct"] is False:
                counts["incorrect"] += 1
                counts["scored"] += 1
            elif row["score_status"] == "review":
                counts["review"] += 1
            else:
                counts["invalid"] += 1
        elif row["response_status"] in ("pending", "rate_limited"):
            counts["pending"] += 1
        elif row["response_status"] == "truncated":
            counts["truncated"] += 1
        else:
            counts["failures"] += 1
    return counts


def rate(counts):
    return (f'{counts["correct"]}/{counts["scored"]} scored '
            f'({counts["correct"] / counts["scored"]:.1%})' if counts["scored"] else "— (0 scored)")


def run_feedback(result, models):
    """Describe saved progress without calling a capped, incomplete run finished."""
    progress = ", ".join(f"{MODEL_NAMES.get(model, OPENCODE_MODELS.get(model, model))}: "
                         f"{result.get('models', {}).get(model, {}).get('answered', 0)}/"
                         f"{result.get('models', {}).get(model, {}).get('total', 0)} answered, "
                         f"{result.get('models', {}).get(model, {}).get('pending', 0)} pending"
                         for model in models)
    pending = sum(result.get("models", {}).get(model, {}).get("pending", 0) for model in models)
    if result.get("paused"):
        return "warning", f"Comparison paused. {progress}. Inspect saved records before trying again."
    if pending:
        return "warning", (f"Partial comparison: {pending} answer{'s' if pending != 1 else ''} still pending. "
                           f"{progress}. The shared cap may limit coverage; inspect saved records before increasing it.")
    return "success", f"Both models have saved outcomes. {progress}. Inspect the results below."


def matched_comparison(rows, models):
    """Show rates only where every model has an objective score for the same item."""
    if len(models) < 2:
        return []
    by_key = {(row["model"], row["item_id"]): row for row in rows}
    item_ids = {row["item_id"] for row in rows}
    matched = [item_id for item_id in item_ids if all(
        type(by_key.get((model, item_id), {}).get("correct")) is bool for model in models)]
    result = []
    for model in models:
        correct = sum(by_key[(model, item_id)]["correct"] for item_id in matched)
        result.append({"Model": model, "Correct / matched": f"{correct}/{len(matched)}" if matched else "—",
                       "Matched rate": correct / len(matched) if matched else None,
                       "Shared scored items": len(matched)})
    return result


def attention_matches(row, choice):
    if choice == "All":
        return True
    if choice == "Needs review":
        return row["score_status"] == "review"
    if choice == "Incorrect":
        return row["correct"] is False
    if choice == "Invalid / failed":
        return row["score_status"] == "invalid" or row["response_status"] in ("error", "truncated")
    if choice == "Pending":
        return row["response_status"] in ("pending", "rate_limited")
    return row["correct"] is True


def main():
    st.set_page_config(page_title="Evaluation Studio / local evidence", page_icon="◈", layout="wide")
    st.markdown("""<style>
      :root {--ink: #183532; --muted: #45635d; --line: #c8d9d2; --accent: #146c64; --warm: #b75d37;}
      .stApp {
        background: radial-gradient(ellipse at 94% 0%, #e4f1ec 0, transparent 35%), #f7faf8;
        color: var(--ink);
        font-family: 'Avenir Next', 'Segoe UI', sans-serif;
      }
      .block-container {max-width: 1200px; padding: 3rem clamp(1.25rem, 4vw, 4rem) 6rem;}
      h1, h2, h3 {font-family: 'Palatino Linotype', 'Book Antiqua', Georgia, serif;
        letter-spacing: -.04em; color: var(--ink);}
      h1 {font-size: clamp(2.75rem, 5vw, 4.65rem) !important; line-height: 1.06 !important;
        max-width: 850px; margin: .25rem 0 .5rem !important;}
      h2 {font-size: clamp(1.9rem, 3vw, 2.75rem) !important; line-height: 1.12;}
      h3 {font-size: 1.65rem !important;}
      p, label {line-height: 1.55;}
      [data-testid="stCaptionContainer"] {color: var(--muted); letter-spacing: .035em;}
      .studio-eyebrow, .studio-index {font: 700 .74rem/1.5 'Avenir Next','Segoe UI',sans-serif;
        letter-spacing: .19em; color: #315e4f; text-transform: uppercase;}
      .studio-eyebrow::before {content: ''; display: inline-block; width: 22px; height: 2px;
        vertical-align: middle; margin-right: 12px; background: var(--warm);}
      .studio-note {border-left: 2px solid var(--warm); margin: 1.1rem 0 1.5rem;
        padding: .4rem 0 .4rem 1rem; color: var(--muted); max-width: 640px;
        font-size: 1.04rem; line-height: 1.6;}
      div.st-key-workbench {background: #edf5f1; border: 1px solid #c2d8cf;
        border-radius: 1rem; padding: clamp(1.15rem, 3vw, 2rem);
        box-shadow: 0 18px 40px rgba(22,75,70,.07);}
      div.st-key-workbench [data-testid="stForm"] {border: 0; background: transparent; padding: .4rem 0 0;}
      div.st-key-workbench [data-testid="stCaptionContainer"] {font-size: .77rem; font-weight: 650;}
      [data-testid="stSelectbox"] [data-baseweb="select"] > div,
      [data-testid="stTextInput"] input,
      [data-testid="stNumberInput"] input {
        background: #fff !important; border-color: #adc9bf !important;
        border-radius: .7rem !important; color: var(--ink) !important;
      }
      [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
      [data-testid="stTextInput"] input:hover,
      [data-testid="stNumberInput"] input:hover {border-color: var(--accent) !important;}
      [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
      [data-testid="stTextInput"] input:focus,
      [data-testid="stNumberInput"] input:focus {
        box-shadow: 0 0 0 3px rgba(20,108,100,.18) !important;
        border-color: var(--accent) !important;
      }
      [data-baseweb="popover"] [role="listbox"] {
        background: #fff; border: 1px solid #c3d8d0;
        border-radius: .75rem; box-shadow: 0 14px 32px rgba(18,62,57,.16);
      }
      [data-baseweb="popover"] [role="option"] {color: var(--ink);}
      [data-baseweb="popover"] [role="option"]:hover,
      [data-baseweb="popover"] [role="option"][aria-selected="true"] {
        background: #e3f2ed; color: #0d504a;
      }
      [data-testid="stAlert"] {border-radius: .6rem; border-width: 1px;}
      [data-testid="stMetric"] {background: #fff; border: 1px solid var(--line);
        border-top: 3px solid var(--accent); padding: 1.15rem; border-radius: .6rem;
        min-height: 126px; box-shadow: 0 12px 24px rgba(18,58,45,.055);}
      [data-testid="stMetricValue"] {font-family: Georgia,serif; color: var(--ink); font-size: 2rem;}
      [data-testid="stMetricLabel"] {color: #365b54;}
      [data-testid="stDataFrame"] {border: 1px solid var(--line); border-radius: .6rem;
        box-shadow: 0 8px 26px rgba(22,53,47,.045);}
      [data-testid="stTabs"] [role="tablist"] {border-bottom: 1px solid var(--line); gap: .3rem;}
      [data-testid="stTabs"] button[role="tab"] {font-weight: 650; color: #415a52;}
      [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {color: var(--accent);}
      div[data-testid="stFormSubmitButton"] button, div[data-testid="stDownloadButton"] button {
        background: var(--accent); color: #fff; border: 1px solid var(--accent); border-radius: .65rem;
        font-weight: 700; padding-inline: 1.4rem; min-height: 2.9rem;
      }
      div[data-testid="stFormSubmitButton"] button:hover, div[data-testid="stDownloadButton"] button:hover {
        background: #0d5751; color: #fff; border-color: #0d5751; transform: translateY(-1px);
        box-shadow: 0 8px 18px rgba(20,108,100,.17);
      }
      button:focus-visible, [role="tab"]:focus-visible {outline: 3px solid #b75d37 !important; outline-offset: 2px;}
      @media(max-width: 700px) {
        .block-container {padding: 1.5rem 1rem 4rem;}
        [data-testid="stTabs"] [role="tablist"] {overflow-x: auto;}
        [data-testid="stMetric"] {min-height: 0;}
        [data-testid="stCodeBlock"] pre {white-space: pre-wrap; overflow-wrap: anywhere;}
      }
      @media(prefers-reduced-motion: reduce) {
        div[data-testid="stFormSubmitButton"] button:hover, div[data-testid="stDownloadButton"] button:hover {transform: none;}
      }
    </style>""", unsafe_allow_html=True)

    st.markdown('<div class="studio-eyebrow">Evaluation studio / local-first research</div>', unsafe_allow_html=True)
    st.title("Evidence, not a leaderboard.")
    st.markdown('<div class="studio-note">Start with a saved example, then inspect real runs with care. '
                'Viewing results never sends requests.</div>', unsafe_allow_html=True)
    st.caption("START HERE  /  1. Explore the offline demo  →  2. Opt in to a live comparison if ready  →  3. Read saved answers below")
    if st.button("Try offline demo", help="Create a synthetic four-answer development run. No key or provider request is used."):
        try:
            folder = create_demo_run()
        except (OSError, ValueError):
            st.error("Could not create the offline demo. Check the local runs folder and try again.")
        else:
            st.session_state["selected_run"] = folder.name
            st.success("Synthetic demo saved. Its four example answers are ready to inspect below.")
    st.caption("Four synthetic answers · no account, key or network request needed. Demo scores are not measured model performance.")
    with st.expander("Compare live models (optional)", expanded=False):
        control_panel()
    st.markdown('<div class="studio-eyebrow" style="margin-top:2.2rem">EVIDENCE ARCHIVE</div>', unsafe_allow_html=True)
    st.header("Read the record.")
    st.caption("Saved runs only · choosing a run or answer never starts requests")
    choices = sorted((p for p in RUNS.iterdir() if p.is_dir() and not p.is_symlink()),
                     key=lambda p: p.name) if RUNS.is_dir() else []
    if not choices:
        st.info("No saved runs found in runs/. Confirm a local run above to create one.")
        return
    preferred = st.session_state.pop("selected_run", None)
    if preferred:
        match = next((path for path in choices if path.name == preferred), None)
        if match is not None:
            st.session_state["viewer_run"] = match
    folder = st.selectbox("Saved run", choices, key="viewer_run", format_func=lambda path: path.name)
    try:
        config, items, responses, scores, summary = load_run(folder)
        models = config["models"]
        if not isinstance(models, list) or not models or not isinstance(summary.get("models"), dict):
            raise ValueError("Run metadata is missing its model list or summary.")
        rows = joined_rows(items, responses, scores, models)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        st.error("Cannot read this saved run. Inspect its local files for missing or invalid records.")
        return

    synthetic = config.get("synthetic") is True or summary.get("synthetic") is True
    evidence = ("SYNTHETIC · OFFLINE FIXTURE — not measured model performance" if synthetic else
                "DECLARED LIVE · SAVED RECORDS (not independently verified)" if config.get("synthetic") is False and summary.get("synthetic") is False
                else "EVIDENCE TYPE UNVERIFIED · inspect run metadata before interpreting results")
    st.caption("EVIDENCE STATUS  /  READ BEFORE COMPARING")
    st.badge("Synthetic example" if synthetic else "Saved live record" if "UNVERIFIED" not in evidence
             else "Evidence type unverified", color="orange" if synthetic or "UNVERIFIED" in evidence else "blue")
    (st.warning if synthetic or "UNVERIFIED" in evidence else st.info)(evidence)
    source = summary.get("source", config.get("source", "not recorded"))
    display_source = "OpenCode · saved live" if isinstance(source, str) and source.startswith("opencode") else source
    st.caption(f"Source: {display_source}  ·  "
               f"Dataset: {config.get('dataset_version', 'not recorded')}")
    if not synthetic and not responses:
        st.warning("No model responses are saved in this run. An attempted request may still have reached the provider. Inspect local attempts and your provider account before trying again; there is no measured comparison here.")
    with st.expander("Run provenance and frozen dataset hash"):
        st.code(config.get("dataset_hash", "not recorded"), language="text")
        st.write("Model routes:", config.get("providers", config.get("provider", "OpenCode provider login" if
                                                        isinstance(source, str) and source.startswith("opencode") else "offline fixture")))
        st.write("Created:", config.get("created_at", "not recorded"))
    with st.expander("How to read these results"):
        st.write("Correct / scored includes only objectively scored answers. Review, invalid, failed, "
                 "truncated, and pending items have separate counts.")
        st.write("Coding and summarization are proxy checks requiring human review. "
                 "The results do not establish an overall model ranking.")

    if len(models) == 2:
        overview, compare, categories, robustness, inspector = st.tabs(
            ["Overview", "Compare answers", "By category", "Paired robustness", "Answer inspector"])
    else:
        overview, categories, robustness, inspector = st.tabs(
            ["Overview", "By category", "Paired robustness", "Answer inspector"])
        compare = None
    with overview:
        st.header("Model coverage")
        st.caption("Saved results only. A blank score means there are no objectively scored answers; pending and failed requests are not counted as wrong.")
        focus = st.selectbox("Focus model", models, key="overview_model")
        focused = summary["models"].get(focus, {})
        correct, scored = focused.get("correct", 0), focused.get("scored", 0)
        cards = st.columns(4)
        cards[0].metric("Correct / scored", f"{correct}/{scored}" if scored else "—",
                        help="Only answers with an objective score count here.")
        cards[1].metric("Answered / total", f"{focused.get('answered', 0)}/{focused.get('total', len(items))}")
        cards[2].metric("For human review", focused.get("review", 0))
        cards[3].metric("Pending", focused.get("pending", 0))
        if scored:
            st.progress(correct / scored, text=f"{focus} · {correct}/{scored} scored ({correct / scored:.1%})")
        else:
            st.caption("No objectively scored answers yet for this model; no rate is shown.")
        completed = focused.get("total", len(items)) - focused.get("pending", 0)
        if focused.get("total", len(items)):
            st.progress(completed / focused.get("total", len(items)),
                        text=f"Saved outcomes: {completed}/{focused.get('total', len(items))}")
        st.caption("Failed, invalid and truncated requests are shown separately in the full table below.")
        model_table = []
        for model in models:
            counts = summary["models"].get(model, {})
            scored = counts.get("correct", 0) + counts.get("incorrect", 0)
            model_table.append({"Model": model, "Correct / scored": rate({"correct": counts.get("correct", 0),
                                                                              "scored": scored}),
                                "Answered / total": f"{counts.get('answered', '—')} / {counts.get('total', '—')}",
                                "Review": counts.get("review", "—"), "Invalid": counts.get("invalid", "—"),
                                "Failures": counts.get("failures", "—"), "Truncated": counts.get("truncated", "—"),
                                "Pending": counts.get("pending", "—")})
        st.dataframe(model_table, width="stretch", hide_index=True)
        if len(models) > 1:
            st.caption("COVERAGE  /  SAVED OUTCOMES BY MODEL")
            for model in models:
                counts = summary["models"].get(model, {})
                total = counts.get("total", len(items))
                completed = total - counts.get("pending", total)
                if total:
                    st.progress(completed / total, text=f"{MODEL_NAMES.get(model, OPENCODE_MODELS.get(model, model))} · {completed}/{total} saved outcomes")
            if any(summary["models"].get(model, {}).get("pending", 0) for model in models):
                st.info("Partial comparison: pending answers are not counted as wrong. Same-item rates below use only shared scored items.")
        matched = matched_comparison(rows, models)
        if matched:
            st.subheader("Same-item comparison")
            st.caption("Includes only items with an objective score from every model. "
                       "Coverage and failures remain visible above; no overall ranking is inferred.")
            if matched[0]["Shared scored items"]:
                st.dataframe(matched, width="stretch", hide_index=True,
                             column_config={"Matched rate": st.column_config.ProgressColumn(
                                 "Matched rate", format="%.0f%%", min_value=0, max_value=1)})
            else:
                st.info("No questions have objective scores for both models yet. Check coverage and saved answers before comparing.")
        st.caption("No cost or token estimates: the saved records do not provide a comparable measure.")

    if compare is not None:
        with compare:
            st.header("The same question, two saved records")
            st.caption("Read answers side by side. Pending, failed and review items are not objective scores or a model ranking.")
            item = st.selectbox("Question to compare", items, key="compare_item",
                                format_func=lambda entry: f"{entry['id']} · {entry.get('category', 'Question')}")
            st.write("Question")
            st.code(item["prompt"], language="text")
            st.write("Reference answer")
            st.code(item.get("reference_answer") or "Not recorded", language="text")
            selected_rows = {row["model"]: row for row in rows if row["item_id"] == item["id"]}
            for column, model in zip(st.columns(2, gap="medium"), models):
                row = selected_rows[model]
                with column.container(border=True):
                    st.subheader(MODEL_NAMES.get(model, OPENCODE_MODELS.get(model, model)))
                    st.caption(model)
                    status = row["response_status"]
                    if status == "ok":
                        st.write("Saved answer")
                        st.code(row["raw_answer"] if row["raw_answer"] is not None else "No saved answer", language="text")
                        if row["score_status"] == "scored" and type(row["correct"]) is bool:
                            st.write("Objective score: " + ("Correct" if row["correct"] else "Incorrect"))
                        elif row["score_status"] == "review":
                            st.info("Needs human review · no objective score.")
                        else:
                            st.warning("Invalid or unscored · no objective score.")
                        if row["explanation"]:
                            st.write("Scoring explanation")
                            st.code(row["explanation"], language="text")
                    elif status in ("pending", "rate_limited"):
                        st.info("Rate limited · no saved answer" if status == "rate_limited" else "Pending · no saved answer")
                    else:
                        st.warning("Truncated · no objective score" if status == "truncated" else "Request failed · no saved answer")

    with categories:
        st.header("Capability slices")
        st.caption("Each row uses its own model × category denominator from the frozen dataset; "
                   "review and missing answers are not treated as wrong.")
        category_table = []
        for model in models:
            for category in sorted({row["category"] for row in rows}):
                group = [row for row in rows if row["model"] == model and row["category"] == category]
                counts = tally(group)
                category_table.append({"Model": model, "Category": category,
                                       "Correct / scored": rate(counts),
                                       "Objective rate": counts["correct"] / counts["scored"] if counts["scored"] else None,
                                       "Items": counts["total"],
                                       "Review": counts["review"], "Invalid": counts["invalid"],
                                       "Failed": counts["failures"], "Truncated": counts["truncated"],
                                       "Pending": counts["pending"]})
        st.dataframe(category_table, width="stretch", hide_index=True,
                     column_config={"Objective rate": st.column_config.ProgressColumn(
                         "Objective rate", help="Correct / scored only. Blank means no objectively scored answers.",
                         format="%.0f%%", min_value=0, max_value=1)})
        st.caption("Coding = syntax/signature proxy; summarization = constraints proxy. "
                   "Neither gives a correctness rate without human review.")

    with robustness:
        st.header("Original ↔ paraphrase")
        st.caption("Only paired metrics already saved in summary.json are reported below. "
                   "Delta is original minus paraphrase in percentage points when present.")
        any_pairs = False
        for model in models:
            pairs = summary["models"].get(model, {}).get("pairs")
            if isinstance(pairs, dict):
                any_pairs = True
                st.subheader(model)
                complete, planned = pairs.get("complete", 0), pairs.get("planned", 0)
                delta = pairs.get("original_minus_variant_pp")
                a, b, c = st.columns(3)
                a.metric("Complete scored pairs", f"{complete}/{planned}")
                b.metric("Original correct", f"{pairs.get('original_correct', 0)}/{complete}" if complete else "—")
                c.metric("Paraphrase correct", f"{pairs.get('variant_correct', 0)}/{complete}" if complete else "—")
                st.write("Original − paraphrase:", f"{delta:+.1f} percentage points" if delta is not None else
                         "No complete objectively scored pairs")
                st.caption(f"Original correct / paraphrase wrong: {pairs.get('original_correct_variant_wrong', 0)}  ·  "
                           f"Original wrong / paraphrase correct: {pairs.get('original_wrong_variant_correct', 0)}")
        if not any_pairs:
            st.info("No paired aggregate in this saved summary. No robustness metric is inferred.")
        st.subheader("Pair case explorer")
        pair_ids = sorted({str(row["pair_id"]) for row in rows if row["pair_id"] is not None})
        if pair_ids:
            pair_model = st.selectbox("Model for pair", models)
            pair_id = st.selectbox("Pair ID", pair_ids)
            pair_rows = [row for row in rows if row["model"] == pair_model and str(row["pair_id"]) == pair_id]
            for row in sorted(pair_rows, key=lambda r: r["variant"] != "original"):
                st.write(row["variant"], "·", row["item_id"])
                st.write("Prompt")
                st.code(row["prompt"], language="text")
                st.write("Response")
                st.code(row["raw_answer"] if row["raw_answer"] is not None else "No saved answer", language="text")
                st.write("Status:", row["response_status"], "· Score:", row["score_status"] or "not scored")
            st.caption("Cases are descriptive; review/invalid/missing halves do not count as accuracy flips.")
        else:
            st.info("No pair IDs in the frozen dataset.")

    with inspector:
        st.header("Answer inspector")
        left, middle, right = st.columns(3)
        selected_model = left.selectbox("Model", models, key="inspect_model")
        selected_category = middle.selectbox("Category", ["All", *sorted({r["category"] for r in rows})])
        attention = right.selectbox("Show answers", ["All", "Needs review", "Incorrect",
                                                       "Invalid / failed", "Pending", "Correct"])
        query = st.text_input("Find item", placeholder="Search item ID or prompt")
        shown = [row for row in rows if row["model"] == selected_model and
                 (selected_category == "All" or row["category"] == selected_category) and
                 attention_matches(row, attention) and
                 (not query or query.casefold() in f"{row['item_id']} {row['prompt']}".casefold())]
        st.caption(f"Showing {len(shown)} of {len(items)} saved dataset questions for {selected_model}")
        if not shown:
            st.info("No answers match these filters. Try a broader category, status, or search.")
        table = [{"Item": r["item_id"], "Category": r["category"], "Variant": r["variant"],
                  "Response": r["response_status"], "Score": r["score_status"] or "—",
                  "Correct": "yes" if r["correct"] is True else "no" if r["correct"] is False else "not judged"}
                 for r in shown]
        filter_key = hashlib.sha256(json.dumps([selected_model, selected_category, attention, query],
                                               ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
        selected = st.dataframe(table, width="stretch", hide_index=True, on_select="rerun",
                                selection_mode="single-row", key=f"answer_table_{filter_key}")
        if shown:
            chosen = selected.selection.rows[0] if selected.selection.rows else 0
            if chosen >= len(shown):
                chosen = 0
            row = shown[chosen]
            st.caption("Select a row to inspect its saved prompt, response, and scoring details.")
            st.subheader("Prompt")
            st.write(row["prompt"])
            st.subheader("Reference answer")
            st.code(row["reference_answer"] or "Not recorded", language="text")
            st.subheader("Raw model response")
            st.code(row["raw_answer"] if row["raw_answer"] is not None else "No saved answer", language="text")
            st.write(f"Response: {row['response_status']} · Score: {row['score_status'] or 'not scored'}")
            if type(row["correct"]) is bool:
                st.write("Objective score: " + ("Correct" if row["correct"] else "Incorrect"))
            elif row["score_status"] == "review":
                st.info("Needs human review · not an objective correctness score.")
            elif row["score_status"] == "invalid":
                st.warning("Invalid answer · not an objective correctness score.")
            if row["error"]:
                st.warning("A request failure was saved for this item; inspect local logs for details.")
            if row["scorer"] in PROXY:
                st.warning(PROXY[row["scorer"]])
            st.write("Scoring explanation:", row["explanation"] or "No saved score")
            st.write("Scorer:", row["scorer"], "· Declared rules:", row["rules"] or {})
            st.write("Saved checks:", row["checks"] if row["checks"] is not None else "Not available")
            if isinstance(row["latency_ms"], (int, float)):
                st.caption(f"Saved latency: {row['latency_ms']:.1f} ms (not comparable to live provider latency for fixtures)")
        st.download_button("Download saved run as CSV", data=export_csv(rows),
                           file_name="saved_run_answers.csv", mime="text/csv",
                           help="Includes saved prompts, references, raw responses, scores and missing rows. No files are written.")


if __name__ == "__main__":
    main()
