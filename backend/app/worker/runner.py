"""SQLite-serialized reservations and fenced result persistence."""

import hashlib
import json
import random
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.models import (
    DatasetItem,
    Experiment,
    ExperimentEvent,
    ExperimentModel,
    GenerationJob,
    ModelResponse,
    ModelSnapshot,
    Provider,
    ProviderAccountState,
    RequestAttempt,
)
from app.providers.common import GenerationRequest, ProviderError
from app.providers.dispatch import adapter_entry, dispatch
from app.providers.fixture import Fixture
from app.providers.policy import decide
from app.services.experiment_design import generation_messages
from app.services.results import score_response


def utc(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def locked(sessions):
    """Acquire SQLite's writer lock before reading shared limits/leases."""
    session = sessions()
    try:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        return session
    except BaseException:
        session.close()
        raise


def event(session, experiment_id, kind, **details):
    session.add(ExperimentEvent(experiment_id=experiment_id, event_type=kind, details=details))


def finish(session, experiment_id):
    row = session.get(Experiment, experiment_id)
    if row.status not in {"queued", "running"}:
        return
    states = session.scalars(select(GenerationJob.status).where(GenerationJob.experiment_id == experiment_id)).all()
    if states and all(state in {"succeeded", "failed", "cancelled"} for state in states):
        row.status = "completed_with_errors" if "failed" in states or "cancelled" in states else "completed"
        event(session, experiment_id, row.status)


class Worker:
    def __init__(self, sessions: sessionmaker, adapters: dict, *, clock=None, rng=None, monotonic=None,
                 manual_cap=40, spacing_seconds=4, owner=None, execution_mode="live"):
        self.sessions = sessions
        self.adapters = adapters
        self.clock = clock or (lambda: datetime.now(UTC))
        self.rng = rng or random.Random()
        self.monotonic = monotonic or time.monotonic
        self.manual_cap = manual_cap
        self.spacing = spacing_seconds
        self.execution_mode = execution_mode
        self.owner = owner or uuid4().hex

    def recover(self):
        with locked(self.sessions) as session:
            now = self.clock()
            for job in session.scalars(select(GenerationJob).where(
                    GenerationJob.status == "leased", GenerationJob.lease_expires_at <= now)).all():
                if session.scalar(select(ModelResponse.id).where(ModelResponse.job_id == job.id)):
                    job.status = "succeeded"
                else:
                    attempt = session.scalar(select(RequestAttempt).where(RequestAttempt.job_id == job.id)
                                             .order_by(RequestAttempt.attempt_number.desc()))
                    if attempt and attempt.outcome == "reserved" and attempt.dispatched_at is None:
                        attempt.outcome = "unsent"
                        slot = session.scalar(select(ExperimentModel).where(
                            ExperimentModel.experiment_id == job.experiment_id,
                            ExperimentModel.slot == job.model_slot))
                        provider_id = session.get(ModelSnapshot, slot.model_snapshot_id).provider_id
                        account = session.scalar(select(ProviderAccountState).where(
                            ProviderAccountState.provider_id == provider_id))
                        if account and account.request_day == utc(attempt.reserved_at).date().isoformat():
                            account.request_count = max(0, account.request_count - 1)
                        job.attempt_count -= 1
                        job.status = "pending"
                    else:
                        if attempt and attempt.outcome == "dispatched":
                            attempt.outcome = "unknown_remote_outcome"
                        job.status = "interrupted"
                        row = session.get(Experiment, job.experiment_id)
                        if row.status in {"queued", "running"}:
                            row.status, row.pause_reason = "interrupted", "unknown_remote_outcome"
                        event(session, job.experiment_id, "interrupted", job_id=job.id)
                job.lease_token = job.lease_owner = job.lease_expires_at = None
            session.commit()

    def claim(self):
        with locked(self.sessions) as session:
            now = self.clock()
            # Global single-flight, including a different worker process.
            if session.scalar(select(GenerationJob.id).where(
                    GenerationJob.status == "leased", GenerationJob.lease_expires_at > now).limit(1)):
                session.commit()
                return None
            jobs = session.scalars(select(GenerationJob).join(
                Experiment, Experiment.id == GenerationJob.experiment_id).where(
                GenerationJob.status.in_(["pending", "retry-wait"]),
                (GenerationJob.next_eligible_at.is_(None) | (GenerationJob.next_eligible_at <= now)),
                Experiment.status.in_(["queued", "running"])
            ).order_by(Experiment.id, GenerationJob.execution_order)).all()
            for job in jobs:
                exp = session.get(Experiment, job.experiment_id)
                if exp.provenance_mode != self.execution_mode:
                    exp.status, exp.pause_reason = "paused", "execution_mode_mismatch"
                    event(session, exp.id, "paused", reason=exp.pause_reason)
                    continue
                if job.attempt_count >= 1 + exp.config["retries_per_job"]:
                    job.status = "failed"
                    finish(session, exp.id)
                    continue
                used = session.scalar(select(func.count(RequestAttempt.id)).join(GenerationJob).where(
                    GenerationJob.experiment_id == exp.id, RequestAttempt.outcome != "unsent"))
                if used >= exp.config["attempt_cap"]:
                    exp.status, exp.pause_reason = "paused", "experiment_cap"
                    event(session, exp.id, "paused", reason="experiment_cap")
                    continue
                slot = session.scalar(select(ExperimentModel).where(
                    ExperimentModel.experiment_id == exp.id, ExperimentModel.slot == job.model_slot))
                snapshot = session.get(ModelSnapshot, slot.model_snapshot_id)
                provider = session.get(Provider, snapshot.provider_id)
                if (provider.slug == "fixture" and (exp.provenance_mode != "demo"
                        or snapshot.model_id not in {"fixture/alpha-v1", "fixture/beta-v1"}
                        or snapshot.pricing_evidence != {"provenance": "synthetic_fixture"}
                        or snapshot.pricing_source != "fixture://local")):
                    exp.status, exp.pause_reason = "paused", "fixture_demo_only"
                    event(session, exp.id, "paused", reason=exp.pause_reason)
                    continue
                if exp.provenance_mode == "demo" and provider.slug != "fixture":
                    exp.status, exp.pause_reason = "paused", "demo_fixture_required"
                    event(session, exp.id, "paused", reason=exp.pause_reason)
                    continue
                account = session.scalar(select(ProviderAccountState).where(
                    ProviderAccountState.provider_id == provider.id))
                if account is None:
                    account = ProviderAccountState(provider_id=provider.id, request_day=now.date().isoformat(),
                                                   request_count=0)
                    session.add(account)
                    session.flush()
                if account.request_day != now.date().isoformat():
                    account.request_day, account.request_count = now.date().isoformat(), 0
                if (account.quota_limit is not None and account.quota_used is not None
                        and utc(account.quota_observed_at) is not None
                        and utc(account.quota_observed_at).date() == now.date()):
                    local_since_observation = max(0, account.request_count - account.quota_app_count)
                    if account.quota_used + local_since_observation >= account.quota_limit:
                        exp.status, exp.pause_reason = "paused", "quota"
                        event(session, exp.id, "paused", reason="quota",
                              quota_source=account.quota_source, observed_at=utc(account.quota_observed_at).isoformat())
                        continue
                if account.request_count >= self.manual_cap:
                    exp.status, exp.pause_reason = "paused", "manual_cap"
                    event(session, exp.id, "paused", reason="manual_cap")
                    continue
                if utc(account.cooldown_until) and utc(account.cooldown_until) > now:
                    continue
                token = uuid4().hex
                changed = session.execute(update(GenerationJob).where(
                    GenerationJob.id == job.id, GenerationJob.status == job.status,
                    GenerationJob.attempt_count == job.attempt_count).values(
                    status="leased", lease_owner=self.owner, lease_token=token,
                    lease_expires_at=now + timedelta(seconds=exp.config["timeout_seconds"] + 60),
                    attempt_count=job.attempt_count + 1))
                if changed.rowcount != 1:
                    continue
                account.request_count += 1
                if self.spacing and exp.provenance_mode != "demo":
                    account.cooldown_until = now + timedelta(seconds=self.spacing)
                last_number = session.scalar(select(func.max(RequestAttempt.attempt_number)).where(
                    RequestAttempt.job_id == job.id)) or 0
                attempt = RequestAttempt(job_id=job.id, attempt_number=last_number + 1,
                                         outcome="reserved", reserved_at=now)
                session.add(attempt)
                if exp.status == "queued":
                    exp.status = "running"
                session.flush()
                result = (job.id, attempt.id, token, provider.slug, snapshot.model_id)
                session.commit()
                return result
            session.commit()
        return None

    def step(self):
        self.recover()
        claimed = self.claim()
        if not claimed:
            return False
        job_id, attempt_id, token, slug, model_id = claimed
        with self.sessions() as session:
            job = session.get(GenerationJob, job_id)
            exp = session.get(Experiment, job.experiment_id)
            item = session.get(DatasetItem, job.dataset_item_id)
            request = GenerationRequest(model_id, generation_messages(exp.config["system_prompt"], vars(item)),
                                        exp.config["max_tokens"], exp.config["temperature"],
                                        timeout_seconds=exp.config["timeout_seconds"],
                                        provenance="synthetic_fixture" if exp.provenance_mode == "demo" else "live")
            fingerprint = hashlib.sha256(json.dumps(vars(request), sort_keys=True).encode()).hexdigest()
        with locked(self.sessions) as session:
            job = session.get(GenerationJob, job_id)
            exp = session.get(Experiment, job.experiment_id)
            attempt = session.get(RequestAttempt, attempt_id)
            if job.lease_token != token or exp.status not in {"running", "queued"}:
                attempt.outcome = "unsent"
                job.status = "cancelled" if exp.status == "cancelled" else "pending"
                job.lease_token = job.lease_owner = job.lease_expires_at = None
                job.attempt_count -= 1
                provider = session.scalar(select(Provider).where(Provider.slug == slug))
                account = session.scalar(select(ProviderAccountState).where(ProviderAccountState.provider_id == provider.id))
                if account.request_day == self.clock().date().isoformat():
                    account.request_count -= 1
                session.commit()
                return True
            snapshot = session.scalar(select(ModelSnapshot).join(Provider).where(
                Provider.slug == slug, ModelSnapshot.model_id == model_id).order_by(ModelSnapshot.id.desc()))
            demo = exp.provenance_mode == "demo"
            synthetic = (demo and slug == "fixture" and snapshot is not None
                         and model_id in {"fixture/alpha-v1", "fixture/beta-v1"}
                         and snapshot.pricing_evidence == {"provenance": "synthetic_fixture"}
                         and snapshot.pricing_source == "fixture://local")
            decision = (None if synthetic else decide(slug, adapter_entry(snapshot), utc(snapshot.pricing_checked_at),
                               self.clock(), request)) if snapshot else None
            if snapshot is None or (not synthetic and not snapshot.pricing_source) or (
                not synthetic and snapshot.pricing_expires_at and utc(snapshot.pricing_expires_at) <= self.clock()
            ) or snapshot.endpoint_family != exp.config["models"][job.model_slot]["endpoint"] or (
                (not synthetic and not decision.allowed) or (not synthetic and not self.adapters[slug].headers)):
                attempt.outcome = "unsent"
                job.status = "pending"
                job.attempt_count -= 1
                job.lease_token = job.lease_owner = job.lease_expires_at = None
                exp.status, exp.pause_reason = "paused", "stale_pricing_or_route"
                provider = session.scalar(select(Provider).where(Provider.slug == slug))
                account = session.scalar(select(ProviderAccountState).where(
                    ProviderAccountState.provider_id == provider.id))
                if account.request_day == utc(attempt.reserved_at).date().isoformat():
                    account.request_count = max(0, account.request_count - 1)
                event(session, exp.id, "paused", reason=exp.pause_reason)
                session.commit()
                return True
            attempt.eligibility_evidence = ({"snapshot_id": snapshot.id, "provenance": "synthetic_fixture",
                                             "decision": {"allowed": True, "reason": "synthetic_fixture"}}
                                            if synthetic else {"snapshot_id": snapshot.id, "pricing": snapshot.pricing_evidence,
                                            "source": snapshot.pricing_source,
                                            "checked_at": utc(snapshot.pricing_checked_at).isoformat() if snapshot.pricing_checked_at else None,
                                             "decision": decision.evidence()})
            attempt.request_fingerprint = fingerprint
            attempt.outcome, attempt.dispatched_at = "dispatched", self.clock()
            session.commit()
        started = self.monotonic()

        def record_authorized(evidence):
            with locked(self.sessions) as session:
                job = session.get(GenerationJob, job_id)
                exp = session.get(Experiment, job.experiment_id)
                attempt = session.get(RequestAttempt, attempt_id)
                if job.lease_token != token or exp.status not in {"running", "queued"}:
                    raise ProviderError("dispatch_cancelled", evidence=evidence)
                attempt.eligibility_evidence = evidence
                session.commit()

        try:
            # This central resolver checks the latest persisted price immediately before HTTP.
            with self.sessions() as session:
                chosen = Fixture() if demo else self.adapters[slug]
                response = dispatch(session, chosen, request, on_authorized=record_authorized, demo=demo)
            error = None
        except ProviderError as exc:
            response, error = None, exc
        except Exception:  # noqa: BLE001 - never persist a raw provider/transport exception
            response, error = None, ProviderError("upstream_unavailable")
        duration = max(0, int((self.monotonic() - started) * 1000))
        with locked(self.sessions) as session:
            job = session.get(GenerationJob, job_id)
            if job.lease_token != token or job.status != "leased":
                session.commit()
                return True
            attempt = session.get(RequestAttempt, attempt_id)
            exp = session.get(Experiment, job.experiment_id)
            attempt.duration_ms, attempt.completed_at = duration, self.clock()
            if response is not None and demo and response.metadata.get("provenance") != "synthetic_fixture":
                response, error = None, ProviderError("fixture_provenance_missing")
            if response is not None:
                attempt.outcome, attempt.provider_response_id = "succeeded", response.response_id
                saved = ModelResponse(job_id=job.id, attempt_id=attempt.id, raw_text=response.text,
                                      returned_identity=response.model_id, finish_reason=response.finish_reason,
                                      usage=response.usage, safe_metadata=response.metadata,
                                       identity_mismatch=response.model_id != model_id,
                                       provenance="synthetic_fixture" if demo else "live")
                session.add(saved)
                job.status = "succeeded"
                event(session, exp.id, "response_saved", job_id=job.id)
                session.flush()
                try:
                    with session.begin_nested():
                        score_response(session, saved)
                except Exception:  # noqa: BLE001 - scoring must not roll back an accepted response
                    event(session, exp.id, "scoring_failed", job_id=job.id)
            else:
                status = error.status
                attempt.error_code, attempt.retry_after = error.code[:80], error.retry_after
                if error.evidence is not None:
                    attempt.eligibility_evidence = error.evidence
                local_rejection = status is None and error.code not in {"upstream_unavailable", "invalid_response"}
                attempt.outcome = ("unsent" if local_rejection else "failed" if status in {400, 401, 402, 403, 404, 422}
                                   else "unknown_remote_outcome")
                if local_rejection:
                    provider = session.scalar(select(Provider).where(Provider.slug == slug))
                    account = session.scalar(select(ProviderAccountState).where(
                        ProviderAccountState.provider_id == provider.id))
                    if account.request_day == utc(attempt.reserved_at).date().isoformat():
                        account.request_count = max(0, account.request_count - 1)
                    job.attempt_count -= 1
                reason = ({401: "credentials", 402: "quota", 404: "unavailable_model"}.get(status)
                          or ("rate_limit" if status == 429 else None))
                if exp.status == "cancelled":
                    job.status = "cancelled"
                elif reason or local_rejection:
                    exp.status, exp.pause_reason = "paused", reason or error.code
                    event(session, exp.id, "paused", reason=exp.pause_reason)
                if exp.status == "cancelled":
                    pass
                elif status in {400, 401, 402, 403, 404, 422} or error.code in {"invalid_response", "credentials_unavailable"}:
                    job.status = "failed" if status in {400, 403, 422} or error.code == "invalid_response" else "pending"
                elif local_rejection:
                    job.status = "pending"
                elif job.attempt_count <= exp.config["retries_per_job"]:
                    delay = min(300, 2 ** min(job.attempt_count, 8)) + self.rng.random()
                    job.next_eligible_at = max(self.clock() + timedelta(seconds=delay),
                                               utc(error.retry_after) or self.clock())
                    job.status = "retry-wait"
                else:
                    job.status = "failed"
                if status == 429:
                    provider = session.scalar(select(Provider).where(Provider.slug == slug))
                    account = session.scalar(select(ProviderAccountState).where(
                        ProviderAccountState.provider_id == provider.id))
                    account.cooldown_until = job.next_eligible_at or error.retry_after
                event(session, exp.id, "attempt_failed", job_id=job.id, code=attempt.error_code)
            job.lease_token = job.lease_owner = job.lease_expires_at = None
            finish(session, exp.id)
            session.commit()
        return True
