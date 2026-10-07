"""Local-only Flask interface for saved evaluations and opt-in comparisons."""

import csv
import hashlib
import json
import math
import os
import re
import secrets
import stat
import threading
from hmac import compare_digest
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, flash, get_flashed_messages, redirect, render_template, request, send_file, session, url_for


ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
DATASETS = ROOT / "datasets" / "v1.0"
DATASET_OPTIONS = [
    {"id": "dev.jsonl", "label": "Development · 4 questions"},
    {"id": "benchmark.jsonl", "label": "Held-out · 24 questions"},
]
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
BACKENDS = {
    "OpenRouter": [{"id": key, "label": f"{label} · {MODEL_PROVIDERS[key]}"}
                   for key, label in MODEL_NAMES.items()],
    "OpenCode (free-labeled)": [{"id": key, "label": label}
                                for key, label in OPENCODE_MODELS.items()],
}
RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

app = Flask(__name__)
app.secret_key = secrets.token_bytes(32)  # Never persist across server restarts.
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# ponytail: one process-wide worker; use a process-wide queue/lock if multi-process serving is needed.
worker_lock = threading.Lock()
progress = {"run": None, "event": None, "notice": None}
nonce_lock = threading.Lock()
used_nonces = set()


@app.before_request
def local_request_only():
    if request.host not in ("127.0.0.1:8501", "localhost:8501"):
        abort(403)
    if request.method == "POST" and request.headers.get("Origin") not in (
            None, "http://127.0.0.1:8501", "http://localhost:8501"):
        abort(403)


def safe_run_path(name):
    if not isinstance(name, str) or not RUN_NAME.fullmatch(name):
        raise ValueError("Invalid run name.")
    folder = RUNS / name
    if RUNS.is_symlink() or folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError("Unsafe run directory.")
    return folder


def safe_file(folder, name):
    path = folder / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe saved run file.")
    return path


def dataset_options():
    from evaluation.dataset import load_dataset

    options = []
    for option in DATASET_OPTIONS:
        items = load_dataset(DATASETS / option["id"])
        pairs = {}
        for item in items:
            pair = pairs.setdefault(item["pair_id"], {"id": item["pair_id"],
                                                       "pair_id": item["pair_id"],
                                                       "category": item["category"]})
            pair[item["variant"]] = item
        options.append({**option, "items": items, "pairs": list(pairs.values())})
    return options


def records(folder, name, *, required=False):
    path = folder / name
    if not path.exists() and not required:
        return []
    data = safe_file(folder, name).read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError("Incomplete saved log.")
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def csv_matches(folder, items, responses, scores, config):
    from evaluation.analysis import CSV_FIELDS, _csv_cell

    try:
        path = safe_file(folder, "results.csv")
        with path.open(encoding="utf-8", newline="") as stream:
            actual = list(csv.DictReader(stream))
        response_keys = {(row["model"], row["item_id"]): row for row in responses}
        score_keys = {(row["model"], row["item_id"]): row for row in scores}
        expected = []
        for model in config["models"]:
            for item in items:
                response = response_keys.get((model, item["id"]), {})
                score = score_keys.get((model, item["id"]), {})
                status = response.get("status", "pending")
                if status == "ok" and response.get("finish_reason") == "length":
                    status = "truncated"
                row = dict(zip(CSV_FIELDS, (str(config["synthetic"]).lower(), config["source"], model,
                    item["id"], item["pair_id"], item["variant"], item["split"], item["category"],
                    status, score.get("status", ""),
                    str(score["correct"]).lower() if score.get("correct") is not None else "",
                    response.get("answer") or "", response.get("error") or "",
                    response.get("latency_ms", ""))))
                expected.append({key: "" if value is None else str(_csv_cell(value))
                                 for key, value in row.items()})
        return actual == expected
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, csv.Error):
        return False


