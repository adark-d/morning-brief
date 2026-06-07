from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from morning_brief.core.interfaces.guardrail import (
    GuardrailResult,
    GuardrailSeverity,
    InputGuardrail,
)
from morning_brief.core.models.market_data import MarketSnapshot


class YieldRangeGuardrail(InputGuardrail):
    """Reject the snapshot if any Treasury yield is outside the plausible range.

    Catches the classic data-corruption bug (e.g. a 10Y printed as 14.42% or a
    decimal-form 0.0442). Out of range is CRITICAL — wrong numbers must never
    reach the model.
    """

    def __init__(self, min_pct: float, max_pct: float) -> None:
        self._min = min_pct
        self._max = max_pct

    @property
    def name(self) -> str:
        return "yield_range"

    def validate(self, snapshot: MarketSnapshot) -> GuardrailResult:
        out_of_range = {
            maturity: point.yield_pct
            for maturity, point in snapshot.yields.items()
            if not (self._min <= point.yield_pct <= self._max)
        }
        if out_of_range:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.CRITICAL,
                passed=False,
                message=f"Yields outside [{self._min}, {self._max}]: {out_of_range}",
                context={m: str(v) for m, v in out_of_range.items()},
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message="All yields within plausible range",
        )


class CompletenessGuardrail(InputGuardrail):
    """Require a minimum number of Treasury maturities.

    Zero yields is a CRITICAL abort (no curve to analyse); fewer than the required
    count is a WARNING (degrade with a flag).
    """

    def __init__(self, min_maturities_required: int) -> None:
        self._min_required = min_maturities_required

    @property
    def name(self) -> str:
        return "yield_completeness"

    def validate(self, snapshot: MarketSnapshot) -> GuardrailResult:
        count = len(snapshot.yields)
        if count == 0:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.CRITICAL,
                passed=False,
                message="No Treasury yields available",
                context={"count": "0"},
            )
        if count < self._min_required:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.WARNING,
                passed=False,
                message=f"Only {count} of {self._min_required} required maturities",
                context={"count": str(count), "required": str(self._min_required)},
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message=f"{count} maturities available",
        )


class StalenessGuardrail(InputGuardrail):
    """Flag or reject the snapshot based on how old its data is.

    Older than ``warn_after_hours`` (or already flagged stale) is a WARNING;
    older than ``reject_after_hours`` is a CRITICAL abort.

    The clock is injected so the rule stays a pure function of its inputs and tests
    are deterministic; the default reads the real UTC clock.
    """

    def __init__(
        self,
        warn_after_hours: float,
        reject_after_hours: float = 24.0,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._warn_after = warn_after_hours
        self._reject_after = reject_after_hours
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def name(self) -> str:
        return "staleness"

    def validate(self, snapshot: MarketSnapshot) -> GuardrailResult:
        age_hours = (self._now() - snapshot.timestamp).total_seconds() / 3600
        context = {"age_hours": f"{age_hours:.2f}"}

        if age_hours > self._reject_after:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.CRITICAL,
                passed=False,
                message=f"Data is {age_hours:.1f}h old (reject threshold {self._reject_after}h)",
                context=context,
            )
        if age_hours > self._warn_after or snapshot.data_quality.is_stale:
            return GuardrailResult(
                rule_name=self.name,
                severity=GuardrailSeverity.WARNING,
                passed=False,
                message=f"Data is {age_hours:.1f}h old (warn threshold {self._warn_after}h)",
                context=context,
            )
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.PASS,
            passed=True,
            message="Data is fresh",
            context=context,
        )
