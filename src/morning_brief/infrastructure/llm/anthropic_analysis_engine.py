from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Final

import anthropic
import structlog
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, ValidationError

from morning_brief.core.exceptions.errors import (
    AnalysisTimeoutError,
    InvalidResponseError,
    ModelUnavailableError,
)
from morning_brief.core.interfaces.analysis_engine import AnalysisEngine
from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.market_data import MarketSnapshot

if TYPE_CHECKING:
    from anthropic.types import Usage

logger = structlog.get_logger(__name__)

# Per-1M-token pricing (input, output) in USD. Models absent here yield cost=None.
_PRICING: Final[dict[str, tuple[float, float]]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

_CORRECTIVE_INSTRUCTION: Final = (
    "Your previous response did not satisfy the required schema or field limits. "
    "Return only valid structured output that respects every field constraint."
)


class _AnalysisDraft(BaseModel):
    """The content Claude produces — provenance (model, version, cost) is added by us.

    Field constraints mirror BriefAnalysis so the SDK validates the model's output
    against the same business rules client-side.
    """

    headline: Annotated[str, Field(min_length=10, max_length=150)]
    yield_curve_summary: Annotated[str, Field(min_length=20, max_length=300)]
    key_signals: Annotated[list[str], Field(min_length=2, max_length=5)]
    macro_context: Annotated[str, Field(min_length=20, max_length=400)]
    watch_today: Annotated[list[str], Field(min_length=2, max_length=3)]
    full_narrative: Annotated[str, Field(min_length=150, max_length=4000)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class AnthropicAnalysisEngine(AnalysisEngine):
    """Produces a BriefAnalysis by calling Claude with structured output."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        fallback_model: str | None = None,
        max_retries: int = 2,
        client: AsyncAnthropic | None = None,
    ) -> None:
        """Initialise the engine.

        Args:
            model: Primary Claude model id.
            api_key: Anthropic API key. Ignored if ``client`` is supplied.
            fallback_model: Model to try if the primary is unavailable.
            max_retries: SDK transport retries (429/5xx/connection).
            client: Pre-built AsyncAnthropic (used by tests); built from api_key otherwise.
        """
        self._model = model
        self._fallback_model = fallback_model
        self._client = client or AsyncAnthropic(api_key=api_key, max_retries=max_retries)
        logger.info("anthropic_engine_initialised", model=model, fallback_model=fallback_model)

    async def analyse(
        self,
        snapshot: MarketSnapshot,
        prompt: str,
        *,
        prompt_version: str = "unversioned",
        max_tokens: int = 2000,
        timeout_seconds: float = 30.0,
    ) -> BriefAnalysis:
        user_content = _format_snapshot(snapshot)
        try:
            return await self._analyse_with_model(
                self._model, prompt, user_content, prompt_version, max_tokens, timeout_seconds
            )
        except ModelUnavailableError:
            if self._fallback_model is None:
                raise
            logger.warning(
                "primary_model_unavailable_falling_back",
                primary=self._model,
                fallback=self._fallback_model,
            )
            return await self._analyse_with_model(
                self._fallback_model,
                prompt,
                user_content,
                prompt_version,
                max_tokens,
                timeout_seconds,
            )

    async def health_check(self) -> HealthStatus:
        """Lightweight probe — retrieve the model metadata, not a full inference."""
        start = time.perf_counter()
        try:
            await self._client.models.retrieve(self._model)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                component="AnthropicAnalysisEngine",
                message=f"Claude API probe failed: {exc}",
                latency_ms=elapsed_ms,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return HealthStatus(
            state=HealthState.HEALTHY,
            component="AnthropicAnalysisEngine",
            message=f"Claude model {self._model} reachable",
            latency_ms=elapsed_ms,
        )

    async def _analyse_with_model(
        self,
        model: str,
        prompt: str,
        user_content: str,
        prompt_version: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> BriefAnalysis:
        draft, usage = await self._call_with_validation_retry(
            model, prompt, user_content, max_tokens, timeout_seconds
        )
        return BriefAnalysis(
            headline=draft.headline,
            yield_curve_summary=draft.yield_curve_summary,
            key_signals=tuple(draft.key_signals),
            macro_context=draft.macro_context,
            watch_today=tuple(draft.watch_today),
            full_narrative=draft.full_narrative,
            confidence=draft.confidence,
            model_used=model,
            prompt_version=prompt_version,
            generated_at=datetime.now(UTC),
            cost_usd=_estimate_cost(model, usage),
        )

    async def _call_with_validation_retry(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> tuple[_AnalysisDraft, Usage]:
        try:
            return await self._call(model, system_prompt, user_content, max_tokens, timeout_seconds)
        except InvalidResponseError as first_error:
            logger.warning(
                "analysis_validation_failed_retrying", model=model, error=str(first_error)
            )
            corrective_prompt = f"{system_prompt}\n\n{_CORRECTIVE_INSTRUCTION}"
            try:
                return await self._call(
                    model, corrective_prompt, user_content, max_tokens, timeout_seconds
                )
            except InvalidResponseError as second_error:
                raise InvalidResponseError(
                    f"Claude response failed schema validation after one retry: {second_error}"
                ) from second_error

    async def _call(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> tuple[_AnalysisDraft, Usage]:
        try:
            response = await self._client.with_options(timeout=timeout_seconds).messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
                output_format=_AnalysisDraft,
            )
        except anthropic.APITimeoutError as exc:
            raise AnalysisTimeoutError(f"Claude timed out after {timeout_seconds}s") from exc
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
            raise ModelUnavailableError(f"Claude API error for model {model}: {exc}") from exc
        except ValidationError as exc:
            raise InvalidResponseError(f"Claude response failed schema validation: {exc}") from exc

        draft = response.parsed_output
        if draft is None:
            raise InvalidResponseError("Claude returned no structured output")
        return draft, response.usage


def _estimate_cost(model: str, usage: Usage) -> float | None:
    prices = _PRICING.get(model)
    if prices is None:
        logger.warning("unknown_model_pricing", model=model)
        return None
    input_price, output_price = prices
    cost = (usage.input_tokens / 1_000_000) * input_price + (
        usage.output_tokens / 1_000_000
    ) * output_price
    return round(cost, 6)


def _format_snapshot(snapshot: MarketSnapshot) -> str:
    """Render the snapshot into a compact text block for the user message."""
    lines = [f"Market snapshot at {snapshot.timestamp.isoformat()}", ""]

    if snapshot.yields:
        lines.append("Treasury yields (%):")
        lines += [f"  {m}: {p.yield_pct}" for m, p in snapshot.yields.items()]
    if snapshot.instruments:
        lines.append("Instruments:")
        lines += [f"  {s}: {p.price}" for s, p in snapshot.instruments.items()]
    if snapshot.fx:
        lines.append("FX rates:")
        lines += [f"  {pair}: {p.rate}" for pair, p in snapshot.fx.items()]

    dq = snapshot.data_quality
    lines += [
        "",
        f"Data quality: {len(dq.sources_succeeded)}/{len(dq.sources_attempted)} sources, "
        f"stale={dq.is_stale}",
    ]
    return "\n".join(lines)
