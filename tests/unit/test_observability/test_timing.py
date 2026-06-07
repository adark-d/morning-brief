from __future__ import annotations

import pytest
import structlog
from structlog.testing import capture_logs

from morning_brief.observability.timing import log_duration


def test_log_duration_emits_event_with_duration_ms() -> None:
    logger = structlog.get_logger()
    with capture_logs() as logs, log_duration(logger, "stage_timing", stage="analysis"):
        pass

    assert len(logs) == 1
    entry = logs[0]
    assert entry["event"] == "stage_timing"
    assert entry["stage"] == "analysis"
    assert isinstance(entry["duration_ms"], float)
    assert entry["duration_ms"] >= 0.0


def test_log_duration_logs_then_reraises_when_block_fails() -> None:
    logger = structlog.get_logger()
    with (
        capture_logs() as logs,
        pytest.raises(ValueError, match="boom"),
        log_duration(logger, "stage_timing", stage="x"),
    ):
        raise ValueError("boom")

    # The duration is recorded even though the wrapped block raised.
    assert len(logs) == 1
    assert logs[0]["event"] == "stage_timing"
    assert logs[0]["stage"] == "x"
    assert "duration_ms" in logs[0]
