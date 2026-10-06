"""Opt-in local run controls and read-only viewer. Start with: streamlit run app.py"""

import csv
import hashlib
import html
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
    activity_area = st.empty()
    activity = []

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
        label = choices[event['model']] if opencode else MODEL_NAMES[event['model']]
        item_id = str(event.get("item_id", ""))
        outcome = (statuses.get(status, "No scored answer") if status != "ok" else
                   "Scored · correct" if score == "scored" and event.get("correct") is True else
                   "Scored · incorrect" if score == "scored" and event.get("correct") is False else
                   "Review · no objective score" if score == "review" else
                   "Invalid · no objective score" if score == "invalid" else
                   "Unscored answer")
        activity.append((label, item_id, outcome, completed, attempts))
        with progress_area.container(border=True):
            st.caption(f"02  /  {backend.upper()} · LATEST SAVED EVENT")
            st.subheader(f"{label} · {item_id}")
            a, b = st.columns(2)
            a.metric("Saved outcomes", f"{completed}/{planned}")
            b.metric("Cumulative attempts", attempts)
            st.progress(completed / planned, text=f"{completed}/{planned} planned model answers saved")
            st.caption("Saved outcomes exclude rate limits; attempts include retries and earlier attempts when resuming. Full raw records and rules appear in the saved-run viewer below.")
            st.write("1 / Dataset question")
            st.code(str(event.get("prompt") or "Not recorded"), language="text")
            if status == "ok":
                st.write("2 / Saved extracted answer (raw response in inspector)")
                st.code(str(event.get("answer") if event.get("answer") is not None else "No saved answer"), language="text")
            else:
                st.warning(statuses.get(status, "Request did not produce a scored answer"))
            st.write("3 / Dataset reference")
            st.code(str(event.get("reference_answer") or "Not recorded"), language="text")
            if status == "ok":
                st.write("4 / Saved scoring decision")
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
        with activity_area.container(border=True):
            st.caption("LIVE ACTIVITY  /  EVENTS SAVED THIS SUBMISSION")
            st.write("Saved response events in arrival order · this list does not include unresolved attempts or earlier sessions.")
            for name, question, decision, saved, tries in activity:
                st.write(f"{name} · {question} — {decision} · {saved}/{planned} saved outcomes · {tries} cumulative attempts")

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
    st.session_state["walkthrough_follow"] = True
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


