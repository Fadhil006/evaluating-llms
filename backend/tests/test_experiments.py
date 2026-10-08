from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from test_foundation import migrate

from app.api.experiments import router
from app.config import Settings
from app.db import make_engine
from app.models import (
    Dataset,
    DatasetItem,
    DatasetVersion,
    Experiment,
    ExperimentEvent,
    ExperimentModel,
    GenerationJob,
    ModelSnapshot,
    Provider,
    RequestAttempt,
)
from app.providers.policy import REQUIRED


def setup(tmp_path):
    path = tmp_path / "lab.sqlite3"
    migrate(path)
    engine = make_engine(Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3"))
    app = FastAPI()
    app.state.sessions = sessionmaker(engine)
    app.include_router(router)
    with app.state.sessions.begin() as session:
        dataset = Dataset(name="Example", origin="imported")
        session.add(dataset)
        session.flush()
        version = DatasetVersion(dataset_id=dataset.id, version="v1", content_sha256="a" * 64,
                                 import_schema_version="1")
        session.add(version)
        session.flush()
        session.add_all(DatasetItem(dataset_version_id=version.id, external_id=f"item-{i:02}",
                                    task_type="short_factual" if i % 2 else "arithmetic", prompt="Question",
                                    reference_answers=["SECRET ANSWER"], scoring_config={"secret": "SECRET SCORER"})
                        for i in range(12))
        provider = Provider(slug="openrouter", base_url="https://example.invalid", credential_configured=True)
        session.add(provider)
        session.flush()
        for model_id, params, pricing in (("one", ["max_tokens", "temperature"], {k: "0" for k in REQUIRED}),
                                          ("two", ["max_tokens"], {}),
                                          ("three", ["max_tokens"], {})):
            session.add(ModelSnapshot(provider_id=provider.id, model_id=model_id, display_name=model_id,
                                      endpoint_family="chat/completions", supported_parameters=params,
                                      pricing_evidence=pricing, pricing_checked_at=datetime.now(UTC),
                                      pricing_source="https://example.invalid/catalog",
                                      availability="available"))
    with Session(engine) as session:
        ids = session.scalars(select(ModelSnapshot.id).order_by(ModelSnapshot.id)).all()
        version_id = session.scalar(select(DatasetVersion.id))
    return TestClient(app), engine, {"name": "Trial", "dataset_version_id": version_id,
                                    "model_snapshot_ids": ids[:2], "seed": 4}, ids


def test_estimate_create_update_clone_and_saved_snapshot(tmp_path):
    client, engine, payload, ids = setup(tmp_path)
    estimate = client.post("/api/experiments/estimate", json=payload)
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["estimate"] == {
        "initial_candidate_requests": 20, "maximum_candidate_retries": 20,
        "unconstrained_maximum_attempts": 60, "maximum_attempts": 40,
        "metadata_startup": 1, "metadata_refresh": 1}
    assert len(estimate.json()["item_ids"]) == 10
    assert estimate.json()["ready"] is False
    assert estimate.json()["policy_decisions_advisory"][1]["reason"] == "unknown_pricing"
    saved = client.post("/api/experiments", json=payload)
    assert saved.status_code == 201, saved.text
    draft = saved.json()
    assert draft["config"]["item_ids"] == estimate.json()["item_ids"]
    assert draft["config"]["category_counts"] == estimate.json()["category_counts"]
    assert draft["config"]["dataset_content_sha256"] == "a" * 64
    assert [m["model_id"] for m in draft["config"]["models"]] == ["one", "two"]
    assert "SECRET" not in saved.text
    assert client.get("/api/experiments").json()[0]["config_sha256"] == draft["config_sha256"]
    assert client.get(f"/api/experiments/{draft['id']}").json() == draft
    change = client.put(f"/api/experiments/{draft['id']}", json=payload | {
        "name": "Changed", "model_snapshot_ids": ids[1:], "item_ids": ["item-11", "item-00"],
        "repetitions": 2, "attempt_cap": 30})
    assert change.status_code == 200, change.text
    assert change.json()["config"]["item_ids"] == ["item-11", "item-00"]
    assert change.json()["config_sha256"] != draft["config_sha256"]
    clone = client.post(f"/api/experiments/{draft['id']}/clone")
    assert clone.status_code == 201, clone.text
    assert clone.json()["id"] != draft["id"]
    assert clone.json()["config"]["item_ids"] == ["item-11", "item-00"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ExperimentModel)) == 4
        assert session.scalars(select(ExperimentModel.model_snapshot_id).where(
            ExperimentModel.experiment_id == draft["id"]).order_by(ExperimentModel.slot)).all() == ids[1:]
    engine.dispose()


