from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.api.datasets import router as datasets_router
from app.api.experiments import router as experiments_router
from app.api.exports import router as exports_router
from app.api.results import router as results_router
from app.api.review import router as review_router
from app.api.worker import router as worker_router
from app.config import Settings, load_settings
from app.db import make_engine
from app.models import ModelSnapshot, Provider, ProviderAccountState
from app.providers.catalog import refresh, serialize_model
from app.providers.common import ProviderError
from app.providers.fixture import Fixture
from app.providers.openrouter import OpenRouter
from app.providers.zen import Zen


class Health(BaseModel):
    status: str
    database: str


class PublicSettings(BaseModel):
    execution_mode: str
    free_only: bool
    request_timeout_seconds: int
    providers_configured: dict[str, bool]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.check_storage()
    engine = make_engine(settings)
    sessions = sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="LLM Comparison Lab", lifespan=lifespan)
    app.include_router(datasets_router)
    app.include_router(experiments_router)
    app.include_router(exports_router)
    app.include_router(results_router)
    app.include_router(worker_router)
    app.include_router(review_router)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
    app.state.sessions = sessions
    app.state.execution_mode = settings.execution_mode
    app.state.export_redactions = [key.get_secret_value() for key in
                                   (settings.openrouter_api_key, settings.opencode_zen_api_key)]

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT version_num FROM alembic_version"))
        except SQLAlchemyError:
            return Health(status="unavailable", database="unavailable")
        return Health(status="ok", database="reachable")

    @app.get("/api/settings", response_model=PublicSettings)
    def public_settings() -> PublicSettings:
        return PublicSettings(
            execution_mode=settings.execution_mode,
            free_only=settings.free_only,
            request_timeout_seconds=settings.request_timeout_seconds,
            providers_configured={
                "openrouter": bool(settings.openrouter_api_key.get_secret_value()),
                "opencode_zen": bool(settings.opencode_zen_api_key.get_secret_value()),
            },
        )

    def adapter(slug: str, client: httpx.Client):
        if slug == "fixture" and settings.execution_mode == "demo":
            return Fixture()
        if slug == "openrouter":
            return OpenRouter(settings.openrouter_api_key.get_secret_value(), client)
        if slug == "opencode_zen":
            return Zen(settings.opencode_zen_api_key.get_secret_value(), client)
        raise HTTPException(404, "Unknown provider")

    @app.get("/api/providers")
    def providers():
        with sessions() as session:
            records = {p.slug: p for p in session.scalars(select(Provider)).all()}
            result = [{"slug": slug, "credential_configured": bool(key.get_secret_value()),
                     "connection_status": records[slug].connection_status if slug in records else "unchecked",
                     "checked_at": records[slug].checked_at if slug in records else None,
                     "policy_links": {"pricing": "https://opencode.ai/docs/zen/" if slug == "opencode_zen" else "https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties"}}
                     for slug, key in (("openrouter", settings.openrouter_api_key), ("opencode_zen", settings.opencode_zen_api_key))]
            if settings.execution_mode == "demo":
                result.append({"slug": "fixture", "credential_configured": False,
                               "connection_status": "synthetic", "checked_at": None,
                               "policy_links": {}})
            return result

    @app.post("/api/models/refresh")
    def refresh_models():
        results = {}
        if settings.execution_mode == "demo":
            provider_adapter = Fixture()
            with sessions.begin() as session:
                results["fixture"] = {"status": "synthetic", "models": refresh(session, provider_adapter,
                                                                                      provider_adapter.catalog())}
            return results
        with httpx.Client(timeout=httpx.Timeout(settings.request_timeout_seconds, connect=5), follow_redirects=False) as client:
            for slug in ("openrouter", "opencode_zen"):
                provider_adapter = adapter(slug, client)
                if not provider_adapter.headers and slug != "opencode_zen":
                    results[slug] = {"status": "unconfigured"}
                    continue
                try:
                    entries = provider_adapter.catalog()
                except ProviderError as exc:
                    results[slug] = {"status": "unavailable", "reason": exc.code}
                    with sessions.begin() as session:
                        provider = session.scalar(select(Provider).where(Provider.slug == slug))
                        if provider:
                            provider.connection_status = "unavailable"
                            provider.checked_at = datetime.now(UTC)
                    continue
                with sessions.begin() as session:
                    results[slug] = {"status": "reachable", "models": refresh(session, provider_adapter, entries)}
        return results

    @app.post("/api/providers/{slug}/check")
    def check_provider(slug: str):
        if settings.execution_mode == "demo":
            if slug == "fixture":
                return {"status": "synthetic", "quota": None}
            return {"status": "disabled_in_demo", "quota": None}
        with httpx.Client(timeout=httpx.Timeout(settings.request_timeout_seconds, connect=5), follow_redirects=False) as client:
            provider_adapter = adapter(slug, client)
            if not provider_adapter.headers:
                return {"status": "unconfigured", "quota": None}
            try:
                quota = provider_adapter.quota()
            except ProviderError as exc:
                return {"status": "unavailable", "reason": exc.code, "quota": None}
            if quota is not None:
                with sessions.begin() as session:
                    provider = session.scalar(select(Provider).where(Provider.slug == slug))
                    if provider is None:
                        provider = Provider(slug=slug, base_url=provider_adapter.base_url,
                                            credential_configured=True)
                        session.add(provider)
                        session.flush()
                    state = session.scalar(select(ProviderAccountState).where(
                        ProviderAccountState.provider_id == provider.id))
                    if state is None:
                        state = ProviderAccountState(provider_id=provider.id, request_day=quota.observed_at.date().isoformat(),
                                                     request_count=0, quota_app_count=0)
                        session.add(state)
                    state.quota_observed_at = quota.observed_at
                    state.quota_source = quota.source
                    state.quota_limit = quota.free_limit
                    state.quota_used = quota.free_used
                    state.quota_app_count = state.request_count if state.request_day == quota.observed_at.date().isoformat() else 0
            return {"status": "reachable" if quota else "unknown", "quota": {"free_limit": quota.free_limit, "free_used": quota.free_used, "observed_at": quota.observed_at} if quota else None}

    @app.get("/api/models")
    def models():
        with sessions() as session:
            rows = session.execute(select(ModelSnapshot, Provider.slug, Provider.credential_configured)
                                   .join(Provider).order_by(ModelSnapshot.id.desc())).all()
            latest = {}
            now = datetime.now(UTC)
            for row, slug, credential_configured in rows:
                latest.setdefault((slug, row.model_id), serialize_model(row, slug, now, credential_configured))
            return list(latest.values())

    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (frontend / "assets").is_dir() and (frontend / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend_route(path: str):
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
