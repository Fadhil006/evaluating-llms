"""Pure, versioned scorers for the dataset importer's declared scoring language."""

import json
import math
import re
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation

SCORER_VERSION = "1"
NORMALIZATION_VERSION = "unicode-nfc-casefold-whitespace-v1"
TOKENIZER_VERSION = "unicode-word-casefold-v1"
TASK_METRICS = {
    "multiple_choice": "label_accuracy",
    "short_factual": "normalized_exact_match",
    "extractive_qa": "token_f1",
    "arithmetic": "numeric_exact",
    "classification": "label_accuracy",
    "structured_extraction": "json_exact_fields",
    "summarization": "rouge_l_f1",
    "instruction_following": "instruction_checks",
}
WORD = re.compile(r"\w+", re.UNICODE)
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def tokens(text: str) -> list[str]:
    return WORD.findall(unicodedata.normalize("NFC", text).casefold())


def _json(text: str):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(text, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")))

    def finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                finite(child)
        elif isinstance(item, list):
            for child in item:
                finite(child)

    finite(value)
    return value


def _schema_valid(value, schema: dict) -> bool:
    # Importer permits only flat objects with required primitive fields and no extras.
    if not isinstance(value, dict) or set(value) != set(schema["properties"]):
        return False
    types = {"string": lambda x: isinstance(x, str),
             "boolean": lambda x: isinstance(x, bool),
             "integer": lambda x: type(x) is int,
             "number": lambda x: type(x) in (int, float)}
    return all(types[spec["type"]](value[key]) for key, spec in schema["properties"].items())


def _json_equal(left, right) -> bool:
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    return left == right


def _f1(overlap: int, prediction: int, reference: int) -> float:
    return 2 * overlap / (prediction + reference) if prediction + reference else 1.0


def _lcs(a: list[str], b: list[str]) -> int:
    previous = [0] * (len(b) + 1)
    for word in a:
        current = [0]
        for index, other in enumerate(b, 1):
            current.append(previous[index - 1] + 1 if word == other else
                           max(current[-1], previous[index]))
        previous = current
    return previous[-1]


def _label(text: str, labels: list[str], *, choice: bool) -> str | None:
    text = text.strip()
    lines = text.splitlines()
    if choice and lines and re.fullmatch(r"Answer:\s*.+", lines[-1]):
        candidate = lines[-1].split(":", 1)[1].strip()
        # A declared final line is valid only if earlier text does not assert another answer.
        if any(re.fullmatch(r"\s*Answer:\s*.+", line) or line.strip() in labels
               for line in lines[:-1]):
            return None
    else:
        candidate = text
    return candidate if candidate in labels else None


def _number(text: str) -> Decimal | None:
    lines = text.strip().splitlines()
    if lines and re.fullmatch(r"Answer:\s*.+", lines[-1]):
        if any(re.fullmatch(r"\s*Answer:\s*.+", line) for line in lines[:-1]):
            return None
        text = lines[-1].split(":", 1)[1].strip()
    else:
        text = text.strip()
    if not NUMBER.fullmatch(text):
        return None
    try:
        number = Decimal(text)
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def score(task: str, raw_answer: str | None, references: list, config: dict,
          *, truncated: bool = False) -> dict:
    """Score one response; null metric values mean no completed answer to grade.

    Completed but unparseable answers receive zero correctness, while missing and
    truncated answers receive null. Config and references come from validated items.
    """
    metric = TASK_METRICS[task]
    if config["metric"] != metric:
        raise ValueError("Scorer does not match task")
    values = {metric: None}
    if metric == "normalized_exact_match":
        values = {"raw_exact_match": None, "normalized_exact_match": None}
    elif metric == "json_exact_fields":
        values = {"json_valid": None, "schema_valid": None, "field_exact": None}
    elif metric == "instruction_checks":
        values = {"instruction_checks": None, "checks_passed": None}
    result = {"scorer_version": SCORER_VERSION, "normalization_version": NORMALIZATION_VERSION,
              "tokenizer_version": TOKENIZER_VERSION, "task_type": task, "raw_answer": raw_answer,
              "extracted_answer": None, "normalized_answer": None, "parse_status": "missing",
              "metrics": values, "explanation": "No response recorded"}
    if raw_answer is None:
        return result
    if truncated:
        result.update(parse_status="truncated", explanation="Response truncated; metrics not computed")
        return result
    if not raw_answer.strip():
        result.update(parse_status="unparseable", explanation="Empty completed response")
        result["metrics"] = dict.fromkeys(values, 0.0)
        return result

    result.update(extracted_answer=raw_answer, normalized_answer=normalize(raw_answer),
                  parse_status="valid", explanation="Parsed completed response")
    if metric == "label_accuracy":
        answer = _label(raw_answer, config["labels"], choice=task == "multiple_choice")
        if answer is None:
            result.update(extracted_answer=None, normalized_answer=None,
                          parse_status="unparseable", explanation="No single declared label")
            values[metric] = 0.0
        else:
            result.update(extracted_answer=answer, normalized_answer=answer,
                          explanation="Single declared label compared with accepted references")
            values[metric] = float(answer in references)
    elif metric == "normalized_exact_match":
        answer = normalize(raw_answer)
        values["raw_exact_match"] = float(raw_answer in references)
        values[metric] = float(answer in {normalize(ref) for ref in references})
        result["explanation"] = "Raw and NFC/casefold/whitespace exact match; punctuation retained"
    elif metric == "token_f1":
        answer = tokens(raw_answer)
        result["normalized_answer"] = answer
        values[metric] = max(_f1(sum((Counter(answer) & Counter(tokens(ref))).values()),
                                  len(answer), len(tokens(ref))) for ref in references)
        result["explanation"] = "Maximum multiset Unicode-word token F1 over references"
    elif metric == "numeric_exact":
        if config["units"] != "none":
            raise ValueError("Unsupported units policy")
        number = _number(raw_answer)
        if number is None:
            result.update(extracted_answer=None, normalized_answer=None,
                          parse_status="unparseable", explanation="Expected a single finite number without units")
            values[metric] = 0.0
        else:
            result.update(extracted_answer=str(number), normalized_answer=str(number))
            absolute = Decimal(str(config["absolute_tolerance"]))
            relative = Decimal(str(config["relative_tolerance"]))
            values[metric] = float(any(abs(number - Decimal(str(ref))) <=
                                       max(absolute, relative * abs(Decimal(str(ref))))
                                       for ref in references))
            result["explanation"] = "Decimal comparison: error <= max(absolute, relative × |reference|); units=none"
    elif metric == "json_exact_fields":
        try:
            parsed = _json(raw_answer)
        except (ValueError, TypeError):
            result.update(extracted_answer=None, normalized_answer=None,
                          parse_status="malformed_json", explanation="Invalid JSON or duplicate key")
            values.update(json_valid=0.0, schema_valid=0.0, field_exact=0.0)
        else:
            result.update(extracted_answer=parsed, normalized_answer=parsed)
            valid = _schema_valid(parsed, config["schema"])
            values.update(json_valid=1.0, schema_valid=float(valid),
                          field_exact=float(valid and any(_json_equal(parsed, ref) for ref in references)))
            if not valid:
                result.update(parse_status="invalid_schema", explanation="JSON violates declared fields or types")
            else:
                result["explanation"] = "Inline schema valid; exact fields compared with accepted references"
    elif metric == "rouge_l_f1":
        answer = tokens(raw_answer)
        result["normalized_answer"] = answer
        values[metric] = max(_f1(_lcs(answer, tokens(ref)), len(answer), len(tokens(ref)))
                             for ref in references)
        result["explanation"] = "Maximum ROUGE-L F1 word-sequence overlap; not factuality"
    elif metric == "instruction_checks":
        passed = 0
        malformed = False
        checks = config["checks"]
        for check in checks:
            if check["type"] == "exact_text":
                passed += raw_answer == check["value"]
            elif check["type"] == "json_exact":
                try:
                    parsed = _json(raw_answer)
                    result.update(extracted_answer=parsed, normalized_answer=parsed)
                    passed += _json_equal(parsed, check["value"])
                except (ValueError, TypeError):
                    malformed = True
            else:
                raise ValueError("Unsupported instruction check")
        values.update(instruction_checks=passed / len(checks), checks_passed=passed)
        result["explanation"] = f"{passed}/{len(checks)} declared checks passed"
        if malformed:
            result["parse_status"] = "malformed_json"
    return result


def classification_macro_f1(results: list[tuple[str, dict]], labels: list[str]) -> float | None:
    """Macro F1 over declared classes; completed invalid predictions count as false negatives.

    Input pairs are (true label, per-item score result). Missing/truncated items
    have no confusion entry and must be counted separately by the caller.
    """
    eligible = [(truth, result["normalized_answer"]) for truth, result in results
                if result["parse_status"] not in {"missing", "truncated"}]
    if not eligible:
        return None
    if any(truth not in labels for truth, _ in eligible):
        raise ValueError("True label outside declared classes")
    return sum(_f1(sum(truth == prediction == label for truth, prediction in eligible),
                   sum(prediction == label for _, prediction in eligible),
                   sum(truth == label for truth, _ in eligible))
               for label in labels) / len(labels)