def load_run(folder):
    """Read frozen records without invoking a runner or provider."""
    if RUNS.is_symlink() or folder.parent != RUNS or folder.is_symlink() or not folder.is_dir():
        raise ValueError("Unsafe run directory.")
    config = json.loads(safe_file(folder, "config.json").read_text(encoding="utf-8"))
    snapshot = safe_file(folder, "dataset.jsonl").read_bytes()
    items = records(folder, "dataset.jsonl", required=True)
    responses = records(folder, "responses.jsonl")
    saved_scores = records(folder, "scores.jsonl")
    attempts = records(folder, "attempts.jsonl")
    if not isinstance(config, dict) or not isinstance(config.get("models"), list):
        raise ValueError("Invalid run metadata.")
    from evaluation.analysis import analyze
    from evaluation.dataset import validate_dataset
    from evaluation.runner import _scorer_hash

    models = config["models"]
    if (not models or len(models) != len(set(models)) or
            any(not isinstance(model, str) or not model for model in models) or
            type(config.get("synthetic")) is not bool or
            not isinstance(config.get("source"), str) or
            config.get("schema_version", 1) != 1 or
            not isinstance(config.get("scorer_version"), str) or
            hashlib.sha256(snapshot).hexdigest() != config.get("dataset_hash")):
        raise ValueError("Inconsistent saved run.")
    validate_dataset(items)
    if {item["split"] for item in items} != {config.get("split")} or {item["dataset_version"] for item in items} != {config.get("dataset_version")}:
        raise ValueError("Inconsistent frozen dataset.")
    if ("selected_item_ids" in config and config["selected_item_ids"] != [item["id"] for item in items] or
            "selected_pair_ids" in config and config["selected_pair_ids"] !=
            list(dict.fromkeys(item["pair_id"] for item in items))):
        raise ValueError("Inconsistent frozen pair selection.")
    item_ids = {item["id"]: item for item in items}
    latency_warning = False
    for record in responses:
        latency = record.get("latency_ms")
        if latency is not None and (type(latency) not in (int, float) or
                                    not math.isfinite(latency) or latency < 0):
            # Keep inspecting the answer, but do not present malformed latency as a measurement.
            record["latency_ms"] = None
            latency_warning = True
    for record in (*responses, *saved_scores):
        if (not isinstance(record, dict) or record.get("model") not in models or
                record.get("item_id") not in item_ids or record.get("synthetic") is not config["synthetic"]):
            raise ValueError("Invalid saved record linkage.")
    if config["synthetic"]:
        if attempts:
            raise ValueError("Unexpected synthetic attempts.")
    else:
        from evaluation.runner import _validate_live_logs
        unresolved = _validate_live_logs(config, items, attempts, responses)
    seen, effective_responses = set(), {}
    for response in responses:
        key = (response["model"], response["item_id"])
        if response.get("status") not in ("ok", "error", "truncated", "rate_limited"):
            raise ValueError("Invalid response status.")
        if response["status"] == "rate_limited":
            continue
        if key in seen:
            raise ValueError("Duplicate response.")
        seen.add(key)
        effective_responses[key] = response
    eligible = {key for key, response in effective_responses.items()
                if response["status"] == "ok" and response.get("finish_reason") != "length"}
    score_keys = set()
    for record in saved_scores:
        key = (record["model"], record["item_id"])
        if (key not in eligible or key in score_keys or
                record.get("status") not in ("scored", "review", "invalid") or
                record.get("status") == "scored" and type(record.get("correct")) is not bool or
                record.get("status") != "scored" and record.get("correct") is not None):
            raise ValueError("Invalid or ineligible saved score.")
        score_keys.add(key)
    scores = saved_scores
    summary = analyze(items, responses, scores, models, synthetic=config["synthetic"], source=config["source"])
    summary["scorer_version_current"] = config["scorer_version"] == _scorer_hash()
    summary["latency_data_warning"] = latency_warning
    summary["unresolved_attempts"] = unresolved if not config["synthetic"] else 0
    summary["paused"] = bool(summary["unresolved_attempts"] or responses and
        responses[-1]["status"] == "rate_limited" or not config["synthetic"] and
        any(row.get("error") in ("reported cost is positive", "returned model differs from requested ID",
                                 "returned provider differs from requested slug") for row in responses))
    pending = sum(summary["models"][model]["pending"] for model in models)
    missing_scores = sum(summary["models"][model].get("unscored", 0) for model in models)
    other_failures = sum(summary["models"][model]["failures"] + summary["models"][model]["invalid"] +
                         summary["models"][model]["truncated"] + summary["models"][model]["rate_limited"]
                         for model in models)
    status = ("paused" if summary["paused"] else "partial"
              if pending or missing_scores or other_failures else "complete")
    # A CSV is trustworthy only if all saved derived files agree with frozen records.
    reports_current = False
    try:
        saved_summary = json.loads(safe_file(folder, "summary.json").read_text(encoding="utf-8"))
        reports_current = (saved_scores == scores and isinstance(saved_summary, dict) and
                           all(saved_summary.get(key) == summary[key] for key in
                               ("synthetic", "source", "models", "matched_comparison", "unresolved_attempts")) and
                           csv_matches(folder, items, responses, saved_scores, config) and
                           (config["synthetic"] or all(row.get("error") in (
                               None, "HTTP 429", "HTTP 4xx", "HTTP 5xx", "reported cost is positive",
                               "returned model differs from requested ID",
                               "returned provider differs from requested slug") for row in responses)))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        pass
    if not config["synthetic"]:
        for response in responses:
            if response.get("error") and response["error"] not in (
                    "HTTP 429", "HTTP 4xx", "HTTP 5xx", "reported cost is positive",
                    "returned model differs from requested ID", "returned provider differs from requested slug"):
                response["error"] = "Provider error; inspect local logs."
    summary["evidence_label"] = (
        "NOT MEASURED · no saved model responses; check attempts and provider before retrying"
        if not responses else
        "SYNTHETIC · OFFLINE FIXTURE — not measured model performance"
        if config.get("synthetic") is True and summary.get("synthetic") is True else
        "DECLARED LIVE · saved records, not independently verified"
        if config.get("synthetic") is False and summary.get("synthetic") is False else
        "EVIDENCE TYPE UNVERIFIED · inspect run metadata")
    return {"id": folder.name, "config": config, "summary": summary, "status": status,
            "csv_available": reports_current, "items": items, "responses": responses,
            "scores": scores, "attempts": attempts}


