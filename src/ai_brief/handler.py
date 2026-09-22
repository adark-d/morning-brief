from __future__ import annotations

import asyncio
from typing import cast
from uuid import uuid4

import structlog

from ai_brief.models import BriefError
from ai_brief.pipeline import execute
from brief_core.logging import configure_logging, log_failure
from brief_core.monitor import check_completion
from brief_core.settings import Settings


def run_handler(event: object, context: object) -> dict[str, str]:
    """Load scheduled-run settings and deliver the daily brief."""

    _ = (event, context)
    configure_logging()
    tokens = structlog.contextvars.bind_contextvars(run_id=str(uuid4()))
    try:
        if (
            isinstance(event, dict)
            and cast(dict[str, object], event).get("action") == "check_completion"
        ):
            check_completion()
            return {"status": "checked"}
        settings = Settings()
        if not settings.send_email:
            raise BriefError("Scheduled handler requires MORNING_BRIEF_SEND_EMAIL=true")
        run = asyncio.run(execute(settings))
        return {"run_id": run.run_id, "status": run.status}
    except Exception as exc:
        log_failure("invocation_failed", exc)
        raise BriefError("Brief invocation failed; inspect structured logs") from None
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
