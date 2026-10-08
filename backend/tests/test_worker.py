import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from test_experiments import setup

from app.api.results import router as results_router
from app.api.worker import router
from app.models import (
    DatasetItem,
    Experiment,
    GenerationJob,
    MetricResult,
    ModelResponse,
    ModelSnapshot,
    Provider,
    ProviderAccountState,
    RequestAttempt,
)
from app.providers.common import GenerationResponse, ProviderError, get_json, parse_retry_after
from app.providers.policy import REQUIRED
from app.providers.zen import Zen
from app.providers.zen_pricing import ZEN_PRICING_EXPIRES_AT, ZEN_PRICING_SOURCE
from app.providers.zen_pricing import evidence as zen_evidence
from app.worker.runner import Worker


class Adapter:
    slug = "openrouter"
    headers: ClassVar[dict[str, str]] = {"Authorization": "test-only"}

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = 0

    def generate(self, request, entry, checked_at):
        self.calls += 1
        if self.responses:
            value = self.responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        return GenerationResponse("SECRET ANSWER", request.model_id, "response-1", "stop",
                                  {"total_tokens": 2}, {})


def trial(tmp_path, *, cap=8, retries=2, items=None):
    client, engine, payload, ids = setup(tmp_path)
    with sessionmaker(engine).begin() as session:
        for item in session.scalars(select(DatasetItem)):
            item.scoring_config = ({"metric": "normalized_exact_match"} if item.task_type == "short_factual"
                                   else {"metric": "numeric_exact", "units": "none", "absolute_tolerance": 0,
                                         "relative_tolerance": 0})
        original = session.get(ModelSnapshot, ids[1])
        session.add(ModelSnapshot(provider_id=original.provider_id, model_id=original.model_id,
                                  display_name=original.model_id, endpoint_family="chat/completions",
                                  supported_parameters=["max_tokens"],
                                  pricing_evidence={k: "0" for k in REQUIRED},
                                  pricing_source="https://example.invalid/catalog",
                                  pricing_checked_at=datetime.now(UTC), availability="available"))
    draft = client.post("/api/experiments", json=payload | {
        "item_ids": items or ["item-01", "item-03"], "attempt_cap": cap,
        "retries_per_job": retries}).json()
    assert client.post(f"/api/experiments/{draft['id']}/start").status_code == 200
    api = FastAPI()
    api.state.sessions = sessionmaker(engine)
    api.include_router(router)
    api.include_router(results_router)
    return client, TestClient(api), engine, draft["id"]


def test_results_scoring_progress_and_terminal(tmp_path):
    _, api, engine, exp_id = trial(tmp_path)
    adapter = Adapter()
    worker = Worker(sessionmaker(engine), {"openrouter": adapter}, spacing_seconds=0)
    while worker.step():
        pass
    with sessionmaker(engine)() as session:
        assert session.get(Experiment, exp_id).status == "completed"
        assert session.scalar(select(func.count()).select_from(ModelResponse)) == 4
        assert session.scalar(select(func.count()).select_from(MetricResult)) > 0
        assert session.scalar(select(func.count()).select_from(RequestAttempt)) == 4
        assert all(a.eligibility_evidence["snapshot_id"] for a in session.scalars(select(RequestAttempt)))
    progress = api.get(f"/api/experiments/{exp_id}/progress").json()
    assert (progress["completed"], progress["attempts_consumed"], progress["attempts_remaining"]) == (4, 4, 4)
    metrics = api.get(f"/api/experiments/{exp_id}/results").json()["summaries"]
    assert metrics and all(row["latency_sample_count"] == 2 for row in metrics)
    assert all(row["usage_sample_count"] == 2 and row["completion_tokens_total"] is None for row in metrics)
    assert worker.step() is False and adapter.calls == 4
    engine.dispose()


