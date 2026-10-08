"""Dataset router; include with ``app.include_router(router)`` from the parent app.

Upload raw UTF-8 bytes with Content-Type text/csv or application/x-ndjson.
CSV arrays/objects must be JSON strings, e.g. reference_answers: "[""blue""]",
scoring_config: "{""metric"":""normalized_exact_match"",""normalization"":""unicode_nfc_casefold_trim_collapse_whitespace""}".
Save uses name and version query parameters; dataset_id adds an immutable version.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.models import Dataset, DatasetItem, DatasetVersion
from app.services.datasets import MAX_BYTES, ImportProblem, error, preview, save

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


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
    path = Path(__file__).resolve().parents[3] / "datasets" / "original_demo_v1.jsonl"
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
                           "source": item.source or "unknown", "license": item.license or "unknown"}
                          for item in session.scalars(select(DatasetItem).where(DatasetItem.dataset_version_id == row.id).order_by(DatasetItem.external_id))]}
