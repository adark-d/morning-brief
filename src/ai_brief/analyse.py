from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import structlog
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from ai_brief.checks import check_brief, check_ids
from ai_brief.models import Brief, BriefError, Selection, Story
from ai_brief.prompt import EXPLANATION_PROMPT, SELECTION_PROMPT


def _input_context(interests: str, stories: tuple[Story, ...]) -> str:
    """Delimit runtime data so it remains separate from the instructions."""

    payload = json.dumps(
        {
            "interests": interests,
            "stories": [story.model_dump(mode="json") for story in stories],
        }
    )
    return f"# Input data\n\n{payload}"


class Analyst(Protocol):
    """The analysis operations and usage totals required by the pipeline."""

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...

    async def select(self, stories: tuple[Story, ...], interests: str) -> Selection: ...

    async def explain(self, stories: tuple[Story, ...], interests: str) -> Brief: ...


@dataclass
class NewsAnalyst:
    """Analysis and usage for one run; create a fresh instance for each brief."""

    selection_model: Model
    explanation_model: Model
    topic_count: int = 5
    selection_max_tokens: int = 1_000
    explanation_max_tokens: int = 6_000
    retries: int = 1
    request_limit: int = 2
    input_tokens: int = 0
    output_tokens: int = 0

    async def select(self, stories: tuple[Story, ...], interests: str) -> Selection:
        """Choose useful stories and track model usage."""

        agent = Agent(
            self.selection_model,
            output_type=Selection,
            retries=self.retries,
            instructions=SELECTION_PROMPT.format(topic_count=self.topic_count),
        )

        def validate_selection(selection: Selection) -> Selection:
            """Let the model correct invalid IDs; an empty selection ends the run."""
            try:
                check_ids(selection.story_ids, stories, self.topic_count)
            except BriefError as exc:
                structlog.get_logger(__name__).warning(
                    "model_output_rejected", task="selection", reason=str(exc)
                )
                raise ModelRetry(str(exc)) from exc
            return selection

        agent.output_validator(validate_selection)
        usage = RunUsage()
        try:
            result = await agent.run(
                _input_context(interests, stories),
                usage=usage,
                usage_limits=UsageLimits(request_limit=self.request_limit),
                model_settings={"max_tokens": self.selection_max_tokens},
            )
        finally:
            # Retain reported usage even when validation or a later request fails.
            self.input_tokens += usage.input_tokens
            self.output_tokens += usage.output_tokens
        return result.output

    async def explain(self, stories: tuple[Story, ...], interests: str) -> Brief:
        """Turn selected stories into grounded lessons and track model usage."""

        agent = Agent(
            self.explanation_model,
            output_type=Brief,
            retries=self.retries,
            instructions=EXPLANATION_PROMPT,
        )

        def validate_lessons(brief: Brief) -> Brief:
            """Return failed content checks to the model for correction."""
            try:
                check_brief(brief, stories, self.topic_count)
            except BriefError as exc:
                structlog.get_logger(__name__).warning(
                    "model_output_rejected", task="explanation", reason=str(exc)
                )
                raise ModelRetry(str(exc)) from exc
            return brief

        agent.output_validator(validate_lessons)
        usage = RunUsage()
        try:
            result = await agent.run(
                _input_context(interests, stories),
                usage=usage,
                usage_limits=UsageLimits(request_limit=self.request_limit),
                model_settings={"max_tokens": self.explanation_max_tokens},
            )
        finally:
            # Retain reported usage even when validation or a later request fails.
            self.input_tokens += usage.input_tokens
            self.output_tokens += usage.output_tokens
        return result.output
