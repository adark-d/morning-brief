from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime

import httpx
import structlog
from pydantic import HttpUrl, ValidationError

from ai_brief.content import article_text, canonical_url
from ai_brief.models import BriefError, Issue, Story
from ai_brief.sources import configured_sources
from ai_brief.sources.base import SourceBatch
from brief_core.http import HttpFetchError, fetch_text


async def fetch_issue(
    client: httpx.AsyncClient,
    now: datetime,
    max_age_hours: int,
    source_names: tuple[str, ...] = ("tldr",),
    timeout_seconds: float = 30,
) -> Issue:
    """Collect enabled sources and keep the first occurrence of each article URL."""
    sources = configured_sources(source_names)
    if not sources:
        raise BriefError("Configure at least one news source")
    batches: list[SourceBatch] = []
    warnings: list[str] = []
    # Share a bounded window so a stalled source cannot starve later sources.
    for source in sources:
        try:
            async with asyncio.timeout(timeout_seconds / len(sources)):
                batches.append(await source.fetch(client, now, max_age_hours))
        except (httpx.HTTPError, HttpFetchError, BriefError, ValidationError, TimeoutError) as exc:
            warnings.append(f"{source.name}: source unavailable ({type(exc).__name__})")
            structlog.get_logger().warning(
                "source_unavailable", source=source.name, error_type=type(exc).__name__
            )
    if not batches:
        raise BriefError("All configured news sources failed")

    stories_by_url: dict[str, Story] = {}
    for batch in batches:
        for story in batch.stories:
            article_url = canonical_url(str(story.url))
            stories_by_url.setdefault(
                article_url,
                story.model_copy(
                    update={
                        "id": hashlib.sha256(article_url.encode()).hexdigest(),
                        "url": HttpUrl(article_url),
                    }
                ),
            )

    if not stories_by_url:
        raise BriefError("Sources returned no usable stories")

    return Issue(
        collected_at=now,
        stories=tuple(stories_by_url.values()),
        warnings=tuple(warnings),
    )


async def enrich(
    client: httpx.AsyncClient,
    story: Story,
    hosts: tuple[str, ...],
    min_content_chars: int,
    max_content_chars: int,
) -> Story:
    """Attach bounded, readable text from the original article."""
    html = await fetch_text(client, str(story.url), hosts)
    content = article_text(html, min_content_chars, max_content_chars)
    return story.model_copy(update={"content": content})
