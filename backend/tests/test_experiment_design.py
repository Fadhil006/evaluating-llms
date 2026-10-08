import json
from pathlib import Path

import pytest

from app.services.experiment_design import (
    common_settings,
    estimate_requests,
    generation_messages,
    select_items,
)


def test_balanced_deterministic_selection_preserves_source_order():
    path = Path(__file__).resolve().parents[2] / "datasets/original_demo_v1.jsonl"
    items = [json.loads(line) for line in path.read_text().splitlines()]
    design = select_items(items, seed=3)
    assert design == select_items(items, seed=3)
    assert len(design["item_ids"]) == 10
    assert sorted(design["category_counts"].values()) == [1, 1, 2, 2, 2, 2]
    assert design["item_ids"] == [item["id"] for item in items if item["id"] in design["item_ids"]]
    assert len({tuple(select_items(items, seed=seed)["category_counts"].items()) for seed in range(20)}) > 1
    assert len(select_items(items[:3], seed=3)["item_ids"]) == 3
    with pytest.raises(ValueError, match="distinct"):
        select_items([items[0], items[0]], seed=3)


def test_uneven_inventory_redistributes_and_keeps_stable_order():
    items = [{"id": str(i), "task_type": "rare" if i == 0 else "common"} for i in range(12)]
    result = select_items(items, seed=7)
    assert result["category_counts"] == {"rare": 1, "common": 9}
    assert result["item_ids"] == [str(i) for i in range(12) if str(i) in result["item_ids"]]


def test_messages_never_include_hidden_evaluation_fields():
    item = {"prompt": "Choose one", "context": "Visible context", "choices": ["A. yes", "B. no"],
            "reference_answers": ["SECRET_REFERENCE_1"],
            "scoring_config": {"schema": "SECRET_CONFIG_2"}, "tags": ["SECRET_TAG_3"]}
    messages = generation_messages("Shared instruction", item, {"type": "object", "name": "visible"})
    assert messages[0] == ("system", "Shared instruction")
    assert messages[1][0] == "user"
    assert all(part in messages[1][1] for part in ("Choose one", "Visible context", "A. yes", "B. no", "visible"))
    assert not any(secret in str(messages) for secret in ("SECRET_REFERENCE_1", "SECRET_CONFIG_2", "SECRET_TAG_3"))
    assert generation_messages("System", {"prompt": "Hello"}) == (("system", "System"), ("user", "Hello"))


def test_budget_cap_and_separate_metadata():
    result = estimate_requests(3, 10, 1, 2, 40, metadata_startup=3, metadata_refresh=2)
    assert result == {"initial_candidate_requests": 30, "maximum_candidate_retries": 10,
                      "unconstrained_maximum_attempts": 90, "maximum_attempts": 40,
                      "metadata_startup": 3, "metadata_refresh": 2}
    assert estimate_requests(2, 4, 3, 0, 100)["maximum_attempts"] == 24
    with pytest.raises(ValueError, match="cap"):
        estimate_requests(3, 10, 1, 2, 29)


def test_distinct_routes_and_common_requested_settings():
    routes = [("gateway_a", "model", ("max_tokens", "temperature", "seed")),
              ("gateway_b", "model", ("max_tokens", "temperature"))]
    assert common_settings(routes, ("temperature",)) == {"max_tokens", "temperature"}
    with pytest.raises(ValueError, match="seed"):
        common_settings(routes, ("seed",))
    with pytest.raises(ValueError, match="distinct"):
        common_settings([routes[0], routes[0]])
    with pytest.raises(ValueError, match="max_tokens"):
        common_settings([routes[0], ("gateway_c", "other", ())])
