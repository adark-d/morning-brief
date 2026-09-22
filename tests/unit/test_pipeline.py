from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from ai_brief.models import Issue, Selection
from ai_brief.pipeline import run_pipeline
from brief_core.settings import Settings
from tests.mock_analyst import MockAnalyst


async def test_pipeline_preview_returns_brief_without_delivery(
    issue: Issue, monkeypatch: pytest.MonkeyPatch
) -> None:
    sender = AsyncMock()
    monkeypatch.setattr("ai_brief.pipeline.fetch_issue", AsyncMock(return_value=issue))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(404, request=r))
    ) as client:
        run = await run_pipeline(
            Settings(),
            client,
            MockAnalyst(),
            sender,
            issue.collected_at,
        )
    assert run.status == "preview"
    assert "<!doctype html>" in run.html
    assert run.warnings
    sender.assert_not_called()


async def test_pipeline_quiet_day_completes_without_explanation_or_delivery(
    issue: Issue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = Mock(input_tokens=10, output_tokens=2)
    analyst.select = AsyncMock(return_value=Selection(story_ids=()))
    analyst.explain = AsyncMock()
    sender = AsyncMock()
    enrich = AsyncMock()
    monkeypatch.setattr("ai_brief.pipeline.fetch_issue", AsyncMock(return_value=issue))
    monkeypatch.setattr("ai_brief.pipeline.enrich", enrich)
    settings = Settings(
        send_email=True, sender="from@example.com", recipients=("reader@example.com",)
    )

    async with httpx.AsyncClient() as client:
        run = await run_pipeline(settings, client, analyst, sender, issue.collected_at)

    assert run.status == "skipped"
    assert run.brief is None
    assert run.html == ""
    analyst.explain.assert_not_awaited()
    enrich.assert_not_awaited()
    sender.assert_not_awaited()


async def test_pipeline_enrichment_budget_preserves_summary_delivery(
    issue: Issue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from ai_brief.models import Story

    stories = tuple(issue.stories[0].model_copy(update={"id": str(i)}) for i in range(3))
    issue = issue.model_copy(update={"stories": stories})
    attempts: list[str] = []

    async def stalled_fetch(
        client: httpx.AsyncClient,
        story: Story,
        hosts: tuple[str, ...],
        min_chars: int,
        max_chars: int,
    ) -> Story:
        _ = (client, hosts, min_chars, max_chars)
        attempts.append(story.id)
        await asyncio.Event().wait()
        return story

    sender = AsyncMock()
    monkeypatch.setattr("ai_brief.pipeline.fetch_issue", AsyncMock(return_value=issue))
    monkeypatch.setattr("ai_brief.pipeline.enrich", stalled_fetch)
    settings = Settings(
        send_email=True,
        sender="from@example.com",
        recipients=("reader@example.com",),
        enrichment_timeout_seconds=0.01,
    )
    async with httpx.AsyncClient() as client:
        run = await run_pipeline(settings, client, MockAnalyst(), sender, issue.collected_at)
    assert run.status == "success"
    assert len(run.warnings) == 3
    assert attempts == ["0"]
    sender.assert_awaited_once()
