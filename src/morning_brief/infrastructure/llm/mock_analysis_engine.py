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
                "Markets enter the session in a holding pattern ahead of the US CPI release. "
                "Treasury yields are little changed across the curve and the dollar is modestly "
                "softer. Crude is firmer on supply concerns while equity futures point to a flat "
                "open. The CPI print is the decisive event; a hotter number could revive the "
                "higher-for-longer narrative and steepen the front end of the curve."
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
