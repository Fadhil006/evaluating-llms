"""Independent read-only worker progress router."""

from collections import Counter

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from app.models import Experiment, GenerationJob, ProviderAccountState, RequestAttempt

router = APIRouter(prefix="/api/experiments", tags=["worker"])


@router.get("/{experiment_id}/progress")
def progress(request: Request, experiment_id: int):
    with request.app.state.sessions() as session:
        exp = session.get(Experiment, experiment_id)
        if exp is None:
            raise HTTPException(404, "Experiment not found")
        counts = Counter(session.scalars(select(GenerationJob.status).where(
            GenerationJob.experiment_id == experiment_id)))
        used = session.scalar(select(func.count(RequestAttempt.id)).join(GenerationJob).where(
            GenerationJob.experiment_id == experiment_id, RequestAttempt.outcome != "unsent"))
        accounts = session.scalars(select(ProviderAccountState)).all()
        return {"status": exp.status, "pause_reason": exp.pause_reason,
                "completed": counts["succeeded"], "failed": counts["failed"],
                "pending": counts["pending"] + counts["retry-wait"] + counts["interrupted"],
                "in_flight": counts["leased"], "cancelled": counts["cancelled"],
                "attempts_consumed": used, "attempts_remaining": max(0, exp.config.get("attempt_cap", 0) - used),
                 "accounts": [{"provider_id": a.provider_id, "request_day": a.request_day,
                               "application_attempts": a.request_count,
                               "quota": ({"limit": a.quota_limit, "used_at_observation": a.quota_used,
                                         "observed_at": a.quota_observed_at, "source": a.quota_source}
                                        if a.quota_limit is not None and a.quota_used is not None else "unknown"),
                               "cooldown_until": a.cooldown_until} for a in accounts]}
