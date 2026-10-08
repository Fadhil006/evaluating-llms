import csv
import io
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from test_foundation import migrate

from app.api.datasets import router
from app.config import Settings
from app.db import make_engine
from app.models import Dataset, DatasetItem, DatasetVersion
from app.services.datasets import preview


def client_for(tmp_path):
    path = tmp_path / "lab.sqlite3"
    migrate(path)
    engine = make_engine(Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3"))
    app = FastAPI()
    app.state.sessions = sessionmaker(engine)
    app.include_router(router)
    return TestClient(app), engine


def send(client, rows, *, save=False, format="jsonl", params=None):
    data = "\n".join(json.dumps(row) for row in rows).encode()
    if format == "csv":
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in rows)
        data = out.getvalue().encode()
    return client.post("/api/datasets/import" + ("" if save else "/preview"),
                       content=data, headers={"content-type": "text/csv" if format == "csv" else "application/x-ndjson"},
                       params=params or ({"name": "test", "version": "v1"} if save else None))


def row():
    return {"id": "one", "task_type": "short_factual", "prompt": "What color?",
            "reference_answers": ["blue"], "scoring_config": {"metric": "normalized_exact_match",
            "normalization": "unicode_nfc_casefold_trim_collapse_whitespace"}}


def test_preview_save_manifest_roundtrip_and_duplicate_version(tmp_path):
    client, engine = client_for(tmp_path)
    item = row()
    csv_preview = send(client, [item], format="csv")
    json_preview = send(client, [item])
    assert csv_preview.status_code == json_preview.status_code == 200
    assert csv_preview.json()["content_sha256"] == json_preview.json()["content_sha256"]
    saved = send(client, [item], save=True)
    assert saved.status_code == 201, saved.text
    dataset_id = saved.json()["dataset_id"]
    assert saved.json()["manifest"]["license"] == "unknown"
    detail = client.get(f"/api/datasets/{dataset_id}/versions/v1").json()
    assert detail["items"][0]["license"] == detail["items"][0]["source"] == "unknown"
    assert detail["content_sha256"] == json_preview.json()["content_sha256"]
    assert send(client, [item], save=True, params={"name": "test", "version": "v2", "dataset_id": dataset_id}).status_code == 422
    assert client.get("/api/datasets").json()[0]["versions"] == [{"id": 1, "version": "v1"}]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(DatasetItem)) == 1
    engine.dispose()


def test_no_partial_import_and_row_errors(tmp_path):
    client, engine = client_for(tmp_path)
    bad = row() | {"id": "two", "scoring_config": {"metric": "eval", "code": "import os"}}
    response = send(client, [row(), bad], save=True)
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["row"] == 2
    assert response.json()["detail"]["errors"][0]["field"] == "scoring_config"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Dataset)) == 0
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 0
    duplicate = send(client, [row(), row()], save=True)
    assert duplicate.status_code == 422
    assert duplicate.json()["detail"]["errors"][0]["field"] == "id"
    assert client.post("/api/datasets/import/preview", content=b"x" * (5 * 1024 * 1024 + 1),
                       headers={"content-type": "application/x-ndjson"}).status_code == 413
    assert send(client, [row()] * 5001).status_code == 422
    assert client.post("/api/datasets/import/preview", content=b'not json\n', headers={"content-type": "application/x-ndjson"}).json()["detail"]["errors"][0]["row"] == 1
    engine.dispose()


def test_duplicate_normalized_content_acknowledgment(tmp_path):
    client, engine = client_for(tmp_path)
    other = row() | {"id": "two", "prompt": "  WHAT   COLOR?  "}
    flagged = send(client, [row(), other]).json()["duplicate_content"]
    assert flagged == [{"row": 2, "id": "two", "matches_row": 1}]
    assert send(client, [row(), other], save=True).status_code == 422
    saved = send(client, [row(), other], save=True, params={"name": "test", "version": "v1", "acknowledge_duplicates": "true"})
    assert saved.status_code == 201, saved.text
    assert saved.json()["manifest"]["duplicate_content_acknowledged"] is True
    engine.dispose()


def test_bad_csv_task_fields_and_hash_order(tmp_path):
    client, engine = client_for(tmp_path)
    second = row() | {"id": "two", "prompt": "Different question?"}
    assert send(client, [row(), second]).json()["content_sha256"] == send(client, [second, row()]).json()["content_sha256"]
    malformed = client.post("/api/datasets/import/preview", content=b'id,prompt\none\n',
                            headers={"content-type": "text/csv"})
    assert malformed.status_code == 422
    assert malformed.json()["detail"]["errors"][0]["field"] == "row"
    missing = row() | {"task_type": "multiple_choice", "scoring_config": {"metric": "label_accuracy", "labels": ["A", "B"]}}
    response = send(client, [missing])
    assert response.status_code == 422
    assert any(e["field"] == "choices" for e in response.json()["detail"]["errors"])
    assert client.post("/api/datasets/import/preview", content=b'{"id":1,"id":2}\n',
                       headers={"content-type": "application/x-ndjson"}).status_code == 422
    engine.dispose()


def test_original_dataset_and_unsafe_schema(tmp_path):
    original = Path(__file__).resolve().parents[2] / "datasets/original_demo_v1.jsonl"
    result = preview(original.read_bytes(), "jsonl")
    assert result["row_count"] == 30
    assert len(result["category_inventory"]) == 6
    client, engine = client_for(tmp_path)
    data = {"id": "one", "task_type": "structured_extraction", "prompt": "Extract JSON",
            "reference_answers": [{"name": "A"}], "scoring_config": {"metric": "json_exact_fields",
            "schema": {"$ref": "https://example.invalid/schema"}}}
    response = send(client, [data])
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["field"] == "scoring_config"
    engine.dispose()


def test_dataset_routes_integrated_in_main_app(tmp_path):
    path = tmp_path / "main.sqlite3"
    migrate(path)
    from app.main import create_app

    api = TestClient(create_app(Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3")), base_url="http://localhost")
    assert api.get("/api/datasets").status_code == 200
    installed = api.post("/api/datasets/built-in")
    assert installed.status_code == 201
    assert installed.json()["already_present"] is False
    assert api.post("/api/datasets/built-in").json()["already_present"] is True
    detail = api.get(f"/api/datasets/{installed.json()['dataset_id']}/versions/v1").json()
    assert len(detail["items"]) == 30
    assert detail["manifest"]["license"] == "CC0-1.0"
    assert api.get("/api/datasets").json()[0]["origin"] == "original"
    engine = make_engine(Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3"))
    engine.dispose()
