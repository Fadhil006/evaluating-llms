from datetime import UTC, datetime

import httpx

from app.providers.common import (
    CatalogEntry,
    GenerationRequest,
    GenerationResponse,
    QuotaObservation,
    get_json,
    normalize_response,
)
from app.providers.policy import require_free


class OpenRouter:
    slug = "openrouter"
    base_url = "https://openrouter.ai/api/v1"

    def __init__(self, key: str, client: httpx.Client):
        self.client = client
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}

    def catalog(self) -> list[CatalogEntry]:
        data = get_json(self.client, "GET", f"{self.base_url}/models", headers=self.headers)
        if not isinstance(data.get("data"), list):
            from app.providers.common import ProviderError

            raise ProviderError("invalid_catalog")
        entries = []
        for raw in data["data"]:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                continue
            params = raw.get("supported_parameters")
            architecture = raw.get("architecture")
            outputs = architecture.get("output_modalities") if isinstance(architecture, dict) else None
            entries.append(CatalogEntry(
                model_id=raw["id"], name=raw.get("name") if isinstance(raw.get("name"), str) else raw["id"],
                endpoint="chat/completions" if isinstance(outputs, list) and "text" in outputs else "unsupported",
                context_length=raw.get("context_length") if type(raw.get("context_length")) is int else None,
                supported_parameters=tuple(p for p in params if isinstance(p, str)) if isinstance(params, list) else (),
                pricing=raw.get("pricing") if isinstance(raw.get("pricing"), dict) else {},
                available=raw.get("is_ready") is not False,
                version={"created": raw["created"]} if type(raw.get("created")) is int else {},
                is_free=raw.get("is_free") is True,
            ))
        return entries

    def quota(self) -> QuotaObservation | None:
        if not self.headers:
            return None
        data = get_json(self.client, "GET", f"{self.base_url}/key", headers=self.headers).get("data")
        if not isinstance(data, dict):
            return QuotaObservation(f"{self.base_url}/key", datetime.now(UTC))
        counters = data.get("free_model_daily_requests")
        counters = counters if isinstance(counters, dict) else {}
        limit, used = counters.get("limit"), counters.get("used")
        return QuotaObservation(f"{self.base_url}/key", datetime.now(UTC), limit if type(limit) is int and limit >= 0 else None, used if type(used) is int and used >= 0 else None)

    def generate(self, request: GenerationRequest, entry: CatalogEntry, checked_at: datetime) -> GenerationResponse:
        require_free(self.slug, entry, checked_at, request)
        if not self.headers:
            from app.providers.common import ProviderError

            raise ProviderError("credentials_unavailable")
        body = {
            "model": request.model_id,
            "messages": [{"role": role, "content": text} for role, text in request.messages],
            "max_tokens": request.max_tokens, "stream": False,
            "provider": {"allow_fallbacks": False, "require_parameters": True,
                         "max_price": {"prompt": "0", "completion": "0", "request": "0", "image": "0"}},
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.seed is not None:
            body["seed"] = request.seed
        return normalize_response(get_json(self.client, "POST", f"{self.base_url}/chat/completions",
                                           headers=self.headers, json=body, timeout=request.timeout_seconds))
