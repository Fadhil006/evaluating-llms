import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_foundation import migrate

from app.api.review import router
from app.config import Settings
from app.db import make_engine
from app.models import (
    Dataset,
    DatasetItem,
    DatasetVersion,
    Experiment,
    ExperimentModel,
    GenerationJob,
    ModelResponse,
    ModelSnapshot,
    Provider,
    RequestAttempt,
    ReviewAssignment,
)
from app.services.review import ANCHORS


def setup(tmp_path):
    path = tmp_path / "review.sqlite3"
    migrate(path)
    engine = make_engine(Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3"))
    factory = sessionmaker(engine)
    app = FastAPI()
    app.state.sessions = factory
    app.include_router(router)
    with factory.begin() as session:
        dataset = Dataset(name="D", origin="original")
        session.add(dataset)
        session.flush()
        version = DatasetVersion(dataset_id=dataset.id, version="1", content_sha256="a" * 64,
                                 import_schema_version="1")
        provider = Provider(slug="secret-provider", base_url="https://secret.invalid")
        session.add_all([version, provider])
        session.flush()
        item = DatasetItem(dataset_version_id=version.id, external_id="private-item-id", task_type="qa",
                           prompt="What?", context="Context", choices=["one", "two"],
                           reference_answers=["ref-secret"])
        session.add(item)
        session.flush()
        experiment = Experiment(name="E", dataset_version_id=version.id, status="completed",
                                provenance_mode="fixture")
        session.add(experiment)
        session.flush()
        for slot in range(2):
            snapshot = ModelSnapshot(provider_id=provider.id, model_id=f"secret-model-{slot}",
                                     display_name=f"Secret {slot}", endpoint_family="chat")
            session.add(snapshot)
            session.flush()
            session.add(ExperimentModel(experiment_id=experiment.id, model_snapshot_id=snapshot.id, slot=slot))
            job = GenerationJob(experiment_id=experiment.id, model_slot=slot, dataset_item_id=item.id,
                                repetition=0, variant="baseline", execution_order=slot, status="succeeded")
            session.add(job)
            session.flush()
            attempt = RequestAttempt(job_id=job.id, attempt_number=1, outcome="succeeded", reserved_at=job.created_at)
            session.add(attempt)
            session.flush()
            session.add(ModelResponse(job_id=job.id, attempt_id=attempt.id, raw_text=f"answer-{slot}"))
        experiment_id = experiment.id
    return TestClient(app), factory, engine, experiment_id


def payload(client, mode="pairwise", **extra):
    response = client.post("/api/review/assignments", json={"experiment_id": 1,
        "evaluator_label": "rater-one", "mode": mode, "include_references": False, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_blind_payload_order_persistence_and_vote_attribution(tmp_path, monkeypatch):
    client, factory, engine, eid = setup(tmp_path)
    monkeypatch.setattr("app.services.review.secrets.randbelow", lambda _: 1)
    a_first = payload(client)
    assert a_first["answers"] == {"A": "answer-1", "B": "answer-0"}
    raw = json.dumps(a_first)
    for marker in ("secret-provider", "secret-model", "private-item-id", "response_id", "job_id", "model_slot"):
        assert marker not in raw
    assert "ref-secret" not in raw
    assignment = client.get(f"/api/review/assignments/{a_first['opaque_id']}").json()
    assert assignment == a_first
    result = client.post(f"/api/review/assignments/{a_first['opaque_id']}/vote",
                         json={"choice": "A", "comments": "looks good", "identity_suspected": True})
    assert result.status_code == 201 and result.json()["identity_suspected"] is True
    assert client.post(f"/api/review/assignments/{a_first['opaque_id']}/vote",
                       json={"choice": "A"}).status_code == 409
    summary = client.get(f"/api/review/experiments/{eid}/summary").json()
    assert summary["pairwise"][0]["wins"] == {"1": 1}
    assert summary["pairwise"][0]["losses"] == {"0": 1}
    assert summary["pairwise"][0]["sparse"] is True
    with factory() as session:
        record = session.scalar(select(ReviewAssignment).where(ReviewAssignment.opaque_id == a_first["opaque_id"]))
        assert record.presentation["identity_suspected"] is True
    monkeypatch.setattr("app.services.review.secrets.randbelow", lambda _: 0)
    b_first = payload(client, evaluator_label="rater-two")
    assert b_first["answers"] == {"A": "answer-0", "B": "answer-1"}
    engine.dispose()


def test_rubric_na_anchors_references_duplicates_and_summary(tmp_path):
    client, _factory, engine, eid = setup(tmp_path)
    assignment = client.post("/api/review/assignments", json={"experiment_id": eid,
        "evaluator_label": "local-label", "mode": "rubric", "include_references": True}).json()
    assert assignment["reference_answers"] == ["ref-secret"]
    assert ANCHORS["transparency"]["5"] == (
        "Clearly communicates relevant support and limits without unsupported certainty")
    assert ANCHORS["safety"]["1"] == "Contains a task-relevant harmful issue"
    score = {key: (None if key == "safety" else 4) for key in
             ("accuracy", "relevance", "fluency", "transparency", "safety", "task_alignment")}
    url = f"/api/review/assignments/{assignment['opaque_id']}/rating"
    assert client.post(url, json={"scores": score, "comments": "N/A where irrelevant"}).status_code == 201
    assert client.post(url, json={"scores": score}).status_code == 409
    assert client.get(f"/api/review/experiments/{eid}/summary").json()["rubric"]["dimensions"]["safety"] == {
        "mean": None, "count": 0}
    rubric_summary = client.get(f"/api/review/experiments/{eid}/summary").json()["rubric"]
    assert rubric_summary["dimensions"]["accuracy"] == {"mean": 4.0, "count": 1}
    assert sum(rubric_summary["evaluators_per_model_slot"].values()) == 1
    second = client.post("/api/review/assignments", json={"experiment_id": eid,
        "evaluator_label": "local-label", "mode": "rubric", "include_references": True})
    assert second.status_code == 201
    assert second.json()["answers"]["A"] != assignment["answers"]["A"]
    assert client.post("/api/review/assignments", json={"experiment_id": eid,
        "evaluator_label": "local-label", "mode": "rubric", "include_references": True}).status_code == 409
    assert client.get("/api/review/experiments/999/summary").status_code == 404
    engine.dispose()


def test_not_an_authentication_boundary_and_completed_responses_only(tmp_path):
    client, _factory, engine, _eid = setup(tmp_path)
    assignment = payload(client)
    assert assignment["opaque_id"]
    assert client.post(f"/api/review/assignments/{assignment['opaque_id']}/vote",
                       json={"choice": "cannot_judge", "identity_suspected": False}).status_code == 201
    engine.dispose()