def test_global_claim_caps_and_unsent_recovery(tmp_path):
    _, _, engine, _ = trial(tmp_path)
    now = datetime.now(UTC)
    clock = lambda: now
    first = Worker(sessionmaker(engine), {"openrouter": Adapter()}, clock=clock, manual_cap=1, spacing_seconds=0)
    second = Worker(sessionmaker(engine), {"openrouter": Adapter()}, clock=clock, manual_cap=1, spacing_seconds=0)
    claim = first.claim()
    assert claim and second.claim() is None
    with sessionmaker(engine)() as session:
        assert session.scalar(select(func.count()).select_from(RequestAttempt)) == 1
    with sessionmaker(engine).begin() as session:
        session.get(GenerationJob, claim[0]).lease_expires_at = now - timedelta(seconds=1)
    second.recover()
    with sessionmaker(engine)() as session:
        assert session.get(RequestAttempt, claim[1]).outcome == "unsent"
        assert session.get(ProviderAccountState, 1).request_count == 0
    assert second.claim()
    engine.dispose()


def test_price_change_before_dispatch_releases_unsent_and_pauses(tmp_path):
    _, api, engine, exp_id = trial(tmp_path)
    adapter = Adapter()
    worker = Worker(sessionmaker(engine), {"openrouter": adapter})
    original_claim = worker.claim

    def change_price():
        claim = original_claim()
        with sessionmaker(engine).begin() as session:
            old = session.scalar(select(ModelSnapshot).where(ModelSnapshot.model_id == claim[4]).order_by(
                ModelSnapshot.id.desc()))
            session.add(ModelSnapshot(provider_id=old.provider_id, model_id=old.model_id,
                                      display_name=old.model_id, endpoint_family=old.endpoint_family,
                                      pricing_evidence={**{k: "0" for k in REQUIRED}, "request": "1"},
                                      pricing_source="https://example.invalid/catalog",
                                      pricing_checked_at=datetime.now(UTC), availability="available"))
        return claim

    worker.claim = change_price
    assert worker.step()
    assert adapter.calls == 0
    progress = api.get(f"/api/experiments/{exp_id}/progress").json()
    assert progress["status"] == "paused" and progress["attempts_consumed"] == 0
    engine.dispose()


def test_catalog_refresh_between_worker_precheck_and_dispatch_is_recorded(tmp_path, monkeypatch):
    _, api, engine, exp_id = trial(tmp_path)
    adapter = Adapter()
    worker = Worker(sessionmaker(engine), {"openrouter": adapter}, spacing_seconds=0)
    from app.providers.dispatch import dispatch as current_dispatch

    def catalog_changes_then_dispatch(session, current_adapter, request, on_authorized=None, *, demo=False):
        with sessionmaker(engine).begin() as update_session:
            old = update_session.scalar(select(ModelSnapshot).where(
                ModelSnapshot.model_id == request.model_id).order_by(ModelSnapshot.id.desc()))
            update_session.add(ModelSnapshot(provider_id=old.provider_id, model_id=old.model_id,
                                             display_name=old.model_id, endpoint_family=old.endpoint_family,
                                             supported_parameters=["max_tokens"],
                                             pricing_evidence={**{k: "0" for k in REQUIRED}, "request": "1"},
                                             pricing_source="https://example.invalid/catalog",
                                             pricing_checked_at=datetime.now(UTC), availability="available"))
        return current_dispatch(session, current_adapter, request, on_authorized, demo=demo)

    monkeypatch.setattr("app.worker.runner.dispatch", catalog_changes_then_dispatch)
    assert worker.step()
    assert adapter.calls == 0
    progress = api.get(f"/api/experiments/{exp_id}/progress").json()
    assert progress["status"] == "paused" and progress["attempts_consumed"] == 0
    with sessionmaker(engine)() as session:
        attempt = session.scalar(select(RequestAttempt).order_by(RequestAttempt.id.desc()))
        latest = session.scalar(select(ModelSnapshot).where(
            ModelSnapshot.model_id == attempt.eligibility_evidence["decision"]["model_id"])
                                 .order_by(ModelSnapshot.id.desc()))
        assert attempt.outcome == "unsent"
        assert attempt.eligibility_evidence["snapshot_id"] == latest.id
        assert attempt.eligibility_evidence["decision"]["reason"] == "nonzero_or_invalid_pricing"
    engine.dispose()


