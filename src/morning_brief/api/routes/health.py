from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str = Field(
        description='Liveness indicator. `"ok"` when the process is up and serving requests.',
        examples=["ok"],
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    response_description="The service is up and serving requests.",
)
async def health() -> HealthResponse:
    """Report whether the process is alive and serving. No authentication required.

    This is a shallow **liveness** check intended for load balancers and uptime
    monitors — it returns `ok` as long as the process can serve a request. It does not
    verify downstream dependencies (data, LLM, delivery, storage); deep **readiness**
    probing of those is deferred to the deployment-hardening phase.
    """
    return HealthResponse(status="ok")
