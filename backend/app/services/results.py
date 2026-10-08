"""Local scoring and scheduled-job-based experiment reporting."""

import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation import scoring
from app.models import (
    DatasetItem,
    ExperimentModel,
    GenerationJob,
    MetricResult,
    ModelResponse,
    ModelSnapshot,
    Provider,
    RequestAttempt,
)


def score_response(session: Session, response: ModelResponse) -> list[MetricResult]:
    """Persist only missing metric/version pairs; never alter an accepted response."""
    job = session.get(GenerationJob, response.job_id)
    item = session.get(DatasetItem, job.dataset_item_id)
    if item.reference_answers:
        result = scoring.score(item.task_type, response.raw_text, item.reference_answers,
                               item.scoring_config, truncated=response.finish_reason == "length")
    else:
        # No reference cannot be graded, even when the answer is well formed.
        result = scoring.score(item.task_type, None, [], item.scoring_config)
        result.update(parse_status="missing_reference", explanation="No reference answer available")
    existing = {(row.metric, row.scorer_version) for row in session.scalars(select(MetricResult).where(
        MetricResult.response_id == response.id))}
    added = []
    for metric, value in result["metrics"].items():
        if (metric, result["scorer_version"]) in existing:
            continue
        normalized = result["normalized_answer"]
        if normalized is not None and not isinstance(normalized, str):
            normalized = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        row = MetricResult(response_id=response.id, metric=metric, scorer_version=result["scorer_version"],
                           value=value, normalized_answer=normalized, parse_status=result["parse_status"],
                           explanation=f"{result['explanation']} (normalization={result['normalization_version']}; "
                                       f"tokenizer={result['tokenizer_version']}; scorer={result['scorer_version']})")
        session.add(row)
        added.append(row)
    return added


def recover_scores(session: Session, experiment_id: int) -> None:
    """Rescore persisted answers with the current version, without invoking generation."""
    responses = session.scalars(select(ModelResponse).join(GenerationJob).where(
        GenerationJob.experiment_id == experiment_id)).all()
    for response in responses:
        try:
            score_response(session, response)
        except (ValueError, KeyError, TypeError):
            # A broken scoring declaration remains unscored; the saved answer is never regenerated.
            continue
    session.flush()


def _records(session: Session, experiment_id: int):
    jobs = session.scalars(select(GenerationJob).where(GenerationJob.experiment_id == experiment_id)
                           .order_by(GenerationJob.id)).all()
    items = {row.id: row for row in session.scalars(select(DatasetItem).where(
        DatasetItem.id.in_({job.dataset_item_id for job in jobs})))} if jobs else {}
    responses = {row.job_id: row for row in session.scalars(select(ModelResponse).where(
        ModelResponse.job_id.in_([job.id for job in jobs])))} if jobs else {}
    scores = defaultdict(dict)
    if responses:
        for row in session.scalars(select(MetricResult).where(MetricResult.response_id.in_(
            [response.id for response in responses.values()]), MetricResult.scorer_version == scoring.SCORER_VERSION)):
            scores[row.response_id][row.metric] = row
    return jobs, items, responses, scores


