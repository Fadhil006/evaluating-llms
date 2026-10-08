"""Synthetic HTTP contracts; no provider credentials or live network."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_foundation import migrate

from app.config import Settings
from app.db import make_engine
from app.main import create_app
from app.models import ModelSnapshot, Provider
from app.providers.common import CatalogEntry, GenerationRequest, ProviderError
from app.providers.dispatch import dispatch
from app.providers.fixture import Fixture
from app.providers.openrouter import OpenRouter
from app.providers.policy import decide
from app.providers.zen import Zen
from app.providers.zen_pricing import ZEN_PRICING_EXPIRES_AT, ZEN_PRICING_SOURCE
from app.providers.zen_pricing import evidence as zen_evidence

NOW = datetime.now(UTC)
ZEN_NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)
ZERO = {key: "0" for key in ("prompt", "completion", "request", "input_cache_read", "input_cache_write", "internal_reasoning")}
ENTRY = CatalogEntry("vendor/model:free", "Test", "chat/completions", 8192, ("max_tokens",), ZERO)
REQUEST = GenerationRequest(ENTRY.model_id, (("user", "hello"),))


@pytest.mark.parametrize(("price", "reason"), [
    ({}, "unknown_pricing"), ({**ZERO, "prompt": "0.00001"}, "nonzero_or_invalid_pricing"),
    ({**ZERO, "request": "NaN"}, "nonzero_or_invalid_pricing"),
    ({**ZERO, "input_cache_read": "0.00001"}, "nonzero_or_invalid_pricing"),
    ({**ZERO, "internal_reasoning": "0.00001"}, "nonzero_or_invalid_pricing"),
    ({**ZERO, "overrides": [{"completion": "0.1"}]}, "conditional_pricing"),
    ({**ZERO, "unexpected_fee": "0"}, "unknown_pricing"),
])
def test_pricing_fail_closed(price, reason):
    entry = CatalogEntry(ENTRY.model_id, ENTRY.name, ENTRY.endpoint, None, ENTRY.supported_parameters, price)
    assert decide("openrouter", entry, NOW, NOW, REQUEST).reason == reason


def test_zero_and_stale_and_unsupported():
    assert decide("openrouter", ENTRY, NOW, NOW, REQUEST).allowed
    assert decide("openrouter", ENTRY, NOW - timedelta(minutes=16), NOW).reason == "stale_pricing"
    assert decide("opencode_zen", ENTRY, NOW, NOW).reason == "official_price_evidence_required"
    assert decide("openrouter", CatalogEntry("openrouter/free", "alias", "chat/completions", None, (), ZERO), NOW, NOW).reason == "unstable_identity"
    assert decide("openrouter", CatalogEntry(ENTRY.model_id, ENTRY.name, ENTRY.endpoint, None,
                 ENTRY.supported_parameters, {"prompt": "0", "completion": "0", "image": "0.2"}),
                 NOW, NOW, REQUEST).allowed
    assert decide("openrouter", CatalogEntry("vendor/other", "Other", "chat/completions", None,
                 ENTRY.supported_parameters, {"prompt": "0", "completion": "0"}),
                 NOW, NOW, GenerationRequest("vendor/other", (("user", "hi"),))).allowed
    assert decide("openrouter", CatalogEntry(ENTRY.model_id, ENTRY.name, ENTRY.endpoint, None,
                 ENTRY.supported_parameters, {}, is_free=True), NOW, NOW, REQUEST).allowed


def test_zen_dated_free_allowlist_and_expiry():
    free = CatalogEntry("big-pickle", "Big Pickle", "chat/completions", None, ("max_tokens",),
                        zen_evidence("big-pickle"), pricing_source=ZEN_PRICING_SOURCE,
                        pricing_expires_at=ZEN_PRICING_EXPIRES_AT)
    request = GenerationRequest(free.model_id, (("user", "hi"),), max_tokens=128)
    assert decide("opencode_zen", free, ZEN_NOW, ZEN_NOW, request).allowed
    stale = ZEN_PRICING_EXPIRES_AT
    assert decide("opencode_zen", free, stale - timedelta(minutes=1), stale, request).reason == "stale_pricing"
    assert decide("opencode_zen", CatalogEntry("big-pickle", "Big Pickle", "responses", None, (),
                 zen_evidence("big-pickle"), pricing_source=ZEN_PRICING_SOURCE,
                 pricing_expires_at=ZEN_PRICING_EXPIRES_AT), ZEN_NOW, ZEN_NOW).reason == "unsupported_endpoint"
    changed = {**zen_evidence("big-pickle"), "prompt": "0.1"}
    assert decide("opencode_zen", CatalogEntry("big-pickle", "Big Pickle", "chat/completions", None,
                 ("max_tokens",), changed, pricing_source=ZEN_PRICING_SOURCE,
                 pricing_expires_at=ZEN_PRICING_EXPIRES_AT), ZEN_NOW, ZEN_NOW).reason == "official_price_evidence_required"
    assert not zen_evidence("gpt-6-luna")


def test_openrouter_transport_payload_quota_and_errors():
    captured = []

    def respond(request):
        captured.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": ENTRY.model_id, "pricing": ZERO, "is_free": True, "supported_parameters": ["max_tokens"], "context_length": 8192, "architecture": {"output_modalities": ["text", "image"]}}]})
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {"free_model_daily_requests": {"limit": 20, "used": 3}, "usage_daily": 3, "limit": 100}})
        return httpx.Response(200, json={"id": "reply", "model": ENTRY.model_id, "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenRouter("test-secret", client)
        catalog_entry = adapter.catalog()[0]
        assert catalog_entry.pricing == ZERO and catalog_entry.is_free
        assert catalog_entry.endpoint == "chat/completions"
        assert adapter.quota().free_used == 3
        assert adapter.generate(REQUEST, ENTRY, NOW).text == "ok"
    payload = __import__("json").loads(captured[-1].content)
    assert set(payload) == {"model", "messages", "max_tokens", "stream", "provider"}
    assert payload["provider"] == {"allow_fallbacks": False, "require_parameters": True, "max_price": {"prompt": "0", "completion": "0", "request": "0", "image": "0"}}
    assert all("test-secret" not in str(value) for value in (payload,))
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(429, text="test-secret"))) as client:
        with pytest.raises(ProviderError, match="http_429") as error:
            OpenRouter("test-secret", client).catalog()
        assert "test-secret" not in str(error.value)
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"data": {"usage_daily": 4, "limit": 100}}))) as client:
        assert OpenRouter("secret", client).quota().free_used is None


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_status_errors_are_sanitized(status):
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, text="secret-in-upstream-body"))) as client:
        with pytest.raises(ProviderError, match=f"http_{status}") as exc:
            OpenRouter("secret", client).catalog()
        assert "secret-in-upstream-body" not in str(exc.value)


def test_unavailable_and_malformed_catalog():
    with (
        httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"data": "not models"}))) as client,
        pytest.raises(ProviderError, match="invalid_catalog"),
    ):
        OpenRouter("secret", client).catalog()
    unavailable = CatalogEntry(ENTRY.model_id, ENTRY.name, ENTRY.endpoint, None, (), ZERO, available=False)
    assert decide("openrouter", unavailable, NOW, NOW).reason == "unavailable"


def test_zen_endpoint_support_and_no_dispatch(monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return ZEN_NOW

    monkeypatch.setattr("app.providers.policy.datetime", FrozenDateTime)
    captured = []

    def respond(req):
        captured.append(req)
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "big-pickle"}, {"id": "muse-spark-1.3-contributor-free"}, {"id": "jev-1.13-free"}, {"id": "gpt-6-sol"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = Zen("secret", client)
        entries = adapter.catalog()
        assert [e.endpoint for e in entries] == ["chat/completions", "unsupported", "unsupported", "unsupported"]
        assert entries[0].pricing_source == ZEN_PRICING_SOURCE
        assert entries[0].supported_parameters == ("max_tokens",)
        assert decide("opencode_zen", entries[0], ZEN_NOW, ZEN_NOW,
                      GenerationRequest("big-pickle", (("user", "hi"),), max_tokens=64)).allowed
        assert adapter.generate(GenerationRequest("big-pickle", (("user", "hi"),), max_tokens=64),
                                entries[0], ZEN_NOW).text == "ok"
        assert captured[-1].url.path.endswith("/chat/completions")
        assert adapter.quota() is None
        with pytest.raises(ProviderError, match="unsupported_endpoint"):
            adapter.generate(GenerationRequest("gpt-6-sol", (("user", "hi"),)), entries[3], NOW)


def test_zen_allowlisted_free_model_requires_server_key():
    captured = []
    with httpx.Client(transport=httpx.MockTransport(lambda req: captured.append(req) or httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}))) as client:
        adapter = Zen("", client)
        entry = CatalogEntry("big-pickle", "Big Pickle", "chat/completions", None, ("max_tokens",),
                             zen_evidence("big-pickle"), pricing_source=ZEN_PRICING_SOURCE,
                             pricing_expires_at=ZEN_PRICING_EXPIRES_AT)
        request = GenerationRequest("big-pickle", (("user", "hi"),), max_tokens=64)
        with pytest.raises(ProviderError, match="credentials_unavailable"):
            adapter.generate(request, entry, datetime.now(UTC))
    assert captured == []


def test_zen_public_catalog_exposes_only_dated_free_entries_without_key(tmp_path, monkeypatch):
    path = tmp_path / "zen.sqlite3"
    migrate(path)
    settings = Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3",
                        openrouter_api_key="", opencode_zen_api_key="")

    class Client(httpx.Client):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, transport=httpx.MockTransport(lambda req: httpx.Response(
                200, json={"data": [{"id": "big-pickle"}, {"id": "muse-spark-1.3-contributor-free"}]})), **kwargs)

    monkeypatch.setattr("app.main.httpx.Client", Client)
    with TestClient(create_app(settings), base_url="http://localhost") as api:
        result = api.post("/api/models/refresh").json()
        assert result["opencode_zen"] == {"status": "reachable", "models": 2}
        rows = api.get("/api/models").json()
        free = next(row for row in rows if row["model_id"] == "big-pickle")
        unsupported = next(row for row in rows if row["model_id"] == "muse-spark-1.3-contributor-free")
        assert free["eligibility"]["allowed"] is True
        assert unsupported["eligibility"]["reason"] == "unsupported_endpoint"
        assert api.get("/api/providers").json()[0]["credential_configured"] is False


def test_generation_uses_experiment_deadline():
    seen = []

    def respond(request):
        seen.append(request.extensions.get("timeout"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenRouter("key", client)
        request = GenerationRequest(ENTRY.model_id, (("user", "hi"),), timeout_seconds=7.5)
        adapter.generate(request, ENTRY, NOW)
    assert seen == [{"connect": 7.5, "read": 7.5, "write": 7.5, "pool": 7.5}]


def test_fixture_is_labeled_and_rejects_unknown_model():
    adapter = Fixture()
    result = adapter.generate(GenerationRequest("fixture/alpha-v1", (("user", "hi"),)), adapter.catalog()[0], NOW)
    assert result.metadata == {"provenance": "synthetic_fixture"}
    assert "DEMONSTRATION" in result.text
    with pytest.raises(ProviderError, match="unknown_fixture_model"):
        adapter.generate(REQUEST, adapter.catalog()[0], NOW)


def test_catalog_api_persists_and_blocks_paid_change(tmp_path, monkeypatch):
    path = tmp_path / "live.sqlite3"
    migrate(path)
    settings = Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3", openrouter_api_key="sentinel-secret", opencode_zen_api_key="")
    state = {"pricing": ZERO}

    def respond(request):
        return httpx.Response(200, json={"data": [{"id": ENTRY.model_id, "pricing": state["pricing"], "is_free": True, "supported_parameters": ["max_tokens"], "architecture": {"output_modalities": ["text"]}}]})

    class Client(httpx.Client):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr("app.main.httpx.Client", Client)
    with TestClient(create_app(settings), base_url="http://localhost") as api:
        assert api.post("/api/models/refresh").json()["openrouter"]["models"] == 1
        first = next(row for row in api.get("/api/models").json() if row["provider"] == "openrouter")
        assert first["eligibility"]["allowed"], first
        assert first["is_free"] is True
        assert first["pricing_evidence"] == ZERO
        state["pricing"] = {**ZERO, "completion": "1"}
        api.post("/api/models/refresh")
        current = next(row for row in api.get("/api/models").json() if row["provider"] == "openrouter")
        assert current["eligibility"]["reason"] == "nonzero_or_invalid_pricing"
        assert current["id"] != first["id"]
        assert "sentinel-secret" not in str(api.get("/api/providers").json()) + str(current)


def test_dispatch_uses_latest_persisted_evidence(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    migrate(path)
    settings = Settings(database_path=path, demo_database_path=tmp_path / "demo.sqlite3")
    engine = make_engine(settings)
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={"model": ENTRY.model_id, "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client, Session(engine) as session, session.begin():
        provider = Provider(slug="openrouter", base_url=OpenRouter.base_url)
        session.add(provider)
        session.flush()
        good = ModelSnapshot(provider_id=provider.id, model_id=ENTRY.model_id, display_name="test",
                             endpoint_family="chat/completions", capabilities={}, supported_parameters=["max_tokens"],
                             pricing_evidence=ZERO, pricing_checked_at=NOW, availability="available")
        session.add(good)
        session.flush()
        adapter = OpenRouter("test-key", client)
        assert dispatch(session, adapter, REQUEST).text == "ok"
        paid = ModelSnapshot(provider_id=provider.id, model_id=ENTRY.model_id, display_name="test",
                             endpoint_family="chat/completions", capabilities={}, supported_parameters=["max_tokens"],
                             pricing_evidence={**ZERO, "prompt": "1"}, pricing_checked_at=NOW,
                             availability="available")
        session.add(paid)
        session.flush()
        with pytest.raises(ProviderError, match="nonzero_or_invalid_pricing"):
            dispatch(session, adapter, REQUEST)
    assert len(captured) == 1
    engine.dispose()
