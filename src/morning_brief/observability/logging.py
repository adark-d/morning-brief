from __future__ import annotations

import logging

import structlog
from structlog.typing import Processor

from morning_brief.config.settings import ObservabilitySettings


def configure_logging(settings: ObservabilitySettings) -> None:
    level = logging.getLevelNamesMapping()[settings.log_level.value]
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if settings.json_logs
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