def test_retry_after_and_permanent_error(tmp_path):
    client, api, engine, exp_id = trial(tmp_path)
    now = datetime.now(UTC)
    adapter = Adapter([ProviderError("http_503", 503, now + timedelta(seconds=90)),
                       ProviderError("http_400", 400)])
    worker = Worker(sessionmaker(engine), {"openrouter": adapter}, clock=lambda: now, rng=__import__("random").Random(1))
    assert worker.step()
    with sessionmaker(engine)() as session:
        attempt = session.scalar(select(RequestAttempt))
        assert attempt.retry_after.replace(tzinfo=UTC) == now + timedelta(seconds=90)
        assert session.get(GenerationJob, attempt.job_id).status == "retry-wait"
    worker.clock = lambda: now + timedelta(seconds=91)
    assert worker.step()
    assert adapter.calls == 2
    assert api.get(f"/api/experiments/{exp_id}/progress").json()["failed"] == 1
    assert client.post(f"/api/experiments/{exp_id}/cancel").status_code == 200
    engine.dispose()


def test_http_error_normalizes_retry_after_without_body():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        429, headers={"Retry-After": "120"}, json={"secret": "never log this"})))
    try:
        get_json(client, "POST", "https://example.invalid")
        assert False
    except ProviderError as exc:
        assert exc.code == "http_429" and exc.retry_after is not None
        assert "secret" not in str(exc)
    assert parse_retry_after("Wed, 07 Oct 2026 12:00:00 GMT") == datetime(2026, 10, 7, 12, tzinfo=UTC)
    assert parse_retry_after("garbage") is None
    assert parse_retry_after("9" * 128) == datetime.max.replace(tzinfo=UTC)


def test_real_process_restart_recovers_dispatched_uncertainty(tmp_path):
    client, _, engine, exp_id = trial(tmp_path)
    path = tmp_path / "lab.sqlite3"
    code = """from datetime import UTC, datetime, timedelta
from sqlalchemy.orm import sessionmaker
from app.config import Settings
from app.db import make_engine
from app.models import GenerationJob, RequestAttempt
from app.worker.runner import Worker
engine = make_engine(Settings(database_path=__import__('os').environ['WORKER_DB']))
sessions = sessionmaker(engine)
worker = Worker(sessions, {}, spacing_seconds=0)
claim = worker.claim()
assert claim is not None
with sessions.begin() as session:
    job = session.get(GenerationJob, claim[0])
    attempt = session.get(RequestAttempt, claim[1])
    attempt.dispatched_at = datetime.now(UTC)
    attempt.outcome = 'dispatched'
    job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
"""
    subprocess.run([sys.executable, "-c", code], check=True, env=os.environ | {"WORKER_DB": str(path)})
    subprocess.run([sys.executable, "-c", """import os
from sqlalchemy.orm import sessionmaker
from app.config import Settings
from app.db import make_engine
from app.worker.runner import Worker
Worker(sessionmaker(make_engine(Settings(database_path=os.environ['WORKER_DB']))), {}).recover()
"""], check=True, env=os.environ | {"WORKER_DB": str(path)})
    with sessionmaker(engine)() as session:
        assert session.scalar(select(RequestAttempt.outcome)) == "unknown_remote_outcome"
        assert session.get(Experiment, exp_id).status == "interrupted"
    assert client.post(f"/api/experiments/{exp_id}/resume").status_code == 409
    assert client.post(f"/api/experiments/{exp_id}/resume?acknowledge_uncertain=true").status_code == 200
    adapter = Adapter()
    worker = Worker(sessionmaker(engine), {"openrouter": adapter}, spacing_seconds=0)
    while worker.step():
        pass
    with sessionmaker(engine)() as session:
        assert session.get(Experiment, exp_id).status == "completed"
        assert session.scalar(select(func.count()).select_from(ModelResponse)) == 4
        assert session.scalar(select(func.count()).select_from(RequestAttempt)) == 5
    engine.dispose()


