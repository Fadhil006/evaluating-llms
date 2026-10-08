"""Allowlisted experiment report data and safe standalone renderers."""

import csv
import html
import importlib.metadata
import io
import json
import platform
import re
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Dataset,
    DatasetItem,
    DatasetVersion,
    Experiment,
    ExperimentEvent,
    ExperimentModel,
    GenerationJob,
    HumanRating,
    MetricResult,
    ModelResponse,
    ModelSnapshot,
    PairwiseVote,
    Provider,
    RequestAttempt,
    ReviewAssignment,
)
from app.services.results import recover_scores, results
from app.services.review import summary


def _clean(value, secrets):
    if isinstance(value, dict):
        return {str(k): _clean(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v, secrets) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def report_data(session: Session, experiment_id: int, redactions: list[str] | None = None) -> dict | None:
    """Build a versioned report without serializing ORM objects or private state."""
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        return None
    recover_scores(session, experiment_id)
    version = session.get(DatasetVersion, experiment.dataset_version_id)
    dataset = session.get(Dataset, version.dataset_id) if version else None
    config = experiment.config or {}
    models = []
    for slot in session.scalars(select(ExperimentModel).where(
            ExperimentModel.experiment_id == experiment_id).order_by(ExperimentModel.slot)):
        snap = session.get(ModelSnapshot, slot.model_snapshot_id)
        provider = session.get(Provider, snap.provider_id)
        models.append({"slot": slot.slot, "provider": provider.slug, "model_id": snap.model_id,
                       "display_name": snap.display_name, "endpoint": snap.endpoint_family,
                       "capabilities": snap.capabilities, "supported_parameters": snap.supported_parameters,
                       "pricing": snap.pricing_evidence, "pricing_source": snap.pricing_source,
                       "pricing_checked_at": snap.pricing_checked_at,
                       "pricing_expires_at": snap.pricing_expires_at,
                       "provider_version": snap.provider_version, "availability": snap.availability,
                       "selected_snapshot_id": next((m.get("snapshot_id") for m in config.get("models", [])
                                                      if m.get("provider") == provider.slug and
                                                      m.get("model_id") == snap.model_id), snap.id)})
    jobs = session.scalars(select(GenerationJob).where(GenerationJob.experiment_id == experiment_id)
                           .order_by(GenerationJob.execution_order)).all()
    events = session.scalars(select(ExperimentEvent).where(ExperimentEvent.experiment_id == experiment_id)
                             .order_by(ExperimentEvent.id)).all()
    terminal_events = [event for event in events if event.event_type in
                       {"completed", "completed_with_errors", "cancelled"}]
    item_map = {i.id: i for i in session.scalars(select(DatasetItem).where(
        DatasetItem.id.in_({j.dataset_item_id for j in jobs})))} if jobs else {}
    data = {"schema_version": "1", "exported_at": datetime.now(UTC),
        "demonstration_label": ("DEMONSTRATION — synthetic responses, no live API calls"
                                if experiment.provenance_mode == "demo" else None),
        "experiment": {"id": experiment.id, "name": experiment.name,
            "status": experiment.status, "pause_reason": experiment.pause_reason,
            "config_schema_version": experiment.config_schema_version, "config": config,
            "config_sha256": experiment.config_sha256, "provenance_mode": experiment.provenance_mode,
            "created_at": experiment.created_at, "started_at": experiment.started_at,
            "completed_at": terminal_events[-1].created_at if terminal_events else None},
        "dataset": ({"id": dataset.id, "name": dataset.name, "description": dataset.description,
                     "origin": dataset.origin, "source": dataset.source, "license": dataset.license,
                     "version_id": version.id, "version": version.version,
                     "content_sha256": version.content_sha256, "manifest": version.manifest,
                     "category_inventory": version.category_inventory,
                     "import_schema_version": version.import_schema_version,
                     "selected_item_ids": config.get("item_ids", [])} if dataset and version else None),
        "models": models,
        "software": {"application": "llm-comparison-lab", "python": platform.python_version(),
                     "sqlalchemy": importlib.metadata.version("sqlalchemy")},
        "runtime_versions": config.get("models", []),
        "jobs": [],
        "events": [{"timestamp": event.created_at, "type": event.event_type, "details": event.details}
                   for event in events],
        "aggregates": results(session, experiment_id),
        "human_review": summary(session, experiment_id),
        "limitations": ["Convenience sample; not representative of all tasks or users.",
                        "Route latency is measured under this run's conditions, not intrinsic model speed.",
                        "Human evaluator labels are local and unauthenticated; review is not accuracy.",
                        "Fixture provenance indicates synthetic responses, not live provider performance.",
                        "Unknown usage remains unknown; absent responses remain missing, not zero."]}
    data["human_feedback"] = []
    for rating in session.scalars(select(HumanRating).join(ReviewAssignment).where(
            ReviewAssignment.experiment_id == experiment_id)):
        data["human_feedback"].append({"kind": "rubric", "rubric_version": rating.rubric_version,
            "evaluator_label": rating.evaluator_label, "scores": rating.scores, "comments": rating.comments})
    for vote in session.scalars(select(PairwiseVote).join(ReviewAssignment).where(
            ReviewAssignment.experiment_id == experiment_id)):
        data["human_feedback"].append({"kind": "pairwise", "rubric_version": vote.rubric_version,
            "evaluator_label": vote.evaluator_label, "choice": vote.choice, "comments": vote.comments})
    for job in jobs:
        item = item_map[job.dataset_item_id]
        attempt_rows = session.scalars(select(RequestAttempt).where(RequestAttempt.job_id == job.id)
                                       .order_by(RequestAttempt.attempt_number)).all()
        response = session.scalar(select(ModelResponse).where(ModelResponse.job_id == job.id))
        scores = []
        if response:
            scores = [{"metric": m.metric, "scorer_version": m.scorer_version, "value": m.value,
                       "normalized_answer": m.normalized_answer, "parse_status": m.parse_status,
                       "explanation": m.explanation}
                      for m in session.scalars(select(MetricResult).where(MetricResult.response_id == response.id)
                                               .order_by(MetricResult.metric, MetricResult.scorer_version))]
        data["jobs"].append({"job_id": job.id, "model_slot": job.model_slot,
            "item_id": item.external_id, "task_type": item.task_type, "prompt": item.prompt,
            "context": item.context, "choices": item.choices, "reference_answers": item.reference_answers,
            "repetition": job.repetition, "variant": job.variant, "status": job.status,
            "execution_order": job.execution_order, "attempts": [{"number": a.attempt_number,
                "outcome": a.outcome, "reserved_at": a.reserved_at, "dispatched_at": a.dispatched_at,
                "completed_at": a.completed_at, "duration_ms": a.duration_ms,
                "error_code": a.error_code, "retry_after": a.retry_after,
                "eligibility_evidence": a.eligibility_evidence} for a in attempt_rows],
            "requested_identity": {"provider": next((m["provider"] for m in models
                                    if m["slot"] == job.model_slot), None),
                                   "model_id": next((m["model_id"] for m in models
                                                     if m["slot"] == job.model_slot), None)},
            "response": ({"text": response.raw_text, "returned_identity": response.returned_identity,
                "identity_differs": response.identity_mismatch,
                "finish_reason": response.finish_reason, "truncated": response.finish_reason == "length",
                "identity_mismatch": response.identity_mismatch, "usage": response.usage,
                "upstream_route": {key: response.safe_metadata[key] for key in ("provider", "route")
                                   if key in response.safe_metadata},
                "provenance": response.provenance, "scores": scores} if response else None)})
    return _clean(data, redactions or [])


def render_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)


