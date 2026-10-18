"""Read and repair locally scored experiment results (mount independently)."""

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request, status

from app.models import Experiment
from app.services.analysis_store import create_analysis, get_analysis, list_analyses
from app.services.results import response_detail, response_rows, results

router = APIRouter(prefix="/api/experiments", tags=["results"])


@router.get("/{experiment_id}/results")
def get_results(request: Request, experiment_id: int, model_slot: Annotated[list[int] | None, Query()] = None,
                analysis_id: int | None = None):
    with request.app.state.sessions.begin() as session:
        if session.get(Experiment, experiment_id) is None:
            raise HTTPException(404, "Experiment not found")
        try:
            data = results(session, experiment_id, model_slot)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if analysis_id is not None:
            analysis = get_analysis(session, experiment_id, analysis_id)
            if analysis is None:
                raise HTTPException(404, "Analysis not found")
            data["analysis"] = analysis
        return data


@router.get("/{experiment_id}/responses/{response_id}")
def get_response(request: Request, experiment_id: int, response_id: int):
    with request.app.state.sessions.begin() as session:
        if session.get(Experiment, experiment_id) is None:
            raise HTTPException(404, "Experiment not found")
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
        return response_rows(session, experiment_id, model_slot=model_slot, task_type=task_type,
                             status=status, offset=offset, limit=limit)


@router.post("/{experiment_id}/analyses", status_code=status.HTTP_201_CREATED)
def post_analysis(request: Request, experiment_id: int,
                  selected_model_slots: Annotated[list[int] | None, Body(embed=True)] = None):
    with request.app.state.sessions.begin() as session:
        try:
            analysis = create_analysis(session, experiment_id, selected_model_slots)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if analysis is None:
            raise HTTPException(404, "Experiment not found")
        return analysis


@router.get("/{experiment_id}/analyses")
def get_analyses(request: Request, experiment_id: int):
    with request.app.state.sessions() as session:
        if session.get(Experiment, experiment_id) is None:
            raise HTTPException(404, "Experiment not found")
        return list_analyses(session, experiment_id)


@router.get("/{experiment_id}/analyses/{analysis_id}")
def get_one_analysis(request: Request, experiment_id: int, analysis_id: int):
    with request.app.state.sessions() as session:
        analysis = get_analysis(session, experiment_id, analysis_id)
        if analysis is None:
            if session.get(Experiment, experiment_id) is None:
                raise HTTPException(404, "Experiment not found")
            raise HTTPException(404, "Analysis not found")
        return analysis
