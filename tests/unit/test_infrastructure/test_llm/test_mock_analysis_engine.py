"""Tests for MockAnalysisEngine."""

from __future__ import annotations

import pytest
from tests.fixtures import make_market_snapshot

from morning_brief.core.exceptions.errors import InvalidResponseError, ModelUnavailableError
from morning_brief.core.interfaces.base import HealthState
from morning_brief.infrastructure.llm.mock_analysis_engine import MockAnalysisEngine


@pytest.mark.asyncio
async def test_returns_valid_analysis_with_provenance() -> None:
    engine = MockAnalysisEngine(model="mock-model", cost_usd=0.01)
    analysis = await engine.analyse(make_market_snapshot(), "prompt", prompt_version="v1.0")

    assert analysis.model_used == "mock-model"
    assert analysis.prompt_version == "v1.0"
    assert analysis.cost_usd == 0.01
    assert 0.0 <= analysis.confidence <= 1.0
    assert len(analysis.key_signals) >= 2


@pytest.mark.asyncio
async def test_fail_unavailable_raises_model_unavailable() -> None:
    engine = MockAnalysisEngine(fail_unavailable=True)
    with pytest.raises(ModelUnavailableError):
        await engine.analyse(make_market_snapshot(), "prompt")


@pytest.mark.asyncio
async def test_fail_invalid_raises_invalid_response() -> None:
    engine = MockAnalysisEngine(fail_invalid=True)
    with pytest.raises(InvalidResponseError):
        await engine.analyse(make_market_snapshot(), "prompt")


@pytest.mark.asyncio
async def test_unhealthy_flag() -> None:
    engine = MockAnalysisEngine(unhealthy=True)
    status = await engine.health_check()
    assert status.state == HealthState.UNHEALTHY
