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

_COMMON_RESPONSES: dict[int | str, dict[str, object]] = {
    **error_responses(UnauthenticatedError, AuthNotConfiguredError),
    int(HTTPStatus.UNPROCESSABLE_ENTITY): {
        "model": ErrorResponse,
        "description": "The request path or query parameters failed validation.",
    },
}

router = APIRouter(
    prefix="/briefs",
    tags=["Briefs"],
    dependencies=[Depends(require_auth)],
    responses=_COMMON_RESPONSES,
)

_ApplicationDep = Annotated[Application, Depends(get_application)]


@router.post(
    "/run",
    response_model=RunResponse,
    summary="Trigger a brief run",
    response_description="A summary of the completed run, including its final status.",
)
async def trigger_run(application: _ApplicationDep) -> RunResponse:
    """Run the pipeline once, synchronously, and return a summary of the outcome.

    The full pipeline executes before the response returns: data fetch, guardrails,
    LLM analysis, rendering, and delivery. The run is always persisted to the audit
    store and is immediately retrievable via the other endpoints.

    A run that fails its pipeline is **not** an HTTP error — it returns `200 OK` with
    `status: "failed"` (or `"partial"` when only some recipients were reached). Use the
    `status` and `error_count` fields to judge the outcome.
    """
    run = await application.orchestrator.run()
    return RunResponse.from_run(run)


@router.get(
    "/latest",
    response_model=BriefRunResponse,
    summary="Get the most recent run",
    response_description="The full, PII-free audit record of the most recent run.",
    responses=error_responses(NotFoundError),
)
async def get_latest_run(application: _ApplicationDep) -> BriefRunResponse:
    """Return the full audit record of the most recently triggered run.

    "Most recent" is by trigger time (`triggered_at`), not by write order. Returns
    `404 Not Found` when no runs have been recorded yet.
    """
    run = await application.audit_store.get_latest()
    if run is None:
        raise NotFoundError("no runs recorded")
    return BriefRunResponse.from_run(run)


@router.get(
    "",
    response_model=list[RunResponse],
    summary="List runs for a date",
    response_description="Summaries of every run triggered on the given UTC date.",
)
async def list_runs_on_date(
    application: _ApplicationDep,
    run_date: Annotated[
        date,
        Query(
            alias="date",
            description=(
                "The UTC calendar date to list runs for, in ISO 8601 format "
                "(YYYY-MM-DD), e.g. `2026-06-07`. Matches runs by their trigger time."
            ),
        ),
    ],
) -> list[RunResponse]:
    """List summaries of every run triggered on a given UTC calendar date.

    Results are ordered by trigger time. An empty list means no runs were triggered on
    that date (this is a normal `200 OK`, not a `404`).
    """
    runs = await application.audit_store.query_by_date(run_date)
    return [RunResponse.from_run(run) for run in runs]


@router.get(
    "/{run_id}",
    response_model=BriefRunResponse,
    summary="Get a run by id",
    response_description="The full, PII-free audit record of the requested run.",
    responses=error_responses(NotFoundError),
)
async def get_run(
    application: _ApplicationDep,
    run_id: Annotated[
        UUID,
        Path(description="The run's unique identifier (UUID), as returned by `POST /briefs/run`."),
    ],
) -> BriefRunResponse:
    """Return the full audit record for a single run by its id.

    Returns `404 Not Found` if no run has that id. The id is validated as a UUID, so
    malformed input (e.g. glob metacharacters) is rejected with `422` at the edge,
    before it can reach the audit store.
    """
    run = await application.audit_store.get_by_id(str(run_id))
    if run is None:
        raise NotFoundError(f"run {run_id} not found")
    return BriefRunResponse.from_run(run)
