from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from test_foundation import migrate

from app.api.results import router
from app.config import Settings
from app.db import make_engine
from app.models import (
    Dataset,
    DatasetItem,
    DatasetVersion,
    Experiment,
    ExperimentModel,
    GenerationJob,
    MetricResult,
    ModelResponse,
    ModelSnapshot,
    Provider,
    RequestAttempt,
)
from app.services.results import recover_scores, score_response


def setup(tmp_path, count=10):
    path = tmp_path / "results.sqlite3"
    migrate(path)
    engine = make_engine(Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3"))
    factory = sessionmaker(engine)
    app = FastAPI()
    app.state.sessions = factory
    app.include_router(router)
    with factory.begin() as session:
        dataset = Dataset(name="Test", origin="imported")
        session.add(dataset)
        session.flush()
        version = DatasetVersion(dataset_id=dataset.id, version="1", content_sha256="a" * 64,
                                 import_schema_version="1")
        provider = Provider(slug="fixture", base_url="https://example.invalid")
        session.add_all([version, provider])
        session.flush()
        experiment = Experiment(name="Results", dataset_version_id=version.id, status="queued", provenance_mode="demo")
        session.add(experiment)
        session.flush()
        for slot in range(2):
            model = ModelSnapshot(provider_id=provider.id, model_id=f"model-{slot}",
                                  display_name=f"model-{slot}", endpoint_family="chat/completions")
            session.add(model)
            session.flush()
            session.add(ExperimentModel(experiment_id=experiment.id, model_snapshot_id=model.id, slot=slot))
        for i in range(count):
            item = DatasetItem(dataset_version_id=version.id, external_id=f"item-{i}", task_type="multiple_choice",
                               prompt="Choose A", choices=["A", "B"], reference_answers=["A"],
                               scoring_config={"metric": "label_accuracy", "labels": ["A", "B"]})
            session.add(item)
            session.flush()
            for slot in range(2):
                session.add(GenerationJob(experiment_id=experiment.id, model_slot=slot, dataset_item_id=item.id,
                                          repetition=0, variant="baseline", execution_order=i * 2 + slot,
                                          status="pending"))
        experiment_id = experiment.id
    return TestClient(app), factory, engine, experiment_id


def save(factory, experiment_id, slot, index, text, *, finish=None, mismatch=False):
    with factory.begin() as session:
        job = session.scalar(select(GenerationJob).join(DatasetItem).where(
            GenerationJob.experiment_id == experiment_id, GenerationJob.model_slot == slot,
            DatasetItem.external_id == f"item-{index}"))
        job.status = "succeeded"
        attempt = RequestAttempt(job_id=job.id, attempt_number=1, outcome="succeeded", reserved_at=job.created_at)
        session.add(attempt)
        session.flush()
        response = ModelResponse(job_id=job.id, attempt_id=attempt.id, raw_text=text,
                                 finish_reason=finish, identity_mismatch=mismatch)
        session.add(response)
        session.flush()
        response_id = response.id
    return response_id


def test_score_idempotency_version_rescore_and_recovery(tmp_path, monkeypatch):
    client, factory, engine, eid = setup(tmp_path, 1)
    response_id = save(factory, eid, 0, 0, "A")
    with factory.begin() as session:
        response = session.get(ModelResponse, response_id)
        assert len(score_response(session, response)) == 1
        assert score_response(session, response) == []  # pending rows in same session
    with factory.begin() as session:
        assert score_response(session, session.get(ModelResponse, response_id)) == []
        session.get(MetricResult, 1).value = 0.0  # old result must not be overwritten
    monkeypatch.setattr("app.evaluation.scoring.SCORER_VERSION", "2")
    with factory.begin() as session:
        recover_scores(session, eid)
        recover_scores(session, eid)
    with factory() as session:
        rows = session.scalars(select(MetricResult).order_by(MetricResult.scorer_version)).all()
        assert [(r.scorer_version, r.value) for r in rows] == [("1", 0.0), ("2", 1.0)]
        assert session.scalar(select(func.count()).select_from(ModelResponse)) == 1
        assert session.scalar(select(func.count()).select_from(RequestAttempt)) == 1
    assert client.get(f"/api/experiments/{eid}/responses/{response_id}").json()["metrics"][1]["value"] == 1.0
    engine.dispose()


def test_denominators_common_missing_identity_and_detail(tmp_path):
    client, factory, engine, eid = setup(tmp_path)
    good = save(factory, eid, 0, 0, "A")
    for i in range(1, 10):
        with factory.begin() as session:
            job = session.scalar(select(GenerationJob).join(DatasetItem).where(
                GenerationJob.experiment_id == eid, GenerationJob.model_slot == 0,
                DatasetItem.external_id == f"item-{i}"))
            job.status = "failed"
    for i in range(10):
        save(factory, eid, 1, i, "A", mismatch=i == 9)
    url = f"/api/experiments/{eid}/results"
    first = client.get(url)
    assert first.status_code == 200, first.text
    data = first.json()
    a, b = data["summaries"]
    assert (a["scheduled_jobs"], a["responses"], a["failures"], a["quality"], a["overall_success"]) == (
        10, 1, 9, 1.0, 0.1)
    assert (b["quality"], b["quality_denominator"], b["identity_mismatch"], b["overall_success"]) == (
        1.0, 9, 1, 0.9)
    common = data["common_completed"][0]
    assert common["count"] == 1
    assert common["models"][1]["omitted_count"] == 8
    assert len(common["models"][1]["omitted_keys"]) == 8
    assert client.get(url, params={"model_slot": 1}).json()["common_completed"][0]["count"] == 9
    assert client.get(url, params={"model_slot": 5}).status_code == 422
    detail = client.get(f"/api/experiments/{eid}/responses/{good}").json()
    assert detail["metrics"][0]["value"] == 1.0
    assert (detail["metrics"][0]["quality_denominator"], detail["metrics"][0]["scheduled_denominator"]) == (1, 10)
    assert "scorer=1" in detail["metrics"][0]["explanation"]
    rows = client.get(f"/api/experiments/{eid}/responses", params={"model_slot": 0, "status": "answered"}).json()
    assert rows["total"] == 1 and rows["items"][0]["response"]["raw_text"] == "A"
    assert client.get(f"/api/experiments/{eid}/responses", params={"status": "failed"}).json()["total"] == 9
    assert client.get(f"/api/experiments/{eid}/responses", params={"limit": 101}).status_code == 422
    assert client.get(f"/api/experiments/{eid}/responses/9999").status_code == 404
    assert client.get("/api/experiments/9999/results").status_code == 404
    engine.dispose()


def test_missing_truncated_malformed_are_distinct(tmp_path):
    client, factory, engine, eid = setup(tmp_path, 4)
    save(factory, eid, 0, 0, "A", finish="length")
    malformed = save(factory, eid, 0, 1, "not a declared label")
    with factory.begin() as session:
        item = session.scalar(select(DatasetItem).where(DatasetItem.external_id == "item-2"))
        item.reference_answers = []
    save(factory, eid, 0, 2, "A")
    result = client.get(f"/api/experiments/{eid}/results").json()["summaries"][0]
    assert (result["scheduled_jobs"], result["responses"], result["complete"], result["truncated"],
            result["missing_reference"], result["pending"], result["parseable"], result["format_failures"],
            result["metric_eligible"], result["quality"], result["quality_denominator"]) == (
                4, 3, 2, 1, 1, 1, 0, 1, 1, 0.0, 1)
    assert client.get(f"/api/experiments/{eid}/responses/{malformed}").json()["metrics"][0]["parse_status"] == "unparseable"
    with factory() as session:
        truncated = session.scalar(select(MetricResult).join(ModelResponse).where(ModelResponse.finish_reason == "length"))
        assert truncated.value is None and truncated.parse_status == "truncated"
        missing = session.scalar(select(MetricResult).where(MetricResult.parse_status == "missing_reference"))
        assert missing.value is None
    assert client.get(f"/api/experiments/{eid}/results", params={"model_slot": 1}).json()["summaries"][0]["quality"] is None
    engine.dispose()


def test_classification_macro_f1_uses_eligible_predictions(tmp_path):
    client, factory, engine, eid = setup(tmp_path, 2)
    with factory.begin() as session:
        for item in session.scalars(select(DatasetItem)):
            item.task_type = "classification"
            item.reference_answers = ["A" if item.external_id == "item-0" else "B"]
    save(factory, eid, 0, 0, "A")
    save(factory, eid, 0, 1, "A")
    summary = client.get(f"/api/experiments/{eid}/results", params={"model_slot": 0}).json()["summaries"][0]
    assert summary["quality"] == 0.5
    assert summary["macro_f1"] == 1 / 3  # A: 2/3, B: 0
    engine.dispose()
