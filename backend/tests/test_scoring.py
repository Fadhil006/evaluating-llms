import json
from pathlib import Path

import pytest

from app.evaluation.scoring import SCORER_VERSION, classification_macro_f1, score


def scored(task, text, refs, **config):
    return score(task, text, refs, config)


def test_original_dataset_configurations_and_perfect_references():
    path = Path(__file__).resolve().parents[2] / "datasets/original_demo_v1.jsonl"
    for line in path.read_text().splitlines():
        item = json.loads(line)
        ref = item["reference_answers"][0]
        text = ref if isinstance(ref, str) else json.dumps(ref)
        result = score(item["task_type"], text, item["reference_answers"], item["scoring_config"])
        assert result["parse_status"] == "valid", item["id"]
        assert result["raw_answer"] == text
        assert all(value == 1 for key, value in result["metrics"].items()
                   if key != "checks_passed"), item["id"]
        assert result["scorer_version"] == SCORER_VERSION


def test_choice_single_final_and_ambiguous_labels():
    config = {"metric": "label_accuracy", "labels": ["A", "B", "C"]}
    assert scored("multiple_choice", "A", ["A"], **config)["metrics"]["label_accuracy"] == 1
    wrong = scored("multiple_choice", "Answer: B", ["A"], **config)
    assert (wrong["parse_status"], wrong["metrics"]["label_accuracy"]) == ("valid", 0)
    assert scored("multiple_choice", "Reasoning here\nAnswer: C", ["C"], **config)["parse_status"] == "valid"
    for text in ("A or B", "A\nAnswer: B", "Answer: A\nAnswer: B", "D", "A B", "A\nB", " "):
        result = scored("multiple_choice", text, ["A"], **config)
        assert result["parse_status"] == "unparseable"
        assert result["metrics"]["label_accuracy"] == 0


def test_exact_normalization_keeps_punctuation_and_no_substrings():
    config = {"metric": "normalized_exact_match",
              "normalization": "unicode_nfc_casefold_trim_collapse_whitespace"}
    result = scored("short_factual", "  CAFE\u0301   AU   LAIT  ", ["café au lait", "coffee"], **config)
    assert result["metrics"] == {"raw_exact_match": 0, "normalized_exact_match": 1}
    assert result["normalized_answer"] == "café au lait"
    assert scored("short_factual", "coffee!", ["coffee"], **config)["metrics"]["normalized_exact_match"] == 0
    assert scored("short_factual", "strong coffee", ["coffee"], **config)["metrics"]["normalized_exact_match"] == 0


def test_multiset_f1_and_no_overlap():
    config = {"metric": "token_f1", "tokenizer": "unicode_word_casefold"}
    result = scored("extractive_qa", "cat cat dog", ["cat dog", "bird"], **config)
    assert result["metrics"]["token_f1"] == pytest.approx(4 / 5)
    assert scored("extractive_qa", "bird", ["cat"], **config)["metrics"]["token_f1"] == 0
    assert scored("extractive_qa", "!!!", ["???"], **config)["metrics"]["token_f1"] == 1


def test_decimal_numeric_tolerances_units_and_ambiguity():
    config = {"metric": "numeric_exact", "absolute_tolerance": "0.01",
              "relative_tolerance": "0.1", "units": "none"}
    for text, ref in (("-1.01", "-1"), ("1e2", "100"), ("Answer: .99", "1")):
        assert scored("arithmetic", text, [ref], **config)["metrics"]["numeric_exact"] == 1
    assert scored("arithmetic", "0.02", ["0"], **config)["metrics"]["numeric_exact"] == 0
    for text in ("1 or 2", "1 km", "NaN", "Infinity", "Answer: 1\nAnswer: 2", "1 2"):
        assert scored("arithmetic", text, ["1"], **config)["parse_status"] == "unparseable"
    with pytest.raises(ValueError, match="units"):
        scored("arithmetic", "1", ["1"], **(config | {"units": "km"}))