def test_validation_atomicity_non_draft_conflict_and_clone(tmp_path):
    client, engine, payload, ids = setup(tmp_path)
    for update, field in (({"item_ids": ["item-00", "missing"]}, "item_ids"),
                          ({"item_ids": ["item-00", "item-00"]}, "item_ids"),
                          ({"model_snapshot_ids": [ids[0], ids[0]]}, "model_snapshot_ids"),
                          ({"model_snapshot_ids": [ids[0], 999999]}, "model_snapshot_ids"),
                          ({"temperature": 0}, "model_snapshot_ids"),
                          ({"attempt_cap": 19}, "attempt_cap"),
                          ({"dataset_version_id": 999999}, "dataset_version_id")):
        for path in ("/api/experiments/estimate", "/api/experiments"):
            response = client.post(path, json=payload | update)
            assert response.status_code == 422, response.text
            assert response.json()["detail"]["errors"][0]["field"] == field
    assert client.post("/api/experiments", json=payload | {"extra": 1}).status_code == 422
    assert client.post("/api/experiments", json=payload | {"max_tokens": 5000}).status_code == 422
    assert client.post("/api/experiments", json=payload | {"repetitions": 0}).status_code == 422
    assert client.get("/api/experiments/999999").status_code == 404
    draft = client.post("/api/experiments", json=payload).json()
    bad = client.put(f"/api/experiments/{draft['id']}", json=payload | {"item_ids": ["bad"]})
    assert bad.status_code == 422
    assert client.get(f"/api/experiments/{draft['id']}").json()["config_sha256"] == draft["config_sha256"]
    with sessionmaker(engine).begin() as session:
        session.get(Experiment, draft["id"]).status = "queued"
    assert client.put(f"/api/experiments/{draft['id']}", json=payload).status_code == 409
    assert client.post(f"/api/experiments/{draft['id']}/clone").json()["status"] == "draft"
    engine.dispose()


def test_resume_requires_acknowledgement_for_unknown_remote_outcome(tmp_path):
    client, engine, payload, ids = setup(tmp_path)
    with Session(engine) as session, session.begin():
        session.get(ModelSnapshot, ids[1]).pricing_evidence = {k: "0" for k in REQUIRED}
    draft = client.post("/api/experiments", json=payload).json()
    with sessionmaker(engine).begin() as session:
        experiment = session.get(Experiment, draft["id"])
        experiment.status = "paused"
        item = session.scalar(select(DatasetItem).where(DatasetItem.dataset_version_id == experiment.dataset_version_id))
        job = GenerationJob(experiment_id=experiment.id, model_slot=0, dataset_item_id=item.id,
                            repetition=0, execution_order=0, status="failed")
        session.add(job)
        session.flush()
        now = datetime.now(UTC)
        session.add(RequestAttempt(job_id=job.id, attempt_number=1, outcome="unknown_remote_outcome",
                                   reserved_at=now, dispatched_at=now))
    url = f"/api/experiments/{draft['id']}/resume"
    assert client.post(url).status_code == 409
    assert client.post(url + "?acknowledge_uncertain=true").json()["status"] == "queued"
    engine.dispose()


