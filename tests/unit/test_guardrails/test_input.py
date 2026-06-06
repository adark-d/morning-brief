"""Tests for the input guardrails."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.fixtures import make_data_quality_report, make_market_snapshot, make_yield_point

from morning_brief.core.interfaces.guardrail import GuardrailSeverity
from morning_brief.core.models.market_data import MarketSnapshot
from morning_brief.guardrails.input import (
    CompletenessGuardrail,
    StalenessGuardrail,
    YieldRangeGuardrail,
)


# ============================================
# Yield range
# ============================================
def test_yield_range_passes_for_plausible_yields() -> None:
    result = YieldRangeGuardrail(0.1, 20.0).validate(make_market_snapshot())
    assert result.severity is GuardrailSeverity.PASS


def test_yield_range_aborts_on_out_of_range_yield() -> None:
    snapshot = make_market_snapshot(
        yields={"30Y": make_yield_point(maturity="30Y", yield_pct=22.0)}
    )
    result = YieldRangeGuardrail(0.1, 20.0).validate(snapshot)
    assert result.severity is GuardrailSeverity.CRITICAL


# ============================================
# Completeness
# ============================================
def test_completeness_passes_with_enough_maturities() -> None:
    yields = {
        "2Y": make_yield_point(maturity="2Y"),
        "10Y": make_yield_point(maturity="10Y"),
        "30Y": make_yield_point(maturity="30Y"),
    }
    result = CompletenessGuardrail(3).validate(make_market_snapshot(yields=yields))
    assert result.severity is GuardrailSeverity.PASS


def test_completeness_warns_below_required() -> None:
    result = CompletenessGuardrail(3).validate(make_market_snapshot())  # only 1 yield
    assert result.severity is GuardrailSeverity.WARNING


def test_completeness_aborts_with_no_yields() -> None:
    result = CompletenessGuardrail(3).validate(make_market_snapshot(yields={}))
    assert result.severity is GuardrailSeverity.CRITICAL


# ============================================
# Staleness  (clock pinned via the injected `now` so age is deterministic)
# ============================================
_NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def _aged(hours_ago: float, *, is_stale: bool = False) -> MarketSnapshot:
    return make_market_snapshot(
        timestamp=_NOW - timedelta(hours=hours_ago),
        data_quality=make_data_quality_report(is_stale=is_stale),
    )


def test_staleness_passes_for_fresh_data() -> None:
    guardrail = StalenessGuardrail(warn_after_hours=4, now=lambda: _NOW)
    assert guardrail.validate(_aged(1)).severity is GuardrailSeverity.PASS


def test_staleness_warns_for_old_data() -> None:
    guardrail = StalenessGuardrail(warn_after_hours=4, now=lambda: _NOW)
    assert guardrail.validate(_aged(6)).severity is GuardrailSeverity.WARNING


def test_staleness_aborts_for_very_old_data() -> None:
    guardrail = StalenessGuardrail(warn_after_hours=4, reject_after_hours=24, now=lambda: _NOW)
    assert guardrail.validate(_aged(30)).severity is GuardrailSeverity.CRITICAL


def test_staleness_warns_when_flagged_stale_even_if_fresh() -> None:
    guardrail = StalenessGuardrail(warn_after_hours=4, now=lambda: _NOW)
    assert guardrail.validate(_aged(1, is_stale=True)).severity is GuardrailSeverity.WARNING
