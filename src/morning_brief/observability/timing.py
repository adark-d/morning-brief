from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

from structlog.typing import FilteringBoundLogger


@contextmanager
def log_duration(
    logger: FilteringBoundLogger,
    event: str,
    **fields: object,
) -> Generator[None]:
    """Log ``event`` with the wall-clock ``duration_ms`` of the wrapped block.

    Brackets a unit of work and emits one structured log line carrying its duration,
    so latency is queryable per stage in the log aggregator. Always logs — including
    when the block raises, since the duration of a stage that failed is itself a
    signal; the exception then propagates unchanged (its cause is logged separately by
    the caller).
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(event, duration_ms=duration_ms, **fields)
