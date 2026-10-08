"""Blinded human-review API; identity-bearing joins remain server-side."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.models import ReviewAssignment
from app.services.review import (
    ReviewProblem,
    create_assignment,
    get_assignment,
    submit_rating,
    submit_vote,
    summary,
)

router = APIRouter(prefix="/api/review", tags=["review"])


class AssignmentInput(BaseModel):
    experiment_id: int
    evaluator_label: str = Field(min_length=1, max_length=120)
    mode: Literal["rubric", "pairwise"]
    include_references: bool


class RatingInput(BaseModel):
    scores: dict[str, int | None]
    comments: str | None = Field(default=None, max_length=4000)


class VoteInput(BaseModel):
    choice: Literal["A", "B", "tie", "cannot_judge"]
    comments: str | None = Field(default=None, max_length=4000)
    identity_suspected: bool = False


def _raise(exc: ReviewProblem):
    status = 404 if str(exc) == "Experiment not found" else 409 if "already" in str(exc) else 422
    raise HTTPException(status, str(exc)) from None


@router.post("/assignments", status_code=201)
def create(request: Request, body: AssignmentInput):
    try:
        with request.app.state.sessions.begin() as session:
            return create_assignment(session, body.experiment_id, body.evaluator_label,
                                    body.mode, body.include_references)
    except ReviewProblem as exc:
        _raise(exc)


@router.get("/assignments/{opaque_id}")
def read(request: Request, opaque_id: str):
    with request.app.state.sessions() as session:
        assignment = get_assignment(session, opaque_id)
        if assignment is None:
            raise HTTPException(404, "Assignment not found")
        return assignment


@router.post("/assignments/{opaque_id}/rating", status_code=201)
def rate(request: Request, opaque_id: str, body: RatingInput):
    try:
        with request.app.state.sessions.begin() as session:
            assignment = session.scalar(select(ReviewAssignment).where(
                ReviewAssignment.opaque_id == opaque_id))
            if assignment is None:
                raise HTTPException(404, "Assignment not found")
            submit_rating(session, assignment, body.scores, body.comments)
            return {"status": "saved", "rubric_version": "1"}
    except ReviewProblem as exc:
        _raise(exc)


@router.post("/assignments/{opaque_id}/vote", status_code=201)
def vote(request: Request, opaque_id: str, body: VoteInput):
    try:
        with request.app.state.sessions.begin() as session:
            assignment = session.scalar(select(ReviewAssignment).where(
                ReviewAssignment.opaque_id == opaque_id))
            if assignment is None:
                raise HTTPException(404, "Assignment not found")
            submit_vote(session, assignment, body.choice, body.comments, body.identity_suspected)
            return {"status": "saved", "rubric_version": "1", "identity_suspected": body.identity_suspected}
    except ReviewProblem as exc:
        _raise(exc)


@router.get("/experiments/{experiment_id}/summary")
def get_summary(request: Request, experiment_id: int):
    try:
        with request.app.state.sessions() as session:
            return summary(session, experiment_id)
    except ReviewProblem as exc:
        _raise(exc)
