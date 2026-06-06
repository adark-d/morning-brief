"""Deterministic in-memory ReportRenderer for testing.

Produces a minimal but contract-valid RenderedReport without Jinja2, so tests can
exercise the pipeline without depending on templates. The `fail` flag simulates a
rendering failure for testing graceful degradation.

Implements core.interfaces.report_renderer.ReportRenderer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from morning_brief.core.exceptions.errors import TemplateError
from morning_brief.core.interfaces.report_renderer import ReportRenderer
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.report import RenderedReport, ReportFormat


class MockRenderer(ReportRenderer):
    """Deterministic renderer that echoes the analysis into a valid report."""

    def __init__(self, *, fail: bool = False) -> None:
        """Construct the mock.

        Args:
            fail: When True, render() raises TemplateError (simulates failure).
        """
        self._fail = fail

    def render(self, analysis: BriefAnalysis) -> RenderedReport:
        if self._fail:
            raise TemplateError("Mock renderer configured to fail")

        signals = "\n".join(f"- {signal}" for signal in analysis.key_signals)
        plain_text_body = f"{analysis.headline}\n\n{analysis.full_narrative}\n\n{signals}"
        html_body = f"<h1>{analysis.headline}</h1><p>{analysis.full_narrative}</p>"

        return RenderedReport(
            subject=f"Morning Brief — {analysis.generated_at:%d %b %Y}",
            html_body=html_body,
            plain_text_body=plain_text_body,
            rendered_at=datetime.now(UTC),
            template_version="mock-v1",
            contains_disclaimer=False,
        )

    def supported_formats(self) -> tuple[ReportFormat, ...]:
        return (ReportFormat.HTML_EMAIL, ReportFormat.PLAIN_TEXT)