def test_manual_cap_pause_midnight_and_identity(tmp_path):
    _, api, engine, exp_id = trial(tmp_path)
    now = datetime.now(UTC)
    adapter = Adapter([GenerationResponse("SECRET ANSWER", "unexpected-route", "id-1", "stop", None, {})])
    worker = Worker(sessionmaker(engine), {"openrouter": adapter}, clock=lambda: now,
                    manual_cap=1, spacing_seconds=0)
    assert worker.step()
    assert worker.step() is False
    status = api.get(f"/api/experiments/{exp_id}/progress").json()
    assert status["pause_reason"] == "manual_cap" and status["completed"] == 1
    with sessionmaker(engine)() as session:
        assert session.scalar(select(ModelResponse.identity_mismatch)) is True
        assert session.scalar(select(ProviderAccountState.request_count)) == 1
    worker.clock = lambda: now + timedelta(days=1)
    with sessionmaker(engine).begin() as session:
        session.get(Experiment, exp_id).status = "queued"
    # Catalog evidence is stale the next day: the account resets but dispatch fails closed.
    assert worker.step()
    with sessionmaker(engine)() as session:
        assert session.scalar(select(ProviderAccountState.request_count)) == 0
    engine.dispose()


def test_known_provider_free_quota_exhaustion_pauses_before_request(tmp_path):
    _, api, engine, exp_id = trial(tmp_path)
    now = datetime.now(UTC)
    with sessionmaker(engine).begin() as session:
        snapshot = session.scalar(select(ModelSnapshot).order_by(ModelSnapshot.id))
        provider_id = snapshot.provider_id
        session.add(ProviderAccountState(provider_id=provider_id, request_day=now.date().isoformat(),
                                         request_count=0, quota_limit=4, quota_used=4,
                                         quota_app_count=0, quota_observed_at=now,
                                         quota_source="https://openrouter.ai/api/v1/key"))
    adapter = Adapter()
    worker = Worker(sessionmaker(engine), {"openrouter": adapter}, clock=lambda: now, spacing_seconds=0)
    assert worker.step() is False
    assert adapter.calls == 0
    progress = api.get(f"/api/experiments/{exp_id}/progress").json()
    assert (progress["status"], progress["pause_reason"], progress["attempts_consumed"]) == (
        "paused", "quota", 0)
    engine.dispose()


def test_zen_allowlisted_free_route_dispatches_with_configured_key(tmp_path):
    client, engine, payload, ids = setup(tmp_path)
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={"model": "big-pickle", "choices": [
            {"message": {"content": "ok"}, "finish_reason": "stop"}]})

    with sessionmaker(engine).begin() as session:
        provider = session.scalar(select(Provider).where(Provider.slug == "openrouter"))
        provider.slug, provider.base_url, provider.credential_configured = "opencode_zen", "https://opencode.ai/zen/v1", True
        for snapshot_id, model_id in zip(ids[:2], ("big-pickle", "space-bunny-free")):
            snapshot = session.get(ModelSnapshot, snapshot_id)
            snapshot.model_id, snapshot.display_name = model_id, model_id
            snapshot.endpoint_family, snapshot.supported_parameters = "chat/completions", ["max_tokens"]
            snapshot.pricing_evidence, snapshot.pricing_source = zen_evidence(model_id), ZEN_PRICING_SOURCE
            snapshot.pricing_checked_at, snapshot.pricing_expires_at = datetime.now(UTC), ZEN_PRICING_EXPIRES_AT
    draft = client.post("/api/experiments", json=payload | {"item_ids": ["item-01"], "retries_per_job": 0,
                                                             "attempt_cap": 2}).json()
    assert client.post(f"/api/experiments/{draft['id']}/start").status_code == 200
    api = FastAPI()
    api.state.sessions = sessionmaker(engine)
    api.include_router(router)
    api.include_router(results_router)
    test_api = TestClient(api)
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        worker = Worker(sessionmaker(engine), {"opencode_zen": Zen("test-key", http)}, spacing_seconds=0)
        assert worker.step()
    assert captured[0].url.path.endswith("/chat/completions")
    assert captured[0].headers.get("authorization") == "Bearer test-key"
    with sessionmaker(engine)() as session:
        attempt = session.scalar(select(RequestAttempt).order_by(RequestAttempt.id.desc()))
        assert attempt.outcome == "succeeded" and attempt.eligibility_evidence["decision"]["allowed"]
    assert test_api.get(f"/api/experiments/{draft['id']}/progress").json()["completed"] == 1
    test_api.close()
    client.close()
    engine.dispose()


