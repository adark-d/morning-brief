from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HealthState(StrEnum):
    """Outcome of a component's health check."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Health check result returned by every external-dependency interface.

    Using a dataclass rather than a Pydantic model because this lives in
    interfaces (and ABCs avoid heavy dependencies on the interface layer).
    """

    state: HealthState
    component: str
    message: str = ""
    latency_ms: float | None = None
