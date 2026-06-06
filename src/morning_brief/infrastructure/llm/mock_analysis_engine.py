"""Deterministic in-memory AnalysisEngine for testing.

Returns a fixed, valid BriefAnalysis without calling Claude. Constructor flags
simulate the failure modes the pipeline must degrade against.

Implements core.interfaces.analysis_engine.AnalysisEngine.
"""

from __future__ import annotations

from datetime import UTC, datetime

from morning_brief.core.exceptions.errors import InvalidResponseError, ModelUnavailableError
from morning_brief.core.interfaces.analysis_engine import AnalysisEngine
from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.market_data import MarketSnapshot


class MockAnalysisEngine(AnalysisEngine):
    """Deterministic AnalysisEngine for testing the pipeline without Claude."""

    def __init__(
        self,
        *,
        model: str = "mock-model",
        cost_usd: float | None = 0.0,
        fail_unavailable: bool = False,
        fail_invalid: bool = False,
        unhealthy: bool = False,
    ) -> None:
        self._model = model
        self._cost_usd = cost_usd
        self._fail_unavailable = fail_unavailable
        self._fail_invalid = fail_invalid
        self._unhealthy = unhealthy

    async def analyse(
        self,
        snapshot: MarketSnapshot,
        prompt: str,
        *,
        prompt_version: str = "unversioned",
        max_tokens: int = 2000,
        timeout_seconds: float = 30.0,
    ) -> BriefAnalysis:
        # The mock ignores the inputs except prompt_version; reference them so the
        # signature can mirror the interface without tripping unused-argument lint.
        _ = (snapshot, prompt, max_tokens, timeout_seconds)
        if self._fail_unavailable:
            raise ModelUnavailableError("Mock configured to simulate an unavailable model")
        if self._fail_invalid:
            raise InvalidResponseError("Mock configured to simulate an invalid response")

        return BriefAnalysis(
            headline="Yields steady ahead of the CPI release at 13:30 GMT.",
            yield_curve_summary="2s10s spread holds near 38 bps, signalling cautious risk appetite.",
            key_signals=("Steady front-end yields", "Risk-off equity futures"),
            macro_context="Oil firm, dollar softer, VIX subdued — markets in wait-and-see mode.",
            watch_today=("US CPI at 13:30 GMT", "30Y auction at 18:00 GMT"),
            full_narrative=(
                # Spec-compliant length (~150-500 words) and deliberately decimal-free, so a
                # mock pipeline run passes the length and numerical-grounding guardrails cleanly
                # against any snapshot.
                "Markets enter the session in a holding pattern ahead of the US CPI release, "
                "with desks reluctant to add risk before the print. Treasury yields are little "
                "changed across the curve, the front end anchored as traders await fresh "
                "inflation data, and the long end steady on limited supply pressure. The curve "
                "remains modestly inverted, signalling a market that is cautious rather than "
                "convinced of a near-term policy shift. Crude is firmer on renewed supply "
                "concerns, the dollar is modestly softer against the majors, and equity futures "
                "point to a broadly flat open. Credit spreads remain well behaved, with no sign "
                "of stress in investment-grade or high-yield cash, and volatility sits near the "
                "low end of its recent range. Today's CPI print is the decisive event on the "
                "calendar; a hotter-than-expected number could revive the higher-for-longer "
                "narrative, lift front-end yields, and flatten the curve further, while a softer "
                "reading would likely see duration bid and the front end richen. Beyond the data, "
                "desks are watching the afternoon government auction for a read on sponsorship, "
                "where a weak tail or soft bid-to-cover would hint at waning demand. Positioning "
                "is light and conviction low, so the brief counsels patience: let the print set "
                "direction rather than anticipating it, and keep risk measured into the number."
            ),
            confidence=0.82,
            model_used=self._model,
            prompt_version=prompt_version,
            generated_at=datetime.now(UTC),
            cost_usd=self._cost_usd,
        )

    async def health_check(self) -> HealthStatus:
        state = HealthState.UNHEALTHY if self._unhealthy else HealthState.HEALTHY
        return HealthStatus(
            state=state,
            component="MockAnalysisEngine",
            message="Mock analysis engine ready",
            latency_ms=0.0,
        )