def csrf_valid():
    token, nonce = session.get("csrf_token"), session.get("submission_nonce")
    submitted_token = request.form.get("csrf_token", "")
    submitted_nonce = request.form.get("submission_nonce", "")
    valid = (isinstance(token, str) and isinstance(nonce, str) and
             compare_digest(token, submitted_token) and compare_digest(nonce, submitted_nonce))
    session["submission_nonce"] = secrets.token_urlsafe(32)  # Consume even rejected submissions.
    if not valid:
        return False
    with nonce_lock:
        # ponytail: bounded process-local replay ledger; fail closed at capacity, restart to clear.
        if submitted_nonce in used_nonces or len(used_nonces) >= 100000:
            return False
        used_nonces.add(submitted_nonce)
    return True


@app.get("/")
def index():
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    session.setdefault("submission_nonce", secrets.token_urlsafe(32))
    runs = []
    if RUNS.is_dir() and not RUNS.is_symlink():
        for folder in sorted(RUNS.iterdir()):
            if not RUN_NAME.fullmatch(folder.name) or folder.is_symlink() or not folder.is_dir():
                continue
            try:
                runs.append(load_run(safe_run_path(folder.name)))
            except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, UnicodeError):
                runs.append({"id": folder.name, "config": {}, "summary": {}, "status": "error",
                             "csv_available": False, "items": [], "responses": [], "scores": [],
                             "attempts": []})
    selected_id = request.args.get("run")
    selected = next((run for run in runs if run["id"] == selected_id), None)
    error = None
    if selected_id is not None and selected is None:
        error = "Cannot read this saved run. Inspect its local files for missing or invalid records."
    messages = get_flashed_messages(with_categories=True)
    notice = next((text for category, text in messages if category == "notice"), None)
    error = error or next((text for category, text in messages if category == "error"), None)
    busy = worker_lock.locked()
    if selected_id == progress["run"]:
        event = progress["event"]
        if busy and event:
            notice = (f"Saved progress: {event['completed']}/{event['planned']} outcomes, "
                      f"{event['attempts']} cumulative attempts; latest {event['model']} "
                      f"{event['item_id']} ({event['status']}).")
        elif not busy and progress["notice"]:
            notice = progress["notice"]
    try:
        datasets = dataset_options()
    except (OSError, ValueError, TypeError, UnicodeError):
        datasets = []
        error = error or "Question sets unavailable; no run can be started."
    has_successful_live = any(
        run.get("status") != "error" and run["config"].get("synthetic") is False and
        any(response.get("status") == "ok" for response in run["responses"])
        for run in runs)
    return render_template("index.html", datasets=datasets,
                           pair_options={option["id"]: option["pairs"] for option in datasets},
                           backends=BACKENDS,
                           runs=[{k: run[k] for k in ("id", "config", "summary", "status", "csv_available")} for run in runs],
                           selected=selected, busy=busy, csrf_token=session["csrf_token"],
                           submission_nonce=session["submission_nonce"], notice=notice, error=error,
                           evidence_status="successful live responses saved" if has_successful_live else "measured results pending",
                           has_successful_live=has_successful_live)


