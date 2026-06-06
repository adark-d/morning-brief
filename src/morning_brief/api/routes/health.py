"""Health endpoint — unauthenticated liveness check.

Deep readiness (pinging the data, LLM, delivery, and storage dependencies via
their health_check contracts) is deferred to the deployment-hardening phase; this
is a plain liveness probe for load balancers and uptime checks.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = Field(description="Liveness indicator; 'ok' when the process is serving")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    response_description="The service is up and serving requests",
)
async def health() -> HealthResponse:
    """Unauthenticated liveness check for load balancers and uptime monitors.

    Deep readiness (pinging the data, LLM, delivery, and storage dependencies via
    their health-check contracts) is deferred to the deployment-hardening phase.
    """
    return HealthResponse(status="ok")
