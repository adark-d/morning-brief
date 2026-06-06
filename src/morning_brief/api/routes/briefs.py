"""Brief endpoints — trigger a run and retrieve immutable audit records.

Every route here requires a bearer token. A run that fails is still a successful
API call: the orchestrator never raises, it records a FAILED ``BriefRun``, and the
trigger endpoint reports that recorded outcome (HTTP 200 with ``status="failed"``).
"""

from __future__ import annotations

from datetime import date
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from morning_brief.api.dependencies import get_application
from morning_brief.api.errors import (
    AuthNotConfiguredError,
    ErrorResponse,
    NotFoundError,
    UnauthenticatedError,
    error_responses,
)
from morning_brief.api.middleware.auth import require_auth
from morning_brief.api.schemas.responses import BriefRunResponse, RunResponse
from morning_brief.application.composition import Application

# Every route on this router is authenticated, so it can return the auth errors;
# 422 is added explicitly because it originates in FastAPI, not an ApiError, and
# overrides FastAPI's default schema with our ErrorResponse envelope.
_COMMON_RESPONSES: dict[int | str, dict[str, object]] = {
    **error_responses(UnauthenticatedError, AuthNotConfiguredError),
    int(HTTPStatus.UNPROCESSABLE_ENTITY): {
        "model": ErrorResponse,
        "description": "Request validation failed",
    },
}

router = APIRouter(
    prefix="/briefs",
    tags=["briefs"],
    dependencies=[Depends(require_auth)],
    responses=_COMMON_RESPONSES,
)

_ApplicationDep = Annotated[Application, Depends(get_application)]


@router.post(
    "/run",
    response_model=RunResponse,
    summary="Trigger a morning-brief run",
    response_description="A summary of the completed run, including its final status",
)
async def trigger_run(application: _ApplicationDep) -> RunResponse:
    """Run the pipeline once, synchronously, and return its summary.

    The run always completes and is persisted to the audit store; a failed brief
    is reported as ``status="failed"`` rather than as an HTTP error.
    """
    run = await application.orchestrator.run()
    return RunResponse.from_run(run)


@router.get(
    "/latest",
    response_model=BriefRunResponse,
    summary="Retrieve the most recent run",
    response_description="The audit record of the most recent run (recipient-free)",
    responses=error_responses(NotFoundError),
)
async def get_latest_run(application: _ApplicationDep) -> BriefRunResponse:
    """Return the most recently triggered run, or 404 if none exist yet."""
    run = await application.audit_store.get_latest()
    if run is None:
        raise NotFoundError("no runs recorded")
    return BriefRunResponse.from_run(run)


@router.get(
    "",
    response_model=list[RunResponse],
    summary="List runs for a UTC date",
    response_description="Summaries of every run triggered on the given date",
)
async def list_runs_on_date(
    application: _ApplicationDep,
    on: Annotated[
        date,
        Query(description="UTC calendar date in ISO format, e.g. 2026-06-06"),
    ],
) -> list[RunResponse]:
    """Return summaries of every run triggered on a given UTC calendar date."""
    runs = await application.audit_store.query_by_date(on)
    return [RunResponse.from_run(run) for run in runs]


@router.get(
    "/{run_id}",
    response_model=BriefRunResponse,
    summary="Retrieve a run by id",
    response_description="The audit record of the requested run (recipient-free)",
    responses=error_responses(NotFoundError),
)
async def get_run(
    application: _ApplicationDep,
    run_id: Annotated[UUID, Path(description="The run's UUID")],
) -> BriefRunResponse:
    """Return a single run by its id, or 404 if it does not exist.

    ``run_id`` is validated as a UUID, so non-UUID input (e.g. glob metacharacters)
    is rejected with 422 before it can reach the audit store.
    """
    run = await application.audit_store.get_by_id(str(run_id))
    if run is None:
        raise NotFoundError(f"run {run_id} not found")
    return BriefRunResponse.from_run(run)
