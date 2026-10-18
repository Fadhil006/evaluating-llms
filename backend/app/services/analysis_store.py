"""Persistence and retrieval for explicit immutable experiment analyses."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation import scoring
from app.models import (
    AnalysisSnapshot,
    DatasetItem,
    DatasetVersion,
    Experiment,
    ExperimentModel,
    GenerationJob,
    MetricResult,
    ModelResponse,
)
from app.services.analysis import create_snapshot
from app.services.results import recover_scores


def create_analysis(session: Session, experiment_id: int,
                    selected_slots: list[int] | None = None) -> dict | None:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        return None

    # This is the only API path that locally recovers missing score versions.
    recover_scores(session, experiment_id)
    version = session.get(DatasetVersion, experiment.dataset_version_id)
    jobs = session.scalars(select(GenerationJob).where(
        GenerationJob.experiment_id == experiment_id).order_by(GenerationJob.id)).all()
    item_ids = {job.dataset_item_id for job in jobs}
    items = {item.id: item for item in session.scalars(select(DatasetItem).where(
        DatasetItem.id.in_(item_ids)))} if item_ids else {}
    slots = session.scalars(select(ExperimentModel).where(
        ExperimentModel.experiment_id == experiment_id).order_by(ExperimentModel.slot)).all()
    known_slots = {slot.slot for slot in slots}
    selected_slots = tuple(selected_slots if selected_slots is not None else sorted(known_slots)[:2])
    if len(selected_slots) != 2 or len(set(selected_slots)) != 2 or set(selected_slots) - known_slots:
        raise ValueError("Select exactly two distinct model slots belonging to this experiment")
    planned = []
    for job in jobs:
        if job.model_slot not in selected_slots:
            continue
        item = items[job.dataset_item_id]
        planned.append({"item_id": item.external_id, "model_slot": job.model_slot,
                        "task_type": item.task_type, "repetition": job.repetition,
                        "variant": job.variant, "family_id": item.family_id,
                        "split": item.split, "variant_id": item.variant_id,
                        "status": job.status})

    response_rows = session.scalars(select(ModelResponse).join(GenerationJob).where(
        GenerationJob.experiment_id == experiment_id)).all()
    response_by_id = {response.id: response for response in response_rows}
    response_to_job = {response.id: response.job_id for response in response_rows}
    observations = []
    instruction_counts = {}
    if response_to_job:
        metric_rows = session.scalars(select(MetricResult).where(
            MetricResult.response_id.in_(response_to_job)).order_by(MetricResult.id)).all()
        job_by_id = {job.id: job for job in jobs}
        pooled_checks = {}
        for score in metric_rows:
            job = job_by_id[response_to_job[score.response_id]]
            response = response_by_id[score.response_id]
            if job.model_slot not in selected_slots or response.identity_mismatch:
                continue
            if response.finish_reason == "length" and score.scorer_version != scoring.INSTRUCTION_CHECK_SCORER_VERSION:
                continue
            item = items[job.dataset_item_id]
            if score.metric in {"instruction_pooled_passed", "instruction_pooled_total"}:
                pooled_checks.setdefault(score.response_id, {})[score.metric] = score.value
                continue
            # Version-qualified identities prevent incompatible scorer versions
            # from being pooled into an ambiguous metric.
            observations.append({"item_id": item.external_id, "model_slot": job.model_slot,
                                 "task_type": item.task_type,
                                 "metric": f"{score.metric}@{score.scorer_version}",
                                 "metric_name": score.metric, "metric_version": score.scorer_version,
                                 "value": score.value, "repetition": job.repetition,
                                 "variant": job.variant, "status": job.status})
            if score.metric == "instruction_all_checks" and score.value is not None:
                stats = instruction_counts.setdefault((item.task_type, job.model_slot),
                                                       {"all_checks_passed": 0, "all_checks_total": 0,
                                                        "pooled_passed": 0, "pooled_total": 0})
                stats["all_checks_passed"] += int(score.value == 1)
                stats["all_checks_total"] += 1
        for response_id, values in pooled_checks.items():
            passed = values.get("instruction_pooled_passed")
            total = values.get("instruction_pooled_total")
            if passed is None or not total:
                continue
            job = job_by_id[response_to_job[response_id]]
            response = response_by_id[response_id]
            if job.model_slot not in selected_slots or response.identity_mismatch:
                continue
            item = items[job.dataset_item_id]
            stats = instruction_counts.setdefault((item.task_type, job.model_slot),
                                                   {"all_checks_passed": 0, "all_checks_total": 0,
                                                    "pooled_passed": 0, "pooled_total": 0})
            stats["pooled_passed"] += passed
            stats["pooled_total"] += total

    config = experiment.config or {}
    eligibility = {}
    for row in observations:
        key = f"{row['task_type']}:{row['metric']}"
        entry = eligibility.setdefault(key, {"scheduled": 0, "scored": 0, "eligible": 0,
                                             "scorer_version": row["metric_version"]})
        entry["scored"] += 1
        entry["eligible"] += int(row["value"] is not None)
    for row in planned:
        matching = [entry for key, entry in eligibility.items()
                    if key.startswith(f"{row['task_type']}:")]
        for entry in matching:
            entry["scheduled"] += 1
    manifest = {"experiment_id": experiment.id, "dataset_version_id": experiment.dataset_version_id,
                "dataset_sha256": version.content_sha256 if version else None,
                "selected_model_slots": list(selected_slots), "provenance_mode": experiment.provenance_mode,
                "config": config, "config_sha256": experiment.config_sha256,
                "scorer_version": scoring.SCORER_VERSION,
                "scorer_versions_observed": sorted({row["metric_version"] for row in observations}),
                "metric_eligibility": eligibility,
                "instruction_summary": {f"{task}:{slot}": {
                    **counts,
                    "all_checks_accuracy": (counts["all_checks_passed"] / counts["all_checks_total"]
                                             if counts["all_checks_total"] else None),
                    "pooled_accuracy": (counts["pooled_passed"] / counts["pooled_total"]
                                         if counts["pooled_total"] else None)}
                    for (task, slot), counts in sorted(instruction_counts.items())},
                "family_mapping": {item.external_id: {"family_id": item.family_id,
                                  "split": item.split, "variant_id": item.variant_id}
                                   for item in items.values()},
                "sampling_seed": config.get("seed", 0), "software_version": "1"}
    body = create_snapshot(manifest, planned, observations, selected_slots=selected_slots,
                           seed=config.get("seed", 0))
    record = AnalysisSnapshot(experiment_id=experiment_id, manifest=manifest,
                              snapshot=body, content_sha256=body["sha256"])
    session.add(record)
    session.flush()
    return {"id": record.id, "sha256": body["sha256"], "results": body["results"], "manifest": manifest}


def list_analyses(session: Session, experiment_id: int) -> list[dict]:
    rows = session.scalars(select(AnalysisSnapshot).where(
        AnalysisSnapshot.experiment_id == experiment_id).order_by(AnalysisSnapshot.id)).all()
    return [{"id": row.id, "sha256": row.content_sha256, "results": row.snapshot["results"],
             "manifest": row.manifest} for row in rows]


def get_analysis(session: Session, experiment_id: int, analysis_id: int) -> dict | None:
    row = session.scalar(select(AnalysisSnapshot).where(
        AnalysisSnapshot.experiment_id == experiment_id, AnalysisSnapshot.id == analysis_id))
    if row is None:
        return None
    return {"id": row.id, "sha256": row.content_sha256, "results": row.snapshot["results"],
            "manifest": row.manifest}
