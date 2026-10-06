"""Durable fixture runs and explicit, capped live runs with offline reanalysis."""

import hashlib
import fcntl
import json
import math
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .analysis import analyze, export_csv
from .dataset import load_dataset, validate_dataset

DEFAULT_MODELS = ("fixture-a", "fixture-b")
SYSTEM_PROMPT = "Answer the question accurately and concisely."
PROMPT_TEMPLATE = "Question: {prompt}\nAnswer:"
TEMPERATURE = 0
MAX_TOKENS = 512


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _write(path, value):
    # Derived outputs are replaced only after they are fully written.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(_json(value) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _records(path):
    if not path.exists():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError(f"truncated JSONL: {path}")
    records = []
    for number, line in enumerate(data.splitlines(), 1):
        try:
            records.append(json.loads(line))
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"invalid JSONL: {path} line {number}") from exc
    return records


def _append(path, record):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(_json(record) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _snapshot(items):
    return "".join(_json(item) + "\n" for item in items).encode("utf-8")


def _scorer_hash():
    return hashlib.sha256(Path(__file__).with_name("scoring.py").read_bytes()).hexdigest()


@contextmanager
def _locked(run_dir):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / ".run.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("run directory locked by another process") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _prepare(run_dir, items, config):
    snapshot_bytes = _snapshot(items)
    config_path, snapshot = run_dir / "config.json", run_dir / "dataset.jsonl"
    if config_path.exists():
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        if {k: v for k, v in stored.items() if k != "created_at"} != config:
            raise ValueError("run config mismatch; use a new run directory")
        if not snapshot.exists() or snapshot.read_bytes() != snapshot_bytes:
            raise ValueError("frozen dataset snapshot mismatch")
    else:
        if any(p.name != ".run.lock" for p in run_dir.iterdir()):
            raise ValueError("run directory contains files without a config")
        run_dir.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(snapshot_bytes)
        _write(config_path, {**config, "created_at": _timestamp()})


def _config(items, models, synthetic, source):
    splits = {item["split"] for item in items}
    if len(splits) != 1:
        raise ValueError("mixed dev/test dataset; use a single split per run")
    return {"synthetic": synthetic, "source": source, "models": models,
            "dataset_hash": hashlib.sha256(_snapshot(items)).hexdigest(),
            "dataset_version": items[0]["dataset_version"], "split": splits.pop(),
            "scorer_version": _scorer_hash()}


def _validate_live_logs(config, items, attempts, responses):
    """Validate durable intent/response linkage before reports or dispatch."""
    model = config["models"][0]
    by_id = {item["id"] for item in items}
    try:
        ids = [a["attempt_id"] for a in attempts]
        if (len(ids) > 40 or len(ids) != len(set(ids)) or any(
                not isinstance(a["attempt_id"], str) or not a["attempt_id"] or
                a["model"] != model or a["item_id"] not in by_id or a["synthetic"] is not False
                for a in attempts)):
            raise ValueError("invalid attempt log")
        by_attempt = {a["attempt_id"]: a for a in attempts}
        seen = set()
        for response in responses:
            aid = response["attempt_id"]
            if (aid in seen or aid not in by_attempt or response["model"] != model or
                    response["item_id"] != by_attempt[aid]["item_id"] or
                    response["synthetic"] is not False):
                raise ValueError("orphan or mismatched live response")
            seen.add(aid)
        return len(ids) - len(seen)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("corrupt live attempt/response log") from exc


def reanalyze(run_dir):
    """Acquire the same per-run lock used for dispatch and rebuild reports."""
    with _locked(run_dir):
        return _reanalyze_unlocked(Path(run_dir))


def _reanalyze_unlocked(run_dir):
    """Rebuild derived files solely from the frozen dataset and saved responses."""
    from .scoring import score

    run_dir = Path(run_dir)
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    if config["scorer_version"] != _scorer_hash():
        raise ValueError("scorer version changed; cannot reanalyze or resume")
    snapshot = run_dir / "dataset.jsonl"
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != config["dataset_hash"]:
        raise ValueError("frozen dataset hash mismatch")
    items = load_dataset(snapshot)
    if {item["split"] for item in items} != {config["split"]}:
        raise ValueError("dataset split mismatch")
    by_id = {item["id"]: item for item in items}
    responses = _records(run_dir / "responses.jsonl")
    unresolved = (_validate_live_logs(config, items, _records(run_dir / "attempts.jsonl"), responses)
                  if not config["synthetic"] else 0)
    seen, scores = set(), []
    for response in responses:
        model, item_id = response["model"], response["item_id"]
        key = (model, item_id)
        if model not in config["models"] or item_id not in by_id or key in seen:
            raise ValueError(f"unexpected or duplicate response key: {key}")
        if response["status"] == "rate_limited":
            # Retry on a later invocation; never count a 429 as an answer.
            continue
        seen.add(key)
        if response["status"] != "ok" or response.get("finish_reason") == "length":
            continue
        result = score(by_id[item_id], response["answer"])
        scores.append({"synthetic": config["synthetic"], "model": model, "item_id": item_id,
                       "category": by_id[item_id]["category"], **result})
    result = analyze(items, responses, scores, config["models"], synthetic=config["synthetic"],
                     source=config["source"])
    result["unresolved_attempts"] = unresolved
    result["paused"] = bool(unresolved or responses and responses[-1]["status"] == "rate_limited" or
                            not config["synthetic"] and any(r.get("error") in
                            ("returned model differs from requested ID", "reported cost is positive",
                             "returned provider differs from requested slug") for r in responses))
    score_path = run_dir / "scores.jsonl"
    tmp = score_path.with_name(score_path.name + ".tmp")
    tmp.write_text("".join(_json(record) + "\n" for record in scores), encoding="utf-8")
    os.replace(tmp, score_path)
    _write(run_dir / "summary.json", result)
    export_csv(run_dir / "results.csv", items, responses, scores, config["models"],
               synthetic=config["synthetic"], source=config["source"])
    return result


def run(dataset, fixtures, run_dir, models=DEFAULT_MODELS):
    with _locked(run_dir):
        return _run_unlocked(dataset, fixtures, Path(run_dir), models)


def _run_unlocked(dataset, fixtures, run_dir, models):
    """Run local JSON fixture responses. A 429 saves progress and pauses."""
    models = list(models)
    if not models or len(models) != len(set(models)) or any(not isinstance(m, str) or not m for m in models):
        raise ValueError("models must be distinct nonempty labels")
    dataset, fixtures, run_dir = Path(dataset), Path(fixtures), Path(run_dir)
    items = load_dataset(dataset)
    validate_dataset(items)
    config = {**_config(items, models, True, "offline_fixture"),
              "fixtures_path": str(fixtures.resolve())}
    _prepare(run_dir, items, config)
    fixture_data = json.loads(fixtures.read_text(encoding="utf-8"))
    if not isinstance(fixture_data, dict):
        raise ValueError("fixtures must map model labels to item mappings")
    responses = _records(run_dir / "responses.jsonl")
    keys = {(row["model"], row["item_id"]) for row in responses if row["status"] != "rate_limited"}
    # Validate the existing log before appending anything, including duplicate entries.
    _reanalyze_unlocked(run_dir)
    paused = False
    for model in models:
        mapping = fixture_data.get(model, {})
        if not isinstance(mapping, dict):
            raise ValueError(f"fixture model {model!r} must map item ids to responses")
        for item in items:
            key = (model, item["id"])
            if key in keys:
                continue
            start = time.perf_counter()
            now = _timestamp()
            fixture = mapping.get(item["id"])
            if isinstance(fixture, str):
                fixture = {"status": 200, "answer": fixture}
            if fixture is None:
                fixture = {"status": "missing", "error": "no fixture supplied"}
            if not isinstance(fixture, dict):
                raise ValueError(f"invalid fixture for {key}")
            code = fixture.get("status", 200)
            if code == 200 and isinstance(fixture.get("answer"), str):
                status, answer, error = "ok", fixture["answer"], None
            elif code == 429:
                status, answer, error = "rate_limited", None, fixture.get("error", "fixture 429")
            else:
                status, answer, error = "error", None, fixture.get("error", f"fixture status {code}")
            _append(run_dir / "responses.jsonl", {
                "synthetic": True, "model": model, "item_id": item["id"], "status": status,
                "raw_answer": answer, "answer": answer, "error": str(error) if error is not None else None,
                "fixture_status": code, "started_at": now, "finished_at": _timestamp(),
                "latency_ms": (time.perf_counter() - start) * 1000,
            })
            if status == "rate_limited":
                paused = True
                break
        if paused:
            break
    result = _reanalyze_unlocked(run_dir)
    result["paused"] = paused
    _write(run_dir / "summary.json", result)
    return result


def run_live(dataset, run_dir, model, provider, max_requests=4):
    with _locked(run_dir):
        return _run_live_unlocked(dataset, Path(run_dir), model, provider, max_requests)


def _run_live_unlocked(dataset, run_dir, model, provider, max_requests):
    """Opt-in live run; unresolved attempts block all automatic redispatch."""
    from .openrouter import FREE_MODELS, generate

    if model not in FREE_MODELS or not isinstance(provider, str) or not provider.strip():
        raise ValueError("explicit allowed :free model and nonempty provider required")
    if type(max_requests) is not int or not 1 <= max_requests <= 40:
        raise ValueError("max-requests must be between 1 and 40")
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        raise ValueError("OPENROUTER_API_KEY is required")
    provider = provider.strip()
    dataset, run_dir = Path(dataset), Path(run_dir)
    items = load_dataset(dataset)
    config = {**_config(items, [model], False, "openrouter_live"), "provider": provider,
              "system_prompt": SYSTEM_PROMPT, "prompt_template": PROMPT_TEMPLATE,
              "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
              "code_version": "0.1.0"}
    _prepare(run_dir, items, config)
    attempts = _records(run_dir / "attempts.jsonl")
    responses = _records(run_dir / "responses.jsonl")
    if _validate_live_logs(config, items, attempts, responses):
        raise ValueError("unresolved live attempt; inspect provider and logs manually before any retry")
    result = _reanalyze_unlocked(run_dir)
    if any(r.get("error") in ("returned model differs from requested ID",
                              "reported cost is positive", "returned provider differs from requested slug")
           for r in responses):
        raise ValueError("suspicious routing or billing; inspect saved records before resuming")
    done = {r["item_id"] for r in responses if r["status"] != "rate_limited"}
    paused = False
    # Budget is cumulative per run, not reset by restarting the process.
    for item in items:
        if item["id"] in done or len(attempts) >= max_requests:
            continue
        if attempts:
            time.sleep(3)
        intent = {"attempt_id": uuid4().hex, "model": model, "item_id": item["id"],
                  "started_at": _timestamp(), "synthetic": False}
        _append(run_dir / "attempts.jsonl", intent)
        attempts.append(intent)
        start = time.perf_counter()
        try:
            reply = generate(model, PROMPT_TEMPLATE.format(prompt=item["prompt"]),
                             SYSTEM_PROMPT, provider, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
        except RuntimeError as exc:
            # Only known HTTP classifications are definite responses; do not persist exception text.
            message = str(exc)
            if message == "OpenRouter HTTP 429 rate limited":
                status, error = "rate_limited", "HTTP 429"
            elif message.startswith("OpenRouter HTTP 5xx (") or message.startswith("OpenRouter HTTP 4xx ("):
                status, error = "error", "HTTP 5xx" if "5xx" in message else "HTTP 4xx"
            else:
                # Timeout/transport/unknown failure may have reached the provider.
                paused = True
                break
            reply = None
        except Exception:
            paused = True
            break
        else:
            usage = reply.get("usage") or {}
            try:
                reported_cost = float(usage.get("cost", 0))
            except (TypeError, ValueError, OverflowError):
                reported_cost = float("nan")
            returned_provider_slug = reply.get("returned_provider_slug")
            if not math.isfinite(reported_cost) or reported_cost > 0:
                status, error = "error", "reported cost is positive"
            elif reply.get("returned_model") not in (None, model):
                status, error = "error", "returned model differs from requested ID"
            elif returned_provider_slug is not None and returned_provider_slug != provider:
                # Only the returned slug is comparable; provider can be a display name.
                status, error = "error", "returned provider differs from requested slug"
            else:
                status, error = (("truncated", None) if reply.get("finish_reason") == "length"
                                 else ("ok", None))
        record = {"attempt_id": intent["attempt_id"], "synthetic": False, "model": model,
                  "item_id": item["id"], "status": status, "error": error,
                  "answer": reply["answer"] if reply is not None else None,
                  "raw_answer": reply["raw_response"] if reply is not None else None,
                  "returned_model": reply.get("returned_model") if reply else None,
                  "provider": reply.get("provider") if reply else None,
                  "returned_provider_slug": reply.get("returned_provider_slug") if reply else None,
                  "usage": {k: (reply.get("usage") or {}).get(k) for k in
                            ("prompt_tokens", "completion_tokens", "total_tokens") if
                            k in (reply.get("usage") or {})} | (
                                {"cost": reported_cost if math.isfinite(reported_cost) else None}
                                if reply and "cost" in (reply.get("usage") or {}) else {})
                            if reply else None,
                  "finish_reason": reply.get("finish_reason") if reply else None,
                  "generation_id": reply.get("generation_id") if reply else None,
                  "started_at": intent["started_at"], "finished_at": _timestamp(),
                  "latency_ms": (time.perf_counter() - start) * 1000}
        _append(run_dir / "responses.jsonl", record)
        responses.append(record)
        result = _reanalyze_unlocked(run_dir)
        if status == "rate_limited" or error in ("returned model differs from requested ID",
                                                 "reported cost is positive",
                                                 "returned provider differs from requested slug"):
            paused = True
            break
    result["paused"] = paused
    result["unresolved_attempts"] = sum(a["attempt_id"] not in
                                        {r.get("attempt_id") for r in responses} for a in attempts)
    _write(run_dir / "summary.json", result)
    return result
