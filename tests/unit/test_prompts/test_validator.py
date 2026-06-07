from __future__ import annotations

import pytest
from tests.fixtures import make_market_snapshot

from morning_brief.core.exceptions.errors import IncompletePromptError
from morning_brief.prompts.builder import PromptBuilder
from morning_brief.prompts.models import AssembledPrompt
from morning_brief.prompts.registry import PromptRegistry
from morning_brief.prompts.validator import PromptValidator


@pytest.fixture
def assembled() -> AssembledPrompt:
    return PromptBuilder(PromptRegistry()).build(make_market_snapshot())


def test_validate_passes_for_a_complete_prompt(assembled: AssembledPrompt) -> None:
    PromptValidator().validate(assembled)  # should not raise


def test_validate_rejects_missing_system() -> None:
    with pytest.raises(IncompletePromptError):
        PromptValidator().validate(AssembledPrompt(system="  ", context="data", version="v"))


def test_validate_rejects_missing_context() -> None:
    with pytest.raises(IncompletePromptError):
        PromptValidator().validate(AssembledPrompt(system="sys", context="", version="v"))


def test_estimate_tokens_is_positive(assembled: AssembledPrompt) -> None:
    assert PromptValidator().estimate_tokens(assembled) > 0


def test_within_budget_flags_oversized_prompt(assembled: AssembledPrompt) -> None:
    assert PromptValidator(max_tokens=100_000).within_budget(assembled) is True
    assert PromptValidator(max_tokens=1).within_budget(assembled) is False