def render_html(data: dict) -> str:
    rows = "".join("<tr><td>{}</td><td>{}</td><td>{}</td><td><pre>{}</pre></td></tr>".format(
        *(html.escape(str(v if v is not None else "")) for v in
          (job["model_slot"], job["item_id"], job["status"],
           job["response"]["text"] if job["response"] else ""))) for job in data["jobs"])
    title = html.escape(str(data["experiment"]["name"]))
    manifest = html.escape(render_json(data))
    banner = ("<strong>DEMONSTRATION — synthetic responses, no live API calls</strong>" +
              "<br>" if data["demonstration_label"] else "")
    return ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>" + title +
            " report</title>" + banner + "<h1>" + title + "</h1><table><thead><tr><th>Slot</th><th>Item</th>"
            "<th>Status</th><th>Response</th></tr></thead><tbody>" + rows +
            "</tbody></table><h2>Allowlisted report manifest</h2><pre>" + manifest + "</pre></html>")


def render_markdown(data: dict) -> str:
    def code(value):
        text = str(value if value is not None else "")
        fence = "`" * max(3, max((len(m.group()) for m in re.finditer(r"`+", text)), default=0) + 1)
        return f"{fence}\n{text}\n{fence}"
    lines = ["# Experiment report", ""]
    if data["demonstration_label"]:
        lines.extend([f"**{data['demonstration_label']}**", ""])
    lines.extend([f"Name: {code(data['experiment']['name'])}",
                  f"Status: `{data['experiment']['status']}`", "", "## Provenance", "",
                  code(json.dumps({"dataset": data["dataset"], "models": data["models"]},
                                  ensure_ascii=False, indent=2)), "", "## Responses", ""])
    for job in data["jobs"]:
        lines.extend([f"### Slot {job['model_slot']} — item {code(job['item_id'])}", "",
                      f"Status: `{job['status']}`", "", code(job["prompt"]), "",
                      code(job["response"]["text"] if job["response"] else "[no response]"), ""])
    lines.extend(["## Aggregates", "", code(json.dumps(data["aggregates"], ensure_ascii=False, indent=2)),
                  "", "## Human review", "", code(json.dumps(data["human_review"], ensure_ascii=False, indent=2)),
                  "", "## Limitations", "", *[f"- {line}" for line in data["limitations"]], ""])
    return "\n".join(lines)


