"""Dataset router; include with ``app.include_router(router)`` from the parent app.

Upload raw UTF-8 bytes with Content-Type text/csv or application/x-ndjson.
CSV arrays/objects must be JSON strings, e.g. reference_answers: "[""blue""]",
scoring_config: "{""metric"":""normalized_exact_match"",""normalization"":""unicode_nfc_casefold_trim_collapse_whitespace""}".
Save uses name and version query parameters; dataset_id adds an immutable version.
"""

import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from app.models import Dataset, DatasetItem, DatasetVersion
from app.services.datasets import MAX_BYTES, ImportProblem, error, preview, save

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

STARTER_SETS = ((5, "LLM Comparison Lab Starter 5"),
                (10, "LLM Comparison Lab Starter 10"),
                (20, "LLM Comparison Lab Starter 20"))
CATEGORY_ORDER = ("arithmetic", "multiple_choice", "short_factual",
                  "structured_extraction", "instruction_following", "summarization")
STARTER_DESCRIPTION = (
    "Newly authored CC0 local examples selected from the LLM Comparison Lab Original Demo; "
    "a small overlapping convenience set for descriptive exploration, not an established or validated benchmark."
)


async def upload(request: Request) -> tuple[bytes, str]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    format = {"text/csv": "csv", "application/x-ndjson": "jsonl", "application/jsonl": "jsonl"}.get(content_type)
    if format is None:
        raise HTTPException(415, detail={"errors": [error(0, "file", "Use text/csv or application/x-ndjson")]})
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, detail={"errors": [error(0, "file", "File exceeds 5 MiB")]})
    return bytes(data), format


def invalid(exc: ImportProblem) -> HTTPException:
    return HTTPException(422, detail={"errors": exc.errors})


@router.post("/import/preview")
async def import_preview(request: Request):
    data, format = await upload(request)
    try:
        return preview(data, format)
    except ImportProblem as exc:
        raise invalid(exc) from None


@router.post("/import", status_code=201)
async def import_save(request: Request, name: str, version: str, dataset_id: int | None = None,
                      description: str = "", source: str = "unknown", license: str = "unknown",
                      acknowledge_duplicates: bool = False):
    data, format = await upload(request)
    try:
        # A single commit on success, rollback on validation or database failure.
        with request.app.state.sessions.begin() as session:
            return save(session, data, format, name=name, version=version, dataset_id=dataset_id,
                        description=description, source=source, license=license,
                        acknowledge_duplicates=acknowledge_duplicates)
    except ImportProblem as exc:
        raise invalid(exc) from None


