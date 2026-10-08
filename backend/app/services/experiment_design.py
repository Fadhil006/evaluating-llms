"""Pure selection, prompt construction, and candidate-request estimates."""

import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Literal


def select_items(items: Sequence[Mapping], seed: int, limit: int = 10) -> dict:
    """Allocate slots evenly, rotate leftover slots by seed, preserve source order."""
    if not 0 <= limit <= 10:
        raise ValueError("limit must be between 0 and 10")
    ids = [item["id"] for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("item IDs must be distinct")
    groups: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        groups.setdefault(item["task_type"], []).append(index)
    rng = random.Random(seed)
    categories = list(groups)
    rng.shuffle(categories)
    quota = dict.fromkeys(categories, 0)
    remaining = min(limit, len(items))
    while remaining:
        for category in categories:
            if remaining and quota[category] < len(groups[category]):
                quota[category] += 1
                remaining -= 1
    selected = sorted(index for category in categories
                      for index in rng.sample(groups[category], quota[category]))
    return {"seed": seed, "item_ids": [ids[index] for index in selected],
            "category_counts": dict(Counter(items[index]["task_type"] for index in selected))}


def generation_messages(system_prompt: str, item: Mapping, public_task_schema: dict | None = None
                        ) -> tuple[tuple[Literal["system", "user"], str], ...]:
    """Explicit allowlist: evaluation-only item fields never enter the request."""
    sections = [item["prompt"]]
    if item.get("context"):
        sections.append(f"Context:\n{item['context']}")
    if item.get("choices"):
        sections.append("Choices:\n" + "\n".join(item["choices"]))
    if public_task_schema is not None:
        sections.append("Public task schema:\n" + json.dumps(public_task_schema, ensure_ascii=False, sort_keys=True))
    return (("system", system_prompt), ("user", "\n\n".join(sections)))


def estimate_requests(models: int, items: int, repetitions: int, retries: int,
                      attempt_cap: int, *, metadata_startup: int = 0,
                      metadata_refresh: int = 0) -> dict:
    values = (models, items, repetitions, retries, attempt_cap, metadata_startup, metadata_refresh)
    if any(type(value) is not int or value < 0 for value in values) or models < 2 or not items or not repetitions:
        raise ValueError("expected >=2 models, positive items/repetitions and nonnegative counts")
    initial = models * items * repetitions
    if attempt_cap < initial:
        raise ValueError("attempt cap cannot cover initial candidate requests")
    maximum = min(initial * (1 + retries), attempt_cap)
    return {"initial_candidate_requests": initial,
            "maximum_candidate_retries": maximum - initial,
            "unconstrained_maximum_attempts": initial * (1 + retries),
            "maximum_attempts": maximum,
            "metadata_startup": metadata_startup, "metadata_refresh": metadata_refresh}


def common_settings(routes: Sequence[tuple[str, str, Sequence[str]]],
                    requested: Sequence[str] = ()) -> set[str]:
    """Validate distinct gateway/model routes and requested shared parameters."""
    identities = [(gateway, model) for gateway, model, _ in routes]
    if len(routes) < 2 or len(set(identities)) != len(routes) or any(not all(identity) for identity in identities):
        raise ValueError("at least two distinct gateway/model routes are required")
    common = set.intersection(*(set(parameters) for _, _, parameters in routes))
    missing = {"max_tokens", *requested} - common
    if missing:
        raise ValueError("unsupported shared settings: " + ", ".join(sorted(missing)))
    return common
