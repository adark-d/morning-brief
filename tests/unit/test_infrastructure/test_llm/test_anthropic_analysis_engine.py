from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import anthropic
import httpx
import pytest
from pydantic import ValidationError
from tests.fixtures import make_market_snapshot

from morning_brief.core.exceptions.errors import (
    AnalysisTimeoutError,
    InvalidResponseError,
    ModelUnavailableError,
)
from morning_brief.core.interfaces.base import HealthState
from morning_brief.infrastructure.llm.anthropic_analysis_engine import (
    AnthropicAnalysisEngine,
    _AnalysisDraft,
)

_NARRATIVE = (
    "Markets enter the session in a holding pattern ahead of the US CPI release. "
    "Treasury yields are little changed and the dollar is modestly softer, while crude "
    "is firmer on supply concerns and equity futures point to a flat open this morning."
)

_VALID_DRAFT = _AnalysisDraft(
    headline="Yields steady ahead of the CPI release at 13:30 GMT.",
    yield_curve_summary="2s10s spread holds near 38 bps, signalling cautious risk appetite.",
    key_signals=["Steady front-end yields", "Risk-off equity futures"],
    macro_context="Oil firm, dollar softer, VIX subdued — markets in wait-and-see mode.",
    watch_today=["US CPI at 13:30 GMT", "30Y auction at 18:00 GMT"],
    full_narrative=_NARRATIVE,
    confidence=0.8,
)

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _parsed(input_tokens: int = 1_000_000, output_tokens: int = 1_000_000) -> MagicMock:
    response = MagicMock()
    response.parsed_output = _VALID_DRAFT
    response.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return response


def _validation_error() -> ValidationError:
    try:
        _AnalysisDraft.model_validate({"headline": "too short"})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


@pytest.fixture
def client() -> Iterator[MagicMock]:
    mock = MagicMock()
    mock.with_options.return_value = mock  # with_options(timeout=...) -> same mock
    mock.messages.parse = AsyncMock()
    mock.models.retrieve = AsyncMock()
    yield mock


@pytest.mark.asyncio
async def test_maps_structured_output_and_records_provenance(client: MagicMock) -> None:
    client.messages.parse.return_value = _parsed()
    engine = AnthropicAnalysisEngine(model="claude-opus-4-8", client=client)

    analysis = await engine.analyse(make_market_snapshot(), "system prompt", prompt_version="v1.0")

    assert analysis.model_used == "claude-opus-4-8"
    assert analysis.prompt_version == "v1.0"
    assert analysis.key_signals == ("Steady front-end yields", "Risk-off equity futures")
    # 1M input @ $5 + 1M output @ $25 = $30.00
    assert analysis.cost_usd == 30.0


@pytest.mark.asyncio
async def test_unknown_model_yields_no_cost(client: MagicMock) -> None:
    client.messages.parse.return_value = _parsed()
    engine = AnthropicAnalysisEngine(model="some-unpriced-model", client=client)

    analysis = await engine.analyse(make_market_snapshot(), "prompt")
    assert analysis.cost_usd is None


@pytest.mark.asyncio
async def test_validation_failure_retries_once_then_succeeds(client: MagicMock) -> None:
    client.messages.parse.side_effect = [_validation_error(), _parsed()]
    engine = AnthropicAnalysisEngine(model="claude-opus-4-8", client=client)

    analysis = await engine.analyse(make_market_snapshot(), "prompt")

    assert analysis.headline.startswith("Yields steady")
    assert client.messages.parse.await_count == 2


@pytest.mark.asyncio
async def test_validation_failure_twice_raises_invalid_response(client: MagicMock) -> None:
    client.messages.parse.side_effect = [_validation_error(), _validation_error()]
    engine = AnthropicAnalysisEngine(model="claude-opus-4-8", client=client)

    with pytest.raises(InvalidResponseError):
        await engine.analyse(make_market_snapshot(), "prompt")
    assert client.messages.parse.await_count == 2


@pytest.mark.asyncio
async def test_timeout_maps_to_analysis_timeout(client: MagicMock) -> None:
    client.messages.parse.side_effect = anthropic.APITimeoutError(request=_REQUEST)
    engine = AnthropicAnalysisEngine(model="claude-opus-4-8", client=client)

    with pytest.raises(AnalysisTimeoutError):
        await engine.analyse(make_market_snapshot(), "prompt")


@pytest.mark.asyncio
async def test_connection_error_without_fallback_raises_unavailable(client: MagicMock) -> None:
    client.messages.parse.side_effect = anthropic.APIConnectionError(request=_REQUEST)
    engine = AnthropicAnalysisEngine(model="claude-opus-4-8", client=client)

    with pytest.raises(ModelUnavailableError):
        await engine.analyse(make_market_snapshot(), "prompt")


@pytest.mark.asyncio
async def test_falls_back_to_secondary_model_when_primary_unavailable(client: MagicMock) -> None:
    client.messages.parse.side_effect = [
        anthropic.APIConnectionError(request=_REQUEST),  # primary fails
        _parsed(input_tokens=1_000_000, output_tokens=1_000_000),  # fallback succeeds
    ]
    engine = AnthropicAnalysisEngine(
        model="claude-opus-4-8",
        fallback_model="claude-haiku-4-5",
        client=client,
    )

    analysis = await engine.analyse(make_market_snapshot(), "prompt")

    assert analysis.model_used == "claude-haiku-4-5"
    # haiku pricing: 1M @ $1 + 1M @ $5 = $6.00
    assert analysis.cost_usd == 6.0
    assert client.messages.parse.await_count == 2


@pytest.mark.asyncio
async def test_health_check_healthy_when_model_reachable(client: MagicMock) -> None:
    engine = AnthropicAnalysisEngine(model="claude-opus-4-8", client=client)
    status = await engine.health_check()
    assert status.state == HealthState.HEALTHY


@pytest.mark.asyncio
async def test_health_check_unhealthy_when_probe_fails(client: MagicMock) -> None:
    client.models.retrieve.side_effect = anthropic.APIConnectionError(request=_REQUEST)
    engine = AnthropicAnalysisEngine(model="claude-opus-4-8", client=client)

    status = await engine.health_check()
    assert status.state == HealthState.UNHEALTHY