def render_csv(data: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["job_id", "model_slot", "provider", "model_id", "requested_model_id", "item_id", "task_type", "repetition",
                     "variant", "job_status", "prompt", "attempt_number", "attempt_outcome", "duration_ms", "error_code",
                     "response", "returned_identity", "finish_reason", "usage_json", "metric", "scorer_version",
                     "value", "parse_status", "human_feedback", "human_comments"])
    routes = {m["slot"]: m for m in data["models"]}
    def safe(value):
        if isinstance(value, str) and re.match(r"^[\s\x00-\x1f]*[=+@-]", value):
            return "'" + value
        return value
    for job in data["jobs"]:
        route = routes.get(job["model_slot"], {})
        attempts = job["attempts"] or [None]
        scores = job["response"]["scores"] if job["response"] else []
        for attempt in attempts:
            for score in scores or [None]:
                row = [job["job_id"], job["model_slot"], route.get("provider"), route.get("model_id"),
                       job["requested_identity"]["model_id"],
                       job["item_id"], job["task_type"], job["repetition"], job["variant"], job["status"], job["prompt"],
                       attempt["number"] if attempt else None, attempt["outcome"] if attempt else None,
                       attempt["duration_ms"] if attempt else None, attempt["error_code"] if attempt else None,
                       job["response"]["text"] if job["response"] else None,
                       job["response"]["returned_identity"] if job["response"] else None,
                       job["response"]["finish_reason"] if job["response"] else None,
                       json.dumps(job["response"]["usage"], ensure_ascii=False) if job["response"] and
                       job["response"]["usage"] is not None else None,
                       score["metric"] if score else None, score["scorer_version"] if score else None,
                       score["value"] if score else None, score["parse_status"] if score else None,
                        json.dumps(data["human_feedback"], ensure_ascii=False),
                        "\n".join(feedback["comments"] for feedback in data["human_feedback"]
                                  if feedback["comments"])]
                writer.writerow([safe(value) for value in row])
    return stream.getvalue()
