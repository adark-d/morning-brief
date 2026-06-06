"""Tests for the guardrail runner and report aggregation."""

from __future__ import annotations

from tests.fixtures import make_market_snapshot, make_yield_point

from morning_brief.core.interfaces.guardrail import GuardrailResult, GuardrailSeverity
from morning_brief.guardrails.input import CompletenessGuardrail, YieldRangeGuardrail
from morning_brief.guardrails.runner import GuardrailReport, run_input


def _result(severity: GuardrailSeverity) -> GuardrailResult:
    return GuardrailResult(
        rule_name="r",
        severity=severity,
        passed=severity is GuardrailSeverity.PASS,
    )


def test_report_should_abort_when_any_critical() -> None:
    report = GuardrailReport((_result(GuardrailSeverity.PASS), _result(GuardrailSeverity.CRITICAL)))
    assert report.should_abort is True
    assert len(report.critical) == 1


def test_report_warnings_collected_without_abort() -> None:
    report = GuardrailReport((_result(GuardrailSeverity.PASS), _result(GuardrailSeverity.WARNING)))
    assert report.should_abort is False
    assert report.passed is False
    assert len(report.warnings) == 1


def test_report_passed_when_all_clean() -> None:
    report = GuardrailReport((_result(GuardrailSeverity.PASS),))
    assert report.passed is True
    assert report.should_abort is False


def test_run_input_executes_each_guardrail_and_aggregates() -> None:
    snapshot = make_market_snapshot(
        yields={"30Y": make_yield_point(maturity="30Y", yield_pct=22.0)}
    )
    report = run_input(
        (YieldRangeGuardrail(0.1, 20.0), CompletenessGuardrail(3)),
        snapshot,
    )
    assert len(report.results) == 2
    assert report.should_abort is True  # the out-of-range yield is CRITICAL
