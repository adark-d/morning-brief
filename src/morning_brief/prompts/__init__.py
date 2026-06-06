"""Prompt layer — versioned templates, registry, builder, and validator.

Prompts are versioned YAML assets, not strings in code. The registry loads them by
name and version; the builder assembles them into a complete prompt; the validator
checks completeness and token budget before the prompt reaches the LLM.
"""

from morning_brief.prompts.builder import PromptBuilder
from morning_brief.prompts.models import (
    AssembledPrompt,
    ContextTemplate,
    FewShotExample,
    FewShotExamples,
    OutputSchema,
    PromptSelection,
    SystemPrompt,
)
from morning_brief.prompts.registry import PromptRegistry
from morning_brief.prompts.validator import PromptValidator

__all__ = [
    "AssembledPrompt",
    "ContextTemplate",
    "FewShotExample",
    "FewShotExamples",
    "OutputSchema",
    "PromptBuilder",
    "PromptRegistry",
    "PromptSelection",
    "PromptValidator",
    "SystemPrompt",
]
