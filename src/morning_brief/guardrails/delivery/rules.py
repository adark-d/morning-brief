from __future__ import annotations

from collections.abc import Iterable

from morning_brief.core.interfaces.guardrail import (
    DeliveryGuardrail,
    GuardrailResult,
    GuardrailSeverity,
)
from morning_brief.core.models.report import RenderedReport


class RecipientWhitelistGuardrail(DeliveryGuardrail):
    """Reject delivery if any recipient is not on the configured whitelist."""

    def __init__(self, whitelist: Iterable[str]) -> None:
        self._whitelist = {address.lower() for address in whitelist}

    @property
    def name(self) -> str:
        return "recipient_whitelist"

    def validate(self, report: RenderedReport, recipients: tuple[str, ...]) -> GuardrailResult:
        _ = report  # this rule only inspects recipients; report is part of the interface
        unknown = sorted(r for r in recipients if r.lower() not in self._whitelist)
        if unknown:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.CRITICAL,
                passed=False,
                message=f"Recipients not on whitelist: {unknown}",
                context={"unknown": ", ".join(unknown)},
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message="All recipients on the whitelist",
        )


class ReportCompletenessGuardrail(DeliveryGuardrail):
    """Reject delivery of a report missing its HTML or plain-text body."""

    @property
    def name(self) -> str:
        return "report_completeness"

    def validate(self, report: RenderedReport, recipients: tuple[str, ...]) -> GuardrailResult:
        _ = recipients  # inspects the report only; recipients is part of the interface
        if not report.html_body.strip() or not report.plain_text_body.strip():
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.CRITICAL,
                passed=False,
                message="Report is missing an HTML or plain-text body",
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message="Report has both HTML and plain-text bodies",
        )


class DisclaimerGuardrail(DeliveryGuardrail):
    """Warn if the report carries no compliance disclaimer."""

    @property
    def name(self) -> str:
        return "disclaimer_present"

    def validate(self, report: RenderedReport, recipients: tuple[str, ...]) -> GuardrailResult:
        _ = recipients  # inspects the report only; recipients is part of the interface
        if not report.contains_disclaimer:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.WARNING,
                passed=False,
                message="Report does not carry a compliance disclaimer",
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message="Compliance disclaimer present",
        )
