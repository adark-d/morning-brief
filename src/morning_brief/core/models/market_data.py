from __future__ import annotations

from typing import Annotated

from pydantic import Field

from morning_brief.core.models.base import FrozenModel, UtcDatetime


class YieldPoint(FrozenModel):
    """A single Treasury yield observation.

    Yields are quoted as percentages (e.g. 4.42 for 4.42%, not 0.0442).
    The range catches the common bug of passing the decimal form.
    """

    maturity: Annotated[str, Field(description="e.g. '2Y', '10Y', '30Y'")]
    yield_pct: Annotated[float, Field(ge=-1.0, le=25.0, description="Yield as percent")]
    timestamp: UtcDatetime


class PricePoint(FrozenModel):
    """A single instrument price observation (oil, gold, VIX, equity indices)."""

    symbol: Annotated[str, Field(min_length=1, max_length=20)]
    price: Annotated[float, Field(gt=0)]
    timestamp: UtcDatetime


class FXPoint(FrozenModel):
    """A single FX rate observation (e.g. GBP/USD = 1.27)."""

    pair: Annotated[str, Field(pattern=r"^[A-Z]{3}/[A-Z]{3}$", description="e.g. 'GBP/USD'")]
    rate: Annotated[float, Field(gt=0)]
    timestamp: UtcDatetime


class DataQualityReport(FrozenModel):
    """Summary of what succeeded and what failed during a data fetch.

    Created by the DataProvider after attempting to fetch all sources.
    Consumed by the input guardrails to decide whether to continue.
    """

    sources_attempted: tuple[str, ...]
    sources_succeeded: tuple[str, ...]
    sources_failed: tuple[str, ...]
    is_stale: bool = False
    staleness_threshold_hours: float = 4.0
    notes: tuple[str, ...] = ()

    @property
    def success_rate(self) -> float:
        if not self.sources_attempted:
            return 0.0
        return len(self.sources_succeeded) / len(self.sources_attempted)

    @property
    def is_complete(self) -> bool:
        """True if every attempted source returned data."""
        return set(self.sources_attempted) == set(self.sources_succeeded)


class MarketSnapshot(FrozenModel):
    """The complete picture of market conditions at the moment of data fetch.

    Section 10.1 of the architecture. This is what flows from the data layer
    to the guardrails and then to the prompt builder.
    """

    timestamp: UtcDatetime
    yields: dict[str, YieldPoint] = Field(
        default_factory=dict,
        description="Treasury yields keyed by maturity (e.g. '2Y', '10Y')",
    )
    instruments: dict[str, PricePoint] = Field(
        default_factory=dict,
        description="Oil, gold, VIX, equity indices keyed by symbol",
    )
    fx: dict[str, FXPoint] = Field(
        default_factory=dict,
        description="FX rates keyed by pair (e.g. 'GBP/USD')",
    )
    data_quality: DataQualityReport

    @property
    def has_yields(self) -> bool:
        return bool(self.yields)

    @property
    def has_fx(self) -> bool:
        return bool(self.fx)

    @property
    def has_instruments(self) -> bool:
        return bool(self.instruments)
