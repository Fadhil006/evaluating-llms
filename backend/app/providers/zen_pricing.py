"""Short-lived free-price evidence checked against OpenCode's current official model page."""

from datetime import UTC, date, datetime, time

ZEN_PRICING_SOURCE = "https://opencode.ai/v2/docs/console/models/"
ZEN_PRICING_CHECKED_ON = date(2026, 10, 21)
ZEN_PRICING_EXPIRES_ON = date(2026, 10, 22)
ZEN_PRICING_EXPIRES_AT = datetime.combine(ZEN_PRICING_EXPIRES_ON, time.min, UTC)

# Each exact ID is listed as free and uses the documented OpenAI chat endpoint.
# Jev is free but uses SystemOne, so it is deliberately excluded from chat pricing evidence.
CHAT_FREE_IDS = frozenset({
    "big-pickle",
    "glm-5.3-flash-free",
    "deepseek-v4.1-flash-free",
    "minimax-m3.1-flash-free",
    "beam-free",
    "ll-alpha-free",
    "longcat-2.5-preview-free",
    "exo-free",
    "mimo-v2.6-flash-free",
    "mimo-v2.5-free",
    "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
    "nemotron-3.5-super-vl-free",
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
