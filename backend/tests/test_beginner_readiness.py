import os
import subprocess
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_experiments import setup

from app.models import ModelSnapshot, Provider
from app.providers.policy import REQUIRED


def test_external_env_file_loads_legacy_key_without_copying_secrets(tmp_path):
    env_file = tmp_path / "provider.env"
    env_file.write_text("OPENCODE_API_KEY=test-only-legacy\nOPENROUTER_API_KEY=test-only-router\n")
    env = {key: value for key, value in os.environ.items()
           if key not in {"OPENCODE_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENROUTER_API_KEY"}}
    env["LCLAB_ENV_FILE"] = str(env_file)
    result = subprocess.run([sys.executable, "-c", ("from app.config import Settings; s=Settings(); "
                             "assert s.opencode_zen_api_key.get_secret_value() == 'test-only-legacy'; "
                             "assert s.openrouter_api_key.get_secret_value() == 'test-only-router'")],
                            env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert result.stdout == ""


def test_estimate_requires_live_credentials_and_demo_is_fixture_only(tmp_path):
    client, engine, payload, _ = setup(tmp_path)
    try:
        with Session(engine) as session:
            provider = session.scalar(select(Provider))
            provider.credential_configured = False
            for model in session.scalars(select(ModelSnapshot)):
                model.pricing_evidence = {key: "0" for key in REQUIRED}
            session.commit()
        assert client.post("/api/experiments/estimate", json=payload).json()["ready"] is False
        client.app.state.execution_mode = "demo"
        assert client.post("/api/experiments/estimate", json=payload).json()["ready"] is False
        with Session(engine) as session:
            session.scalar(select(Provider)).slug = "fixture"
            session.commit()
        estimate = client.post("/api/experiments/estimate", json=payload).json()
        assert estimate["ready"] is True
        assert {decision["reason"] for decision in estimate["policy_decisions_advisory"]} == {"synthetic_fixture"}
        assert client.post("/api/experiments", json=payload).json()["ready"] is True
        client.app.state.execution_mode = "live"
        assert client.post("/api/experiments/estimate", json=payload).json()["ready"] is False
    finally:
        engine.dispose()
