from __future__ import annotations

from datetime import UTC, datetime

from morning_brief.core.interfaces.guardrail import GuardrailSeverity
from morning_brief.core.models.report import RenderedReport
from morning_brief.guardrails.delivery import (
    DisclaimerGuardrail,
    RecipientWhitelistGuardrail,
    ReportCompletenessGuardrail,
)


def _report(*, contains_disclaimer: bool = True) -> RenderedReport:
    return RenderedReport(
        subject="Morning Brief — test",
        html_body="<p>" + "body " * 20 + "</p>",
        plain_text_body="body " * 20,
        rendered_at=datetime.now(UTC),
        template_version="v1.0",
        contains_disclaimer=contains_disclaimer,
    )


def test_whitelist_passes_for_known_recipients() -> None:
    guardrail = RecipientWhitelistGuardrail({"desk@firm.com"})
    result = guardrail.validate(_report(), ("desk@firm.com",))
    assert result.severity is GuardrailSeverity.PASS


def test_whitelist_is_case_insensitive() -> None:
    guardrail = RecipientWhitelistGuardrail({"desk@firm.com"})
    result = guardrail.validate(_report(), ("DESK@FIRM.COM",))
    assert result.severity is GuardrailSeverity.PASS


def test_whitelist_aborts_for_unknown_recipient() -> None:
    guardrail = RecipientWhitelistGuardrail({"desk@firm.com"})
    result = guardrail.validate(_report(), ("desk@firm.com", "leak@external.com"))
    assert result.severity is GuardrailSeverity.CRITICAL
    assert "leak@external.com" in (result.context or {}).get("unknown", "")


def test_report_completeness_passes_for_full_report() -> None:
    result = ReportCompletenessGuardrail().validate(_report(), ("desk@firm.com",))
    assert result.severity is GuardrailSeverity.PASS


def test_report_completeness_aborts_on_empty_body() -> None:
    # model_construct bypasses validation to simulate a malformed report.
    broken = RenderedReport.model_construct(
        subject="Morning Brief",
        html_body="",
        plain_text_body="body " * 20,
        rendered_at=datetime.now(UTC),
        template_version="v1.0",
        additional_formats={},
        contains_disclaimer=True,
    )
    result = ReportCompletenessGuardrail().validate(broken, ("desk@firm.com",))
    assert result.severity is GuardrailSeverity.CRITICAL


def test_disclaimer_passes_when_present() -> None:
    result = DisclaimerGuardrail().validate(_report(contains_disclaimer=True), ("desk@firm.com",))
    assert result.severity is GuardrailSeverity.PASS


def test_disclaimer_warns_when_missing() -> None:
    result = DisclaimerGuardrail().validate(_report(contains_disclaimer=False), ("desk@firm.com",))
    assert result.severity is GuardrailSeverity.WARNING