@router.post("/built-in", status_code=201)
def install_built_in(request: Request):
    """Install or reuse the original CC0 demonstration dataset."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    path = bundle_root / "datasets" / "original_demo_v1.jsonl"
    if not path.is_file():
        raise HTTPException(503, "Built-in dataset file is unavailable")
    data = path.read_bytes()
    with request.app.state.sessions.begin() as session:
        existing = session.scalar(select(Dataset).where(Dataset.name == "LLM Comparison Lab Original Demo"))
        if existing is not None:
            version = session.scalar(select(DatasetVersion).where(
                DatasetVersion.dataset_id == existing.id, DatasetVersion.version == "v1"))
            if version is not None:
                existing.origin = "original"
                existing.description = "Newly authored demonstration items; not an established benchmark."
                return {"dataset_id": existing.id, "version": version.version,
                        "content_sha256": version.content_sha256, "already_present": True}
        try:
            result = save(session, data, "jsonl", name="LLM Comparison Lab Original Demo", version="v1",
                          source="Original examples authored for LLM Comparison Lab (2026-10-07)", license="CC0-1.0")
        except ImportProblem as exc:
            raise invalid(exc) from None
        dataset = session.get(Dataset, result["dataset_id"])
        dataset.origin = "original"
        dataset.description = "Newly authored demonstration items; not an established benchmark."
        return result | {"already_present": False}


@router.post("/starter-sets")
def install_starter_sets(request: Request):
    """Install or reuse immutable nested 5/10/20-item convenience subsets."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    path = bundle_root / "datasets" / "original_demo_v1.jsonl"
    if not path.is_file():
        raise HTTPException(503, "Built-in dataset file is unavailable")
    raw = path.read_bytes()
    original_hash = preview(raw, "jsonl")["content_sha256"]
    source_items = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    groups = {category: [item for item in source_items if item["task_type"] == category]
              for category in CATEGORY_ORDER}
    if len(source_items) != 30 or any(len(items) != 5 for items in groups.values()):
        raise HTTPException(503, "Original dataset does not match the starter-set source contract")
    ordered = [groups[category][index] for index in range(5) for category in CATEGORY_ORDER
               if index < len(groups[category])]
    provenance = {
        "kind": "deterministic_subset",
        "source_dataset": "LLM Comparison Lab Original Demo",
        "source_version": "v1",
        "source_content_sha256": original_hash,
        "selection_recipe": "round-robin by category in arithmetic, multiple_choice, short_factual, structured_extraction, instruction_following, summarization order; source order within category",
        "research_interpretation": "Newly authored CC0 local examples; tiny overlapping convenience subset, descriptive exploration only; not an established/validated benchmark, independent sample, or evidence of reviewer acceptance. Preserve source split, family, variant, and review metadata as-is.",
    }
    results = []
    with request.app.state.sessions.begin() as session:
        for size, name in STARTER_SETS:
            data = "\n".join(json.dumps(item, ensure_ascii=False) for item in ordered[:size]).encode("utf-8")
            expected_hash = preview(data, "jsonl")["content_sha256"]
            existing = session.scalar(select(Dataset).where(Dataset.name == name))
            if existing is not None:
                version = session.scalar(select(DatasetVersion).where(
                    DatasetVersion.dataset_id == existing.id, DatasetVersion.version == "v1"))
                count = session.scalar(select(func.count()).select_from(DatasetItem).where(
                    DatasetItem.dataset_version_id == version.id)) if version else 0
                if version is None or count != size or version.content_sha256 != expected_hash:
                    raise HTTPException(409, f"Existing starter dataset {name!r} has an incompatible version or size")
                results.append({"dataset_id": existing.id, "version": version.version,
                                "question_count": count, "already_present": True,
                                "content_sha256": version.content_sha256})
                continue
            try:
                result = save(session, data, "jsonl", name=name, version="v1",
                              description=STARTER_DESCRIPTION,
                              source="Newly authored local examples for LLM Comparison Lab, subset selection",
                              license="CC0-1.0")
            except ImportProblem as exc:
                raise invalid(exc) from None
            dataset = session.get(Dataset, result["dataset_id"])
            dataset.origin = "original"
            version = session.scalar(select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset.id, DatasetVersion.version == "v1"))
            version.manifest = version.manifest | {"provenance": provenance | {
                "subset_size": size, "selected_source_item_ids": [item["id"] for item in ordered[:size]]}
            }
            results.append({"dataset_id": dataset.id, "version": "v1", "question_count": size,
                            "already_present": False, "content_sha256": result["content_sha256"]})
    return {"datasets": results}


@router.get("")
def list_datasets(request: Request):
    with request.app.state.sessions() as session:
        return [{"id": row.id, "name": row.name, "description": row.description, "origin": row.origin,
                 "source": row.source or "unknown", "license": row.license or "unknown",
                  "versions": [{"id": v.id, "version": v.version} for v in session.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id == row.id).order_by(DatasetVersion.id))]}
                for row in session.scalars(select(Dataset).order_by(Dataset.id))]


@router.get("/{dataset_id}/versions/{version}")
def get_version(request: Request, dataset_id: int, version: str):
    with request.app.state.sessions() as session:
        row = session.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id, DatasetVersion.version == version))
        if row is None:
            raise HTTPException(404, "Dataset version not found")
        return {"dataset_id": dataset_id, "version": row.version, "content_sha256": row.content_sha256,
                "manifest": row.manifest, "category_inventory": row.category_inventory,
                "items": [{"id": item.external_id, "task_type": item.task_type, "prompt": item.prompt,
                           "context": item.context, "choices": item.choices, "reference_answers": item.reference_answers,
                           "scoring_config": item.scoring_config, "tags": item.tags,
                            "source": item.source or "unknown", "license": item.license or "unknown",
                            "split": item.split, "family_id": item.family_id,
                            "variant_id": item.variant_id, "review_status": item.review_status,
                            "provenance": item.provenance}
                          for item in session.scalars(select(DatasetItem).where(DatasetItem.dataset_version_id == row.id).order_by(DatasetItem.external_id))]}
