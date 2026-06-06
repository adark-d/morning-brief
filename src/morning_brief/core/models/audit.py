"""Audit trail models — the immutable record of every pipeline run.

Section 10.3 of the architecture. This is what compliance retrieves when asked
'what did the brief say on March 12th and who got it?'.

Every BriefRun is written once and never modified. The AuditStore enforces this
at the storage layer; the frozen models enforce it at the language layer.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.base import FrozenModel, UtcDatetime
from morning_brief.core.models.market_data import MarketSnapshot


# ============================================
# Enums
# ============================================
class RunStatus(StrEnum):
    """Final status of a pipeline run.

    StrEnum (Python 3.11+) means values are strings, which serialises
    cleanly to JSON without custom encoders.
    """

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DeliveryStatus(StrEnum):
    """Status of a single delivery attempt to one recipient."""

    DELIVERED = "delivered"
    REJECTED = "rejected"  # blocked by delivery guardrail
    FAILED = "failed"  # SMTP/network error
    SKIPPED = "skipped"  # e.g. duplicate-prevention block


class ErrorSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ============================================
# Sub-records
# ============================================
class DeliveryResult(FrozenModel):
    """The outcome of attempting to deliver one report to one recipient."""

    recipient: Annotated[str, Field(min_length=3)]
    channel: Annotated[str, Field(description="e.g. 'email', 'slack'")]
    status: DeliveryStatus
    attempted_at: UtcDatetime
    completed_at: UtcDatetime | None = None
    error_message: str | None = None


class BriefError(FrozenModel):
    """A single error encountered during a pipeline run.

    Errors are recorded but do not necessarily abort the run — graceful
    degradation is the principle (Section 6, Principle 3).
    """

    component: Annotated[str, Field(min_length=1, description="Which component raised")]
    error_type: Annotated[str, Field(min_length=1, description="Exception class name")]
    message: Annotated[str, Field(min_length=1)]
    severity: ErrorSeverity
    occurred_at: UtcDatetime
    context: dict[str, str] = Field(default_factory=dict)


# ============================================
# The complete run record
# ============================================
class BriefRun(FrozenModel):
    """Immutable audit record of a single pipeline execution.

    Section 10.3 of the architecture. This is the record that compliance
    retrieves and that the API exposes via GET /brief/{date}.
    """

    run_id: Annotated[str, Field(default_factory=lambda: str(uuid.uuid4()))]
    triggered_at: UtcDatetime
    completed_at: UtcDatetime | None = None
    status: RunStatus
    snapshot: MarketSnapshot | None = None
    analysis: BriefAnalysis | None = None
    delivery_results: tuple[DeliveryResult, ...] = ()
    errors: tuple[BriefError, ...] = ()
    duration_seconds: float | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == RunStatus.SUCCESS

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def delivered_count(self) -> int:
        return sum(1 for d in self.delivery_results if d.status == DeliveryStatus.DELIVERED)

    @property
    def total_recipients(self) -> int:
        return len(self.delivery_results)