def finish_run(folder, action, *args, **kwargs):
    try:
        result = action(*args, **kwargs)
        models = result.get("models", {})
        incomplete = any(counts.get(key, 0) for counts in models.values()
                        for key in ("pending", "unscored", "invalid", "failures", "truncated", "rate_limited"))
        if result.get("paused") or result.get("unresolved_attempts"):
            message = "Run paused. Inspect saved attempts and provider account; no automatic retry was started."
        elif incomplete:
            message = "Run partial. Some questions are pending, failed, invalid, truncated, or unscored; inspect saved outcomes."
        else:
            message = "Run complete. All selected model/question items have saved score records."
        progress.update(run=folder.name, notice=message)
    except Exception:
        # Exceptions may contain keys, paths, or provider response bodies: never publish them.
        progress.update(run=folder.name, notice="Run paused or failed. Inspect local attempts and provider account before retrying; a request may have reached the provider.")
    finally:
        worker_lock.release()


def start_worker(folder, action, *args, **kwargs):
    """Start a worker with the already-reserved worker lock."""
    progress.update(run=folder.name, event=None, notice=None)
    try:
        threading.Thread(target=finish_run, args=(folder, action, *args), kwargs=kwargs,
                         daemon=True).start()
    except Exception:
        worker_lock.release()
        flash("Could not start the run; no request was started.", "error")
        return redirect(url_for("index"))
    flash("Run started in the background. Saved progress appears when you refresh.", "notice")
    return redirect(url_for("index", run=folder.name))


