"""DataProvider interface — the contract for any market data source.

Today's implementation is yfinance (free, dev) and Alpha Vantage (production).
Tomorrow's might be a Bloomberg feed or an internal data warehouse. The orchestrator
only ever depends on this abstract class — never on a concrete implementation.

Mirrors Section 9.1 of the architecture document.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from morning_brief.core.interfaces.base import HealthStatus
from morning_brief.core.models.market_data import MarketSnapshot


class DataProvider(ABC):
    """Abstract data provider for market data.

    Every concrete implementation:
        - is async (parallel fetches at pipeline start)
        - returns Pydantic models (validation at the boundary)
        - never raises on partial failure — returns a snapshot with a populated
          DataQualityReport flagging which sources failed
        - exposes a health check the pipeline calls before fetching
    """

    @abstractmethod
    async def fetch_snapshot(self) -> MarketSnapshot:
        """Fetch a complete market snapshot.

        Implementations parallelise their internal fetches (yields, instruments, FX).
        Partial failure is recorded in the returned snapshot's data_quality field
        rather than raised — graceful degradation is the principle.

        Returns:
            A MarketSnapshot, possibly with missing sub-sections flagged in
            data_quality.sources_failed.

        Raises:
            APIUnavailableError: only when ALL sources fail simultaneously,
                i.e. when the snapshot would be empty.
        """
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Test whether the upstream data source is reachable.

        Called by the pipeline orchestrator BEFORE attempting a fetch.
        A failed health check causes the run to abort early with a clear error,
        rather than producing a half-empty snapshot.
        """
        ...
