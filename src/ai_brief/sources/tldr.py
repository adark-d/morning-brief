from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import httpx
from pydantic import HttpUrl

from ai_brief.content import canonical_url
from ai_brief.models import BriefError, Story
from ai_brief.sources.base import SourceBatch
from brief_core.http import fetch_text

FEED_URL = "https://tldr.tech/api/rss/ai"


class PageParser(HTMLParser):
    """Extract article blocks and readable text without executing page code."""

    def __init__(self) -> None:
        super().__init__()
        self.articles: list[tuple[str, str]] = []
        self.text: list[str] = []
        self.current: list[str] | None = None
        self.link = ""
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "article":
            self.current = []
            self.link = ""
        if tag == "a" and self.current is not None and not self.link:
            self.link = dict(attrs).get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "article" and self.current is not None:
            self.articles.append((self.link, " ".join(self.current)))
            self.current = None

    def handle_data(self, data: str) -> None:
        if not self.hidden and (value := data.strip()):
            self.text.append(value)
            if self.current is not None:
                self.current.append(value)


class TldrSource:
    name = "tldr"

    async def fetch(
        self, client: httpx.AsyncClient, now: datetime, max_age_hours: int
    ) -> SourceBatch:
        """Fetch the latest TLDR AI issue within the allowed age."""

        # Read issue dates and links from the feed.
        xml = await fetch_text(client, FEED_URL, ("tldr.tech",))
        if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise BriefError("Unexpected XML declarations")
        try:
            root = ET.fromstring(xml)
            entries = [
                (parsedate_to_datetime(item.findtext("pubDate", "")), item.findtext("link", ""))
                for item in root.findall("./channel/item")
            ]
        except (ET.ParseError, ValueError, TypeError) as exc:
            raise BriefError("Malformed TLDR feed") from exc

        # Reject stale issues and unexpected publication links.
        if not entries or any(date.tzinfo is None for date, _ in entries):
            raise BriefError("Feed contains no dated issues")
        published, url = max(entries)
        if not timedelta(0) <= now.astimezone(UTC) - published <= timedelta(hours=max_age_hours):
            raise BriefError("Latest issue is stale or dated in the future")
        if not re.fullmatch(r"https://tldr\.tech/ai/\d{4}-\d{2}-\d{2}", url):
            raise BriefError("Unexpected issue URL")

        html = await fetch_text(client, url, ("tldr.tech",))
        return SourceBatch(self.name, HttpUrl(url), published, parse_stories(html, url, published))


def parse_stories(html: str, issue_url: str, published_at: datetime) -> tuple[Story, ...]:
    """Extract unsponsored stories with their TLDR publication details."""
    page = PageParser()
    page.feed(html)
    stories: dict[str, Story] = {}
    for link, text in page.articles:
        if "(sponsor)" in text.lower() or not link.startswith("https://"):
            continue
        link = canonical_url(link)
        story_id = hashlib.sha256(link.encode()).hexdigest()[:16]
        title = re.split(r"\((?:\d+ minute read|GitHub Repo)\)", text, maxsplit=1)[0]
        stories.setdefault(
            story_id,
            Story(
                id=story_id,
                source="tldr",
                source_url=HttpUrl(issue_url),
                published_at=published_at,
                title=title[:300].strip(),
                url=HttpUrl(link),
                summary=text[:4000],
            ),
        )
    if not stories:
        raise BriefError("Issue contained no usable stories; TLDR markup may have changed")
    return tuple(stories.values())