def test_classification_macro_f1_declared_classes_and_invalid_prediction():
    config = {"metric": "label_accuracy", "labels": ["cat", "dog", "bird"]}
    rows = [(truth, scored("classification", pred, [truth], **config))
            for truth, pred in (("cat", "cat"), ("cat", "dog"), ("dog", "dog"),
                                ("bird", "unknown"))]
    # cat: 2/3, dog: 2/3, bird: 0; average = 4/9.
    assert classification_macro_f1(rows, config["labels"]) == pytest.approx(4 / 9)
    assert classification_macro_f1([], config["labels"]) is None
    assert classification_macro_f1([("bird", score("classification", None, ["bird"], config))],
                                   config["labels"]) is None


def test_json_syntax_schema_fields_and_duplicate_keys():
    config = {"metric": "json_exact_fields", "schema": {"type": "object",
              "required": ["count", "ready"], "additionalProperties": False,
              "properties": {"count": {"type": "integer"}, "ready": {"type": "boolean"}}}}
    refs = [{"count": 3, "ready": True}]
    assert scored("structured_extraction", '{"count":3,"ready":false}', refs, **config)["metrics"] == {
        "json_valid": 1, "schema_valid": 1, "field_exact": 0}
    for text in ('{"count":3,', '{"count":1,"count":3,"ready":true}',
                 '{"count":NaN,"ready":true}', '{"count":1e999,"ready":true}'):
        result = scored("structured_extraction", text, refs, **config)
        assert result["parse_status"] == "malformed_json"
        assert result["metrics"] == {"json_valid": 0, "schema_valid": 0, "field_exact": 0}
    for text in ('{"count":true,"ready":true}', '{"count":3}',
                 '{"count":3,"ready":true,"extra":0}', '{"count":null,"ready":true}',
                 '[3,true]'):
        result = scored("structured_extraction", text, refs, **config)
        assert result["parse_status"] == "invalid_schema"
        assert result["metrics"] == {"json_valid": 1, "schema_valid": 0, "field_exact": 0}
    assert scored("structured_extraction", json.dumps(refs[0]), refs, **config)["metrics"]["field_exact"] == 1


def test_rouge_l_is_ordered_overlap_not_factuality():
    config = {"metric": "rouge_l_f1", "tokenizer": "unicode_word_casefold",
              "reference_aggregation": "max"}
    result = scored("summarization", "a c b", ["a b c", "x y"], **config)
    assert result["metrics"]["rouge_l_f1"] == pytest.approx(2 / 3)
    assert scored("summarization", "!!!", ["???"], **config)["metrics"]["rouge_l_f1"] == 1
    assert scored("summarization", "zero", ["one"], **config)["metrics"]["rouge_l_f1"] == 0


def test_instruction_checks_partial_exact_and_json():
    config = {"metric": "instruction_checks", "checks": [
        {"type": "exact_text", "value": "hello"},
        {"type": "json_exact", "value": {"ready": True}}]}
    result = scored("instruction_following", "hello", ["hello"], **config)
    assert result["parse_status"] == "malformed_json"
    assert result["metrics"] == {"instruction_checks": 0.5, "checks_passed": 1}
    assert scored("instruction_following", '{"ready":1}', [], **config)["metrics"]["checks_passed"] == 0
    assert scored("instruction_following", '{"ready":true}', [], **config)["metrics"]["checks_passed"] == 1
    assert scored("instruction_following", "hello\n", ["hello"],
                  metric="instruction_checks", checks=[config["checks"][0]])["metrics"]["instruction_checks"] == 0


def test_missing_truncated_and_completed_format_failures_are_distinct():
    config = {"metric": "label_accuracy", "labels": ["A", "B"]}
    missing = score("multiple_choice", None, ["A"], config)
    truncated = score("multiple_choice", "A", ["A"], config, truncated=True)
    bad = score("multiple_choice", "unknown", ["A"], config)
    assert [r["parse_status"] for r in (missing, truncated, bad)] == [
        "missing", "truncated", "unparseable"]
    assert [r["metrics"]["label_accuracy"] for r in (missing, truncated, bad)] == [None, None, 0]
    assert truncated["raw_answer"] == "A"
