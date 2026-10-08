"""Catalog observations are append-only; failed refreshes never rewrite evidence."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModelSnapshot, Provider, ProviderCall
from app.providers.common import Adapter, CatalogEntry
from app.providers.policy import FRESH_FOR, decide


def refresh(session: Session, adapter: Adapter, entries: list[CatalogEntry]) -> int:
    provider = session.scalar(select(Provider).where(Provider.slug == adapter.slug))
    if provider is None:
        provider = Provider(slug=adapter.slug, base_url=adapter.base_url, credential_configured=bool(adapter.headers))
        session.add(provider)
        session.flush()
    provider.credential_configured = bool(adapter.headers)
    now = datetime.now(UTC)
    provider.connection_status = "reachable"
    provider.checked_at = now
    if adapter.slug != "fixture":
        session.add(ProviderCall(provider_id=provider.id, call_kind="catalog", outcome="ok"))
    for entry in entries:
        session.add(ModelSnapshot(provider_id=provider.id, model_id=entry.model_id, display_name=entry.name,
                                  endpoint_family=entry.endpoint, capabilities={"context_length": entry.context_length,
                                                                                "is_free": entry.is_free},
                                  supported_parameters=list(entry.supported_parameters), pricing_evidence=entry.pricing,
                                  pricing_source=entry.pricing_source or (adapter.base_url if adapter.slug == "fixture"
                                                                         else f"{adapter.base_url}/models"),
                                  pricing_checked_at=now,
                                  pricing_expires_at=entry.pricing_expires_at or now + FRESH_FOR,
                                  provider_version=entry.version,
                                  availability="available" if entry.available else "unavailable"))
    return len(entries)


def serialize_model(row: ModelSnapshot, slug: str, now: datetime, credential_configured: bool) -> dict:
    entry = CatalogEntry(row.model_id, row.display_name, row.endpoint_family,
                         row.capabilities.get("context_length"), tuple(row.supported_parameters),
                         row.pricing_evidence, row.availability == "available",
                         is_free=row.capabilities.get("is_free") is True, pricing_source=row.pricing_source,
                         pricing_expires_at=row.pricing_expires_at)
    decision = decide(slug, entry, row.pricing_checked_at.replace(tzinfo=UTC) if row.pricing_checked_at else None, now)
    return {"id": row.id, "provider": slug, "model_id": row.model_id, "name": row.display_name,
             "endpoint": row.endpoint_family, "context_length": entry.context_length,
             "supported_parameters": list(entry.supported_parameters), "availability": row.availability,
             "is_free": entry.is_free,
             "credential_configured": credential_configured,
             "pricing_source": row.pricing_source, "pricing_evidence": row.pricing_evidence,
             "checked_at": decision.evidence()["checked_at"],
             "eligibility": decision.evidence()}
