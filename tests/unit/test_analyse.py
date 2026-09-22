from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from ai_brief.analyse import NewsAnalyst
from ai_brief.models import Issue
from tests.mock_analyst import MockAnalyst


async def test_news_analyst_invalid_selection_corrected_on_retry(issue: Issue) -> None:
    attempts = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        correcting = any(
            isinstance(part, RetryPromptPart)
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
        )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name, {"story_ids": ["one" if correcting else "invented"]}
                )
            ],
            timestamp=issue.collected_at,
        )

    model = FunctionModel(respond)
    result = await NewsAnalyst(model, model).select(issue.stories, "evals")
    assert result.story_ids == ("one",)
    assert attempts == 2


async def test_news_analyst_invalid_lesson_corrected_on_retry(issue: Issue) -> None:
    expected = await MockAnalyst().explain(issue.stories, "evals")
    invalid = expected.model_copy(
        update={
            "lessons": (expected.lessons[0].model_copy(update={"explanation": "   "}),),
        }
    )
    attempts = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        correcting = any(
            isinstance(part, RetryPromptPart)
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
        )
        output = expected if correcting else invalid
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))],
            timestamp=issue.collected_at,
        )

    model = FunctionModel(respond)
    result = await NewsAnalyst(model, model).explain(issue.stories, "evals")
    assert result == expected
    assert attempts == 2


async def test_news_analyst_empty_selection_stops_without_forcing_relevance(issue: Issue) -> None:
    model = TestModel(custom_output_args={"story_ids": []})
    selection = await NewsAnalyst(model, model).select(issue.stories, "evals")
    assert selection.story_ids == ()


async def test_news_analyst_long_explanation_accepted_without_retry(issue: Issue) -> None:
    brief = await MockAnalyst().explain(issue.stories, "evals")
    explanation = (
        "A useful explanation can take more space than a fixed word count allows. " * 80
    ).strip()
    lesson = brief.lessons[0].model_copy(update={"explanation": explanation})
    expected = brief.model_copy(update={"lessons": (lesson,)})
    model = TestModel(custom_output_args=expected.model_dump(mode="json"))

    result = await NewsAnalyst(model, model, retries=0).explain(issue.stories, "evals")

    assert result == expected
