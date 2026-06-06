"""HTTP response DTOs.

A run summary for list/trigger endpoints; the full immutable ``BriefRun`` is
returned directly by the single-item endpoints (it is the compliance artifact the
architecture designs the API to expose).
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field

from morning_brief.core.models.audit import BriefRun, RunStatus


class RunResponse(BaseModel):
    """Compact summary of one pipeline run."""

    run_id: str = Field(description="The run's UUID; use it to fetch the full record")
    status: RunStatus = Field(description="Final outcome: success, partial, or failed")
    delivered: int = Field(description="Recipients the brief was delivered to")
    recipients: int = Field(description="Recipients delivery was attempted for")
    error_count: int = Field(description="Number of errors and warnings recorded on the run")
    duration_seconds: float | None = Field(description="Wall-clock duration of the run")

    @classmethod
    def from_run(cls, run: BriefRun) -> Self:
        return cls(
            run_id=run.run_id,
            status=run.status,
            delivered=run.delivered_count,
            recipients=run.total_recipients,
            error_count=len(run.errors),
            duration_seconds=run.duration_seconds,
        )
