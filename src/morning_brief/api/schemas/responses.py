"""HTTP response DTOs.

These are the API's deliberate output contract, kept distinct from the domain
models so the wire format is controlled and the internal model can evolve without
leaking new fields. In particular the audit view never carries recipient addresses
(PII) or free-text error detail — those stay in the stored record for privileged,
forensic access only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field

from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.audit import BriefRun, DeliveryStatus, ErrorSeverity, RunStatus


class RunResponse(BaseModel):
    """Compact summary of one pipeline run (list and trigger endpoints)."""

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


class DeliveryOutcome(BaseModel):
    """One delivery attempt — channel and status only; the recipient is not exposed."""

    channel: str = Field(description="Channel the brief was sent through, e.g. 'email'")
    status: DeliveryStatus = Field(description="Delivery outcome for this attempt")


class RunErrorView(BaseModel):
    """A recorded error/warning, summarised — free-text detail is omitted so it can
    never carry PII or internal information out over the API."""

    component: str = Field(description="Where it originated, e.g. 'guardrail.input'")
    error_type: str = Field(description="Error or rule identifier")
    severity: ErrorSeverity = Field(description="warning, error, or critical")


class BriefRunResponse(BaseModel):
    """The audit record as exposed over HTTP — a PII-free view of a ``BriefRun``."""

    run_id: str = Field(description="The run's UUID")
    status: RunStatus = Field(description="Final outcome: success, partial, or failed")
    triggered_at: datetime = Field(description="When the run started (UTC)")
    completed_at: datetime | None = Field(description="When the run finished (UTC)")
    duration_seconds: float | None = Field(description="Wall-clock duration of the run")
    analysis: BriefAnalysis | None = Field(description="The generated brief (carries no PII)")
    deliveries: tuple[DeliveryOutcome, ...] = Field(
        description="Per-attempt channel and status; recipient addresses are not exposed"
    )
    delivered_count: int = Field(description="Attempts that succeeded")
    total_recipients: int = Field(description="Attempts made")
    errors: tuple[RunErrorView, ...] = Field(description="Recorded errors and warnings")

    @classmethod
    def from_run(cls, run: BriefRun) -> Self:
        return cls(
            run_id=run.run_id,
            status=run.status,
            triggered_at=run.triggered_at,
            completed_at=run.completed_at,
            duration_seconds=run.duration_seconds,
            analysis=run.analysis,
            deliveries=tuple(
                DeliveryOutcome(channel=d.channel, status=d.status) for d in run.delivery_results
            ),
            delivered_count=run.delivered_count,
            total_recipients=run.total_recipients,
            errors=tuple(
                RunErrorView(component=e.component, error_type=e.error_type, severity=e.severity)
                for e in run.errors
            ),
        )