def results(session: Session, experiment_id: int, selected_slots: list[int] | None = None) -> dict:
    slots = session.scalars(select(ExperimentModel).where(ExperimentModel.experiment_id == experiment_id)
                            .order_by(ExperimentModel.slot)).all()
    known = {row.slot for row in slots}
    if selected_slots is None:
        selected_slots = sorted(known)
    if not selected_slots or len(set(selected_slots)) != len(selected_slots) or set(selected_slots) - known:
        raise ValueError("Select distinct model slots belonging to this experiment")
    identities = {}
    for slot in slots:
        snapshot = session.get(ModelSnapshot, slot.model_snapshot_id)
        identities[slot.slot] = {"provider": session.get(Provider, snapshot.provider_id).slug,
                                 "model_id": snapshot.model_id}

    jobs, items, responses, scores = _records(session, experiment_id)
    successful_attempts = session.scalars(select(RequestAttempt).join(GenerationJob).where(
        GenerationJob.experiment_id == experiment_id, RequestAttempt.outcome == "succeeded")).all()
    job_by_id = {job.id: job for job in jobs}
    latency_by_slot = defaultdict(list)
    for attempt in successful_attempts:
        job = job_by_id[attempt.job_id]
        response = responses.get(job.id)
        if job.model_slot in selected_slots and response and response.attempt_id == attempt.id and attempt.duration_ms is not None:
            latency_by_slot[job.model_slot].append(attempt.duration_ms)
    usage_by_slot = defaultdict(list)
    for response in responses.values():
        job = job_by_id[response.job_id]
        if job.model_slot in selected_slots and response.usage is not None and not response.identity_mismatch:
            usage_by_slot[job.model_slot].append(response.usage)
    groups = defaultdict(list)
    for job in jobs:
        if job.model_slot in selected_slots:
            item = items[job.dataset_item_id]
            for metric in scoring.score(item.task_type, None, [], item.scoring_config)["metrics"]:
                groups[(job.model_slot, item.task_type, metric)].append((job, item, responses.get(job.id)))

    summaries = []
    eligible_keys = defaultdict(set)
    values = {}
    binary = {"label_accuracy", "raw_exact_match", "normalized_exact_match", "numeric_exact",
              "json_valid", "schema_valid", "field_exact", "instruction_checks"}
    for (slot, task, metric), rows in sorted(groups.items()):
        counts = {name: 0 for name in ("scheduled_jobs", "responses", "complete", "truncated", "parseable",
                                        "metric_eligible", "missing_reference", "failures", "pending", "cancelled",
                                        "identity_mismatch", "format_failures", "unscored")}
        graded = []
        classification = []
        labels = None
        successes = 0
        for job, item, response in rows:
            counts["scheduled_jobs"] += 1
            if job.status in {"pending", "retry-wait", "leased", "interrupted"} and response is None:
                counts["pending"] += 1
            if job.status == "cancelled" and response is None:
                counts["cancelled"] += 1
            if job.status == "failed" and response is None:
                counts["failures"] += 1
            if response is None:
                continue
            counts["responses"] += 1
            counts["identity_mismatch"] += int(response.identity_mismatch)
            if response.finish_reason == "length":
                counts["truncated"] += 1
                continue
            counts["complete"] += 1
            score = scores[response.id].get(metric)
            if score is None:
                counts["unscored"] += 1
                continue
            if score.parse_status == "valid":
                counts["parseable"] += 1
            elif score.parse_status in {"unparseable", "malformed_json", "invalid_schema"}:
                counts["format_failures"] += 1
            if not item.reference_answers:
                counts["missing_reference"] += 1
            if response.identity_mismatch or score.value is None or not item.reference_answers:
                continue
            counts["metric_eligible"] += 1
            graded.append(score.value)
            if task == "classification" and metric == "label_accuracy":
                labels = item.scoring_config["labels"]
                classification.append((item.reference_answers[0], {
                    "parse_status": score.parse_status, "normalized_answer": score.normalized_answer}))
            successes += metric in binary and score.value == 1
            key = (item.external_id, job.repetition, job.variant)
            eligible_keys[(task, metric, slot)].add(key)
            values[(task, metric, slot, key)] = score.value
        denominator = len(graded)
        latencies = sorted(latency_by_slot[slot])
        usages = usage_by_slot[slot]
        summaries.append({"model_slot": slot, **identities[slot], "task_type": task, "metric": metric,
                          "scorer_version": scoring.SCORER_VERSION, **counts,
                          "quality": sum(graded) / denominator if denominator else None,
                          "quality_denominator": denominator,
                          "macro_f1": scoring.classification_macro_f1(classification, labels) if classification else None,
                          "successes": successes if metric in binary else None,
                           "overall_success": successes / counts["scheduled_jobs"] if metric in binary and counts["scheduled_jobs"] else None,
                           "overall_success_denominator": counts["scheduled_jobs"] if metric in binary else None,
                           "latency_sample_count": len(latencies),
                           "median_request_latency_ms": ((latencies[(len(latencies) - 1) // 2] +
                                                           latencies[len(latencies) // 2]) / 2) if latencies else None,
                           "p95_request_latency_ms": latencies[max(0, (95 * len(latencies) + 99) // 100 - 1)] if latencies else None,
                           "usage_sample_count": len(usages),
                           "prompt_tokens_total": (sum(u["prompt_tokens"] for u in usages if "prompt_tokens" in u)
                                                   if any("prompt_tokens" in u for u in usages) else None),
                           "completion_tokens_total": (sum(u["completion_tokens"] for u in usages if "completion_tokens" in u)
                                                       if any("completion_tokens" in u for u in usages) else None)})

    common = []
    for task, metric in sorted({(row["task_type"], row["metric"]) for row in summaries}):
        sets = [eligible_keys[(task, metric, slot)] for slot in selected_slots]
        intersection = set.intersection(*sets) if sets else set()
        keys = [{"item_id": item, "repetition": repeat, "variant": variant}
                for item, repeat, variant in sorted(intersection)]
        common.append({"task_type": task, "metric": metric, "keys": keys, "count": len(keys),
                       "models": [{"model_slot": slot, "eligible_count": len(eligible_keys[(task, metric, slot)]),
                                   "omitted_count": len(eligible_keys[(task, metric, slot)] - intersection),
                                   "omitted_keys": [{"item_id": i, "repetition": r, "variant": v} for i, r, v in
                                                    sorted(eligible_keys[(task, metric, slot)] - intersection)],
                                   "quality": (sum(values[(task, metric, slot, key)] for key in intersection) /
                                               len(intersection)) if intersection else None}
                                  for slot in selected_slots]})
    return {"experiment_id": experiment_id, "selected_model_slots": selected_slots,
            "summaries": summaries, "common_completed": common}


def response_detail(session: Session, experiment_id: int, response_id: int) -> dict | None:
    response = session.scalar(select(ModelResponse).join(GenerationJob).where(
        ModelResponse.id == response_id, GenerationJob.experiment_id == experiment_id))
    if response is None:
        return None
    job = session.get(GenerationJob, response.job_id)
    item = session.get(DatasetItem, job.dataset_item_id)
    metrics = session.scalars(select(MetricResult).where(MetricResult.response_id == response_id)
                              .order_by(MetricResult.metric, MetricResult.scorer_version)).all()
    denominators = {(row["task_type"], row["metric"]): row for row in
                    results(session, experiment_id, [job.model_slot])["summaries"]}
    return {"id": response.id, "job_id": job.id, "model_slot": job.model_slot,
            "item_id": item.external_id, "repetition": job.repetition, "variant": job.variant,
            "task_type": item.task_type, "raw_text": response.raw_text, "reference_answers": item.reference_answers,
            "reference_policy": "best accepted reference; see metric explanation",
            "returned_identity": response.returned_identity, "identity_mismatch": response.identity_mismatch,
            "finish_reason": response.finish_reason, "truncated": response.finish_reason == "length",
            "metrics": [{"metric": row.metric, "scorer_version": row.scorer_version, "value": row.value,
                         "normalized_answer": row.normalized_answer, "parse_status": row.parse_status,
                         "explanation": row.explanation,
                         "quality_denominator": denominators.get((item.task_type, row.metric), {}).get("quality_denominator"),
                         "scheduled_denominator": denominators.get((item.task_type, row.metric), {}).get("scheduled_jobs")}
                         for row in metrics]}


def response_rows(session: Session, experiment_id: int, *, model_slot: int | None = None,
                  task_type: str | None = None, status: str | None = None,
                  offset: int = 0, limit: int = 50) -> dict:
    jobs = session.scalars(select(GenerationJob).where(GenerationJob.experiment_id == experiment_id)
                           .order_by(GenerationJob.execution_order)).all()
    items = {row.id: row for row in session.scalars(select(DatasetItem).where(
        DatasetItem.id.in_({job.dataset_item_id for job in jobs})))} if jobs else {}
    slots = {row.slot: row for row in session.scalars(select(ExperimentModel).where(
        ExperimentModel.experiment_id == experiment_id))}
    snapshots = {row.id: row for row in session.scalars(select(ModelSnapshot).where(
        ModelSnapshot.id.in_({slot.model_snapshot_id for slot in slots.values()})))} if slots else {}
    providers = {row.id: row for row in session.scalars(select(Provider).where(
        Provider.id.in_({snapshot.provider_id for snapshot in snapshots.values()})))} if snapshots else {}
    response_map = {row.job_id: row for row in session.scalars(select(ModelResponse).where(
        ModelResponse.job_id.in_([job.id for job in jobs])))} if jobs else {}
    response_ids = [row.id for row in response_map.values()]
    metric_rows = session.scalars(select(MetricResult).where(MetricResult.response_id.in_(response_ids))) if response_ids else []
    metrics = defaultdict(list)
    for row in metric_rows:
        metrics[row.response_id].append(row)
    attempts = session.scalars(select(RequestAttempt).join(GenerationJob).where(
        GenerationJob.experiment_id == experiment_id).order_by(RequestAttempt.attempt_number.desc())).all()
    latest_attempt = {}
    for attempt in attempts:
        latest_attempt.setdefault(attempt.job_id, attempt)
    denominator_rows = results(session, experiment_id, sorted(slots))['summaries'] if jobs else []
    denominators = {(row['model_slot'], row['task_type'], row['metric']): row for row in denominator_rows}
    output = []
    for job in jobs:
        item = items[job.dataset_item_id]
        if (model_slot is not None and job.model_slot != model_slot) or (task_type and item.task_type != task_type):
            continue
        response = response_map.get(job.id)
        attempt = latest_attempt.get(job.id)
        if response is None:
            state = "failed" if job.status == "failed" else "cancelled" if job.status == "cancelled" else "pending"
        elif response.finish_reason == "length":
            state = "truncated"
        else:
            score_rows = metrics[response.id]
            state = "malformed" if any(row.parse_status in {"malformed_json", "invalid_schema", "unparseable"}
                                        for row in score_rows) else "answered"
        if status and status != "all" and state != status:
            continue
        snapshot = snapshots[slots[job.model_slot].model_snapshot_id]
        provider = providers[snapshot.provider_id]
        response_metrics = []
        if response:
            for metric in metrics[response.id]:
                summary = denominators.get((job.model_slot, item.task_type, metric.metric), {})
                response_metrics.append({"metric": metric.metric, "scorer_version": metric.scorer_version,
                                        "value": metric.value, "normalized_answer": metric.normalized_answer,
                                        "parse_status": metric.parse_status, "explanation": metric.explanation,
                                        "quality_denominator": summary.get("quality_denominator"),
                                        "scheduled_denominator": summary.get("scheduled_jobs")})
        score_detail = ({"id": response.id, "job_id": job.id, "model_slot": job.model_slot,
                         "item_id": item.external_id, "task_type": item.task_type,
                         "raw_text": response.raw_text, "reference_answers": item.reference_answers,
                         "returned_identity": response.returned_identity, "identity_mismatch": response.identity_mismatch,
                         "finish_reason": response.finish_reason, "truncated": response.finish_reason == "length",
                         "metrics": response_metrics} if response else None)
        output.append({"job_id": job.id, "model_slot": job.model_slot, "provider": provider.slug,
                       "model_id": snapshot.model_id, "item_id": item.external_id,
                       "task_type": item.task_type, "prompt": item.prompt, "context": item.context,
                       "choices": item.choices, "reference_answers": item.reference_answers,
                       "repetition": job.repetition, "variant": job.variant, "job_status": job.status,
                       "status": state, "attempt_error": attempt.error_code if attempt else None,
                       "duration_ms": attempt.duration_ms if response and attempt else None,
                       "usage": response.usage if response else None,
                       "response": score_detail})
    total = len(output)
    return {"total": total, "offset": offset, "limit": limit, "items": output[offset:offset + limit]}
