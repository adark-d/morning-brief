# yfinance ships no type stubs; contain strict-mode unknown-type noise at this
# boundary (mypy is handled via [[tool.mypy.overrides]] in pyproject).
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Final

import structlog
import yfinance
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from morning_brief.core.exceptions.errors import APIUnavailableError, DataFetchError
from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.interfaces.data_provider import DataProvider
from morning_brief.core.models.market_data import (
    DataQualityReport,
    FXPoint,
    MarketSnapshot,
    PricePoint,
    YieldPoint,
)
from morning_brief.infrastructure.data.yfinance_tickers import (
    FX_TICKERS,
    INSTRUMENT_TICKERS,
    TREASURY_YIELD_TICKERS,
)
from morning_brief.observability.timing import log_duration

logger = structlog.get_logger(__name__)

# Upper bound on a single retry backoff, regardless of configured base.
_MAX_BACKOFF_SECONDS: Final = 4.0


class _TransientFetchError(DataFetchError):
    """Internal retry signal: a yfinance failure worth retrying.

    Raised for network errors and empty results (how yfinance signals a transient
    fetch problem). Private to this module — callers never see it, because after
    retries are exhausted the surrounding source loop records the failure instead.
    """


class YFinanceDataProvider(DataProvider):
    """Production DataProvider using Yahoo Finance via the yfinance library.

    Each source (yield maturity, instrument, FX pair) is fetched independently
    with its own timeout and bounded retry. Failures degrade to partial data
    rather than aborting the snapshot.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        """Initialise the provider.

        Args:
            timeout_seconds: Per-source timeout. Bounds the total time spent on a
                single ticker, retries and backoff included.
            max_attempts: Total attempts per ticker before it is recorded as failed.
            retry_backoff_seconds: Base for exponential backoff between attempts.
                Set to 0 to disable waiting (used by tests).
        """
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        logger.info(
            "yfinance_provider_initialised",
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
        )

    async def fetch_snapshot(self) -> MarketSnapshot:
        snapshot_timestamp = datetime.now(UTC)
        start = time.perf_counter()
        logger.info(
            "snapshot_fetch_started", provider="yfinance", timestamp=snapshot_timestamp.isoformat()
        )

        # Fetch the three categories in parallel. Each sub-fetcher isolates its
        # own per-source failures and never raises, so the TaskGroup only surfaces
        # an exception on cancellation — which we deliberately let propagate.
        async with asyncio.TaskGroup() as tg:
            yields_task = tg.create_task(self._fetch_yields(snapshot_timestamp))
            instruments_task = tg.create_task(self._fetch_instruments(snapshot_timestamp))
            fx_task = tg.create_task(self._fetch_fx(snapshot_timestamp))

        yields, yield_failures = yields_task.result()
        instruments, instrument_failures = instruments_task.result()
        fx, fx_failures = fx_task.result()

        sources_attempted = (
            *TREASURY_YIELD_TICKERS.keys(),
            *INSTRUMENT_TICKERS.keys(),
            *FX_TICKERS.keys(),
        )
        sources_failed = (*yield_failures, *instrument_failures, *fx_failures)
        sources_succeeded = tuple(s for s in sources_attempted if s not in sources_failed)

        if not yields and not instruments and not fx:
            raise APIUnavailableError(
                "Yahoo Finance returned no data for any source — "
                "all yields, instruments, and FX failed"
            )

        snapshot = MarketSnapshot(
            timestamp=snapshot_timestamp,
            yields=yields,
            instruments=instruments,
            fx=fx,
            data_quality=DataQualityReport(
                sources_attempted=sources_attempted,
                sources_succeeded=sources_succeeded,
                sources_failed=sources_failed,
                is_stale=False,
            ),
        )

        logger.info(
            "snapshot_fetch_completed",
            provider="yfinance",
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            yields_count=len(yields),
            instruments_count=len(instruments),
            fx_count=len(fx),
            failures_count=len(sources_failed),
        )
        return snapshot

    async def health_check(self) -> HealthStatus:
        """Verify yfinance can reach Yahoo by fetching a single lightweight ticker."""
        start = time.perf_counter()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._probe_yfinance),
                timeout=self._timeout,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                component="YFinanceDataProvider",
                message=f"Probe failed: {exc}",
                latency_ms=elapsed_ms,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return HealthStatus(
            state=HealthState.HEALTHY,
            component="YFinanceDataProvider",
            message="Yahoo Finance reachable",
            latency_ms=elapsed_ms,
        )

    async def _fetch_yields(
        self,
        timestamp: datetime,
    ) -> tuple[dict[str, YieldPoint], tuple[str, ...]]:
        """Fetch all Treasury yields. Returns (successes, failed_maturities)."""
        yields: dict[str, YieldPoint] = {}
        failures: list[str] = []

        for maturity, ticker in TREASURY_YIELD_TICKERS.items():
            try:
                value = await self._fetch_ticker(ticker)
                yields[maturity] = YieldPoint(
                    maturity=maturity,
                    yield_pct=value,
                    timestamp=timestamp,
                )
            except Exception as exc:
                # Record the source and continue — one bad ticker (timeout, empty,
                # malformed, or validation failure) must not abort the others.
                logger.warning("yield_fetch_failed", maturity=maturity, error=str(exc))
                failures.append(maturity)

        return yields, tuple(failures)

    async def _fetch_instruments(
        self,
        timestamp: datetime,
    ) -> tuple[dict[str, PricePoint], tuple[str, ...]]:
        """Fetch all instrument prices. Returns (successes, failed_symbols)."""
        instruments: dict[str, PricePoint] = {}
        failures: list[str] = []

        for symbol, ticker in INSTRUMENT_TICKERS.items():
            try:
                value = await self._fetch_ticker(ticker)
                instruments[symbol] = PricePoint(
                    symbol=symbol,
                    price=value,
                    timestamp=timestamp,
                )
            except Exception as exc:
                logger.warning("instrument_fetch_failed", symbol=symbol, error=str(exc))
                failures.append(symbol)

        return instruments, tuple(failures)

    async def _fetch_fx(
        self,
        timestamp: datetime,
    ) -> tuple[dict[str, FXPoint], tuple[str, ...]]:
        """Fetch all FX pairs. Returns (successes, failed_pairs)."""
        fx: dict[str, FXPoint] = {}
        failures: list[str] = []

        for pair, ticker in FX_TICKERS.items():
            try:
                value = await self._fetch_ticker(ticker)
                fx[pair] = FXPoint(pair=pair, rate=value, timestamp=timestamp)
            except Exception as exc:
                logger.warning("fx_fetch_failed", pair=pair, error=str(exc))
                failures.append(pair)

        return fx, tuple(failures)

    async def _fetch_ticker(self, ticker: str) -> float:
        """Fetch one ticker's latest close with a per-source timeout.

        The blocking yfinance call (and its retries) runs in a worker thread,
        bounded by ``timeout_seconds`` so a slow source cannot stall the snapshot.
        Raises on failure; the calling sub-fetcher records and continues. Per-ticker
        latency is logged at DEBUG so a slow individual source can be pinpointed
        without flooding INFO with one line per ticker.
        """
        with log_duration(
            logger, "ticker_fetched", level="debug", provider="yfinance", ticker=ticker
        ):
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_close_with_retry, ticker),
                timeout=self._timeout,
            )

    def _fetch_close_with_retry(self, ticker: str) -> float:
        """Run the blocking yfinance fetch, retrying only transient failures."""
        retryer = Retrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(
                multiplier=self._retry_backoff_seconds,
                max=_MAX_BACKOFF_SECONDS,
            ),
            retry=retry_if_exception_type(_TransientFetchError),
            reraise=True,
        )
        return retryer(self._fetch_close, ticker)

    def _fetch_close(self, ticker: str) -> float:
        """Blocking yfinance call for one ticker (runs in a worker thread).

        Raises _TransientFetchError for retryable failures — a network/IO error or
        an empty frame, which is how yfinance signals a transient problem. Any other
        error propagates unretried, to be recorded by the calling sub-fetcher.
        """
        try:
            history = yfinance.Ticker(ticker).history(period="2d")  # 2d covers weekend gaps
        except OSError as exc:
            # requests/urllib network failures subclass OSError.
            raise _TransientFetchError(f"network error fetching {ticker}: {exc}") from exc

        if history.empty:
            raise _TransientFetchError(f"empty result for ticker {ticker}")

        return float(history["Close"].iloc[-1])

    def _probe_yfinance(self) -> None:
        """Lightweight probe — fetch a single ticker to verify connectivity."""
        yfinance.Ticker("^GSPC").history(period="1d")
