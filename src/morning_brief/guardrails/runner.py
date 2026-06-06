"""Guardrail runner — executes a tier of guardrails and aggregates the verdict.

Each tier (input, output, delivery) has a different validate() signature, so there
is one run function per tier. All return a GuardrailReport carrying every result
plus the aggregate severity. The orchestrator (Phase 6) decides what to do:
    - CRITICAL  -> abort the pipeline, emit an alert, no delivery
    - WARNING   -> continue, attach the warning to the run
    - PASS      -> continue normally
"""

from __future__ import annotations

from dataclasses import dataclass

from morning_brief.core.interfaces.guardrail import (
    DeliveryGuardrail,
    GuardrailResult,
    GuardrailSeverity,
    InputGuardrail,
    OutputGuardrail,
)
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.market_data import MarketSnapshot
from morning_brief.core.models.report import RenderedReport


@dataclass(frozen=True, slots=True)
class GuardrailReport:
    """The outcome of running a tier of guardrails."""

    results: tuple[GuardrailResult, ...]

    @property
    def critical(self) -> tuple[GuardrailResult, ...]:
        return tuple(r for r in self.results if r.severity is GuardrailSeverity.CRITICAL)

    @property
    def warnings(self) -> tuple[GuardrailResult, ...]:
        return tuple(r for r in self.results if r.severity is GuardrailSeverity.WARNING)

    @property
    def should_abort(self) -> bool:
        """True if any guardrail returned CRITICAL — the pipeline must stop."""
        return bool(self.critical)

    @property
    def passed(self) -> bool:
        """True only if every guardrail passed cleanly."""
        return all(r.severity is GuardrailSeverity.PASS for r in self.results)


def run_input(
    guardrails: tuple[InputGuardrail, ...],
    snapshot: MarketSnapshot,
) -> GuardrailReport:
    return GuardrailReport(tuple(g.validate(snapshot) for g in guardrails))


def run_output(
    guardrails: tuple[OutputGuardrail, ...],
    analysis: BriefAnalysis,
    source_snapshot: MarketSnapshot,
) -> GuardrailReport:
    return GuardrailReport(tuple(g.validate(analysis, source_snapshot) for g in guardrails))


def run_delivery(
    guardrails: tuple[DeliveryGuardrail, ...],
    report: RenderedReport,
    recipients: tuple[str, ...],
) -> GuardrailReport:
    return GuardrailReport(tuple(g.validate(report, recipients) for g in guardrails))
