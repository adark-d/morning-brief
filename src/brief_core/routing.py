from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from brief_core import BriefCoreError
from brief_core.settings import Settings


@dataclass(frozen=True)
class TaskModels:
    """Claude models used to select topics and explain them."""

    selection: Model
    explanation: Model


@asynccontextmanager
async def build_task_models(settings: Settings) -> AsyncGenerator[TaskModels]:
    """Share one Anthropic client for a brief and close it afterwards."""
    if not settings.anthropic_api_key or not settings.anthropic_api_key.get_secret_value().strip():
        raise BriefCoreError("Set ANTHROPIC_API_KEY or MORNING_BRIEF_ANTHROPIC_API_KEY")

    # Pydantic AI handles output corrections within the pipeline's stage deadlines.
    async with AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.model_timeout_seconds,
        max_retries=0,
    ) as client:
        provider = AnthropicProvider(anthropic_client=client)
        yield TaskModels(
            selection=AnthropicModel(settings.selection_model, provider=provider),
            explanation=AnthropicModel(settings.explanation_model, provider=provider),
        )
