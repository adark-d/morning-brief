from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from morning_brief.core.models.base import FrozenModel, UtcDatetime


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
    additional_formats: dict[ReportFormat, str] = Field(default_factory=dict[ReportFormat, str])
    rendered_at: UtcDatetime
    template_version: Annotated[str, Field(min_length=1)]
    contains_disclaimer: bool = False
