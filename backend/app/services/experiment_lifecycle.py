"""Transactional experiment queue transitions; dispatch remains the worker's responsibility."""

import hashlib
import random
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    DatasetItem,
    DatasetVersion,
    Experiment,
    ExperimentEvent,
    ExperimentModel,
    GenerationJob,
    ModelSnapshot,
    Provider,
    RequestAttempt,
)
from app.providers.common import GenerationRequest
from app.providers.dispatch import adapter_entry
from app.providers.policy import Decision, decide
from app.services.datasets import canonical
from app.services.experiment_design import common_settings, generation_messages
from app.services.experiments import Design, DesignProblem, prepare


class LifecycleConflict(Exception):
    pass


def eligible_routes(session: Session, row: Experiment, now: datetime) -> list[dict]:
    config = row.config
    if row.status != "draft" and hashlib.sha256(canonical(config).encode()).hexdigest() != row.config_sha256:
        raise LifecycleConflict("Frozen configuration changed")
    version = session.get(DatasetVersion, row.dataset_version_id)
    if version is None or version.content_sha256 != config["dataset_content_sha256"]:
        raise LifecycleConflict("Dataset version changed; clone and select a valid version")
    saved = config["models"]
    slots = session.scalars(select(ExperimentModel).where(ExperimentModel.experiment_id == row.id)
                            .order_by(ExperimentModel.slot)).all()
    if len(slots) != len(saved) or any(slot.slot != i or slot.model_snapshot_id != model["snapshot_id"]
                                            for i, (slot, model) in enumerate(zip(slots, saved))):
        raise LifecycleConflict("Model slots changed")
    items = session.scalars(select(DatasetItem).where(DatasetItem.dataset_version_id == version.id)).all()
    by_id = {item.external_id: item for item in items}
    if len(set(config["item_ids"])) != len(config["item_ids"]) or any(i not in by_id for i in config["item_ids"]):
        raise LifecycleConflict("Saved items changed")
    routes = []
    fixture_run = row.provenance_mode == "demo"
    if fixture_run and any(model.get("provider") != "fixture" for model in saved):
        raise LifecycleConflict("Demo experiments may select only fixture models")
    if not fixture_run and any(model.get("provider") == "fixture" for model in saved):
        raise LifecycleConflict("Fixture models are demo-only")
    for model in saved:
        original = session.get(ModelSnapshot, model["snapshot_id"])
        provider = session.get(Provider, original.provider_id) if original else None
        if (provider is None or provider.slug != model["provider"] or original.model_id != model["model_id"]
                or original.endpoint_family != model["endpoint"]):
            raise LifecycleConflict("Saved route identity changed")
        if not provider.credential_configured and not fixture_run:
            raise LifecycleConflict(f"{provider.slug}/{original.model_id}: provider key not configured")
        latest = session.scalar(select(ModelSnapshot).where(ModelSnapshot.provider_id == provider.id,
                                ModelSnapshot.model_id == original.model_id).order_by(ModelSnapshot.id.desc()).limit(1))
        if latest is None:
            raise LifecycleConflict("Model no longer discovered")
        entry = adapter_entry(latest)
        checked = latest.pricing_checked_at
        if checked is not None and checked.tzinfo is None:
            checked = checked.replace(tzinfo=UTC)
        context = entry.context_length
        if type(context) is int and context > 0 and any(
            (len(config["system_prompt"]) + len(by_id[item_id].prompt) + len(by_id[item_id].context or "")
             + sum(len(choice) for choice in (by_id[item_id].choices or []))) // 4 + config["max_tokens"] > context
            for item_id in config["item_ids"]
        ):
            raise LifecycleConflict("Requested output and estimated input exceed current context limit")
        request = GenerationRequest(model_id=entry.model_id,
                                    messages=generation_messages(config["system_prompt"], vars(by_id[config["item_ids"][0]])),
                                    max_tokens=config["max_tokens"], temperature=config["temperature"])
        synthetic = (fixture_run and provider.slug == "fixture"
                     and entry.model_id in {"fixture/alpha-v1", "fixture/beta-v1"}
                     and latest.pricing_evidence == {"provenance": "synthetic_fixture"}
                     and latest.pricing_source == "fixture://local")
        decision = (Decision(True, "synthetic_fixture", checked, entry.model_id)
                    if synthetic else decide(provider.slug, entry, checked, now, request))
        if not decision.allowed:
            raise LifecycleConflict(f"{provider.slug}/{entry.model_id}: {decision.reason}")
        if not synthetic and (not latest.pricing_source or (latest.pricing_expires_at is not None and
                                         latest.pricing_expires_at.replace(tzinfo=UTC) <= now)):
            raise LifecycleConflict(f"{provider.slug}/{entry.model_id}: missing or expired pricing source")
        routes.append({"provider": provider.slug, "model_id": entry.model_id,
                       "selected_snapshot_id": original.id, "snapshot_id": latest.id,
                       "endpoint": entry.endpoint, "context_length": context,
                       "supported_parameters": list(entry.supported_parameters),
                       "provider_version": latest.provider_version, "availability": latest.availability,
                       "pricing_evidence": latest.pricing_evidence, "pricing_source": latest.pricing_source,
                       "pricing_checked_at": checked.isoformat() if checked else None,
                       "pricing_expires_at": latest.pricing_expires_at.isoformat() if latest.pricing_expires_at else None,
                       "decision": decision.evidence()})
    try:
        common_settings([(r["provider"], r["model_id"], r["supported_parameters"]) for r in routes],
                        ["temperature"] if config["temperature"] is not None else [])
    except ValueError as exc:
        raise LifecycleConflict(str(exc)) from None
    return routes


