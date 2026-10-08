"""Dated Zen free-price evidence checked against the official pricing/endpoint tables."""

from datetime import UTC, date, datetime, time

ZEN_PRICING_SOURCE = "https://opencode.ai/docs/zen/"
ZEN_PRICING_CHECKED_ON = date(2026, 10, 8)
ZEN_PRICING_EXPIRES_ON = date(2026, 10, 15)
ZEN_PRICING_EXPIRES_AT = datetime.combine(ZEN_PRICING_EXPIRES_ON, time.min, UTC)

# Each exact ID is named in the official pricing table with free input/output/cached-read
# prices and in the endpoint table with chat-completions. Cached-write is explicitly “—”.
CHAT_FREE_IDS = frozenset({
    "big-pickle",
    "space-bunny-free",
    "longcat-2.5-preview-free",
    "exo-free",
    "fledge-alpha-free",
    "mimo-v2.6-flash-free",
    "mimo-v2.5-free",
    "ling-3.1-flash-free",
    "ling-3.0-flash-fin-free",
    "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
})


def evidence(model_id: str) -> dict:
    if model_id not in CHAT_FREE_IDS:
        return {}
    return {
        "prompt": "0",
        "completion": "0",
        "input_cache_read": "0",
        "official_pricing": {"input": "Free", "output": "Free",
                             "cached_read": "Free", "cached_write": "—"},
        "source": ZEN_PRICING_SOURCE,
        "checked_on": ZEN_PRICING_CHECKED_ON.isoformat(),
        "expires_on": ZEN_PRICING_EXPIRES_ON.isoformat(),
    }
