"""In-memory mock implementation of DataProvider for testing.

Returns deterministic, valid market data without any network access. The mock
is fully featured — it can simulate partial failures, latency, or unavailability
via constructor flags. Tests use this to exercise edge cases.

Implements core.interfaces.data_provider.DataProvider.
"""

from __future__ import annotations

from datetime import UTC, datetime

from morning_brief.core.exceptions.errors import APIUnavailableError
from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.interfaces.data_provider import DataProvider
from morning_brief.core.models.market_data import (
    DataQualityReport,
    FXPoint,
    MarketSnapshot,
    PricePoint,
    YieldPoint,
)

# Default deterministic data used by the mock
_DEFAULT_YIELDS: dict[str, float] = {
    "13W": 5.32,
    "5Y": 4.18,
    "10Y": 4.42,
    "30Y": 4.61,
}

_DEFAULT_INSTRUMENTS: dict[str, float] = {
    "VIX": 14.5,
    "CRUDE_OIL": 78.2,
    "GOLD": 2410.0,
    "SP500": 5234.5,
    "DOLLAR_IDX": 104.8,
}

_DEFAULT_FX: dict[str, float] = {
    "GBP/USD": 1.27,
    "EUR/USD": 1.084,
    "USD/JPY": 152.4,
    "USD/CHF": 0.91,
}


class MockDataProvider(DataProvider):
    """Deterministic in-memory DataProvider for testing.

    By default returns a full, valid snapshot. Constructor flags simulate
    partial-failure scenarios for testing the pipeline's degradation handling.
    """

    def __init__(
        self,
        *,
        fail_yields: bool = False,
        fail_instruments: bool = False,
        fail_fx: bool = False,
        fail_all: bool = False,
        unhealthy: bool = False,
    ) -> None:
        """Construct a mock provider with optional failure simulation.

        Args:
            fail_yields: Return empty yields and mark them as failed.
            fail_instruments: Return empty instruments and mark them as failed.
            fail_fx: Return empty FX and mark them as failed.
            fail_all: Raise APIUnavailableError on fetch (simulates total outage).
            unhealthy: health_check returns UNHEALTHY.
        """
        self._fail_yields = fail_yields
        self._fail_instruments = fail_instruments
        self._fail_fx = fail_fx
        self._fail_all = fail_all
        self._unhealthy = unhealthy

    async def fetch_snapshot(self) -> MarketSnapshot:
        if self._fail_all:
            raise APIUnavailableError("Mock configured to simulate total outage")

        timestamp = datetime.now(UTC)

        yields = (
            {}
            if self._fail_yields
            else {
                m: YieldPoint(maturity=m, yield_pct=v, timestamp=timestamp)
                for m, v in _DEFAULT_YIELDS.items()
            }
        )
        instruments = (
            {}
            if self._fail_instruments
            else {
                s: PricePoint(symbol=s, price=v, timestamp=timestamp)
                for s, v in _DEFAULT_INSTRUMENTS.items()
            }
        )
        fx = (
            {}
            if self._fail_fx
            else {p: FXPoint(pair=p, rate=v, timestamp=timestamp) for p, v in _DEFAULT_FX.items()}
        )

        all_sources = (
            *_DEFAULT_YIELDS.keys(),
            *_DEFAULT_INSTRUMENTS.keys(),
            *_DEFAULT_FX.keys(),
        )
        failures: list[str] = []
        if self._fail_yields:
            failures.extend(_DEFAULT_YIELDS.keys())
        if self._fail_instruments:
            failures.extend(_DEFAULT_INSTRUMENTS.keys())
        if self._fail_fx:
            failures.extend(_DEFAULT_FX.keys())

        succeeded = tuple(s for s in all_sources if s not in failures)

        return MarketSnapshot(
            timestamp=timestamp,
            yields=yields,
            instruments=instruments,
            fx=fx,
            data_quality=DataQualityReport(
                sources_attempted=all_sources,
                sources_succeeded=succeeded,
                sources_failed=tuple(failures),
                is_stale=False,
            ),
        )

    async def health_check(self) -> HealthStatus:
        if self._unhealthy:
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                component="MockDataProvider",
                message="Mock configured as unhealthy",
                latency_ms=0.0,
            )
        return HealthStatus(
            state=HealthState.HEALTHY,
            component="MockDataProvider",
            message="Mock data provider ready",
            latency_ms=0.0,
        )
