from __future__ import annotations

import asyncio
import functools
from typing import Any

from mangum import Mangum
from mangum.types import LambdaContext, LambdaEvent

from morning_brief.api.app import create_app
from morning_brief.application.composition import build_application
from morning_brief.aws_bootstrap import bootstrap_secrets
from morning_brief.config import load_settings
from morning_brief.core.models.audit import RunStatus
from morning_brief.observability.logging import configure_logging


class BriefRunFailedError(Exception):
    """Signals a FAILED run to the Lambda runtime.

    Raised by ``run_handler`` *after* the orchestrator has already persisted the
    audit record, so the failure is both auditable and surfaced to AWS (the
    invocation is marked failed, triggering EventBridge retry/DLQ and the alarm).
    """


def run_handler(event: object, context: object) -> dict[str, object]:
    """Scheduled-brief Lambda entry point (invoked by EventBridge Scheduler).

    Runs the pipeline once. The orchestrator persists the immutable audit record
    inside ``run()`` and returns the ``BriefRun``; on a FAILED run we raise *after*
    that record is persisted so the failure stays auditable while still failing the
    invocation. SUCCESS and PARTIAL return a summary (PARTIAL is a degraded success,
    matching the CLI's exit code).
    """
    _ = (event, context)
    bootstrap_secrets()
    settings = load_settings()
    configure_logging(settings.observability)
    run = asyncio.run(build_application(settings).orchestrator.run())
    summary: dict[str, object] = {
        "run_id": run.run_id,
        "status": run.status.value,
        "delivered": run.delivered_count,
        "recipients": run.total_recipients,
        "cost_usd": run.analysis.cost_usd if run.analysis is not None else None,
    }
    if run.status is RunStatus.FAILED:
        raise BriefRunFailedError(f"brief run {run.run_id} finished with status=failed")
    return summary


@functools.cache
def _api_app() -> Mangum:
    """Build the Mangum-wrapped FastAPI app once, reused across warm invocations."""
    bootstrap_secrets()
    settings = load_settings()
    configure_logging(settings.observability)
    return Mangum(create_app(settings), lifespan="off")


def api_handler(event: LambdaEvent, context: LambdaContext) -> dict[str, Any]:
    """HTTP API Lambda entry point (invoked by API Gateway). Bridges the API
    Gateway event to the ASGI FastAPI app via Mangum."""
    return _api_app()(event, context)
