"""Load and validate authored evaluation items (no model outputs are inspected)."""

import ast
import json
import math
from decimal import Decimal, InvalidOperation
from collections import defaultdict


CATEGORIES = {"reasoning", "math", "coding", "knowledge", "summarization", "instruction"}
SCORERS = {
    "reasoning": {"mcq"},
    "math": {"numeric"},
    "coding": {"code_syntax"},
    "knowledge": {"mcq", "short_answer"},
    "summarization": {"summary_constraints"},
    "instruction": {"instruction_rules"},
}
RULE_KEYS = {
    "mcq": set(),
    "numeric": {"tolerance"},
    "code_syntax": {"function_name", "parameters"},
    "short_answer": {"accepted_answers"},
    "summary_constraints": {"min_words", "max_words", "required_terms"},
    "instruction_rules": {"required_keys", "required_json_values", "forbidden_strings", "bullet_count"},
}
FIELDS = {"id", "pair_id", "variant", "split", "category", "scorer", "prompt",
          "reference_answer", "rules", "dataset_version", "source"}


def _reject_constant(value):
    raise ValueError(f"nonstandard JSON constant {value}")


def validate_dataset(items: list[dict]) -> None:
    """Raise ValueError for invalid items or incomplete/inconsistent pairs."""
    if not isinstance(items, list) or not items:
        raise ValueError("dataset must be a nonempty list")
    ids, prompts, pairs = set(), set(), defaultdict(dict)
    versions = set()
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"item {index}: expected object")
        missing = FIELDS - item.keys()
        if missing:
            raise ValueError(f"item {index}: missing fields {sorted(missing)}")
        for field in FIELDS - {"rules"}:
            if not isinstance(item[field], str) or not item[field].strip():
                raise ValueError(f"item {index}: {field} must be a nonempty string")
        if not isinstance(item["rules"], dict):
            raise ValueError(f"item {index}: rules must be an object")
        category, scorer, rules = item["category"], item["scorer"], item["rules"]
        if category not in CATEGORIES or scorer not in SCORERS[category]:
            raise ValueError(f"item {index}: unknown category/scorer combination")
        if item["split"] not in {"test", "dev"} or item["variant"] not in {"original", "paraphrase"}:
            raise ValueError(f"item {index}: invalid split or variant")
        if rules.keys() - RULE_KEYS[scorer]:
            raise ValueError(f"item {index}: unknown rules {sorted(rules.keys() - RULE_KEYS[scorer])}")
        if scorer == "mcq" and item["reference_answer"] not in {"A", "B", "C", "D"}:
            raise ValueError(f"item {index}: invalid MCQ reference")
        if scorer == "numeric":
            tolerance = rules.get("tolerance", 0.0001)
            if (type(tolerance) not in (int, float) or not Decimal(str(tolerance)).is_finite()
                    or tolerance < 0):
                raise ValueError(f"item {index}: invalid numeric tolerance")
        if scorer == "numeric":
            try:
                reference = Decimal(item["reference_answer"])
                if not reference.is_finite() or not math.isfinite(float(reference)):
                    raise ValueError
            except (ValueError, InvalidOperation) as exc:
                raise ValueError(f"item {index}: invalid numeric reference") from exc
        if scorer == "code_syntax" and (not isinstance(rules.get("function_name"), str)
                                        or not rules["function_name"]
                                        or not isinstance(rules.get("parameters"), list)
                                        or any(not isinstance(p, str) or not p for p in rules["parameters"])):
            raise ValueError(f"item {index}: invalid code signature rules")
        if scorer == "short_answer" and (not isinstance(rules.get("accepted_answers"), list)
                                         or not rules["accepted_answers"]
                                         or any(not isinstance(a, str) or not a.strip()
                                                for a in rules["accepted_answers"])):
            raise ValueError(f"item {index}: invalid accepted answers")
        if scorer == "short_answer" and item["reference_answer"].strip().casefold() not in {
                answer.strip().casefold() for answer in rules["accepted_answers"]}:
            raise ValueError(f"item {index}: reference missing from accepted answers")
        if scorer == "summary_constraints" and (type(rules.get("min_words")) is not int
                                                or type(rules.get("max_words")) is not int
                                                or not 0 <= rules["min_words"] <= rules["max_words"]
                                                or not isinstance(rules.get("required_terms"), list)
                                                or not rules["required_terms"]):
            raise ValueError(f"item {index}: invalid summary rules")
        if scorer == "instruction_rules" and not (rules.get("required_keys") or rules.get("required_json_values")
                                                   or rules.get("forbidden_strings") or "bullet_count" in rules):
            raise ValueError(f"item {index}: instruction rules need an effective check")
        if "required_json_values" in rules and (
                not isinstance(rules["required_json_values"], dict)
                or not rules["required_json_values"]
                or any(not isinstance(key, str) or not key.strip()
                       or not isinstance(value, str) or not value.strip()
                       for key, value in rules["required_json_values"].items())):
            raise ValueError(f"item {index}: invalid required_json_values")
        for key in ("required_terms", "required_keys", "forbidden_strings"):
            if key in rules and (not isinstance(rules[key], list)
                                 or any(not isinstance(v, str) or not v.strip() for v in rules[key])):
                raise ValueError(f"item {index}: invalid {key}")
        if "bullet_count" in rules and (type(rules["bullet_count"]) is not int or rules["bullet_count"] < 0):
            raise ValueError(f"item {index}: invalid bullet count")
        if scorer == "code_syntax":
            try:
                tree = ast.parse(item["reference_answer"])
            except SyntaxError as exc:
                raise ValueError(f"item {index}: invalid Python reference") from exc
            if not any(isinstance(node, ast.FunctionDef) and node.name == rules["function_name"]
                       and [arg.arg for arg in node.args.args] == rules["parameters"]
                       for node in tree.body):
                raise ValueError(f"item {index}: reference signature mismatch")
        if item["id"] in ids:
            raise ValueError(f"item {index}: duplicate id")
        ids.add(item["id"])
        prompt_key = " ".join(item["prompt"].split()).casefold()
        if prompt_key in prompts:
            raise ValueError(f"item {index}: duplicate prompt")
        prompts.add(prompt_key)
        pair = pairs[item["pair_id"]]
        if item["variant"] in pair:
            raise ValueError(f"item {index}: duplicate pair variant")
        pair[item["variant"]] = item
        versions.add(item["dataset_version"])
    if len(versions) != 1:
        raise ValueError("mixed dataset versions")
    for pair_id, pair in pairs.items():
        if set(pair) != {"original", "paraphrase"}:
            raise ValueError(f"pair {pair_id}: expected original and paraphrase")
        original, variant = pair["original"], pair["paraphrase"]
        for field in ("split", "category", "scorer", "reference_answer", "rules", "source"):
            if original[field] != variant[field]:
                raise ValueError(f"pair {pair_id}: inconsistent {field} (or split leakage)")


def load_dataset(path) -> list[dict]:
    """Read UTF-8 JSONL and validate the entire dataset before returning it."""
    items = []
    with open(path, encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line, parse_constant=_reject_constant))
            except ValueError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
    validate_dataset(items)
    return items


def select_pairs(items: list[dict], pair_ids=None) -> list[dict]:
    """Select complete base pairs, preserving dataset order; None selects all."""
    validate_dataset(items)
    if pair_ids is None:
        return items
    if (not isinstance(pair_ids, (list, tuple)) or not pair_ids or
            any(not isinstance(pair_id, str) or not pair_id.strip() for pair_id in pair_ids) or
            len(pair_ids) != len(set(pair_ids))):
        raise ValueError("pair_ids must be a nonempty sequence of unique pair IDs")
    available = {item["pair_id"] for item in items}
    if not set(pair_ids) <= available:
        raise ValueError(f"unknown pair IDs: {sorted(set(pair_ids) - available)}")
    selected = [item for item in items if item["pair_id"] in pair_ids]
    validate_dataset(selected)
    if len({item["split"] for item in selected}) != 1:
        raise ValueError("selected pairs must belong to one split")
    return selected
