import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, load_settings
from app.db import make_engine
from app.main import create_app
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
)

BACKEND = Path(__file__).resolve().parents[1]


def migrate(path: Path):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_PATH": str(path), "DEMO_DATABASE_PATH": str(path.parent / "demo.sqlite3"), "EXECUTION_MODE": "live"},
        capture_output=True,
        text=True,
        check=True,
    )
    return result


def test_fresh_migration_constraints_and_restart(tmp_path):
    path = tmp_path / "lab.sqlite3"
    migrate(path)
    settings = Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3")
    engine = make_engine(settings)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar()

    with Session(engine) as session, session.begin():
        dataset = Dataset(name="test", origin="imported")
        session.add(dataset)
        session.flush()
        version = DatasetVersion(dataset_id=dataset.id, version="v1", content_sha256="0" * 64, import_schema_version="1")
        session.add(version)
        session.flush()
        item = DatasetItem(dataset_version_id=version.id, external_id="one", task_type="short", prompt="Q?", reference_answers=["A"])
        session.add(item)
        session.flush()
        experiment = Experiment(name="draft", dataset_version_id=version.id, provenance_mode="live")
        session.add(experiment)
        session.flush()
        provider = Provider(slug="test", base_url="https://example.invalid")
        session.add(provider)
        session.flush()
        model = ModelSnapshot(provider_id=provider.id, model_id="test/model", display_name="test", endpoint_family="chat")
        session.add(model)
        session.flush()
        session.add(ExperimentModel(experiment_id=experiment.id, model_snapshot_id=model.id, slot=0))
        session.flush()
        ids = experiment.id, item.id
        session.add(GenerationJob(experiment_id=ids[0], dataset_item_id=ids[1], model_slot=0, repetition=0, execution_order=0))
    engine.dispose()

    migrate(path)  # an upgrade after restart must preserve existing data
    engine = make_engine(settings)
    with Session(engine) as session:
        assert session.execute(text("SELECT count(*) FROM generation_jobs")).scalar_one() == 1
        session.add(GenerationJob(experiment_id=ids[0], dataset_item_id=ids[1], model_slot=0, repetition=0, execution_order=1))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(GenerationJob(experiment_id=ids[0], dataset_item_id=99999, model_slot=0, repetition=0, execution_order=1))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(GenerationJob(experiment_id=ids[0], dataset_item_id=ids[1], model_slot=1, repetition=0, execution_order=1))
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_safe_config_and_api(tmp_path, monkeypatch, capsys):
    sentinel = "sentinel-secret-value-123"
    monkeypatch.setenv("OPENROUTER_API_KEY", sentinel)
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", sentinel)
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "not-a-timeout")
    with pytest.raises(RuntimeError, match="request_timeout_seconds") as exc:
        load_settings()
    assert sentinel not in str(exc.value) + capsys.readouterr().err
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "60")
    settings = Settings(database_path=tmp_path / "live.sqlite3", demo_database_path=tmp_path / "demo.sqlite3")
    settings.check_storage()
    migrate(settings.active_database_path)
    with TestClient(create_app(settings), base_url="http://localhost") as client:
        health = client.get("/api/health")
        assert health.json() == {"status": "ok", "database": "reachable"}
        response = client.get("/api/settings")
        assert response.json()["providers_configured"] == {"openrouter": True, "opencode_zen": True}
        assert sentinel not in response.text + health.text + capsys.readouterr().err
        assert client.get("/api/settings", headers={"host": "external.example"}).status_code == 400

    monkeypatch.setenv("FREE_ONLY", "false")
    with pytest.raises(RuntimeError, match="free_only") as exc:
        load_settings()
    assert sentinel not in str(exc.value)
    monkeypatch.setenv("FREE_ONLY", "true")
    assert load_settings().free_only is True


def test_storage_and_mode_are_separate(tmp_path):
    with pytest.raises(RuntimeError, match="must differ"):
        Settings(database_path=tmp_path / "same", demo_database_path=tmp_path / "same").check_storage()
    bad_target = tmp_path / "directory.sqlite3"
    bad_target.mkdir()
    with pytest.raises(RuntimeError, match="Database directory/target"):
        Settings(database_path=bad_target, demo_database_path=tmp_path / "demo").check_storage()
    demo = Settings(execution_mode="demo", database_path=tmp_path / "live", demo_database_path=tmp_path / "demo")
    assert demo.active_database_path == tmp_path / "demo"


def test_invalid_startup_does_not_log_secrets(tmp_path):
    sentinel = "sentinel-startup-key-456"
    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app"],
        cwd=BACKEND,
        env={**os.environ, "OPENROUTER_API_KEY": sentinel, "REQUEST_TIMEOUT_SECONDS": "301", "DATABASE_PATH": str(tmp_path / "live")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "request_timeout_seconds" in result.stderr
    assert sentinel not in result.stdout + result.stderr


def test_sqlite_backup_restore_preserves_completed_experiment(tmp_path):
    source, backup = tmp_path / "source.sqlite3", tmp_path / "backup.sqlite3"
    migrate(source)
    settings = Settings(database_path=source, demo_database_path=tmp_path / "demo.sqlite3")
    engine = make_engine(settings)
    with Session(engine) as session, session.begin():
        dataset = Dataset(name="Backup", origin="original", source="test", license="CC0-1.0")
        session.add(dataset)
        session.flush()
        version = DatasetVersion(dataset_id=dataset.id, version="1", content_sha256="a" * 64,
                                 import_schema_version="1")
        session.add(version)
        session.flush()
        item = DatasetItem(dataset_version_id=version.id, external_id="question", task_type="short_factual",
                           prompt="Q", reference_answers=["A"])
        session.add(item)
        provider = Provider(slug="fixture", base_url="fixture://local")
        session.add(provider)
        session.flush()
        model = ModelSnapshot(provider_id=provider.id, model_id="fixture/a", display_name="Fixture",
                              endpoint_family="chat/completions")
        session.add(model)
        experiment = Experiment(name="completed", dataset_version_id=version.id, status="completed",
                                provenance_mode="demo", config={"attempt_cap": 1})
        session.add(experiment)
        session.flush()
        slot = ExperimentModel(experiment_id=experiment.id, model_snapshot_id=model.id, slot=0)
        session.add(slot)
        session.flush()
        job = GenerationJob(experiment_id=experiment.id, model_slot=0, dataset_item_id=item.id,
                            repetition=0, execution_order=0, status="succeeded")
        session.add(job)
        session.flush()
        attempt = RequestAttempt(job_id=job.id, attempt_number=1, outcome="succeeded",
                                 reserved_at=job.created_at)
        session.add(attempt)
        session.flush()
        session.add(ModelResponse(job_id=job.id, attempt_id=attempt.id, raw_text="A",
                                  safe_metadata={"provenance": "synthetic_fixture"}))
    # SQLite's backup API includes a consistent view even with WAL mode enabled.
    with sqlite3.connect(source) as input_db, sqlite3.connect(backup) as output_db:
        input_db.backup(output_db)
    engine.dispose()
    migrate(backup)
    restored = make_engine(Settings(database_path=backup, demo_database_path=tmp_path / "demo-restore.sqlite3"))
    with Session(restored) as session:
        assert session.scalar(text("SELECT count(*) FROM experiments")) == 1
        assert session.scalar(text("SELECT count(*) FROM model_responses")) == 1
        assert session.scalar(text("SELECT status FROM experiments")) == "completed"
        assert session.scalar(text("SELECT raw_text FROM model_responses")) == "A"
    restored.dispose()
