from datetime import datetime

import httpx

from app.providers.common import (
    CatalogEntry,
    GenerationRequest,
    GenerationResponse,
    ProviderError,
    QuotaObservation,
    get_json,
    normalize_response,
)
from app.providers.policy import require_free
from app.providers.zen_pricing import (
    CHAT_FREE_IDS,
    ZEN_PRICING_EXPIRES_AT,
    ZEN_PRICING_SOURCE,
    evidence,
)

# Documented chat endpoints; pricing eligibility is narrower and uses a dated
# exact-ID allowlist in zen_pricing.py.
CHAT_IDS = CHAT_FREE_IDS | frozenset({
    "qwen3.8-max", "deepseek-v4.1-flash", "deepseek-v4-pro", "deepseek-v4-flash",
    "deepseek-v4-flash-vision-exp",
})


class Zen:
    slug = "opencode_zen"
    base_url = "https://opencode.ai/zen/v1"

    def __init__(self, key: str, client: httpx.Client):
        self.client = client
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}

    def catalog(self) -> list[CatalogEntry]:
        data = get_json(self.client, "GET", f"{self.base_url}/models", headers=self.headers)
        if not isinstance(data.get("data"), list):
            raise ProviderError("invalid_catalog")
        entries = []
        for raw in data["data"]:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                continue
            name = raw["id"]
            allowed = name in CHAT_FREE_IDS
            entries.append(CatalogEntry(
                name, name, "chat/completions" if name in CHAT_IDS else "unsupported", None,
                ("max_tokens",) if name in CHAT_IDS else (), evidence(name),
                available=raw.get("available") is not False,
                pricing_source=ZEN_PRICING_SOURCE if allowed else None,
                pricing_expires_at=ZEN_PRICING_EXPIRES_AT if allowed else None,
            ))
        return entries

    def quota(self) -> QuotaObservation | None:
        return None  # No documented Zen free-request-counter endpoint.

    def generate(self, request: GenerationRequest, entry: CatalogEntry, checked_at: datetime) -> GenerationResponse:
        require_free(self.slug, entry, checked_at, request)
        if not self.headers:
            raise ProviderError("credentials_unavailable")
        body = {"model": request.model_id, "messages": [{"role": role, "content": text} for role, text in request.messages], "max_tokens": request.max_tokens, "stream": False}
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.seed is not None:
            body["seed"] = request.seed
        return normalize_response(get_json(self.client, "POST", f"{self.base_url}/chat/completions",
                                           headers=self.headers, json=body, timeout=request.timeout_seconds))
