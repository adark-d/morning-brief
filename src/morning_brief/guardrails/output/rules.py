"""Output guardrails — validate a BriefAnalysis before it reaches the renderer.

Protect recipients from bad model output: fabricated numbers and low-confidence
analyses. Section 13.2 of the architecture document.

Note on scope: rigorous correctness/quality evaluation (LLM-as-judge, factual
accuracy across prompt versions) is the domain of the dedicated evaluation work,
not this guardrail layer. The grounding check here is a fast, conservative
heuristic that flags numbers in the prose with no obvious source in the snapshot —
it raises a WARNING for review rather than a hard abort, to avoid blocking a good
brief on a benign rounding.
"""

from __future__ import annotations

import re

from morning_brief.core.interfaces.guardrail import (
    GuardrailResult,
    GuardrailSeverity,
    OutputGuardrail,
)
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.market_data import MarketSnapshot

_DECIMAL = re.compile(r"\d+\.\d+")
_GROUNDING_TOLERANCE = 0.05


class NumericalGroundingGuardrail(OutputGuardrail):
    """Flag decimal figures in the narrative with no matching value in the snapshot.

    A heuristic hallucination check: it scans the analysis prose for decimal numbers
    (the shape of yields/prices/rates) and verifies each is close to some value in
    the source data. Integers and times are ignored to avoid false positives.
    """

    @property
    def name(self) -> str:
        return "numerical_grounding"

    def validate(self, analysis: BriefAnalysis, source_snapshot: MarketSnapshot) -> GuardrailResult:
        grounded_values = _snapshot_values(source_snapshot)
        cited = _decimals_in(analysis)
        ungrounded = [
            value
            for value in cited
            if not any(abs(value - known) <= _GROUNDING_TOLERANCE for known in grounded_values)
        ]
        if ungrounded:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.WARNING,
                passed=False,
                message=f"Decimal figures with no source in the snapshot: {ungrounded}",
                context={"ungrounded": ", ".join(str(v) for v in ungrounded)},
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message="All cited decimal figures trace to the snapshot",
        )


class ConfidenceGuardrail(OutputGuardrail):
    """Warn when the analysis confidence is below the configured threshold."""

    def __init__(self, warning_threshold: float) -> None:
        self._threshold = warning_threshold

    @property
    def name(self) -> str:
        return "confidence_threshold"

    def validate(self, analysis: BriefAnalysis, source_snapshot: MarketSnapshot) -> GuardrailResult:
        _ = source_snapshot  # confidence is self-contained; snapshot is part of the interface
        if analysis.confidence < self._threshold:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.WARNING,
                passed=False,
                message=f"Confidence {analysis.confidence} below threshold {self._threshold}",
                context={"confidence": str(analysis.confidence)},
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message="Confidence meets threshold",
        )


class NarrativeLengthGuardrail(OutputGuardrail):
    """Warn when the narrative falls outside the configured word band.

    The model schema caps full_narrative by characters — a permissive structural
    ceiling. The business rule (Section 13.2: a 3-minute brief is ~150-500 words)
    is a word count, and it lives here. Outside the band is a WARNING, not an
    abort: a slightly short or long brief is still deliverable and worth flagging
    for review rather than blocking.
    """

    def __init__(self, min_words: int, max_words: int) -> None:
        self._min_words = min_words
        self._max_words = max_words

    @property
    def name(self) -> str:
        return "narrative_length"

    def validate(self, analysis: BriefAnalysis, source_snapshot: MarketSnapshot) -> GuardrailResult:
        _ = source_snapshot  # length is self-contained; snapshot is part of the interface
        word_count = len(analysis.full_narrative.split())
        if not self._min_words <= word_count <= self._max_words:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.WARNING,
                passed=False,
                message=(
                    f"Narrative is {word_count} words; expected {self._min_words}-{self._max_words}"
                ),
                context={"word_count": str(word_count)},
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message=f"Narrative length {word_count} words within range",
        )


def _snapshot_values(snapshot: MarketSnapshot) -> list[float]:
    return (
        [point.yield_pct for point in snapshot.yields.values()]
        + [point.price for point in snapshot.instruments.values()]
        + [point.rate for point in snapshot.fx.values()]
    )


def _decimals_in(analysis: BriefAnalysis) -> list[float]:
    text = " ".join(
        [
            analysis.headline,
            analysis.yield_curve_summary,
            analysis.macro_context,
            analysis.full_narrative,
            *analysis.key_signals,
            *analysis.watch_today,
        ]
    )
    return [float(match) for match in _DECIMAL.findall(text)]
