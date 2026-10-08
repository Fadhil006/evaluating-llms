"""Validate and persist editable experiment designs; no execution happens here."""

import hashlib
from collections import Counter
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    DatasetItem,
    DatasetVersion,
    Experiment,
    ExperimentModel,
    ModelSnapshot,
    Provider,
)
from app.providers.catalog import serialize_model
from app.services.datasets import canonical
from app.services.experiment_design import common_settings, estimate_requests, select_items


class Design(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    dataset_version_id: StrictInt = Field(gt=0)
    model_snapshot_ids: list[StrictInt] = Field(min_length=2, max_length=50)
    item_ids: list[str] | None = Field(default=None, min_length=1, max_length=5000)
    system_prompt: str = Field(default="", max_length=20000)
    max_tokens: StrictInt = Field(default=512, ge=1, le=4096)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    repetitions: StrictInt = Field(default=1, ge=1, le=20)
    seed: StrictInt = 42
    timeout_seconds: StrictInt = Field(default=60, ge=1, le=300)
    retries_per_job: StrictInt = Field(default=2, ge=0, le=10)
    attempt_cap: StrictInt = Field(default=40, ge=1, le=100000)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class DesignProblem(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message


def prepare(session: Session, design: Design) -> tuple[dict, dict]:
    version = session.get(DatasetVersion, design.dataset_version_id)
    if version is None:
        raise DesignProblem("dataset_version_id", "Dataset version not found")
    items = session.scalars(select(DatasetItem).where(DatasetItem.dataset_version_id == version.id)
                            .order_by(DatasetItem.external_id)).all()
    by_id = {item.external_id: item for item in items}
    if design.item_ids is None:
        selection = select_items([{"id": item.external_id, "task_type": item.task_type} for item in items], design.seed)
        selected = selection["item_ids"]
    else:
        selected = design.item_ids
        if len(set(selected)) != len(selected) or any(item_id not in by_id for item_id in selected):
            raise DesignProblem("item_ids", "Item IDs must be distinct and belong to the dataset version")
    if not selected:
        raise DesignProblem("item_ids", "Dataset version contains no items")
    if len(set(design.model_snapshot_ids)) != len(design.model_snapshot_ids):
        raise DesignProblem("model_snapshot_ids", "Model snapshot IDs must be distinct")
    rows = session.execute(select(ModelSnapshot, Provider.slug, Provider.credential_configured).join(Provider).where(
        ModelSnapshot.id.in_(design.model_snapshot_ids))).all()
    models = {row.id: (row, slug, credential_configured) for row, slug, credential_configured in rows}
    if len(models) != len(design.model_snapshot_ids):
        raise DesignProblem("model_snapshot_ids", "Model snapshot not found")
    ordered = [models[model_id] for model_id in design.model_snapshot_ids]
    for row, _, _ in ordered:
        context = row.capabilities.get("context_length") if isinstance(row.capabilities, dict) else None
        if type(context) is int and context > 0 and (design.max_tokens > context or any(
            (len(design.system_prompt) + len(by_id[item_id].prompt) + len(by_id[item_id].context or "")
             + sum(len(choice) for choice in (by_id[item_id].choices or []))) // 4 + design.max_tokens > context
            for item_id in selected
        )):
            raise DesignProblem("max_tokens", "Requested output and estimated input exceed a model context limit")
    try:
        common_settings([(slug, row.model_id, row.supported_parameters) for row, slug, _ in ordered],
                        ["temperature"] if design.temperature is not None else [])
        estimate = estimate_requests(len(ordered), len(selected), design.repetitions, design.retries_per_job,
                                      design.attempt_cap, metadata_startup=len({slug for _, slug, _ in ordered}),
                                      metadata_refresh=len({slug for _, slug, _ in ordered}))
    except ValueError as exc:
        field = "attempt_cap" if "cap" in str(exc) else "model_snapshot_ids"
        raise DesignProblem(field, str(exc)) from None
    if estimate["initial_candidate_requests"] > 10000:
        raise DesignProblem("repetitions", "Initial request budget exceeds 10000")
    # Local sampling seed is not a provider generation seed; no generation seed is requested.
    now = datetime.now(UTC)
    identities = [{"snapshot_id": row.id, "provider": slug, "model_id": row.model_id,
                   "credential_configured": credential_configured,
                   "endpoint": row.endpoint_family, "supported_parameters": row.supported_parameters,
                   "provider_version": row.provider_version}
                  for row, slug, credential_configured in ordered]
    decisions = [serialize_model(row, slug, now, credential_configured)["eligibility"]
                 | {"snapshot_id": row.id, "provider": slug, "credential_configured": credential_configured}
                 for row, slug, credential_configured in ordered]
    config = design.model_dump(exclude={"item_ids", "model_snapshot_ids"}) | {
        "schema_version": "1", "model_snapshot_ids": design.model_snapshot_ids,
        "models": identities, "item_ids": selected,
        "category_counts": dict(Counter(by_id[item_id].task_type for item_id in selected)),
        "dataset_content_sha256": version.content_sha256,
        "policy_decisions_advisory": decisions,
    }
    return config, estimate


def describe(session: Session, row: Experiment) -> dict:
    config = row.config
    estimate = estimate_requests(len(config["model_snapshot_ids"]), len(config["item_ids"]),
                                 config["repetitions"], config["retries_per_job"], config["attempt_cap"],
                                 metadata_startup=len({model["provider"] for model in config["models"]}),
                                 metadata_refresh=len({model["provider"] for model in config["models"]}))
    return {"id": row.id, "name": row.name, "status": row.status, "dataset_version_id": row.dataset_version_id,
            "config_schema_version": row.config_schema_version, "config": config,
            "config_sha256": row.config_sha256, "provenance_mode": row.provenance_mode,
            "created_at": row.created_at, "started_at": row.started_at,
            "estimate": estimate, "ready": all(d["allowed"] and
                (d.get("credential_configured") or row.provenance_mode == "demo")
                for d in config["policy_decisions_advisory"]),
            "readiness_advisory_only": True}


def save_design(session: Session, design: Design, *, row: Experiment | None = None, mode: str = "live") -> dict:
    config, _ = prepare(session, design)
    if row is None:
        row = Experiment(status="draft", provenance_mode=mode)
        session.add(row)
    row.name = design.name
    row.dataset_version_id = design.dataset_version_id
    row.config_schema_version = "1"
    row.config = config
    row.config_sha256 = hashlib.sha256(canonical(config).encode("utf-8")).hexdigest()
    session.flush()
    session.execute(delete(ExperimentModel).where(ExperimentModel.experiment_id == row.id))
    session.add_all(ExperimentModel(experiment_id=row.id, model_snapshot_id=model_id, slot=slot)
                    for slot, model_id in enumerate(design.model_snapshot_ids))
    session.flush()
    return describe(session, row)