@app.post("/runs")
def create_run():
    if not csrf_valid():
        abort(403)
    dataset = request.form.get("dataset")
    backend = request.form.get("backend")
    models = [request.form.get("model_a"), request.form.get("model_b")]
    selected_pairs = request.form.getlist("selected_pairs")
    try:
        folder = safe_run_path(request.form.get("run_name"))
        if dataset not in {option["id"] for option in DATASET_OPTIONS} or backend not in BACKENDS:
            raise ValueError
        if models[0] == models[1] or any(model not in {option["id"] for option in BACKENDS[backend]} for model in models):
            raise ValueError
        cap_text = request.form.get("max_requests", "")
        if not re.fullmatch(r"[1-9][0-9]?", cap_text) or not 1 <= int(cap_text) <= 50:
            raise ValueError
        if request.form.get("confirmed") not in ("on", "true", "yes", "1"):
            raise ValueError
        options = dataset_options()
        available = {pair["id"] for option in options if option["id"] == dataset
                     for pair in option["pairs"]}
        if (not selected_pairs or len(selected_pairs) != len(set(selected_pairs)) or
                not set(selected_pairs) <= available):
            raise ValueError
    except (OSError, TypeError, ValueError, UnicodeError):
        flash("Invalid dataset, selected pairs, backend, models, cap, run name or confirmation. Nothing was sent.", "error")
        return redirect(url_for("index"))
    if not worker_lock.acquire(blocking=False):
        flash("Another run is in progress; no new request was started.", "error")
        return redirect(url_for("index"))
    cap = int(cap_text)
    if backend == "OpenRouter":
        try:
            from evaluation.access import preflight
            access = preflight(max_requests=cap)
            if (not isinstance(access, dict) or access.get("allowed") is False or
                    access.get("ok") is False or
                    type(access.get("free_remaining")) is not int or
                    type(access.get("free_limit")) is not int or
                    access["free_remaining"] < cap):
                raise ValueError
        except Exception:
            worker_lock.release()
            flash("OpenRouter access check blocked this run. Check your local key, quota and spend cap; no model request was started.", "error")
            return redirect(url_for("index"))
    try:
        if backend == "OpenRouter":
            from evaluation.runner import run_live_comparison
            action_args = (DATASETS / dataset, folder, models,
                           {model: MODEL_PROVIDERS[model] for model in models}, cap)
            action = run_live_comparison
        else:
            from evaluation.runner import run_opencode_comparison
            action, action_args = run_opencode_comparison, (DATASETS / dataset, folder, models, cap)
    except Exception:
        worker_lock.release()
        flash("Could not prepare the run; no request was started.", "error")
        return redirect(url_for("index"))
    return start_worker(folder, action, *action_args,
                         pair_ids=selected_pairs,
                         on_progress=lambda event: progress.update(run=folder.name, event={
                            key: event.get(key) for key in ("model", "item_id", "status", "completed", "planned", "attempts")}))


@app.post("/demo")
def create_demo():
    if not csrf_valid():
        abort(403)
    if not worker_lock.acquire(blocking=False):
        flash("Another run is in progress; no new request was started.", "error")
        return redirect(url_for("index"))
    try:
        folder = safe_run_path(f"demo-{uuid4().hex[:10]}")
    except ValueError:
        worker_lock.release()
        flash("Could not create the offline demo.", "error")
        return redirect(url_for("index"))

    def demo():
        from evaluation.runner import run
        RUNS.mkdir(exist_ok=True)
        fixture = RUNS / f"{folder.name}.fixtures.json"
        fixture.write_text(json.dumps({"synthetic-a": {
            "dr1-o": "B", "dr1-p": "A", "dm1-o": "7", "dm1-p": "7"},
            "synthetic-b": {"dr1-o": "A", "dr1-p": "B", "dm1-o": "6", "dm1-p": "7"}}), encoding="utf-8")
        return run(DATASETS / "dev.jsonl", fixture, folder, ["synthetic-a", "synthetic-b"])

    return start_worker(folder, demo)


@app.get("/runs/<run_id>/results.csv")
def download(run_id):
    try:
        folder = safe_run_path(run_id)
        saved = load_run(folder)
        if not saved["csv_available"]:
            raise ValueError("CSV is missing or inconsistent with saved records")
        path = safe_file(folder, "results.csv")
        # Do not follow a symlink if the CSV is replaced between validation and open.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError("Unsafe CSV file")
        stream = os.fdopen(fd, "rb")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, UnicodeError):
        abort(404)
    response = send_file(stream, mimetype="text/csv", as_attachment=True,
                         download_name="results.csv")
    response.call_on_close(stream.close)
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8501, debug=False, use_reloader=False)
