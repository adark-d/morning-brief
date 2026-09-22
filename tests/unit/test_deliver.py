from __future__ import annotations

import pytest

from ai_brief.deliver import render
from ai_brief.models import Issue
from tests.mock_analyst import MockAnalyst


async def test_render_html_escapes_model_output_and_labels_summary(issue: Issue) -> None:
    brief = await MockAnalyst().explain(issue.stories, "evals")
    lesson = brief.lessons[0].model_copy(update={"headline": "<script>alert(1)</script>"})
    html = render(brief.model_copy(update={"lessons": (lesson,)}), issue)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "original article was not retrieved" in html


async def test_render_uses_each_story_source_and_actual_topic_count(issue: Issue) -> None:
    story = issue.stories[0].model_copy(update={"source": "Research digest"})
    issue = issue.model_copy(update={"stories": (story,)})
    brief = await MockAnalyst().explain(issue.stories, "evals")
    html = render(brief, issue)
    assert "1 useful idea explained" in html
    assert "Research digest" in html
    assert str(story.source_url) in html
    assert "TLDR issue" not in html


async def test_plain_email_retains_sources_and_excludes_hidden_preview(
    issue: Issue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    from ai_brief.deliver import send_email
    from brief_core.settings import Settings

    brief = await MockAnalyst().explain(issue.stories, "evals")
    transport = AsyncMock()
    monkeypatch.setattr("ai_brief.deliver.send_html_email", transport)
    await send_email(render(brief, issue), Settings())
    plain = transport.call_args.kwargs["plain_text"]
    assert str(issue.stories[0].url) in plain
    assert str(issue.stories[0].source_url) in plain
    assert "1 useful idea explained clearly" not in plain
