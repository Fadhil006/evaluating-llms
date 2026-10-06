"""Deterministic offline checks; review results are not correctness scores.

Rule keys: mcq uses a reference letter A-D; numeric uses tolerance
(default 1e-4); short_answer uses accepted_answers (strings).
instruction_rules uses required_keys, required_json_values (exact strings),
forbidden_strings, bullet_count.
summary_constraints uses min_words, max_words, required_terms.
code_syntax uses function_name and parameters (positional argument names).
All rule values are declared on the item, never inferred from model output.
"""

import ast
import json
import math
import re
from decimal import Decimal, DecimalException

from evaluation.dataset import _reject_constant


_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _result(correct, status, explanation, checks=None):
    return {"correct": correct, "status": status, "explanation": explanation,
            "checks": checks if checks is not None else {}}


def score(item: dict, answer: str) -> dict:
    """Check one answer without importing or executing any generated content."""
    if not isinstance(item, dict) or not isinstance(answer, str) or not answer.strip():
        return _result(None, "invalid", "Missing or malformed answer/item.")
    rules = item.get("rules", {})
    if not isinstance(rules, dict):
        return _result(None, "invalid", "Rules must be an object.")
    kind = item.get("scorer")

    if kind == "mcq":
        reference = item.get("reference_answer")
        if not isinstance(reference, str) or reference.upper() not in "ABCD" or len(reference) != 1:
            return _result(None, "invalid", "Invalid MCQ reference choice.")
        # Only a bare letter or a single explicitly labeled choice is safe to extract.
        match = re.fullmatch(r"\s*(?:(?:answer|choice)\s*:\s*)?([A-D])\s*[.)]?\s*", answer, re.I)
        if not match:
            return _result(None, "invalid", "Expected exactly one unambiguous A-D choice.")
        choice = match.group(1).upper()
        return _result(choice == reference.upper(), "scored", "Single choice compared to reference.",
                       {"choice": choice})

    if kind == "numeric":
        declared_tolerance = rules.get("tolerance", 1e-4)
        if type(declared_tolerance) not in (int, float):
            return _result(None, "invalid", "Invalid numeric reference or tolerance.")
        try:
            tolerance = Decimal(str(declared_tolerance))
            reference = Decimal(item["reference_answer"])
        except (KeyError, ValueError, TypeError, DecimalException):
            return _result(None, "invalid", "Invalid numeric reference or tolerance.")
        if not reference.is_finite() or not math.isfinite(float(reference)) or not tolerance.is_finite() or tolerance < 0:
            return _result(None, "invalid", "Reference and tolerance must be finite; tolerance nonnegative.")
        text = re.sub(r"^\s*final\s+answer\s*:\s*", "", answer, flags=re.I).strip()
        match = _NUMBER.fullmatch(text)
        if not match:
            if text.casefold() in {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"} or len(_NUMBER.findall(text)) > 1:
                return _result(None, "invalid", "Expected one finite final number, with no extra values or text.")
            if re.search(r"[a-zA-Z%]", text):
                return _result(None, "review", "Units or other text have no declared normalization rule.")
            return _result(None, "invalid", "Expected one finite final number, with no extra values or text.")
        try:
            value = Decimal(text)
            if not value.is_finite() or not math.isfinite(float(value)):
                return _result(None, "invalid", "Non-finite numeric answer.")
            passed = abs(value - reference) <= tolerance
        except DecimalException:
            return _result(None, "invalid", "Numeric answer is outside supported comparison range.")
        # Keep ordinary check values numeric without rounding large answers.
        reported_value = float(value) if abs(value) <= 2**53 else str(value)
        try:
            reported_tolerance = float(tolerance)
        except OverflowError:
            reported_tolerance = str(tolerance)
        if reported_tolerance == float("inf"):
            reported_tolerance = str(tolerance)
        return _result(passed, "scored", "Absolute numeric difference compared to declared tolerance.",
                       {"value": reported_value, "tolerance": reported_tolerance, "within_tolerance": passed})

    if kind == "short_answer":
        reference = item.get("reference_answer")
        accepted = rules.get("accepted_answers")
        if not isinstance(reference, str) or not reference.strip() or not isinstance(accepted, list) or any(
            not isinstance(x, str) or not x.strip() for x in accepted
        ):
            return _result(None, "invalid", "Invalid short-answer reference or accepted answers.")
        normalize = lambda text: " ".join(text.split()).casefold()
        passed = normalize(answer) in {normalize(x) for x in [reference, *accepted]}
        return _result(passed, "scored", "Case/whitespace exact match; equivalence beyond declared forms needs review.",
                       {"accepted_form": passed})

    if kind == "instruction_rules":
        allowed = {"required_keys", "required_json_values", "forbidden_strings", "bullet_count"}
        if not rules or set(rules) - allowed:
            return _result(None, "invalid", "Missing or unsupported instruction rules.")
        keys = rules.get("required_keys", [])
        values = rules.get("required_json_values", {})
        forbidden = rules.get("forbidden_strings", [])
        bullets = rules.get("bullet_count")
        if (not isinstance(keys, list) or any(not isinstance(x, str) or not x for x in keys)
                or not isinstance(values, dict) or any(not isinstance(k, str) or not k.strip()
                                                         or not isinstance(v, str) or not v.strip()
                                                         for k, v in values.items())
                or not isinstance(forbidden, list) or any(not isinstance(x, str) or not x for x in forbidden)
                or ("bullet_count" in rules and (type(bullets) is not int or bullets < 0))):
            return _result(None, "invalid", "Malformed instruction rules.")
        if not (keys or values or forbidden or "bullet_count" in rules):
            return _result(None, "invalid", "Instruction rules need an effective check.")
        checks = {}
        if "required_keys" in rules or "required_json_values" in rules:
            try:
                parsed = json.loads(answer, parse_constant=_reject_constant)
            except ValueError:
                parsed = None
            checks["valid_json_object"] = isinstance(parsed, dict)
            for key in keys:
                checks[f"required_key:{key}"] = isinstance(parsed, dict) and key in parsed
            for key, expected in values.items():
                checks[f"required_json_value:{key}"] = isinstance(parsed, dict) and parsed.get(key) == expected
        if "forbidden_strings" in rules:
            for text in forbidden:
                checks[f"forbidden_string:{text}"] = text.casefold() not in answer.casefold()
        if "bullet_count" in rules:
            checks["bullet_count"] = sum(bool(re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line))
                                         for line in answer.splitlines()) == bullets
        passed = all(checks.values())
        checks["fraction_passed"] = sum(checks.values()) / len(checks)
        return _result(passed, "scored",
                       "Declared format constraints and exact declared JSON values only; not factual correctness.", checks)

    if kind == "summary_constraints":
        low, high = rules.get("min_words"), rules.get("max_words")
        entities = rules.get("required_terms")
        if (type(low) is not int or type(high) is not int or low < 0 or high < low
                or not isinstance(entities, list) or any(not isinstance(x, str) or not x for x in entities)):
            return _result(None, "invalid", "Malformed summary constraints.")
        words = len(answer.split())
        checks = {"word_range": low <= words <= high,
                  "entity_coverage": all(entity.casefold() in answer.casefold() for entity in entities),
                  "word_count": words}
        return _result(None, "review", "Proxy checks only; faithfulness and unsupported claims require review.", checks)

    if kind == "code_syntax":
        name, params = rules.get("function_name"), rules.get("parameters")
        if (not isinstance(name, str) or not name.isidentifier()
                or not isinstance(params, list) or any(not isinstance(p, str) or not p.isidentifier() for p in params)):
            return _result(None, "invalid", "Malformed function name or parameters.")
        try:
            tree = ast.parse(answer)
        except (SyntaxError, ValueError, RecursionError) as exc:
            return _result(None, "invalid", f"Python syntax could not be parsed: {type(exc).__name__}.",
                           {"syntax_valid": False})
        functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and node.name == name]
        checks = {"syntax_valid": True, "function_name": bool(functions),
                  "signature": any([arg.arg for arg in f.args.posonlyargs + f.args.args] == params
                                   and not (f.args.vararg or f.args.kwonlyargs or f.args.kwarg or f.args.defaults)
                                   for f in functions)}
        return _result(None, "review", "Syntax/signature proxy only; code was not executed or judged correct.", checks)

    return _result(None, "invalid", "Unknown scorer.")
