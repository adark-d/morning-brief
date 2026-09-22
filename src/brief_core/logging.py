from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from time import monotonic
from traceback import format_tb

import structlog

from brief_core import BriefCoreError


def configure_logging() -> None:
    """Configure JSON logs for CLIs and serverless handlers."""
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


@contextmanager
def log_stage(name: str) -> Generator[None]:
    """Record stage duration without logging source text or credentials."""
    started = monotonic()
    with structlog.contextvars.bound_contextvars(stage=name):
        status = "failed"
        try:
            yield
            status = "success"
        finally:
            structlog.get_logger().info(
                "brief_stage_finished",
                status=status,
                duration_ms=round((monotonic() - started) * 1000),
            )


def log_failure(event: str, error: Exception, **fields: object) -> None:
    """Log the error location without exposing provider responses or secret values."""
    cause: BaseException | None = error
    while cause is not None and not isinstance(cause, BriefCoreError):
        cause = cause.__cause__

    structlog.get_logger().error(
        event,
        reason=str(cause) if cause is not None else None,
        error_type=type(error).__name__,
        traceback="".join(format_tb(error.__traceback__)),
        **fields,
    )
