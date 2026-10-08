from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Literal, Protocol

import httpx


@dataclass(frozen=True)
class CatalogEntry:
    model_id: str
    name: str
    endpoint: str
    context_length: int | None
    supported_parameters: tuple[str, ...]
    pricing: dict
    available: bool = True
    version: dict = field(default_factory=dict)
    is_free: bool = False
    pricing_source: str | None = None
    pricing_expires_at: datetime | None = None


@dataclass(frozen=True)
class QuotaObservation:
    source: str
    observed_at: datetime
    free_limit: int | None = None
    free_used: int | None = None


@dataclass(frozen=True)
class GenerationRequest:
    model_id: str
    messages: tuple[tuple[Literal["system", "user"], str], ...]
    max_tokens: int = 512
    temperature: float | None = None
    seed: int | None = None
    timeout_seconds: float | None = None
    provenance: str = "live"


@dataclass(frozen=True)
class GenerationResponse:
    text: str
    model_id: str | None
    response_id: str | None
    finish_reason: str | None
    usage: dict | None
    metadata: dict


class ProviderError(Exception):
    def __init__(self, code: str, status: int | None = None, retry_after: datetime | None = None,
                 evidence: dict | None = None):
        self.code = code
        self.status = status
        self.retry_after = retry_after
        self.evidence = evidence
        super().__init__(code)


def parse_retry_after(value: str | None, now: datetime | None = None) -> datetime | None:
    if not value or len(value) > 128:
        return None
    now = now or datetime.now(UTC)
    if value.isascii() and value.isdecimal():
        try:
            return now + timedelta(seconds=int(value))
        except OverflowError:
            return datetime.max.replace(tzinfo=UTC)
    try:
        date = parsedate_to_datetime(value)
        return date.astimezone(UTC) if date.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


class Adapter(Protocol):
    slug: str
    base_url: str
    headers: dict[str, str]

    def catalog(self) -> list[CatalogEntry]: ...
    def quota(self) -> QuotaObservation | None: ...
    def generate(self, request: GenerationRequest, entry: CatalogEntry, checked_at: datetime) -> GenerationResponse: ...


def get_json(client: httpx.Client, method: str, url: str, **kwargs) -> dict:
    try:
        response = client.request(method, url, **kwargs)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("not an object")
        return data
    except httpx.HTTPStatusError as exc:
        raise ProviderError(f"http_{exc.response.status_code}", exc.response.status_code,
                            parse_retry_after(exc.response.headers.get("Retry-After"))) from None
    except (httpx.RequestError, ValueError, TypeError):
        raise ProviderError("upstream_unavailable") from None


def normalize_response(data: dict) -> GenerationResponse:
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"]
        if not isinstance(text, str):
            raise TypeError
    except (KeyError, IndexError, TypeError, ValueError):
        raise ProviderError("invalid_response") from None
    usage = data.get("usage")
    safe_usage = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens") if type(usage.get(k)) is int and usage[k] >= 0} if isinstance(usage, dict) else None
    return GenerationResponse(
        text=text,
        model_id=data.get("model") if isinstance(data.get("model"), str) else None,
        response_id=data.get("id") if isinstance(data.get("id"), str) else None,
        finish_reason=choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None,
        usage=safe_usage,
        metadata={k: data[k] for k in ("provider",) if isinstance(data.get(k), str)},
    )