def start(session: Session, row: Experiment) -> None:
    if row.status != "draft":
        raise LifecycleConflict("Only drafts can start")
    config = row.config
    if hashlib.sha256(canonical(config).encode()).hexdigest() != row.config_sha256:
        raise LifecycleConflict("Draft configuration changed")
    fields = set(Design.model_fields) - {"item_ids", "model_snapshot_ids"}
    try:
        design = Design.model_validate({k: config[k] for k in fields} | {
            "item_ids": config["item_ids"], "model_snapshot_ids": config["model_snapshot_ids"]})
        validated, _ = prepare(session, design)
    except (DesignProblem, ValueError) as exc:
        raise LifecycleConflict(f"Saved draft invalid: {exc}") from None
    if any(validated[k] != config[k] for k in ("item_ids", "models", "dataset_content_sha256", "category_counts")):
        raise LifecycleConflict("Saved draft identity changed")
    now = datetime.now(UTC)
    routes = eligible_routes(session, row, now)
    frozen = config | {"eligibility_at_start": routes, "started_at_utc": now.isoformat(),
                       "provenance_mode": row.provenance_mode,
                       "model_snapshot_ids": [route["snapshot_id"] for route in routes],
                       "models": [dict(model, snapshot_id=route["snapshot_id"],
                                       supported_parameters=route["supported_parameters"],
                                       endpoint=route["endpoint"], provider_version=route["provider_version"])
                                  for model, route in zip(config["models"], routes)]}
    ids = {item.external_id: item.id for item in session.scalars(select(DatasetItem).where(
        DatasetItem.dataset_version_id == row.dataset_version_id))}
    # Shuffle each round independently while cycling slots: nearby work alternates models.
    rng = random.Random(config["seed"])
    jobs = []
    for repetition in range(config["repetitions"]):
        item_ids = list(config["item_ids"])
        rng.shuffle(item_ids)
        for item_id in item_ids:
            slots = list(range(len(routes)))
            rng.shuffle(slots)
            for slot in slots:
                jobs.append(GenerationJob(experiment_id=row.id, model_slot=slot, dataset_item_id=ids[item_id],
                                          repetition=repetition, variant="baseline", execution_order=len(jobs),
                                          status="pending"))
    result = session.execute(update(Experiment).where(Experiment.id == row.id, Experiment.status == "draft")
                             .values(status="queued", config=frozen,
                                     config_sha256=hashlib.sha256(canonical(frozen).encode()).hexdigest(),
                                     started_at=now))
    if result.rowcount != 1:
        raise LifecycleConflict("Experiment already started")
    for slot, route in enumerate(routes):
        session.execute(update(ExperimentModel).where(ExperimentModel.experiment_id == row.id,
                        ExperimentModel.slot == slot).values(model_snapshot_id=route["snapshot_id"]))
    session.add_all(jobs)
    session.add(ExperimentEvent(experiment_id=row.id, event_type="queued", details={"jobs": len(jobs)}))


def transition(session: Session, row: Experiment, action: str, *, acknowledge_uncertain: bool = False) -> None:
    allowed = {"pause": {"queued", "running"}, "resume": {"paused", "interrupted"},
               "cancel": {"draft", "queued", "running", "paused", "interrupted"}}
    if row.status not in allowed[action]:
        raise LifecycleConflict(f"Cannot {action} an experiment in {row.status} state")
    if action == "resume":
        uncertain = session.scalar(select(GenerationJob.id).where(
            GenerationJob.experiment_id == row.id, GenerationJob.status == "interrupted").limit(1))
        uncertain_attempt = session.scalar(select(RequestAttempt.id).join(GenerationJob).where(
            GenerationJob.experiment_id == row.id,
            RequestAttempt.outcome.in_(["uncertain", "unknown_remote_outcome"])).limit(1))
        if not acknowledge_uncertain and (uncertain or uncertain_attempt):
            raise LifecycleConflict("Interrupted jobs require acknowledge_uncertain=true before retry")
        eligible_routes(session, row, datetime.now(UTC))
        session.execute(update(GenerationJob).where(GenerationJob.experiment_id == row.id,
                        GenerationJob.status == "interrupted").values(status="pending", lease_owner=None,
                        lease_token=None, lease_expires_at=None))
    if action == "cancel":
        session.execute(update(GenerationJob).where(GenerationJob.experiment_id == row.id,
                        GenerationJob.status.in_(["pending", "retry-wait", "interrupted"]))
                        .values(status="cancelled"))
    target = {"pause": "paused", "resume": "queued", "cancel": "cancelled"}[action]
    result = session.execute(update(Experiment).where(Experiment.id == row.id, Experiment.status == row.status)
                             .values(status=target, pause_reason="user" if action == "pause" else None))
    if result.rowcount != 1:
        raise LifecycleConflict("Experiment state changed")
    session.add(ExperimentEvent(experiment_id=row.id, event_type=target,
                                details={"in_flight_allowed_to_finish": action == "cancel",
                                         "uncertain_acknowledged": acknowledge_uncertain if action == "resume" else False}))
