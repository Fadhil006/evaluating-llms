import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command

BACKEND = Path(__file__).resolve().parents[1]
OLD_REVISION = "4c9f83a1b2d0"


def test_upgrade_preserves_old_schema_records(tmp_path, monkeypatch):
    database = tmp_path / "legacy.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.sqlite3"))
    monkeypatch.setenv("EXECUTION_MODE", "live")

    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, OLD_REVISION)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO datasets (id, name, description, origin) VALUES (1, 'legacy', '', 'imported')"
        )
        connection.execute(
            "INSERT INTO dataset_versions "
            "(id, dataset_id, version, content_sha256, manifest, category_inventory, import_schema_version) "
            "VALUES (1, 1, 'v1', ?, '{}', '{}', '1')",
            ("a" * 64,),
        )
        connection.execute(
            "INSERT INTO dataset_items "
            "(id, dataset_version_id, external_id, task_type, prompt, reference_answers, scoring_config, tags) "
            "VALUES (1, 1, 'legacy-item', 'short_factual', 'Question?', '[\"Answer\"]', '{}', '[]')"
        )
        connection.execute(
            "INSERT INTO experiments "
            "(id, name, dataset_version_id, status, config_schema_version, config, provenance_mode) "
            "VALUES (1, 'legacy experiment', 1, 'completed', '1', '{}', 'live')"
        )
        connection.execute(
            "INSERT INTO experiment_models (id, experiment_id, model_snapshot_id, slot) "
            "VALUES (1, 1, 1, 0)"
        )
        connection.execute(
            "INSERT INTO providers (id, slug, base_url, credential_configured, connection_status, policy_links) "
            "VALUES (1, 'legacy', 'https://example.invalid', 0, 'unknown', '[]')"
        )
        connection.execute(
            "INSERT INTO model_snapshots "
            "(id, provider_id, model_id, display_name, endpoint_family, capabilities, "
            "supported_parameters, pricing_evidence, provider_version, availability) "
            "VALUES (1, 1, 'legacy/model', 'Legacy', 'chat', '[]', '{}', '{}', '{}', 'available')"
        )
        connection.execute(
            "INSERT INTO generation_jobs "
            "(id, experiment_id, model_slot, dataset_item_id, repetition, variant, execution_order, "
            "status, attempt_count) VALUES (1, 1, 0, 1, 0, 'original', 0, 'succeeded', 1)"
        )
        connection.execute(
            "INSERT INTO request_attempts "
            "(id, job_id, attempt_number, outcome, reserved_at, eligibility_evidence) "
            "VALUES (1, 1, 1, 'succeeded', CURRENT_TIMESTAMP, '{}')"
        )
        connection.execute(
            "INSERT INTO model_responses "
            "(id, job_id, attempt_id, raw_text, safe_metadata, identity_mismatch) "
            "VALUES (1, 1, 1, 'Legacy answer', '{}', 0)"
        )

    command.upgrade(config, "head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT split, family_id FROM dataset_items WHERE id = 1").fetchone() == (
            "legacy_unknown",
            None,
        )
        assert connection.execute("SELECT name, status FROM experiments WHERE id = 1").fetchone() == (
            "legacy experiment",
            "completed",
        )
        assert connection.execute("SELECT prompt, reference_answers FROM dataset_items WHERE id = 1").fetchone() == (
            "Question?",
            '["Answer"]',
        )
        assert connection.execute("SELECT raw_text, provenance FROM model_responses WHERE id = 1").fetchone() == (
            "Legacy answer",
            "live",
        )
        assert connection.execute("SELECT count(*) FROM generation_jobs WHERE id = 1").fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'analysis_snapshots'"
        ).fetchone() == (1,)
