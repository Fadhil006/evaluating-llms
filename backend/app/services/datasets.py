"""Bounded dataset import; scoring declarations are data, never executable instructions."""

import csv
import hashlib
import io
import json
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dataset, DatasetItem, DatasetVersion

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
SCHEMA_VERSION = "1"
FIELDS = {"id", "task_type", "prompt", "context", "reference_answers", "choices", "scoring_config", "tags", "source", "license"}
TASK_METRICS = {
    "multiple_choice": "label_accuracy", "short_factual": "normalized_exact_match",
    "extractive_qa": "token_f1", "arithmetic": "numeric_exact",
    "classification": "label_accuracy", "structured_extraction": "json_exact_fields",
    "summarization": "rouge_l_f1", "instruction_following": "instruction_checks",
}
CONFIG_KEYS = {
    "label_accuracy": {"metric", "labels"},
    "normalized_exact_match": {"metric", "normalization"},
    "token_f1": {"metric", "tokenizer"},
    "numeric_exact": {"metric", "absolute_tolerance", "relative_tolerance", "units"},
    "json_exact_fields": {"metric", "schema"},
    "rouge_l_f1": {"metric", "tokenizer", "reference_aggregation"},
    "instruction_checks": {"metric", "checks"},
}


class ImportProblem(Exception):
    def __init__(self, errors: list[dict]):
        self.errors = errors


