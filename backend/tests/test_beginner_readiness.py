from sqlalchemy import select
from sqlalchemy.orm import Session
from test_experiments import setup

from app.models import ModelSnapshot, Provider
from app.providers.policy import REQUIRED


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