def walkthrough_html(row):
    """A self-contained, accessible animation of one saved evaluation record."""
    def safe(value):
        return html.escape(str(value if value is not None else "Not recorded"), quote=True)

    if row["score_status"] == "scored" and type(row["correct"]) is bool:
        decision = "Correct" if row["correct"] else "Incorrect"
        decision_note = "This answer has an objective score under the declared rule."
    elif row["score_status"] == "review":
        decision, decision_note = "Needs human review", "A proxy check cannot establish correctness."
    elif row["score_status"] == "invalid":
        decision, decision_note = "Invalid answer", "No objective correctness score is assigned."
    else:
        decision, decision_note = "No score yet", "Pending or failed requests are not counted as wrong."
    steps = [
        ("01", "The question", "A prompt from this project's saved dataset.", row["prompt"]),
        ("02", "The model's answer", "The saved raw response. An empty response is not a wrong answer.",
         row["raw_answer"] if row["raw_answer"] is not None else "No saved answer"),
        ("03", "The reference", "The project-authored expected answer.", row["reference_answer"]),
        ("04", "The check", f"Declared scorer: {row['scorer'] or 'not recorded'}.",
         row["explanation"] or "No saved scoring explanation."),
        ("05", "The decision", decision_note, decision),
    ]
    cards = "".join(
        f'<article class="step" tabindex="-1"><span class="number">{number}</span>'
        f'<div><h3>{safe(title)}</h3><p>{safe(note)}</p><div class="value">{safe(value)}</div></div></article>'
        for number, title, note, value in steps
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <style>
      *{{box-sizing:border-box}} body{{margin:0;font:16px/1.5 system-ui,sans-serif;color:#182230;background:#f6f7fb}}
      .shell{{border:1px solid #dce0ed;border-radius:14px;overflow:hidden;background:#fff}}
      .toolbar{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid #dce0ed;background:#f9f9fd}}
      .toolbar strong{{margin-right:auto}} button{{border:1px solid #5048e5;border-radius:8px;background:#5048e5;color:white;font:inherit;font-weight:650;padding:7px 12px;cursor:pointer}}
      button.secondary{{background:white;color:#5048e5}} button:focus-visible{{outline:3px solid #d79648;outline-offset:2px}}
      .counter{{color:#526071;font-size:14px;min-width:75px;text-align:right}}
      .viewport{{height:370px;overflow-y:auto;scroll-behavior:smooth;padding:18px 16px 28px}}
      .step{{display:grid;grid-template-columns:48px 1fr;gap:12px;max-width:820px;margin:0 auto 16px;padding:16px;border:1px solid #dce0ed;border-radius:12px;background:#fafaff;opacity:.66;transition:opacity .35s,border-color .35s,box-shadow .35s}}
      .step.active{{opacity:1;border-color:#5048e5;box-shadow:0 8px 24px #5048e520}}
      .number{{display:grid;place-items:center;width:40px;height:40px;border-radius:50%;background:#eeecff;color:#5048e5;font-weight:750}}
      h3{{margin:0 0 3px;font-size:18px}} p{{margin:0 0 10px;color:#526071;font-size:14px}}
      .value{{white-space:pre-wrap;overflow-wrap:anywhere;padding:10px 12px;border-left:3px solid #d79648;background:#fff;font-weight:550}}
      @media(max-width:500px){{.toolbar{{display:grid;grid-template-columns:auto auto 1fr;gap:8px}}
        .toolbar strong{{grid-column:1/-1}}.counter{{justify-self:end}}
        .viewport{{scrollbar-width:none}}.viewport::-webkit-scrollbar{{display:none}}
        .step{{grid-template-columns:34px 1fr;gap:8px;padding:12px}}.number{{width:32px;height:32px}}}}
      @media(prefers-reduced-motion:reduce){{.viewport{{scroll-behavior:auto}}.step{{transition:none}}}}
    </style></head><body><div class="shell">
      <div class="toolbar"><strong>Follow one saved answer</strong><button id="toggle" type="button">Pause</button>
        <button id="restart" class="secondary" type="button">Restart</button><span id="counter" class="counter" aria-live="polite">1 of 5</span></div>
      <div id="viewport" class="viewport" aria-label="Evaluation walkthrough">{cards}</div>
    </div><script>
      const cards=[...document.querySelectorAll('.step')], viewport=document.getElementById('viewport');
      const toggle=document.getElementById('toggle'), counter=document.getElementById('counter');
      const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
      let index=0, playing=!reduced.matches, timer;
      function show(n){{index=Math.max(0,Math.min(n,cards.length-1));cards.forEach((card,i)=>card.classList.toggle('active',i===index));
        counter.textContent=(index+1)+' of '+cards.length;
        viewport.scrollTo({{top:cards[index].offsetTop-viewport.offsetTop-viewport.clientHeight/2+cards[index].clientHeight/2,
          behavior:reduced.matches?'instant':'smooth'}});
        if(index===cards.length-1){{playing=false;toggle.textContent='Play again';clearInterval(timer)}}}}
      function start(){{clearInterval(timer);playing=true;toggle.textContent='Pause';
        timer=setInterval(()=>{{if(document.hidden)return;if(index===cards.length-1){{clearInterval(timer);playing=false;toggle.textContent='Play again'}}else show(index+1)}},2600)}}
      toggle.addEventListener('click',()=>{{if(playing){{playing=false;clearInterval(timer);toggle.textContent='Play'}}
        else{{if(index===cards.length-1)show(0);start()}}}});
      document.getElementById('restart').addEventListener('click',()=>{{show(0);if(!reduced.matches)start()}});
      cards.forEach((card,i)=>card.addEventListener('click',()=>{{show(i);playing=false;clearInterval(timer);toggle.textContent='Play'}}));
      show(0);if(playing)start();else toggle.textContent='Play';
    </script></body></html>'''


def main():
    st.set_page_config(page_title="Evaluation Studio / local evidence", page_icon="◈", layout="wide")
    st.markdown("""<style>
      :root {--ink:#182230;--muted:#526071;--line:#dde3ed;--accent:#5048e5;--accent-2:#7865ef;--paper:#f6f7fb;--warm:#d79648;}
      .stApp {background:var(--paper);color:var(--ink);font-family:Inter,'Segoe UI',system-ui,sans-serif;}
      .block-container {max-width:1180px;padding:1.7rem clamp(1rem,4vw,3rem) 5rem;}
      h1,h2,h3 {font-family:Inter,'Segoe UI',system-ui,sans-serif;letter-spacing:-.035em;color:var(--ink);}
      h2 {font-size:clamp(1.6rem,2.5vw,2.2rem)!important;} h3 {font-size:1.35rem!important;}
      p,label {line-height:1.55;} [data-testid="stCaptionContainer"] {color:var(--muted);}
      .hero {position:relative;overflow:hidden;border-radius:24px;padding:clamp(1.35rem,3vw,2.3rem);color:#fff;
        background:radial-gradient(circle at 78% 16%,#464394 0,transparent 30%),linear-gradient(135deg,#111a2c 0%,#202949 70%,#342f67 100%);
        box-shadow:0 24px 55px rgba(25,34,64,.18);}
      .hero:after {content:'';position:absolute;inset:0;pointer-events:none;opacity:.2;
        background-image:radial-gradient(#fff 1px,transparent 1px);background-size:20px 20px;
        mask-image:linear-gradient(90deg,transparent 20%,#000 100%);}
      .hero-top,.hero-grid,.hero-bottom {position:relative;z-index:1;}
      .hero-top {display:flex;align-items:center;justify-content:space-between;gap:1rem;padding-bottom:1rem;}
      .brand {font-weight:850;letter-spacing:.13em;font-size:.84rem;}.brand-mark {color:#b8acff;font-size:1.2rem;margin-right:.4rem;}
      .hero-status {border:1px solid #ffffff55;border-radius:999px;padding:.35rem .75rem;color:#e4e7ff;font-size:.75rem;font-weight:700;letter-spacing:.08em;}
      .hero-status:before {content:'';display:inline-block;width:7px;height:7px;border-radius:50%;background:#8ff0bc;margin-right:.55rem;box-shadow:0 0 0 4px #8ff0bc33;}
      .hero-grid {display:grid;grid-template-columns:minmax(0,1.3fr) minmax(250px,.7fr);gap:1.7rem;align-items:center;}
      .hero-kicker {font-size:.76rem;letter-spacing:.17em;font-weight:800;color:#c3bcff;text-transform:uppercase;margin:0 0 .7rem;}
      .hero h1 {max-width:740px;font-size:clamp(2.4rem,4.5vw,4.1rem);line-height:1.04;letter-spacing:-.06em;color:#fff;margin:0 0 .8rem;}
      .hero h1 em {font-style:normal;color:#b8acff;}.hero-copy {max-width:600px;font-size:1.05rem;line-height:1.65;color:#e0e4f1;margin:0;}
      .hero-preview {background:#ffffffed;color:#1b2840;border:1px solid #ffffff88;border-radius:18px;padding:1rem;transform:rotate(2deg);box-shadow:0 22px 50px #070d2566;}
      .preview-top {display:flex;justify-content:space-between;align-items:center;color:#59637a;font-size:.67rem;font-weight:800;letter-spacing:.1em;}
      .preview-dot {width:8px;height:8px;border-radius:50%;background:#5abf91;display:inline-block;margin-right:5px;}
      .preview-question {font-weight:750;font-size:1.02rem;line-height:1.35;margin:1.1rem 0;}
      .preview-answer {display:flex;justify-content:space-between;background:#f2f1ff;border:1px solid #ddd8ff;border-radius:10px;padding:.7rem .8rem;font-size:.85rem;}
      .preview-answer strong {color:#3e35b4;}.preview-result {margin-top:.6rem;background:#e8f8ee;border-radius:10px;padding:.7rem .8rem;color:#176444;font-size:.83rem;font-weight:750;}
      .hero-bottom {display:flex;gap:.55rem;flex-wrap:wrap;margin-top:1rem;}.hero-bottom span {border:1px solid #ffffff35;border-radius:999px;padding:.4rem .7rem;color:#e2e7f6;font-size:.76rem;font-weight:650;}
      .section-kicker,.studio-eyebrow {font-size:.75rem;letter-spacing:.16em;text-transform:uppercase;color:#5b53bf;font-weight:850;margin:1.55rem 0 .15rem;}
      .section-copy {font-size:1rem;color:var(--muted);margin:.25rem 0 1rem;}
      .choice-title {font-size:1.32rem;font-weight:820;letter-spacing:-.03em;line-height:1.2;margin:.25rem 0 .5rem;}
      .choice-label {font-size:.7rem;font-weight:850;letter-spacing:.14em;color:#5148ce;text-transform:uppercase;}
      div.st-key-demo-card,div.st-key-live-card {background:#fff;border:1px solid var(--line);border-radius:18px;padding:1.4rem;
        box-shadow:0 10px 28px rgba(28,39,74,.055);min-height:246px;}
      div.st-key-demo-card {background:linear-gradient(145deg,#fff 60%,#f2efff);border-color:#cac3ff;}
      div.st-key-demo-card [data-testid="stButton"] button {background:#5048e5;color:#fff;border:1px solid #5048e5;border-radius:10px;
        min-height:46px;padding:.55rem 1.15rem;font-weight:750;box-shadow:0 8px 18px #5048e533;}
      div.st-key-demo-card [data-testid="stButton"] button:hover {background:#3932bb;border-color:#3932bb;color:#fff;transform:translateY(-2px);}
      div.st-key-live-card [data-testid="stExpander"] {border:1px solid #d9ddea;border-radius:11px;background:#fafbff;}
      div.st-key-workbench {background:#fff;border:1px solid var(--line);border-radius:16px;padding:clamp(1rem,2vw,1.5rem);}
      div.st-key-workbench [data-testid="stForm"] {border:0;background:transparent;padding:.25rem 0 0;}
      .studio-flow {display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.5rem;list-style:none;padding:0;margin:1.25rem 0 1.75rem;}
      .studio-flow li {background:#fff;border:1px solid var(--line);border-radius:12px;padding:.9rem .75rem;font-size:.82rem;line-height:1.35;
        box-shadow:0 5px 14px #1e2a4408;}
      .studio-flow b {display:block;color:#5048e5;font-size:.66rem;letter-spacing:.12em;margin-bottom:.45rem;}
      .studio-flow li:not(:last-child):after {content:'→';float:right;color:#aaa4e7;font-size:1.05rem;}
      [data-testid="stSelectbox"] [data-baseweb="select"]>div,[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input {
        background:#fff!important;border-color:#ccd3e0!important;border-radius:10px!important;color:var(--ink)!important;}
      [data-testid="stSelectbox"] [data-baseweb="select"]>div:focus-within,[data-testid="stTextInput"] input:focus,
      [data-testid="stNumberInput"] input:focus {border-color:#5048e5!important;box-shadow:0 0 0 3px #5048e522!important;}
      [data-testid="stAlert"] {border-radius:12px;border-width:1px;}
      [data-testid="stMetric"] {background:#fff;border:1px solid var(--line);padding:1rem;border-radius:12px;min-height:112px;box-shadow:0 6px 16px #1e2a4408;}
      [data-testid="stMetricValue"] {font-weight:800;color:var(--ink);font-size:1.8rem;}
      [data-testid="stMetricLabel"] {color:#516073;}
      [data-testid="stDataFrame"] {border:1px solid var(--line);border-radius:12px;overflow:hidden;}
      [data-testid="stTabs"] [role="tablist"] {gap:.4rem;border-bottom:1px solid var(--line);overflow-x:auto;}
      [data-testid="stTabs"] button[role="tab"] {font-weight:700;color:#5c6576;border-radius:9px 9px 0 0;padding-inline:1rem;white-space:nowrap;}
      [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {color:#5048e5;background:#eeecff;}
      div[data-testid="stFormSubmitButton"] button,div[data-testid="stDownloadButton"] button {background:#5048e5;color:#fff;border:1px solid #5048e5;
        border-radius:10px;font-weight:750;min-height:44px;padding-inline:1.2rem;}
      div[data-testid="stFormSubmitButton"] button:hover,div[data-testid="stDownloadButton"] button:hover {background:#3932bb;color:#fff;border-color:#3932bb;}
      button:focus-visible,[role="tab"]:focus-visible {outline:3px solid #d79648!important;outline-offset:2px;}
      @media(max-width:760px) {.block-container{padding:1rem 1rem 4rem}.hero-grid{grid-template-columns:1fr}.hero-preview{display:none}
        .hero-top{padding-bottom:1.25rem}.hero h1{font-size:clamp(2.2rem,9vw,3.3rem)}.studio-flow{grid-template-columns:repeat(2,minmax(0,1fr))}
        div.st-key-demo-card,div.st-key-live-card{min-height:0}[data-testid="stCodeBlock"] pre{white-space:pre-wrap;overflow-wrap:anywhere}}
      @media(prefers-reduced-motion:reduce) {*,*:before,*:after{scroll-behavior:auto!important;animation-duration:.01ms!important;transition-duration:.01ms!important}}
    </style>""", unsafe_allow_html=True)

    st.markdown('''<section class="hero" aria-label="Evaluation Studio introduction">
      <div class="hero-top"><div class="brand"><span class="brand-mark">◈</span> EVAL / STUDIO</div>
        <div class="hero-status">LOCAL EVIDENCE</div></div>
      <div class="hero-grid"><div><p class="hero-kicker">Understand the result, step by step</p>
        <h1>See why an answer <em>earned its score.</em></h1>
        <p class="hero-copy">Explore a model's question, answer, scoring rule and decision in one place.
          Start with a safe example, then inspect saved comparisons when you're ready.</p></div>
        <div class="hero-preview" aria-hidden="true"><div class="preview-top"><span><i class="preview-dot"></i> SAVED EXAMPLE</span><span>01 / 05</span></div>
          <div class="preview-question">Who is younger: Eva or Dan?</div>
          <div class="preview-answer"><span>Model answer</span><strong>B · Dan</strong></div>
          <div class="preview-result">✓ Matches the reference answer</div></div></div>
    </section>''', unsafe_allow_html=True)

    st.markdown('<div class="section-kicker">01 / Start here</div>', unsafe_allow_html=True)
    st.markdown('## Pick your starting point')
    demo_col, live_col = st.columns(2, gap="medium")
    with demo_col:
        with st.container(border=True, key="demo-card"):
            st.markdown('<div class="choice-label">Recommended · no setup</div><div class="choice-title">Explore the offline demo</div>', unsafe_allow_html=True)
            st.write("Watch four example answers get scored. Nothing is sent to a provider.")
            st.caption("Synthetic example · not measured model performance")
            if st.button("Try offline demo", help="Create a synthetic four-answer development run. No key or provider request is used."):
                try:
                    folder = create_demo_run()
                except (OSError, ValueError):
                    st.error("Could not create the offline demo. Check the local runs folder and try again.")
                else:
                    st.session_state["selected_run"] = folder.name
                    st.session_state["walkthrough_follow"] = True
                    st.success("Synthetic demo saved. Follow the walkthrough below.")
    with live_col:
        with st.container(border=True, key="live-card"):
            st.markdown('<div class="choice-label">Optional · uses a provider</div><div class="choice-title">Compare two live models</div>', unsafe_allow_html=True)
            st.write("Choose a dataset and two models. You'll review the attempt cap and confirm before any requests start.")
            with st.expander("Compare live models (optional)", expanded=False):
                control_panel()
    st.caption("START HERE  /  1. Explore the offline demo  →  2. Opt in to a live comparison if ready  →  3. Read saved answers below")
    st.markdown('<div class="section-kicker">The method at a glance</div>', unsafe_allow_html=True)
    st.markdown('''<ol class="studio-flow" aria-label="Evaluation steps">
      <li><b>01 / INPUT</b>Project-authored dataset prompt</li>
      <li><b>02 / REQUEST</b>Chosen model and route</li>
      <li><b>03 / EVIDENCE</b>Saved raw response</li>
      <li><b>04 / CHECK</b>Declared scorer, rules and checks</li>
      <li><b>05 / READOUT</b>Scored, review or failed; compare matched items</li>
    </ol>''', unsafe_allow_html=True)
    with st.expander("Research references and method notes"):
        st.caption("METHOD / This is a project-authored dataset, not a benchmark taken from the cited papers. Objective scores use declared checks; proxy checks need human review.")
        st.markdown("**Reading that shaped this workflow:** [Chang ’24](https://doi.org/10.1145/3641289) · "
                    "[Cao ’25](https://arxiv.org/abs/2504.18838) · "
                    "[Ni ’25](https://arxiv.org/abs/2508.15361) · "
                    "[Mohammadi ’25](https://arxiv.org/abs/2507.21504)  —  context, not the source of this dataset or its results.")
        st.markdown("**Capability categories** — [Chang et al. (2024)](https://doi.org/10.1145/3641289) informs the breadth of questions, not these answers or scores.  \n"
                    "**Generalization and paired robustness** — [Cao et al. (2025)](https://arxiv.org/abs/2504.18838) discusses evaluation beyond fixed benchmarks; this app examines only saved original/paraphrase pairs.  \n"
                    "**Benchmark limits** — [Ni et al. (2025)](https://arxiv.org/abs/2508.15361) surveys benchmark design and limitations; prompts, rules and missing outcomes stay visible.  \n"
                    "**Agent evaluation** — [Mohammadi et al. (2025)](https://arxiv.org/abs/2507.21504) points beyond this single-answer workflow; no agent behavior is evaluated here.")
    st.markdown('<div class="studio-eyebrow" style="margin-top:2.2rem">EVIDENCE ARCHIVE</div>', unsafe_allow_html=True)
    st.header("Read the record.")
    st.caption("Saved runs only · choosing a run or answer never starts requests · dataset questions are project-authored")
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

    st.subheader("See how one answer is evaluated")
    st.write("Watch the saved question, model answer, reference, check, and decision in order. "
             "Use Pause or Restart to control the tour. This only reads local records.")
    example_options = list(range(len(rows)))
    first_scored = next((i for i, row in enumerate(rows) if row["score_status"] == "scored"), 0)
    example_index = st.selectbox("Choose an answer to explain", example_options,
                                 index=first_scored,
                                 format_func=lambda i: f"{rows[i]['item_id']} · {MODEL_NAMES.get(rows[i]['model'], OPENCODE_MODELS.get(rows[i]['model'], rows[i]['model']))} · {rows[i]['category']}",
                                 key="walkthrough_example")
    if example_index is not None:
        follow_walkthrough = st.session_state.pop("walkthrough_follow", False)
        st.iframe(walkthrough_html(rows[example_index]),
                  height=470, alt="Animated explanation of one saved evaluation answer")
        if follow_walkthrough:
            st.html("""<script>
              requestAnimationFrame(() => {
                const heading = document.getElementById('see-how-one-answer-is-evaluated');
                if (heading) heading.scrollIntoView({
                  behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
                  block: 'start'
                });
              });
            </script>""", unsafe_allow_javascript=True)
    st.caption("This animation follows one saved record. For the full rule and recorded checks, open Answer inspector below.")

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
            st.caption(f"Declared check: {item.get('scorer', 'not recorded')} · original/paraphrase pair: {item.get('pair_id', 'not recorded')}")
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
        st.caption("Follow one saved row from dataset input to decision. No requests are sent when you change filters or select a row.")
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
            st.caption("Select a row to inspect its saved prompt, raw response, exact declared rules, and recorded checks.")
            st.subheader("1 / Dataset Prompt")
            st.caption(f"Item {row['item_id']} · {row['category']} · {row['variant']} · pair {row['pair_id'] or 'none'} · project-authored dataset")
            st.write(row["prompt"])
            st.subheader("2 / Chosen model")
            st.code(row["model"], language="text")
            st.subheader("3 / Saved raw model response")
            st.code(row["raw_answer"] if row["raw_answer"] is not None else "No saved answer", language="text")
            st.caption(f"Response status: {row['response_status']}" +
                       (" · A rate limit is not a saved answer." if row["response_status"] == "rate_limited" else ""))
            st.subheader("4 / Declared scorer and rules")
            st.write("Scorer:", row["scorer"] or "Not recorded")
            st.write("Reference answer")
            st.code(row["reference_answer"] or "Not recorded", language="text")
            st.write("Exact declared rules")
            st.code(json.dumps(row["rules"] if row["rules"] is not None else {}, ensure_ascii=False, indent=2), language="json")
            if row["scorer"] in PROXY:
                st.warning(PROXY[row["scorer"]])
            st.subheader("5 / Saved checks and decision")
            st.write("Saved checks")
            st.code(json.dumps(row["checks"], ensure_ascii=False, indent=2) if row["checks"] is not None else
                    "Not available — no saved check for this item", language="json" if row["checks"] is not None else "text")
            st.write(f"Response: {row['response_status']} · Score: {row['score_status'] or 'not scored'}")
            if type(row["correct"]) is bool:
                st.write("Objective score: " + ("Correct" if row["correct"] else "Incorrect"))
            elif row["score_status"] == "review":
                st.info("Needs human review · not an objective correctness score.")
            elif row["score_status"] == "invalid":
                st.warning("Invalid answer · not an objective correctness score.")
            if row["error"]:
                st.warning("A request failure was saved for this item; inspect local logs for details.")
            st.write("Scoring explanation:", row["explanation"] or "No saved score — pending or failed responses cannot be scored.")
            if isinstance(row["latency_ms"], (int, float)):
                st.caption(f"Saved latency: {row['latency_ms']:.1f} ms (not comparable to live provider latency for fixtures)")
        st.download_button("Download saved run as CSV", data=export_csv(rows),
                           file_name="saved_run_answers.csv", mime="text/csv",
                           help="Includes saved prompts, references, raw responses, scores and missing rows. No files are written.")


if __name__ == "__main__":
    main()
