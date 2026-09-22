from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx

from ai_brief.pipeline import run_pipeline
from brief_core.settings import Settings
from tests.mock_analyst import MockAnalyst


async def test_learning_pipeline_fetches_sources_and_delivers() -> None:
    text = "Evaluation datasets let builders compare changes against representative examples. " * 4
    visited: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        visited.append(str(request.url))
        if request.url.path == "/api/rss/ai":
            body = (
                "<rss><channel><item><link>https://tldr.tech/ai/2026-09-21</link>"
                "<pubDate>Mon, 21 Sep 2026 00:00:00 GMT</pubDate></item></channel></rss>"
            )
            content_type = "text/xml"
        elif request.url.host == "tldr.tech":
            body = (
                '<article><a href="https://example.org/evals">Evaluation datasets '
                f"(2 minute read)</a><p>{text}</p></article>"
                '<article><a href="https://example.org/ad">Ad (Sponsor)</a></article>'
            )
            content_type = "text/html"
        else:
            body = f"<main><h1>Evaluation datasets</h1><p>{text}</p></main>"
            content_type = "text/html"
        return httpx.Response(
            200, text=body, headers={"content-type": content_type}, request=request
        )

    sender = AsyncMock()
    settings = Settings(
        send_email=True,
        sender="sender@example.com",
        recipients=("reader@example.com",),
        source_hosts=("example.org",),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        run = await run_pipeline(
            settings, client, MockAnalyst(), sender, datetime(2026, 9, 22, tzinfo=UTC)
        )

    assert run.status == "success"
    assert not run.warnings
    assert visited == [
        "https://tldr.tech/api/rss/ai",
        "https://tldr.tech/ai/2026-09-21",
        "https://example.org/evals",
    ]
    sender.assert_awaited_once()
    assert "Evaluation datasets" in sender.call_args.args[0]
