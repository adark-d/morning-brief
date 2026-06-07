from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from morning_brief.core.exceptions.errors import APIUnavailableError
from morning_brief.core.interfaces.base import HealthState
from morning_brief.infrastructure.data.yfinance_data_provider import YFinanceDataProvider

# Backoff is disabled so retry tests stay sub-millisecond.
_NO_BACKOFF = 0.0


def _frame(close_value: float | None) -> pd.DataFrame:
    """yfinance-shaped frame; empty when close_value is None."""
    return pd.DataFrame({"Close": [] if close_value is None else [close_value]})


def _ticker(close_value: float | None = 4.42) -> MagicMock:
    """A MagicMock imitating yfinance.Ticker with a fixed history result."""
    mock = MagicMock()
    mock.history.return_value = _frame(close_value)
    return mock


@pytest.fixture
def yfinance_module() -> Iterator[MagicMock]:
    """Patch the yfinance module imported in the provider."""
    with patch(
        "morning_brief.infrastructure.data.yfinance_data_provider.yfinance",
    ) as mock_yf:
        yield mock_yf


@pytest.mark.asyncio
async def test_fetch_snapshot_with_all_tickers_succeeding(
    yfinance_module: MagicMock,
) -> None:
    yfinance_module.Ticker.return_value = _ticker(close_value=4.42)

    provider = YFinanceDataProvider(timeout_seconds=5.0, retry_backoff_seconds=_NO_BACKOFF)
    snapshot = await provider.fetch_snapshot()

    assert len(snapshot.yields) > 0
    assert len(snapshot.instruments) > 0
    assert len(snapshot.fx) > 0
    assert snapshot.data_quality.is_complete


@pytest.mark.asyncio
async def test_empty_result_for_one_source_is_recorded_others_survive(
    yfinance_module: MagicMock,
) -> None:
    failing = "GBPUSD=X"  # FX pair GBP/USD

    def behaviour(symbol: str) -> MagicMock:
        return _ticker(close_value=None if symbol == failing else 4.42)

    yfinance_module.Ticker.side_effect = behaviour

    provider = YFinanceDataProvider(timeout_seconds=5.0, retry_backoff_seconds=_NO_BACKOFF)
    snapshot = await provider.fetch_snapshot()

    assert "GBP/USD" in snapshot.data_quality.sources_failed
    assert "GBP/USD" not in snapshot.fx
    # Everything else still came through.
    assert len(snapshot.yields) == 4
    assert len(snapshot.instruments) == 5


@pytest.mark.asyncio
async def test_unexpected_error_in_one_source_does_not_abort_the_rest(
    yfinance_module: MagicMock,
) -> None:
    """An unexpected (non-transient) error in one ticker must not cancel siblings.

    This is the regression guard for TaskGroup's fail-fast cancellation: without
    per-source isolation, one raised error would lose the entire snapshot.
    """
    failing = "CL=F"  # WTI crude -> instrument CRUDE_OIL

    def behaviour(symbol: str) -> MagicMock:
        if symbol == failing:
            raise ValueError("malformed response")  # not a transient/IO error
        return _ticker(close_value=4.42)

    yfinance_module.Ticker.side_effect = behaviour

    provider = YFinanceDataProvider(timeout_seconds=5.0, retry_backoff_seconds=_NO_BACKOFF)
    snapshot = await provider.fetch_snapshot()

    assert "CRUDE_OIL" in snapshot.data_quality.sources_failed
    assert "CRUDE_OIL" not in snapshot.instruments
    assert len(snapshot.yields) == 4
    assert len(snapshot.fx) == 4


@pytest.mark.asyncio
async def test_fetch_snapshot_raises_when_all_sources_fail(
    yfinance_module: MagicMock,
) -> None:
    yfinance_module.Ticker.return_value = _ticker(close_value=None)

    provider = YFinanceDataProvider(timeout_seconds=2.0, retry_backoff_seconds=_NO_BACKOFF)

    with pytest.raises(APIUnavailableError):
        await provider.fetch_snapshot()


@pytest.mark.asyncio
async def test_transient_failure_recovers_on_retry(
    yfinance_module: MagicMock,
) -> None:
    attempts: dict[str, int] = {}

    def behaviour(symbol: str) -> MagicMock:
        attempts[symbol] = attempts.get(symbol, 0) + 1
        # Fail the first attempt for every ticker, succeed thereafter.
        return _ticker(close_value=None if attempts[symbol] == 1 else 4.42)

    yfinance_module.Ticker.side_effect = behaviour

    provider = YFinanceDataProvider(
        timeout_seconds=5.0,
        max_attempts=3,
        retry_backoff_seconds=_NO_BACKOFF,
    )
    snapshot = await provider.fetch_snapshot()

    # Every source recovered on its second attempt.
    assert snapshot.data_quality.is_complete
    assert all(count == 2 for count in attempts.values())


@pytest.mark.asyncio
async def test_retries_are_bounded_by_max_attempts(
    yfinance_module: MagicMock,
) -> None:
    attempts: dict[str, int] = {}

    def behaviour(symbol: str) -> MagicMock:
        attempts[symbol] = attempts.get(symbol, 0) + 1
        return _ticker(close_value=None)

    yfinance_module.Ticker.side_effect = behaviour

    provider = YFinanceDataProvider(
        timeout_seconds=5.0,
        max_attempts=2,
        retry_backoff_seconds=_NO_BACKOFF,
    )

    with pytest.raises(APIUnavailableError):
        await provider.fetch_snapshot()

    assert all(count == 2 for count in attempts.values())


@pytest.mark.asyncio
async def test_health_check_healthy_when_yfinance_responds(
    yfinance_module: MagicMock,
) -> None:
    yfinance_module.Ticker.return_value = _ticker(close_value=5234.5)

    provider = YFinanceDataProvider(timeout_seconds=5.0)
    status = await provider.health_check()

    assert status.state == HealthState.HEALTHY
    assert status.latency_ms is not None


@pytest.mark.asyncio
async def test_health_check_unhealthy_when_yfinance_raises(
    yfinance_module: MagicMock,
) -> None:
    yfinance_module.Ticker.side_effect = RuntimeError("yfinance error")

    provider = YFinanceDataProvider(timeout_seconds=2.0)
    status = await provider.health_check()

    assert status.state == HealthState.UNHEALTHY
