from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from test_experiments import setup

from app.config import Settings
from app.main import create_app
from app.models import Experiment, GenerationJob, ModelResponse, ModelSnapshot, Provider
from app.providers.catalog import refresh
from app.providers.fixture import Fixture
from app.worker.runner import Worker


def test_demo_catalog_execution_and_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.httpx.Client", lambda **kwargs: (_ for _ in ()).throw(AssertionError("HTTPX used")))
    demo_db, live_db = tmp_path / "demo-run.sqlite3", tmp_path / "live.sqlite3"
    from test_foundation import migrate
    migrate(demo_db)
    app = create_app(Settings(execution_mode="demo", demo_database_path=demo_db, database_path=live_db))
    client = TestClient(app, base_url="http://localhost")
    refreshed = client.post("/api/models/refresh")
    assert refreshed.status_code == 200
    assert list(refreshed.json()) == ["fixture"]
    assert refreshed.json()["fixture"]["models"] == 2
    assert client.post("/api/providers/openrouter/check").json()["status"] == "disabled_in_demo"
    rows = client.get("/api/models").json()
    assert len(rows) == 2 and all("DEMONSTRATION" in row["name"] for row in rows)
    ids = [row["id"] for row in rows]
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Provider).where(Provider.slug == "openrouter")) == 0
    # The built-in CC0 dataset endpoint remains independent of provider fixtures.
    assert client.post("/api/datasets/built-in").status_code == 201
    with app.state.sessions() as session:
        from app.models import DatasetVersion
        version_id = session.scalar(select(DatasetVersion.id).order_by(DatasetVersion.id.desc()))
    draft = client.post("/api/experiments", json={"name": "Synthetic run", "dataset_version_id": version_id,
        "model_snapshot_ids": ids, "item_ids": [f"demo-{n}" for n in range(10)], "attempt_cap": 20})
    # Replace selected item IDs with actual built-in IDs.
    assert draft.status_code == 422
    with app.state.sessions() as session:
        from app.models import DatasetItem
        version = session.scalar(select(DatasetVersion).order_by(DatasetVersion.id.desc()))
        item_ids = [row.external_id for row in session.scalars(select(DatasetItem).where(
            DatasetItem.dataset_version_id == version.id).limit(10))]
    draft = client.post("/api/experiments", json={"name": "Synthetic run", "dataset_version_id": version_id,
        "model_snapshot_ids": ids, "item_ids": item_ids, "attempt_cap": 20}).json()
    assert client.post(f"/api/experiments/{draft['id']}/start").status_code == 200
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(GenerationJob)) == 20
    worker = Worker(app.state.sessions, {}, spacing_seconds=4, execution_mode="demo")
    while worker.step():
        pass
    with app.state.sessions() as session:
        experiment = session.get(Experiment, draft["id"])
        responses = session.scalars(select(ModelResponse)).all()
        assert experiment.status == "completed"
        assert len(responses) == 20
        assert all(row.provenance == "synthetic_fixture" and
                   row.safe_metadata["provenance"] == "synthetic_fixture" and
                    row.raw_text == "DEMONSTRATION — synthetic fixture response." for row in responses)
    assert not live_db.exists()


def test_live_fixture_forbidden_and_real_free_policy_unchanged(tmp_path):
    client, engine, payload, _ = setup(tmp_path)
    fixture = Fixture()
    with sessionmaker(engine).begin() as session:
        refresh(session, fixture, fixture.catalog())
        ids = session.scalars(select(ModelSnapshot.id).join(Provider).where(Provider.slug == "fixture")).all()
    response = client.post("/api/experiments", json=payload | {"model_snapshot_ids": ids,
                                                               "item_ids": ["item-01", "item-02"]})
    assert response.status_code == 201
    assert client.post(f"/api/experiments/{response.json()['id']}/start").status_code == 409
    engine.dispose()