def test_experiment_routes_integrated_in_main_app(tmp_path):
    path = tmp_path / "main.sqlite3"
    migrate(path)
    from app.main import create_app

    api = TestClient(create_app(Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3")),
                     base_url="http://localhost")
    assert api.get("/api/experiments").status_code == 200
    assert api.get("/api/datasets").status_code == 200


def test_start_freezes_latest_evidence_jobs_and_lifecycle(tmp_path):
    client, engine, payload, ids = setup(tmp_path)
    with sessionmaker(engine).begin() as session:
        old = session.get(ModelSnapshot, ids[1])
        session.add(ModelSnapshot(provider_id=old.provider_id, model_id=old.model_id, display_name=old.model_id,
                                  endpoint_family=old.endpoint_family, supported_parameters=["max_tokens"],
                                  pricing_evidence={k: "0" for k in REQUIRED},
                                  pricing_source="https://example.invalid/catalog",
                                  pricing_checked_at=datetime.now(UTC), availability="available"))
    draft = client.post("/api/experiments", json=payload | {"item_ids": ["item-01", "item-02"],
                                                           "repetitions": 2, "attempt_cap": 8}).json()
    url = f"/api/experiments/{draft['id']}"
    result = client.post(url + "/start")
    assert result.status_code == 200, result.text
    frozen = result.json()
    assert frozen["status"] == "queued"
    assert frozen["config_sha256"] != draft["config_sha256"]
    assert frozen["config"]["eligibility_at_start"][1]["selected_snapshot_id"] == ids[1]
    assert frozen["config"]["eligibility_at_start"][1]["snapshot_id"] > ids[-1]
    assert frozen["config"]["eligibility_at_start"][1]["pricing_evidence"] == {k: "0" for k in REQUIRED}
    assert "SECRET" not in result.text
    with Session(engine) as session:
        jobs = session.scalars(select(GenerationJob).order_by(GenerationJob.execution_order)).all()
        assert len(jobs) == 8
        assert [job.execution_order for job in jobs] == list(range(8))
        assert len({(j.model_slot, j.dataset_item_id, j.repetition) for j in jobs}) == 8
        assert session.scalar(select(ExperimentModel.model_snapshot_id).where(
            ExperimentModel.experiment_id == draft["id"], ExperimentModel.slot == 1)) == frozen["config"]["model_snapshot_ids"][1]
    assert client.post(url + "/start").status_code == 409
    assert client.put(url, json=payload).status_code == 409
    assert client.post(url + "/resume").status_code == 409
    assert client.post(url + "/pause").json()["status"] == "paused"
    assert client.post(url + "/pause").status_code == 409
    with sessionmaker(engine).begin() as session:
        session.get(GenerationJob, jobs[0].id).status = "succeeded"
        session.get(GenerationJob, jobs[1].id).status = "interrupted"
    assert client.post(url + "/resume").status_code == 409
    assert client.post(url + "/resume?acknowledge_uncertain=true").json()["status"] == "queued"
    with Session(engine) as session:
        assert session.get(GenerationJob, jobs[0].id).status == "succeeded"
        assert session.get(GenerationJob, jobs[1].id).status == "pending"
    assert client.post(url + "/cancel").json()["status"] == "cancelled"
    assert client.post(url + "/cancel").status_code == 409
    with Session(engine) as session:
        assert session.get(GenerationJob, jobs[0].id).status == "succeeded"
        assert session.scalar(select(func.count()).select_from(GenerationJob).where(
            GenerationJob.status == "cancelled")) == 7
        assert session.scalars(select(ExperimentEvent.event_type).order_by(ExperimentEvent.id)).all() == [
            "queued", "paused", "queued", "cancelled"]
    engine.dispose()


def test_start_and_resume_block_changed_or_stale_evidence_without_jobs(tmp_path):
    client, engine, payload, ids = setup(tmp_path)
    draft = client.post("/api/experiments", json=payload).json()
    url = f"/api/experiments/{draft['id']}"
    assert client.post(url + "/start").status_code == 409  # unknown price
    with sessionmaker(engine).begin() as session:
        original = session.get(ModelSnapshot, ids[1])
        session.add(ModelSnapshot(provider_id=original.provider_id, model_id=original.model_id,
                                  display_name=original.model_id, endpoint_family="chat/completions",
                                  supported_parameters=["max_tokens"], pricing_source="https://example.invalid/catalog",
                                  pricing_evidence={k: "0" for k in REQUIRED}, availability="available",
                                  pricing_checked_at=datetime.now(UTC) - timedelta(hours=1)))
    assert client.post(url + "/start").status_code == 409  # latest is stale
    with Session(engine) as session:
        assert session.get(Experiment, draft["id"]).status == "draft"
        assert session.scalar(select(func.count()).select_from(GenerationJob)) == 0
        assert session.scalar(select(func.count()).select_from(ExperimentEvent)) == 0
    engine.dispose()


def test_resume_rechecks_paid_evidence_and_cancel_keeps_inflight(tmp_path):
    client, engine, payload, ids = setup(tmp_path)
    with sessionmaker(engine).begin() as session:
        old = session.get(ModelSnapshot, ids[1])
        session.add(ModelSnapshot(provider_id=old.provider_id, model_id=old.model_id, display_name=old.model_id,
                                  endpoint_family=old.endpoint_family, supported_parameters=["max_tokens"],
                                  pricing_evidence={k: "0" for k in REQUIRED}, pricing_checked_at=datetime.now(UTC),
                                  pricing_source="https://example.invalid/catalog", availability="available"))
    draft = client.post("/api/experiments", json=payload).json()
    url = f"/api/experiments/{draft['id']}"
    assert client.post(url + "/start").status_code == 200
    assert client.post(url + "/pause").status_code == 200
    with sessionmaker(engine).begin() as session:
        old = session.get(ModelSnapshot, ids[1])
        session.add(ModelSnapshot(provider_id=old.provider_id, model_id=old.model_id, display_name=old.model_id,
                                  endpoint_family=old.endpoint_family, supported_parameters=["max_tokens"],
                                  pricing_evidence={**{k: "0" for k in REQUIRED}, "request": "1"},
                                  pricing_checked_at=datetime.now(UTC),
                                  pricing_source="https://example.invalid/catalog", availability="available"))
    assert client.post(url + "/resume").status_code == 409
    with Session(engine) as session:
        assert session.get(Experiment, draft["id"]).status == "paused"
        frozen_hash = session.get(Experiment, draft["id"]).config_sha256
        job_id = session.scalar(select(GenerationJob.id).where(GenerationJob.experiment_id == draft["id"]))
    with sessionmaker(engine).begin() as session:
        session.get(GenerationJob, job_id).status = "leased"
    assert client.post(url + "/cancel").status_code == 200
    with Session(engine) as session:
        assert session.get(Experiment, draft["id"]).config_sha256 == frozen_hash
        assert session.get(GenerationJob, job_id).status == "leased"
        assert session.scalar(select(func.count()).select_from(GenerationJob).where(
            GenerationJob.experiment_id == draft["id"], GenerationJob.status == "pending")) == 0
    engine.dispose()
