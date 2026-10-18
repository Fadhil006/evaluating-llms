import json
from collections import Counter, defaultdict
from pathlib import Path

from app.evaluation.scoring import score
from app.services.datasets import parse, preview, validate

DATASET = Path(__file__).resolve().parents[2] / "datasets/instruction_following_draft_v1.jsonl"


def test_draft_dataset_import_and_family_contract():
    data = DATASET.read_bytes()
    rows = parse(data, "jsonl")
    result = validate(rows)
    inspected = preview(data, "jsonl")
    assert inspected["row_count"] == 10
    assert inspected["duplicate_content"] == []
    assert result["duplicate_content"] == []
    assert Counter(item["split"] for item in result["items"]) == {"dev": 10}
    families = defaultdict(list)
    for item in result["items"]:
        assert item["review_status"] == "draft"
        assert item["provenance"]["origin"] == "project-authored draft; not independently reviewed"
        families[item["family_id"]].append(item)
    assert len(families) == 5
    for family_id, items in families.items():
        assert family_id.startswith("evaluating-llms-2.0:instruction-draft-v1:dev-")
        assert {item["variant_id"] for item in items} == {"original", "wording-variant"}
        assert len({item["prompt"].casefold() for item in items}) == 2
        assert len({json.dumps(item["scoring_config"], sort_keys=True) for item in items}) == 1
        assert len({json.dumps(item["reference_answers"], sort_keys=True) for item in items}) == 1
        assert all(item["split"] == "dev" for item in items)
        assert {item["review_status"] for item in items} == {"draft"}


def test_instruction_check_answer_boundaries():
    config = {"metric": "instruction_checks", "checks": [
        {"type": "required_substring", "value": "blue cedar"},
        {"type": "forbidden_substring", "value": "!"},
        {"type": "exact_word_count", "value": 2},
    ]}
    assert score("instruction_following", "BLUE CEDAR", [], config)["metrics"]["instruction_all_checks"] == 1.0
    result = score("instruction_following", "blue cedar! extra", [], config)
    assert result["metrics"]["instruction_all_checks"] == 0.0
    assert result["metrics"]["instruction_pooled_passed"] == 1
    assert result["metrics"]["instruction_pooled_total"] == 3


def test_instruction_check_exact_reference_and_word_count_boundaries():
    config = {"metric": "instruction_checks", "checks": [
        {"type": "exact_text", "value": "north; east"},
        {"type": "required_substring", "value": "east"},
        {"type": "forbidden_substring", "value": "west"},
        {"type": "exact_word_count", "value": 2},
    ]}
    assert score("instruction_following", "north; east", ["different frozen reference"], config)["metrics"][
        "instruction_all_checks"] == 1.0
    for answer in ("North; east", "north; east ", "north east", "north; east west"):
        result = score("instruction_following", answer, ["north; east"], config)
        assert result["metrics"]["instruction_all_checks"] == 0.0
        assert len(result["check_evidence"]) == 4
