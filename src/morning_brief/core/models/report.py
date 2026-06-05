"""Rendered report models — what the ReportRenderer produces.

Section 9.3 of the architecture. The renderer takes a BriefAnalysis and
produces a RenderedReport that the DeliveryChannel knows how to send.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator

from morning_brief.core.models.base import FrozenModel


class ReportFormat(StrEnum):
    """Supported render formats. Each DeliveryChannel declares which it accepts."""

    HTML_EMAIL = "html_email"
    PLAIN_TEXT = "plain_text"
    SLACK_BLOCKS = "slack_blocks"
    PDF = "pdf"
    JSON_API = "json_api"


class RenderedReport(FrozenModel):
    """The output of a renderer — ready to deliver.

    Holds both HTML and plain-text representations because email delivery
    requires both (HTML for clients that support it, plain text fallback).
    Other formats (Slack blocks, PDF) are stored in `additional_formats`.
    """

    subject: Annotated[str, Field(min_length=5, max_length=200)]
    html_body: Annotated[str, Field(min_length=50)]
    plain_text_body: Annotated[str, Field(min_length=50)]
    additional_formats: dict[ReportFormat, str] = Field(default_factory=dict)
    rendered_at: datetime
    template_version: Annotated[str, Field(min_length=1)]
    contains_disclaimer: bool = False

    @field_validator("rendered_at")
    @classmethod
    def must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("rendered_at must be timezone-aware")
        return v.astimezone(UTC)
