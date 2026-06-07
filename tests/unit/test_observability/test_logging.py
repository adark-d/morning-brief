from __future__ import annotations

import structlog

from morning_brief.config.settings import LogLevel, ObservabilitySettings
from morning_brief.observability.logging import configure_logging


def test_configure_logging_json_mode_marks_structlog_configured() -> None:
    configure_logging(ObservabilitySettings(json_logs=True, log_level=LogLevel.INFO))
    assert structlog.is_configured()


def test_configure_logging_console_mode_yields_a_usable_logger() -> None:
    configure_logging(ObservabilitySettings(json_logs=False, log_level=LogLevel.DEBUG))
    structlog.get_logger().info("ready", component="test", severity="info")  # must not raise
