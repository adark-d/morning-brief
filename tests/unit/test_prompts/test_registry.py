"""Tests for PromptRegistry loading the bundled templates."""

from __future__ import annotations

import pytest

from morning_brief.core.exceptions.errors import PromptNotFoundError
from morning_brief.prompts.registry import PromptRegistry


@pytest.fixture
def registry() -> PromptRegistry:
    return PromptRegistry()


def test_loads_system_prompt(registry: PromptRegistry) -> None:
    system = registry.system("senior_analyst", "v1.0")
    assert system.name == "senior_analyst"
    assert system.version == "v1.0"
    assert "fixed income analyst" in system.content
    assert system.guardrail_instructions.strip()


def test_loads_each_component_kind(registry: PromptRegistry) -> None:
    assert registry.context("market_data", "v1.0").template
    assert registry.output_schema("brief_schema", "v1.0").description
    assert len(registry.few_shot("examples", "v1.0").examples) >= 2


def test_missing_component_raises(registry: PromptRegistry) -> None:
    with pytest.raises(PromptNotFoundError):
        registry.system("does_not_exist", "v9.9")


def test_list_versions(registry: PromptRegistry) -> None:
    assert registry.list_versions("system", "senior_analyst") == ("v1.0",)


def test_loads_are_cached(registry: PromptRegistry) -> None:
    first = registry.system("senior_analyst", "v1.0")
    second = registry.system("senior_analyst", "v1.0")
    assert first == second