def error(row: int, field: str, message: str) -> dict:
    return {"row": row, "field": field, "message": message}


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(data: bytes, format: str) -> list[tuple[int, dict]]:
    if len(data) > MAX_BYTES:
        raise ImportProblem([error(0, "file", "File exceeds 5 MiB")])
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportProblem([error(0, "file", "Expected UTF-8 text")]) from None
    if format == "jsonl":
        lines = [(i, line) for i, line in enumerate(text.splitlines(), 1) if line.strip()]
        if len(lines) > MAX_ROWS:
            raise ImportProblem([error(0, "file", "More than 5000 rows")])
        rows = []
        errors = []
        for number, line in lines:
            try:
                value = json.loads(line, object_pairs_hook=unique_pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                if not isinstance(value, dict):
                    raise TypeError("expected an object")
                rows.append((number, value))
            except (ValueError, TypeError) as exc:
                errors.append(error(number, "row", f"Invalid JSON object: {exc}"))
        if errors:
            raise ImportProblem(errors)
    elif format == "csv":
        try:
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or None in reader.fieldnames:
                raise ImportProblem([error(1, "header", "Missing or duplicate CSV headers")])
            if set(reader.fieldnames) - FIELDS:
                raise ImportProblem([error(1, "header", "Unknown CSV columns: " + ", ".join(sorted(set(reader.fieldnames) - FIELDS)))])
            rows = []
            for row in reader:
                if len(rows) >= MAX_ROWS:
                    raise ImportProblem([error(0, "file", "More than 5000 rows")])
                if None in row or any(value is None for value in row.values()):
                    raise ImportProblem([error(reader.line_num, "row", "CSV column count does not match header")])
                rows.append((reader.line_num, row))
        except csv.Error as exc:
            raise ImportProblem([error(0, "file", f"Invalid CSV: {exc}")]) from None
    else:
        raise ImportProblem([error(0, "format", "Expected csv or jsonl")])
    if not rows:
        raise ImportProblem([error(0, "file", "Dataset must contain at least one row")])
    return rows


def schema_ok(schema: object) -> bool:
    """Deliberately tiny inline object schema; no remote refs or regex."""
    return (isinstance(schema, dict) and set(schema) == {"type", "required", "additionalProperties", "properties"}
            and schema["type"] == "object" and schema["additionalProperties"] is False
            and isinstance(schema["properties"], dict) and 0 < len(schema["properties"]) <= 50
            and all(isinstance(k, str) and k and isinstance(v, dict) and set(v) == {"type"}
                    and isinstance(v["type"], str) and v["type"] in {"string", "number", "integer", "boolean"}
                    for k, v in schema["properties"].items())
            and isinstance(schema["required"], list)
            and all(isinstance(k, str) for k in schema["required"])
            and len(set(schema["required"])) == len(schema["required"])
            and set(schema["required"]) == set(schema["properties"]))


def matches_schema(ref: object, schema: dict) -> bool:
    if not isinstance(ref, dict) or set(ref) != set(schema["properties"]):
        return False
    types = {"string": lambda v: isinstance(v, str), "boolean": lambda v: isinstance(v, bool),
             "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
             "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}
    return all(types[prop["type"]](ref[key]) for key, prop in schema["properties"].items())


def validate_config(task: str, config: object, refs: list, choices: list | None) -> str | None:
    if not isinstance(config, dict) or config.get("metric") != TASK_METRICS[task]:
        return f"Expected scoring_config.metric={TASK_METRICS[task]}"
    metric = config["metric"]
    if set(config) - CONFIG_KEYS[metric]:
        return "Unknown scoring_config keys"
    if metric == "label_accuracy":
        labels = config.get("labels")
        if not isinstance(labels, list) or not 2 <= len(labels) <= 50 or any(not isinstance(x, str) or not x or len(x) > 80 for x in labels) or len(set(labels)) != len(labels):
            return "labels must be 2–50 distinct nonempty strings"
        if any(ref not in labels for ref in refs):
            return "Every reference must be a declared label"
        if task == "multiple_choice" and (not choices or len(choices) != len(labels) or any(not isinstance(c, str) or not c.startswith(label + ". ") for c, label in zip(choices, labels, strict=True))):
            return "choices must correspond to labels (e.g. A. First)"
    elif metric == "normalized_exact_match" and config.get("normalization") != "unicode_nfc_casefold_trim_collapse_whitespace":
        return "Unsupported normalization"
    elif metric == "token_f1" and config.get("tokenizer") != "unicode_word_casefold":
        return "Unsupported tokenizer"
    elif metric == "numeric_exact":
        if config.get("units") != "none":
            return "Only units=none is declared"
        for key in ("absolute_tolerance", "relative_tolerance"):
            try:
                value = Decimal(str(config[key]))
                if not value.is_finite() or value < 0:
                    raise InvalidOperation
            except (KeyError, InvalidOperation, ValueError):
                return f"{key} must be a finite nonnegative number"
        try:
            if any(not Decimal(str(ref)).is_finite() for ref in refs):
                return "Numeric references must be finite"
        except InvalidOperation:
            return "Numeric references must be numbers"
    elif metric == "json_exact_fields":
        schema = config.get("schema")
        if not schema_ok(schema):
            return "schema must be a bounded inline object schema with primitive properties; no $ref or regex"
        if any(not matches_schema(ref, schema) for ref in refs):
            return "References must match schema fields and primitive types"
    elif metric == "rouge_l_f1" and (config.get("tokenizer") != "unicode_word_casefold" or config.get("reference_aggregation") != "max"):
        return "Expected tokenizer=unicode_word_casefold and reference_aggregation=max"
    elif metric == "instruction_checks":
        checks = config.get("checks")
        if not isinstance(checks, list) or not 1 <= len(checks) <= 20 or any(
            not isinstance(check, dict) or set(check) != {"type", "value"} or
            not isinstance(check["type"], str) or check["type"] not in {"exact_text", "json_exact"} or
            (check["type"] == "exact_text" and (not isinstance(check["value"], str) or not check["value"]))
            for check in checks
        ):
            return "checks must declare 1–20 exact_text or json_exact values"
    return None


def validate(rows: list[tuple[int, dict]]) -> dict:
    items = []
    errors = []
    seen_ids = {}
    seen_content = {}
    duplicates = []
    for number, raw in rows:
        if set(raw) - FIELDS:
            errors.append(error(number, "row", "Unknown fields: " + ", ".join(sorted(set(raw) - FIELDS))))
            continue
        item = dict(raw)
        for field in ("reference_answers", "choices", "scoring_config", "tags"):
            if isinstance(item.get(field), str) and item[field]:
                try:
                    item[field] = json.loads(item[field], object_pairs_hook=unique_pairs)
                except ValueError:
                    errors.append(error(number, field, "Expected valid JSON"))
        if any(e["row"] == number for e in errors):
            continue
        for field, limit in (("id", 255), ("task_type", 80), ("prompt", 20000), ("context", 40000), ("source", 512), ("license", 100)):
            value = item.get(field)
            if field in {"context", "source", "license"} and (value is None or value == "" or isinstance(value, str) and not value.strip()):
                item[field] = "unknown" if field in {"source", "license"} else None
            elif not isinstance(value, str) or not value.strip() or len(value) > limit:
                errors.append(error(number, field, f"Expected nonempty text up to {limit} characters"))
            else:
                item[field] = unicodedata.normalize("NFC", value.strip())
        task = item.get("task_type")
        if not isinstance(task, str) or task not in TASK_METRICS:
            errors.append(error(number, "task_type", "Unknown task type"))
        refs = item.get("reference_answers")
        if not isinstance(refs, list) or not 1 <= len(refs) <= 20 or any(
            not isinstance(r, (str, dict, list)) or (isinstance(r, str) and (not r.strip() or len(r) > 10000)) for r in refs
        ):
            errors.append(error(number, "reference_answers", "Expected 1–20 nonempty string or structured references"))
            refs = []
        choices = item.get("choices") or None
        if choices is not None and (not isinstance(choices, list) or len(choices) > 50 or any(not isinstance(c, str) or not c.strip() or len(c) > 1000 for c in choices)):
            errors.append(error(number, "choices", "Expected at most 50 nonempty short strings"))
            choices = None
        if task == "multiple_choice" and not choices:
            errors.append(error(number, "choices", "Multiple choice requires choices"))
        if task != "multiple_choice" and choices:
            errors.append(error(number, "choices", "Choices are only supported for multiple choice"))
        if task in {"short_factual", "extractive_qa", "arithmetic", "classification", "summarization"} and any(not isinstance(r, str) for r in refs):
            errors.append(error(number, "reference_answers", "This task requires text references"))
        if task == "structured_extraction" and any(not isinstance(r, dict) for r in refs):
            errors.append(error(number, "reference_answers", "Structured extraction requires object references"))
        tags = item.get("tags") or []
        if not isinstance(tags, list) or len(tags) > 30 or any(not isinstance(t, str) or not t.strip() or len(t) > 80 for t in tags):
            errors.append(error(number, "tags", "Expected at most 30 short text tags"))
        if isinstance(task, str) and task in TASK_METRICS and refs:
            issue = validate_config(task, item.get("scoring_config"), refs, choices)
            if issue:
                errors.append(error(number, "scoring_config", issue))
        external_id = item.get("id")
        if isinstance(external_id, str) and external_id:
            if external_id in seen_ids:
                errors.append(error(number, "id", f"Duplicate id (row {seen_ids[external_id]})"))
            seen_ids[external_id] = number
        if any(e["row"] == number for e in errors):
            continue
        item["choices"] = choices
        item["tags"] = tags
        # Duplicate identity ignores external ID and attribution, but retains evaluation content.
        content = {k: v for k, v in item.items() if k not in {"id", "source", "license", "tags"}}
        content["prompt"] = " ".join(content["prompt"].split()).casefold()
        content["context"] = " ".join((content["context"] or "").split()).casefold()
        try:
            signature = canonical(content)
        except (ValueError, TypeError):
            errors.append(error(number, "row", "Invalid non-finite or unsupported JSON value"))
            continue
        if signature in seen_content:
            duplicates.append({"row": number, "id": external_id, "matches_row": seen_content[signature]})
        else:
            seen_content[signature] = number
        items.append(item)
    if errors:
        raise ImportProblem(errors)
    items.sort(key=lambda x: x["id"])
    digest = hashlib.sha256(canonical(items).encode("utf-8")).hexdigest()
    return {"items": items, "content_sha256": digest, "duplicate_content": duplicates,
            "category_inventory": dict(sorted(Counter(item["task_type"] for item in items).items()))}


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def preview(data: bytes, format: str) -> dict:
    result = validate(parse(data, format))
    return {"row_count": len(result["items"]), "content_sha256": result["content_sha256"],
            "category_inventory": result["category_inventory"], "duplicate_content": result["duplicate_content"],
            "source": "unknown", "license": "unknown", "import_schema_version": SCHEMA_VERSION}


def save(session: Session, data: bytes, format: str, *, name: str, version: str,
         dataset_id: int | None = None, description: str = "", source: str = "unknown",
         license: str = "unknown", acknowledge_duplicates: bool = False) -> dict:
    result = validate(parse(data, format))  # Never trust a browser preview.
    if result["duplicate_content"] and not acknowledge_duplicates:
        raise ImportProblem([error(d["row"], "content", "Duplicate normalized content; acknowledge_duplicates=true to save") for d in result["duplicate_content"]])
    for field, value, limit in (("name", name, 255), ("version", version, 80), ("description", description, 10000), ("source", source, 512), ("license", license, 100)):
        if not isinstance(value, str) or (field in {"name", "version"} and not value.strip()) or len(value) > limit:
            raise ImportProblem([error(0, field, f"Expected text up to {limit} characters")])
    version = version.strip()
    dataset = session.get(Dataset, dataset_id) if dataset_id is not None else None
    if dataset_id is not None and dataset is None:
        raise ImportProblem([error(0, "dataset_id", "Dataset not found")])
    if dataset is not None:
        if session.scalar(select(DatasetVersion.id).where(DatasetVersion.dataset_id == dataset.id, DatasetVersion.version == version)):
            raise ImportProblem([error(0, "version", "Version already exists")])
        if session.scalar(select(DatasetVersion.id).where(DatasetVersion.dataset_id == dataset.id, DatasetVersion.content_sha256 == result["content_sha256"])):
            raise ImportProblem([error(0, "content_sha256", "Identical content already exists in this dataset")])
    else:
        dataset = Dataset(name=name.strip(), description=description, origin="imported", source=source or "unknown", license=license or "unknown")
        session.add(dataset)
        session.flush()
    manifest = {"import_schema_version": SCHEMA_VERSION, "content_sha256": result["content_sha256"],
                "source": source or "unknown", "license": license or "unknown", "format": format,
                "row_count": len(result["items"]), "duplicate_content": result["duplicate_content"],
                "duplicate_content_acknowledged": bool(result["duplicate_content"] and acknowledge_duplicates),
                "category_inventory": result["category_inventory"]}
    record = DatasetVersion(dataset_id=dataset.id, version=version.strip(), content_sha256=result["content_sha256"],
                            manifest=manifest, category_inventory=result["category_inventory"], import_schema_version=SCHEMA_VERSION)
    session.add(record)
    session.flush()
    session.add_all(DatasetItem(dataset_version_id=record.id, external_id=item["id"], task_type=item["task_type"],
                                prompt=item["prompt"], context=item.get("context"), choices=item["choices"],
                                reference_answers=item["reference_answers"], scoring_config=item["scoring_config"],
                                tags=item["tags"], source=item["source"], license=item["license"])
                    for item in result["items"])
    session.flush()
    return {"dataset_id": dataset.id, "version": record.version, "content_sha256": record.content_sha256,
            "manifest": manifest}
