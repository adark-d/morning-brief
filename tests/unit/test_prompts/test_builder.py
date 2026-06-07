from __future__ import annotations

import pytest
from tests.fixtures import make_market_snapshot

from morning_brief.prompts.builder import PromptBuilder
from morning_brief.prompts.models import PromptSelection
from morning_brief.prompts.registry import PromptRegistry


@pytest.fixture
def builder() -> PromptBuilder:
    return PromptBuilder(PromptRegistry(), PromptSelection())


def test_system_prompt_includes_all_stable_sections(builder: PromptBuilder) -> None:
    assembled = builder.build(make_market_snapshot())

    assert "fixed income analyst" in assembled.system  # persona
    assert "Output format" in assembled.system  # schema description section
    assert "Worked examples" in assembled.system  # few-shot section
    assert "Never state" in assembled.system  # guardrail instructions


def test_context_renders_the_snapshot_data(builder: PromptBuilder) -> None:
    assembled = builder.build(make_market_snapshot())

    assert "10Y" in assembled.context  # the default snapshot has a 10Y yield
    assert "4.42" in assembled.context
    assert "Data quality" in assembled.context


def test_empty_sections_render_as_none_available(builder: PromptBuilder) -> None:
    snapshot = make_market_snapshot()  # has yields, but no instruments or fx
    assembled = builder.build(snapshot)
    assert "(none available)" in assembled.context


def test_version_is_a_composite_of_component_versions(builder: PromptBuilder) -> None:
    assembled = builder.build(make_market_snapshot())
    assert "senior_analyst@v1.0" in assembled.version
    assert "market_data@v1.0" in assembled.version
    assert "brief_schema@v1.0" in assembled.version


def test_full_prompt_joins_system_and_context(builder: PromptBuilder) -> None:
    assembled = builder.build(make_market_snapshot())
    assert assembled.system in assembled.full_prompt
    assert assembled.context in assembled.full_prompt
