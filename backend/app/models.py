"""Phase 1 relational schema. Status strings and JSON payloads gain service validation in later phases."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Record(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp())


class Provider(Record):
    __tablename__ = "providers"

    slug: Mapped[str] = mapped_column(String(80), unique=True)
    base_url: Mapped[str] = mapped_column(String(512))
    credential_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    connection_status: Mapped[str] = mapped_column(String(40), default="unchecked")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    policy_links: Mapped[dict] = mapped_column(JSON, default=dict)


class ProviderAccountState(Record):
    __tablename__ = "provider_account_states"

    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), unique=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quota_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quota_source: Mapped[str | None] = mapped_column(String(512))
    quota_limit: Mapped[int | None] = mapped_column(Integer)
    quota_used: Mapped[int | None] = mapped_column(Integer)
    quota_app_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    request_day: Mapped[str | None] = mapped_column(String(10))
    request_count: Mapped[int] = mapped_column(Integer, default=0)


class ProviderCall(Record):
    __tablename__ = "provider_calls"

    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    call_kind: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(40))


class ModelSnapshot(Record):
    __tablename__ = "model_snapshots"

    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    model_id: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    endpoint_family: Mapped[str] = mapped_column(String(80))
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    supported_parameters: Mapped[list] = mapped_column(JSON, default=list)
    pricing_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    pricing_source: Mapped[str | None] = mapped_column(String(512))
    pricing_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pricing_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_version: Mapped[dict] = mapped_column(JSON, default=dict)
    availability: Mapped[str] = mapped_column(String(40), default="unknown")


class Dataset(Record):
    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(40))
    source: Mapped[str | None] = mapped_column(String(512))
    license: Mapped[str | None] = mapped_column(String(100))


class DatasetVersion(Record):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version"),)

    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    version: Mapped[str] = mapped_column(String(80))
    content_sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    category_inventory: Mapped[dict] = mapped_column(JSON, default=dict)
    import_schema_version: Mapped[str] = mapped_column(String(40))


class DatasetItem(Record):
    __tablename__ = "dataset_items"
    __table_args__ = (UniqueConstraint("dataset_version_id", "external_id"),)

    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"))
    external_id: Mapped[str] = mapped_column(String(255))
    task_type: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    choices: Mapped[list | None] = mapped_column(JSON)
    reference_answers: Mapped[list] = mapped_column(JSON)
    scoring_config: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str | None] = mapped_column(String(512))
    license: Mapped[str | None] = mapped_column(String(100))


class Experiment(Record):
    __tablename__ = "experiments"

    name: Mapped[str] = mapped_column(String(255))
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"))
    status: Mapped[str] = mapped_column(String(40), default="draft")
    pause_reason: Mapped[str | None] = mapped_column(String(80))
    config_schema_version: Mapped[str] = mapped_column(String(40), default="1")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    config_sha256: Mapped[str | None] = mapped_column(String(64))
    provenance_mode: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentModel(Record):
    __tablename__ = "experiment_models"
    __table_args__ = (UniqueConstraint("experiment_id", "slot"),)

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    model_snapshot_id: Mapped[int] = mapped_column(ForeignKey("model_snapshots.id"))
    slot: Mapped[int] = mapped_column(Integer)


class GenerationJob(Record):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["experiment_id", "model_slot"], ["experiment_models.experiment_id", "experiment_models.slot"]
        ),
        UniqueConstraint("experiment_id", "model_slot", "dataset_item_id", "repetition", "variant"),
    )

    experiment_id: Mapped[int] = mapped_column(Integer)
    model_slot: Mapped[int] = mapped_column(Integer)
    dataset_item_id: Mapped[int] = mapped_column(ForeignKey("dataset_items.id"))
    repetition: Mapped[int] = mapped_column(Integer)
    variant: Mapped[str] = mapped_column(String(80), default="baseline")
    execution_order: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    next_eligible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_token: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)


class RequestAttempt(Record):
    __tablename__ = "request_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt_number"),)

    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(40))
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    provider_response_id: Mapped[str | None] = mapped_column(String(255))
    error_code: Mapped[str | None] = mapped_column(String(80))
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eligibility_evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelResponse(Record):
    __tablename__ = "model_responses"

    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id"), unique=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("request_attempts.id"), unique=True)
    raw_text: Mapped[str] = mapped_column(Text)
    returned_identity: Mapped[str | None] = mapped_column(String(255))
    finish_reason: Mapped[str | None] = mapped_column(String(80))
    usage: Mapped[dict | None] = mapped_column(JSON)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[str] = mapped_column(String(40), default="live", server_default="live")
    identity_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)


class MetricResult(Record):
    __tablename__ = "metric_results"
    __table_args__ = (UniqueConstraint("response_id", "metric", "scorer_version"),)

    response_id: Mapped[int] = mapped_column(ForeignKey("model_responses.id"))
    metric: Mapped[str] = mapped_column(String(80))
    scorer_version: Mapped[str] = mapped_column(String(40))
    value: Mapped[float | None]
    normalized_answer: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(40))
    explanation: Mapped[str | None] = mapped_column(Text)


class ReviewAssignment(Record):
    __tablename__ = "review_assignments"
    __table_args__ = (UniqueConstraint("experiment_id", "evaluator_label", "mode", "assignment_key"),)

    opaque_id: Mapped[str] = mapped_column(String(120), unique=True)
    assignment_key: Mapped[str | None] = mapped_column(String(64))
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    dataset_item_id: Mapped[int] = mapped_column(ForeignKey("dataset_items.id"))
    mode: Mapped[str] = mapped_column(String(40))
    evaluator_label: Mapped[str] = mapped_column(String(120))
    presentation: Mapped[dict] = mapped_column(JSON)


class HumanRating(Record):
    __tablename__ = "human_ratings"
    __table_args__ = (UniqueConstraint("response_id", "evaluator_label", "rubric_version"),)

    assignment_id: Mapped[int] = mapped_column(ForeignKey("review_assignments.id"))
    response_id: Mapped[int] = mapped_column(ForeignKey("model_responses.id"))
    evaluator_label: Mapped[str] = mapped_column(String(120))
    rubric_version: Mapped[str] = mapped_column(String(40))
    scores: Mapped[dict] = mapped_column(JSON)
    comments: Mapped[str | None] = mapped_column(Text)


class PairwiseVote(Record):
    __tablename__ = "pairwise_votes"
    __table_args__ = (UniqueConstraint("assignment_id", "evaluator_label", "rubric_version"),)

    assignment_id: Mapped[int] = mapped_column(ForeignKey("review_assignments.id"))
    evaluator_label: Mapped[str] = mapped_column(String(120))
    rubric_version: Mapped[str] = mapped_column(String(40))
    choice: Mapped[str] = mapped_column(String(40))
    comments: Mapped[str | None] = mapped_column(Text)


class ExperimentEvent(Record):
    __tablename__ = "experiment_events"

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    event_type: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
