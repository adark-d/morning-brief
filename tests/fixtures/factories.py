"""Factory functions for constructing valid test data.

Each factory returns a fully valid instance with sensible defaults.
Tests pass keyword arguments to override only the fields they exercise.

This is the standard pattern for keeping tests resilient to model evolution:
when a new required field is added to a model, you update the factory once,
not every test.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.audit import BriefRun, RunStatus
from morning_brief.core.models.market_data import (
    DataQualityReport,
    MarketSnapshot,
    YieldPoint,
)


def make_yield_point(
    maturity: str = "10Y",
    yield_pct: float = 4.42,
    timestamp: datetime | None = None,
) -> YieldPoint:
    """Build a valid YieldPoint."""
    return YieldPoint(
        maturity=maturity,
        yield_pct=yield_pct,
        timestamp=timestamp or datetime.now(UTC),
    )


def make_data_quality_report(
    sources_attempted: tuple[str, ...] = ("yfinance",),
    sources_succeeded: tuple[str, ...] = ("yfinance",),
    sources_failed: tuple[str, ...] = (),
    is_stale: bool = False,
) -> DataQualityReport:
    """Build a valid DataQualityReport."""
    return DataQualityReport(
        sources_attempted=sources_attempted,
        sources_succeeded=sources_succeeded,
        sources_failed=sources_failed,
        is_stale=is_stale,
    )


def make_market_snapshot(
    timestamp: datetime | None = None,
    yields: dict[str, YieldPoint] | None = None,
    data_quality: DataQualityReport | None = None,
) -> MarketSnapshot:
    """Build a valid MarketSnapshot with a 10Y yield by default."""
    timestamp = timestamp or datetime.now(UTC)
    if yields is None:
        yields = {"10Y": make_yield_point(timestamp=timestamp)}
    return MarketSnapshot(
        timestamp=timestamp,
        yields=yields,
        data_quality=data_quality or make_data_quality_report(),
    )


def make_brief_analysis(
    headline: str = "Yields steady ahead of CPI release at 13:30 GMT.",
    yield_curve_summary: str = "2s10s spread holds at 38 bps, signalling cautious risk appetite.",
    key_signals: tuple[str, ...] = ("Steady yields", "Risk-off equities"),
    macro_context: str = "Oil firm, dollar weaker, VIX subdued — markets in wait-and-see mode.",
    watch_today: tuple[str, ...] = ("CPI at 13:30", "30Y auction at 18:00"),
    full_narrative: str = (
        "Markets enter the session in a holding pattern ahead of the US CPI release, with desks "
        "reluctant to add risk before the print. Treasury yields are little changed across the "
        "curve, with the 10Y holding near 4.42% and the front end anchored as traders await fresh "
        "inflation data. The 2s10s spread is steady at 38 bps, signalling a market that is cautious "
        "rather than convinced of a near-term policy shift. Crude is firmer on renewed supply "
        "concerns, the dollar is modestly weaker against the majors, and equity futures point to a "
        "broadly flat open. Credit spreads remain well behaved, with no sign of stress in "
        "investment-grade or high-yield cash. Today's CPI print is the decisive event on the "
        "calendar; a hotter-than-expected number could revive the higher-for-longer narrative, lift "
        "front-end yields, and flatten the curve further, while a soft reading would likely see "
        "duration bid and the 10Y test lower. The 30Y auction later in the session is the second "
        "focus, with dealers watching the tail and bid-to-cover for signs of waning demand."
    ),
    confidence: float = 0.82,
    model_used: str = "claude-opus-4-7",
    prompt_version: str = "v1.0",
    generated_at: datetime | None = None,
) -> BriefAnalysis:
    """Build a valid BriefAnalysis with realistic content."""
    return BriefAnalysis(
        headline=headline,
        yield_curve_summary=yield_curve_summary,
        key_signals=key_signals,
        macro_context=macro_context,
        watch_today=watch_today,
        full_narrative=full_narrative,
        confidence=confidence,
        model_used=model_used,
        prompt_version=prompt_version,
        generated_at=generated_at or datetime.now(UTC),
    )


def make_brief_run(
    run_id: str | None = None,
    triggered_at: datetime | None = None,
    status: RunStatus = RunStatus.SUCCESS,
    snapshot: MarketSnapshot | None = None,
    analysis: BriefAnalysis | None = None,
) -> BriefRun:
    """Build a valid BriefRun. Defaults to a successful run with a snapshot and analysis."""
    triggered_at = triggered_at or datetime.now(UTC)
    return BriefRun(
        run_id=run_id or str(uuid4()),
        triggered_at=triggered_at,
        completed_at=triggered_at,
        status=status,
        snapshot=snapshot or make_market_snapshot(timestamp=triggered_at),
        analysis=analysis or make_brief_analysis(generated_at=triggered_at),
    )
