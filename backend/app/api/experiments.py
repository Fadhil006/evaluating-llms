"""Experiment design and lifecycle routes."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.models import Experiment
from app.services.experiment_lifecycle import LifecycleConflict, start, transition
from app.services.experiments import Design, DesignProblem, describe, prepare, save_design

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def invalid(exc: DesignProblem) -> HTTPException:
    return HTTPException(422, detail={"errors": [{"field": exc.field, "message": exc.message}]})


def get_row(session, experiment_id: int) -> Experiment:
    row = session.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(404, "Experiment not found")
    return row


@router.post("/estimate")
def estimate(request: Request, design: Design):
    try:
        with request.app.state.sessions() as session:
            config, budget = prepare(session, design)
            return {"estimate": budget, "item_ids": config["item_ids"],
                    "category_counts": config["category_counts"], "dataset_content_sha256": config["dataset_content_sha256"],
                    "policy_decisions_advisory": config["policy_decisions_advisory"],
                    "ready": all(d["allowed"] for d in config["policy_decisions_advisory"])}
    except DesignProblem as exc:
        raise invalid(exc) from None


@router.post("", status_code=201)
def create(request: Request, design: Design):
    try:
        with request.app.state.sessions.begin() as session:
            return save_design(session, design, mode=getattr(request.app.state, "execution_mode", "live"))
    except DesignProblem as exc:
        raise invalid(exc) from None


@router.get("")
def list_experiments(request: Request):
    with request.app.state.sessions() as session:
        return [describe(session, row) for row in session.scalars(select(Experiment).order_by(Experiment.id))]


@router.get("/{experiment_id}")
def detail(request: Request, experiment_id: int):
    with request.app.state.sessions() as session:
        return describe(session, get_row(session, experiment_id))


@router.put("/{experiment_id}")
def update(request: Request, experiment_id: int, design: Design):
    try:
        with request.app.state.sessions.begin() as session:
            row = get_row(session, experiment_id)
            if row.status != "draft":
                raise HTTPException(409, "Only drafts can be edited; clone this experiment")
            return save_design(session, design, row=row)
    except DesignProblem as exc:
        raise invalid(exc) from None


@router.post("/{experiment_id}/clone", status_code=201)
def clone(request: Request, experiment_id: int):
    try:
        with request.app.state.sessions.begin() as session:
            original = get_row(session, experiment_id)
            fields = set(Design.model_fields)
            design = Design.model_validate({key: value for key, value in original.config.items() if key in fields}
                                           | {"name": original.name})
            return save_design(session, design, mode=original.provenance_mode)
    except DesignProblem as exc:
        raise invalid(exc) from None


@router.post("/{experiment_id}/start")
def start_experiment(request: Request, experiment_id: int):
    try:
        with request.app.state.sessions.begin() as session:
            row = get_row(session, experiment_id)
            if row.provenance_mode != getattr(request.app.state, "execution_mode", "live"):
                raise LifecycleConflict("Experiment execution mode does not match this database mode")
            start(session, row)
            session.refresh(row)
            return describe(session, row)
    except LifecycleConflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{experiment_id}/pause")
def pause_experiment(request: Request, experiment_id: int):
    return lifecycle(request, experiment_id, "pause")


@router.post("/{experiment_id}/resume")
def resume_experiment(request: Request, experiment_id: int, acknowledge_uncertain: bool = False):
    return lifecycle(request, experiment_id, "resume", acknowledge_uncertain=acknowledge_uncertain)


@router.post("/{experiment_id}/cancel")
def cancel_experiment(request: Request, experiment_id: int):
    return lifecycle(request, experiment_id, "cancel")


def lifecycle(request: Request, experiment_id: int, action: str, *, acknowledge_uncertain: bool = False):
    try:
        with request.app.state.sessions.begin() as session:
            row = get_row(session, experiment_id)
            transition(session, row, action, acknowledge_uncertain=acknowledge_uncertain)
            session.refresh(row)
            return describe(session, row)
    except LifecycleConflict as exc:
        raise HTTPException(409, str(exc)) from None
