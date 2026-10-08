"""Read and repair locally scored experiment results (mount independently)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.models import Experiment
from app.services.results import recover_scores, response_detail, response_rows, results

router = APIRouter(prefix="/api/experiments", tags=["results"])


@router.get("/{experiment_id}/results")
def get_results(request: Request, experiment_id: int, model_slot: Annotated[list[int] | None, Query()] = None):
    with request.app.state.sessions.begin() as session:
        if session.get(Experiment, experiment_id) is None:
            raise HTTPException(404, "Experiment not found")
        recover_scores(session, experiment_id)
        try:
            return results(session, experiment_id, model_slot)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None


@router.get("/{experiment_id}/responses/{response_id}")
def get_response(request: Request, experiment_id: int, response_id: int):
    with request.app.state.sessions.begin() as session:
        if session.get(Experiment, experiment_id) is None:
            raise HTTPException(404, "Experiment not found")
        recover_scores(session, experiment_id)
        detail = response_detail(session, experiment_id, response_id)
        if detail is None:
            raise HTTPException(404, "Response not found")
        return detail


@router.get("/{experiment_id}/responses")
def get_responses(request: Request, experiment_id: int, model_slot: int | None = None,
                  task_type: str | None = None, status: str | None = None,
                  offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    with request.app.state.sessions.begin() as session:
        if session.get(Experiment, experiment_id) is None:
            raise HTTPException(404, "Experiment not found")
        recover_scores(session, experiment_id)
        return response_rows(session, experiment_id, model_slot=model_slot, task_type=task_type,
                             status=status, offset=offset, limit=limit)
