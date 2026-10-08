"""Synthetic-only demo adapter; never reads answer keys."""

from datetime import datetime
from typing import ClassVar

from app.providers.common import (
    CatalogEntry,
    GenerationRequest,
    GenerationResponse,
    QuotaObservation,
)


class Fixture:
    slug = "fixture"
    base_url = "fixture://local"
    headers: ClassVar[dict[str, str]] = {}

    def catalog(self) -> list[CatalogEntry]:
        return [CatalogEntry(f"fixture/{name}-v1", f"DEMONSTRATION — synthetic {name.title()}",
                             "chat/completions", 4096, ("max_tokens",), {"provenance": "synthetic_fixture"})
                for name in ("alpha", "beta")]

    def quota(self) -> QuotaObservation | None:
        return None

    def generate(self, request: GenerationRequest, entry: CatalogEntry, checked_at: datetime) -> GenerationResponse:
        if request.model_id not in {"fixture/alpha-v1", "fixture/beta-v1"} or entry.model_id != request.model_id:
            from app.providers.common import ProviderError

            raise ProviderError("unknown_fixture_model")
        return GenerationResponse("DEMONSTRATION — synthetic fixture response.", request.model_id, None, "stop", None,
                                  {"provenance": "synthetic_fixture"})
