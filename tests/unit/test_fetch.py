from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from ai_brief.content import canonical_url
from ai_brief.fetch import fetch_issue
from ai_brief.models import BriefError
from ai_brief.sources.tldr import TldrSource, parse_stories


def test_parse_stories_excludes_sponsors_and_duplicate_links() -> None:
    html = """<article><a href="https://example.org/a">A (2 minute read)</a><p>Summary</p></article>
    <article><a href="https://example.org/a">Duplicate</a></article>
    <article><a href="https://example.org/ad">Advert (Sponsor)</a></article>"""
    stories = parse_stories(
        html, "https://tldr.tech/ai/2026-09-21", datetime(2026, 9, 21, tzinfo=UTC)
    )
    assert len(stories) == 1
    assert stories[0].title.strip() == "A"


async def test_fetch_issue_stale_feed_rejects() -> None:
    xml = "<rss><channel><item><link>https://tldr.tech/ai/2026-09-01</link><pubDate>Tue, 01 Sep 2026 00:00:00 GMT</pubDate></item></channel></rss>"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text=xml, headers={"content-type": "text/xml"}, request=r)
        )
    ) as client:
        with pytest.raises(BriefError, match="stale"):
            await TldrSource().fetch(client, datetime(2026, 9, 22, tzinfo=UTC), 96)


def test_canonical_url_tracking_parameters_removed_content_parameters_preserved() -> None:
    assert (
        canonical_url("https://example.org/p?id=1&utm_source=tldr#top")
        == "https://example.org/p?id=1"
    )


@pytest.mark.parametrize(
    "message", ["Verify you are human", "Access denied", "We value your privacy"]
)
def test_article_text_blocked_page_rejects(message: str) -> None:
    from ai_brief.content import article_text

    with pytest.raises(BriefError, match="access or browser challenge"):
        article_text(f"<main>{message} {'Please try again. ' * 30}</main>", 200, 16_000)


def test_article_text_prefers_article_and_excludes_navigation() -> None:
    from ai_brief.content import article_text

    text = "Representative evaluation cases expose regressions. " * 5
    html = f"<nav>{'Menu item ' * 200}</nav><main><article>{text}</article></main>"
    result = article_text(html, 200, 16_000)
    assert result == text.strip()
    assert "Menu" not in result


async def test_fetch_issue_failed_source_keeps_healthy_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock, Mock

    from pydantic import HttpUrl

    from ai_brief.sources.base import SourceBatch

    now = datetime(2026, 9, 22, tzinfo=UTC)
    stories = parse_stories(
        '<article><a href="https://example.org/one">Evaluation (2 minute read)</a>'
        "<p>Comparing fixed cases exposes regressions in model behaviour.</p></article>",
        "https://tldr.tech/ai/2026-09-22",
        now,
    )
    failed = Mock(name="failed")
    failed.name = "failed"
    failed.fetch = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    healthy = Mock(name="healthy")
    healthy.name = "healthy"
    healthy.fetch = AsyncMock(
        return_value=SourceBatch(
            "healthy",
            HttpUrl("https://example.org/issue"),
            now,
            stories,
        )
    )
    monkeypatch.setattr("ai_brief.fetch.configured_sources", lambda _: (failed, healthy))
    async with httpx.AsyncClient() as client:
        issue = await fetch_issue(client, now, 96, ("failed", "healthy"))
    assert len(issue.stories) == 1
    assert issue.warnings == ("failed: source unavailable (ReadTimeout)",)
