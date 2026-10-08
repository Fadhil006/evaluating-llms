"""Resolve and enforce the newest persisted pricing evidence before dispatch."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModelSnapshot, Provider
from app.providers.common import Adapter, GenerationRequest, GenerationResponse, ProviderError
from app.providers.policy import decide


def evidence_for(record: ModelSnapshot, decision) -> dict:
    checked_at = record.pricing_checked_at
    checked_at = checked_at.replace(tzinfo=UTC) if checked_at and checked_at.tzinfo is None else checked_at
    expires_at = record.pricing_expires_at
    expires_at = expires_at.replace(tzinfo=UTC) if expires_at and expires_at.tzinfo is None else expires_at
    return {"snapshot_id": record.id, "pricing": record.pricing_evidence,
            "source": record.pricing_source, "checked_at": checked_at.isoformat() if checked_at else None,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "decision": decision.evidence()}


def dispatch(session: Session, adapter: Adapter, request: GenerationRequest,
             on_authorized: Callable[[dict], None] | None = None, *, demo: bool = False) -> GenerationResponse:
    """Dispatch only against the latest catalog observation for this exact route.

    The model sent upstream is sourced from the persisted row rather than any
    client-supplied provider/model URL. Caller owns durable attempt accounting.
    """
    record = session.scalar(
        select(ModelSnapshot)
        .join(Provider)
        .where(Provider.slug == adapter.slug, ModelSnapshot.model_id == request.model_id)
        .order_by(ModelSnapshot.id.desc())
        .limit(1)
    )
    if record is None:
        raise ProviderError("model_not_discovered")
    if adapter.slug == "fixture":
        if (not demo or request.provenance != "synthetic_fixture"
                or record.model_id not in {"fixture/alpha-v1", "fixture/beta-v1"}
                or record.pricing_evidence != {"provenance": "synthetic_fixture"}
                or record.pricing_source != "fixture://local"):
            raise ProviderError("fixture_demo_only")
        evidence = {"snapshot_id": record.id, "provenance": "synthetic_fixture", "decision": {"allowed": True}}
        if on_authorized is not None:
            on_authorized(evidence)
        response = adapter.generate(request, adapter_entry(record), None)
        if response.metadata.get("provenance") != "synthetic_fixture":
            raise ProviderError("fixture_provenance_missing")
        return response
    if demo and adapter.slug == "fixture":
        raise ProviderError("fixture_demo_only")
    checked_at = record.pricing_checked_at
    if checked_at is not None and checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)
    entry = adapter_entry(record)
    decision = decide(adapter.slug, entry, checked_at, datetime.now(UTC), request)
    evidence = evidence_for(record, decision)
    if not decision.allowed:
        raise ProviderError(decision.reason, evidence=evidence)
    if not adapter.headers:
        raise ProviderError("credentials_unavailable", evidence=evidence)
    if on_authorized is not None:
        on_authorized(evidence)
    # Provider.generate repeats the policy guard immediately before network I/O.
    return adapter.generate(request, entry, checked_at)


def adapter_entry(record: ModelSnapshot):
    from app.providers.common import CatalogEntry

    return CatalogEntry(
        model_id=record.model_id,
        name=record.display_name,
        endpoint=record.endpoint_family,
        context_length=record.capabilities.get("context_length"),
        supported_parameters=tuple(record.supported_parameters),
        pricing=record.pricing_evidence,
        available=record.availability == "available",
        version=record.provider_version,
        is_free=record.capabilities.get("is_free") is True,
        pricing_source=record.pricing_source,
        pricing_expires_at=record.pricing_expires_at,
    )
