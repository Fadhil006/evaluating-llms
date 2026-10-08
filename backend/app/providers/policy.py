"""A zero price is evidence, not a model-name convention."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from app.providers.common import CatalogEntry, GenerationRequest
from app.providers.zen_pricing import ZEN_PRICING_EXPIRES_AT, ZEN_PRICING_SOURCE
from app.providers.zen_pricing import evidence as zen_evidence

FRESH_FOR = timedelta(minutes=15)
REQUIRED = {"prompt", "completion"}
PRICE_FIELDS = REQUIRED | {
    "request", "input_cache_read", "input_cache_write", "input_cache_write_1h", "internal_reasoning",
    "image", "image_output", "image_token", "audio", "audio_output", "input_audio", "input_audio_cache",
    "output_audio", "web_search",
}
TEXT_CHARGE_FIELDS = {"request", "input_cache_read", "input_cache_write", "input_cache_write_1h", "internal_reasoning"}
OVERRIDE_CONDITIONS = {"min_prompt_tokens", "utc_days", "utc_start", "utc_end"}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    checked_at: datetime | None
    model_id: str

    def evidence(self) -> dict:
        return {"allowed": self.allowed, "reason": self.reason, "checked_at": self.checked_at.isoformat() if self.checked_at else None, "model_id": self.model_id}


def zero(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        number = Decimal(value)
        return number.is_finite() and number == 0
    except InvalidOperation:
        return False


def decide(slug: str, entry: CatalogEntry, checked_at: datetime | None, now: datetime, request: GenerationRequest | None = None) -> Decision:
    def blocked(reason: str) -> Decision:
        return Decision(False, reason, checked_at, entry.model_id)

    if not entry.model_id or entry.model_id == "openrouter/free" or entry.model_id.endswith("/auto"):
        return blocked("unstable_identity")
    if entry.endpoint != "chat/completions":
        return blocked("unsupported_endpoint")
    if not entry.available:
        return blocked("unavailable")
    if checked_at is None or checked_at.tzinfo is None or not (timedelta(0) <= now - checked_at <= FRESH_FOR):
        return blocked("stale_pricing")
    if request is not None:
        if request.model_id != entry.model_id or not request.messages or any(role not in ("system", "user") or not isinstance(text, str) for role, text in request.messages) or not 1 <= request.max_tokens <= 4096:
            return blocked("invalid_request")
        if request.temperature is not None and "temperature" not in entry.supported_parameters:
            return blocked("unsupported_parameter")
        if request.seed is not None and "seed" not in entry.supported_parameters:
            return blocked("unsupported_parameter")
        if "max_tokens" not in entry.supported_parameters:
            return blocked("unsupported_parameter")
    if slug == "opencode_zen":
        # Zen doesn't publish prices from /models; this exact-ID official doc allowlist
        # expires after seven days and is rechecked on every start/resume/dispatch.
        if (entry.endpoint != "chat/completions" or not zen_evidence(entry.model_id)
                or entry.pricing_source != ZEN_PRICING_SOURCE
                or entry.pricing != zen_evidence(entry.model_id)):
            return blocked("official_price_evidence_required")
        if now >= ZEN_PRICING_EXPIRES_AT or (entry.pricing_expires_at is not None
                                             and now >= entry.pricing_expires_at.replace(tzinfo=UTC)):
            return blocked("stale_pricing")
        return Decision(True, "verified_zero_allowlist", checked_at, entry.model_id)
    if slug != "openrouter":
        return blocked("unknown_provider")
    prices = entry.pricing
    if not isinstance(prices, dict):
        return blocked("unknown_pricing")
    if set(prices) - PRICE_FIELDS - {"overrides"}:
        return blocked("unknown_pricing")
    # Prompt/completion must be explicit zero. OpenRouter marks additional
    # pricing SKUs optional; absent means the catalog publishes no such SKU for
    # this route. Any listed request/cache/reasoning charge can affect text-only
    # calls and therefore must also be explicitly zero. Modalities/plugins we do
    # not send are not part of this request's cost decision.
    if not entry.is_free and not REQUIRED <= prices.keys():
        return blocked("unknown_pricing")
    if not entry.is_free and not all(zero(prices[k]) for k in REQUIRED):
        return blocked("nonzero_or_invalid_pricing")
    if any(key in prices and not zero(prices[key]) for key in TEXT_CHARGE_FIELDS):
        return blocked("nonzero_or_invalid_pricing")
    if entry.is_free and any(key in prices and not zero(prices[key]) for key in REQUIRED):
        return blocked("nonzero_or_invalid_pricing")
    overrides = prices.get("overrides", [])
    if not isinstance(overrides, list):
        return blocked("conditional_pricing")
    if any(not isinstance(tier, dict) or set(tier) - PRICE_FIELDS - OVERRIDE_CONDITIONS
           for tier in overrides):
        return blocked("conditional_pricing")
    if any(any(key in tier and not zero(tier[key]) for key in REQUIRED | TEXT_CHARGE_FIELDS)
           for tier in overrides):
        return blocked("conditional_pricing")
    return Decision(True, "verified_zero", checked_at, entry.model_id)


def require_free(slug: str, entry: CatalogEntry, checked_at: datetime, request: GenerationRequest) -> Decision:
    decision = decide(slug, entry, checked_at, datetime.now(UTC), request)
    if not decision.allowed:
        from app.providers.common import ProviderError

        raise ProviderError(decision.reason)
    return decision
