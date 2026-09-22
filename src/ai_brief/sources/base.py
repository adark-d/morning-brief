from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx
from pydantic import HttpUrl

from ai_brief.models import Story


@dataclass(frozen=True)
class SourceBatch:
    """Stories returned by one source for a single run."""

    name: str
    issue_url: HttpUrl
    published_at: datetime
    stories: tuple[Story, ...]


class Source(Protocol):
    name: str

    async def fetch(
        self, client: httpx.AsyncClient, now: datetime, max_age_hours: int
    ) -> SourceBatch: ...