def test_zen_free_price_without_provider_key_cannot_start(tmp_path):
    client, engine, payload, ids = setup(tmp_path)
    with sessionmaker(engine).begin() as session:
        provider = session.scalar(select(Provider).where(Provider.slug == "openrouter"))
        provider.slug, provider.base_url, provider.credential_configured = "opencode_zen", "https://opencode.ai/zen/v1", False
        for snapshot_id, model_id in zip(ids[:2], ("big-pickle", "space-bunny-free")):
            snapshot = session.get(ModelSnapshot, snapshot_id)
            snapshot.model_id, snapshot.display_name = model_id, model_id
            snapshot.endpoint_family, snapshot.supported_parameters = "chat/completions", ["max_tokens"]
            snapshot.pricing_evidence, snapshot.pricing_source = zen_evidence(model_id), ZEN_PRICING_SOURCE
            snapshot.pricing_checked_at, snapshot.pricing_expires_at = datetime.now(UTC), ZEN_PRICING_EXPIRES_AT
    draft = client.post("/api/experiments", json=payload | {"item_ids": ["item-01"], "retries_per_job": 0,
                                                             "attempt_cap": 2}).json()
    response = client.post(f"/api/experiments/{draft['id']}/start")
    assert response.status_code == 409
    assert "provider key not configured" in response.json()["detail"]
    client.close()
    engine.dispose()


def test_429_pauses_and_cancel_keeps_inflight_response(tmp_path):
    client, api, engine, exp_id = trial(tmp_path)
    adapter = Adapter([ProviderError("http_429", 429, datetime.now(UTC) + timedelta(minutes=2))])
    worker = Worker(sessionmaker(engine), {"openrouter": adapter}, spacing_seconds=0)
    assert worker.step()
    assert api.get(f"/api/experiments/{exp_id}/progress").json()["pause_reason"] == "rate_limit"
    assert adapter.calls == 1 and worker.step() is False
    assert client.post(f"/api/experiments/{exp_id}/cancel").status_code == 200
    engine.dispose()


def test_cancel_during_dispatch_saves_inflight_only(tmp_path):
    client, api, engine, exp_id = trial(tmp_path)

    class CancelAdapter(Adapter):
        def generate(self, request, entry, checked_at):
            assert client.post(f"/api/experiments/{exp_id}/cancel").status_code == 200
            return super().generate(request, entry, checked_at)

    worker = Worker(sessionmaker(engine), {"openrouter": CancelAdapter()}, spacing_seconds=0)
    assert worker.step()
    progress = api.get(f"/api/experiments/{exp_id}/progress").json()
    assert progress["status"] == "cancelled" and progress["completed"] == 1
    assert progress["cancelled"] == 3
    engine.dispose()


def test_shared_account_final_allowance_and_credential_pause(tmp_path):
    client, api, engine, exp_id = trial(tmp_path)
    with sessionmaker(engine)() as session:
        first = session.get(Experiment, exp_id)
        version_id = first.dataset_version_id
        snapshots = first.config["model_snapshot_ids"]
    other = client.post("/api/experiments", json={
        "name": "Second", "dataset_version_id": version_id,
        "model_snapshot_ids": snapshots, "item_ids": ["item-05", "item-07"],
        "attempt_cap": 4,
    }).json()
    assert client.post(f"/api/experiments/{other['id']}/start").status_code == 200
    adapter = Adapter([ProviderError("http_401", 401)])
    worker = Worker(sessionmaker(engine), {"openrouter": adapter}, manual_cap=1, spacing_seconds=0)
    assert worker.step()
    assert api.get(f"/api/experiments/{exp_id}/progress").json()["pause_reason"] == "credentials"
    assert worker.step() is False
    assert api.get(f"/api/experiments/{other['id']}/progress").json()["pause_reason"] == "manual_cap"
    with sessionmaker(engine)() as session:
        assert session.scalar(select(func.count()).select_from(RequestAttempt)) == 1
        assert session.scalar(select(ProviderAccountState.request_count)) == 1
    engine.dispose()
