from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

from brief_core import BriefCoreError

Text: TypeAlias = Annotated[  # noqa: UP040
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Story(Record):
    """An article and the publication that supplied its summary."""

    id: str
    source: Text
    source_url: HttpUrl
    published_at: AwareDatetime
    title: Text
    url: HttpUrl
    summary: Text
    content: str = ""


class Issue(Record):
    """Stories collected across sources for one brief."""

    collected_at: AwareDatetime
    stories: tuple[Story, ...]
    warnings: tuple[str, ...] = ()


class Selection(Record):
    story_ids: Annotated[tuple[str, ...], Field(max_length=5)]


class Lesson(Record):
    story_id: str
    headline: Text
    what_happened: Text
    why_it_matters: Text
    concept: Text
    explanation: Text
    example: Text
    takeaway: Text


class Brief(Record):
    lessons: Annotated[tuple[Lesson, ...], Field(min_length=1, max_length=5)]


class Run(Record):
    """The completed brief and its delivery outcome, held in memory."""

    run_id: str
    started_at: AwareDatetime
    status: Literal["preview", "success", "skipped"]
    issue: Issue
    brief: Brief | None = None
    html: str = ""
    warnings: tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0


class BriefError(BriefCoreError):
    """A failed retrieval, check, or delivery requiring operator attention."""
