from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from tests.fixtures import (
    make_brief_analysis,
    make_brief_run,
    make_data_quality_report,
    make_market_snapshot,
    make_yield_point,
)

from morning_brief.core.models.audit import (
    BriefError,
    BriefRun,
    DeliveryResult,
    DeliveryStatus,
    ErrorSeverity,
    RunStatus,
)
from morning_brief.core.models.market_data import FXPoint, YieldPoint
from morning_brief.core.models.report import RenderedReport

_AWARE = datetime(2026, 5, 10, 7, 0, tzinfo=UTC)
_NAIVE = datetime(2026, 5, 10, 7, 0)  # intentionally naive, to prove it's rejected


_NAIVE_DATETIME_BUILDERS: dict[str, Callable[[], object]] = {
    "YieldPoint": lambda: YieldPoint(maturity="10Y", yield_pct=4.4, timestamp=_NAIVE),
    "FXPoint": lambda: FXPoint(pair="GBP/USD", rate=1.27, timestamp=_NAIVE),
    "MarketSnapshot": lambda: make_market_snapshot(timestamp=_NAIVE),
    "BriefAnalysis": lambda: make_brief_analysis(generated_at=_NAIVE),
    "BriefRun": lambda: make_brief_run(triggered_at=_NAIVE),
    "BriefError": lambda: BriefError(
        component="data",
        error_type="APIUnavailableError",
        message="boom",
        severity=ErrorSeverity.ERROR,
        occurred_at=_NAIVE,
    ),
    "DeliveryResult": lambda: DeliveryResult(
        recipient="a@b.com",
        channel="email",
        status=DeliveryStatus.DELIVERED,
        attempted_at=_NAIVE,
    ),
    "RenderedReport": lambda: RenderedReport(
        subject="Daily Brief",
        html_body="x" * 60,
        plain_text_body="y" * 60,
        rendered_at=_NAIVE,
        template_version="v1.0",
    ),
}


@pytest.mark.parametrize("name", list(_NAIVE_DATETIME_BUILDERS))
def test_models_reject_naive_datetimes(name: str) -> None:
    with pytest.raises(ValidationError):
        _NAIVE_DATETIME_BUILDERS[name]()


def test_aware_non_utc_datetime_is_normalised_to_utc() -> None:
    plus_five = timezone(timedelta(hours=5))
    point = make_yield_point(timestamp=datetime(2026, 5, 10, 12, 0, tzinfo=plus_five))

    assert point.timestamp.tzinfo == UTC
    assert point.timestamp.hour == 7  # 12:00+05:00 == 07:00 UTC
    assert point.timestamp == datetime(2026, 5, 10, 7, 0, tzinfo=UTC)


def test_yield_point_rejects_decimal_form_yield() -> None:
    # 0.0442 is the decimal-form bug; range is percent (e.g. 4.42). Out of range -> ok,
    # but an absurd percent must be rejected.
    with pytest.raises(ValidationError):
        make_yield_point(yield_pct=99.0)


def test_fx_point_rejects_malformed_pair() -> None:
    with pytest.raises(ValidationError):
        FXPoint(pair="GBPUSD", rate=1.27, timestamp=_AWARE)


def test_brief_analysis_confidence_must_be_within_unit_interval() -> None:
    with pytest.raises(ValidationError):
        make_brief_analysis(confidence=1.5)


def test_brief_analysis_key_signals_below_minimum_rejected() -> None:
    with pytest.raises(ValidationError):
        make_brief_analysis(key_signals=("only one",))


def test_brief_analysis_key_signals_above_maximum_rejected() -> None:
    with pytest.raises(ValidationError):
        make_brief_analysis(key_signals=tuple(f"signal {i}" for i in range(6)))


def test_frozen_model_rejects_mutation() -> None:
    point = make_yield_point()
    with pytest.raises(ValidationError):
        point.yield_pct = 1.0


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        YieldPoint(maturity="10Y", yield_pct=4.4, timestamp=_AWARE, bogus=1)  # type: ignore[call-arg]


def test_data_quality_report_success_rate_and_completeness() -> None:
    partial = make_data_quality_report(
        sources_attempted=("a", "b", "c", "d"),
        sources_succeeded=("a", "b", "c"),
        sources_failed=("d",),
    )
    assert partial.success_rate == 0.75
    assert partial.is_complete is False

    complete = make_data_quality_report(
        sources_attempted=("a",), sources_succeeded=("a",), sources_failed=()
    )
    assert complete.is_complete is True


def test_data_quality_report_success_rate_with_no_sources() -> None:
    empty = make_data_quality_report(sources_attempted=(), sources_succeeded=(), sources_failed=())
    assert empty.success_rate == 0.0


def test_market_snapshot_presence_flags() -> None:
    snapshot = make_market_snapshot()
    assert snapshot.has_yields is True
    assert snapshot.has_fx is False
    assert snapshot.has_instruments is False


def test_brief_run_delivery_and_error_properties() -> None:
    delivered = DeliveryResult(
        recipient="a@b.com",
        channel="email",
        status=DeliveryStatus.DELIVERED,
        attempted_at=_AWARE,
    )
    failed = DeliveryResult(
        recipient="c@d.com",
        channel="email",
        status=DeliveryStatus.FAILED,
        attempted_at=_AWARE,
    )
    error = BriefError(
        component="delivery",
        error_type="SMTPError",
        message="refused",
        severity=ErrorSeverity.ERROR,
        occurred_at=_AWARE,
    )
    run = make_brief_run(status=RunStatus.SUCCESS).model_copy(
        update={"delivery_results": (delivered, failed), "errors": (error,)}
    )

    assert run.succeeded is True
    assert run.has_errors is True
    assert run.delivered_count == 1
    assert run.total_recipients == 2


def test_brief_run_json_round_trip_preserves_utc_and_tuples() -> None:
    run = make_brief_run()
    restored = BriefRun.model_validate_json(run.model_dump_json())

    assert restored == run
    assert restored.triggered_at.tzinfo == UTC
    assert isinstance(restored.delivery_results, tuple)


def test_run_status_serialises_as_plain_string() -> None:
    run = make_brief_run(status=RunStatus.PARTIAL)
    assert '"partial"' in run.model_dump_json()
