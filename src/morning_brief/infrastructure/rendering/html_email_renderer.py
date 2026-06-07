from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import structlog
from jinja2 import Environment, PackageLoader, StrictUndefined
from jinja2 import TemplateError as Jinja2TemplateError

from morning_brief.core.exceptions.errors import TemplateError
from morning_brief.core.interfaces.report_renderer import ReportRenderer
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.report import RenderedReport, ReportFormat
from morning_brief.infrastructure.rendering.content import DISCLAIMER

logger = structlog.get_logger(__name__)

_TEMPLATE_VERSION: Final = "v1.0"
_HTML_TEMPLATE: Final = "morning_brief.html.j2"
_TEXT_TEMPLATE: Final = "morning_brief.txt.j2"


def _autoescape(template_name: str | None) -> bool:
    """Autoescape HTML templates only — plain-text output must stay literal."""
    return template_name is not None and template_name.endswith(".html.j2")


class HtmlEmailRenderer(ReportRenderer):
    """Renders a BriefAnalysis into HTML + plain text via bundled Jinja2 templates."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=PackageLoader("morning_brief.infrastructure.rendering", "templates"),
            autoescape=_autoescape,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        # Resolve templates eagerly so a missing/broken template fails at startup,
        # not at 07:00 when the first brief is rendered.
        self._html = self._env.get_template(_HTML_TEMPLATE)
        self._text = self._env.get_template(_TEXT_TEMPLATE)
        logger.info("html_email_renderer_initialised", template_version=_TEMPLATE_VERSION)

    def render(self, analysis: BriefAnalysis) -> RenderedReport:
        subject = f"Morning Brief — {analysis.generated_at:%d %b %Y}"
        context = self._build_context(analysis, subject)
        try:
            html_body = self._html.render(context)
            plain_text_body = self._text.render(context)
        except Jinja2TemplateError as exc:
            raise TemplateError(f"Failed to render morning brief: {exc}") from exc

        return RenderedReport(
            subject=subject,
            html_body=html_body,
            plain_text_body=plain_text_body,
            rendered_at=datetime.now(UTC),
            template_version=_TEMPLATE_VERSION,
            contains_disclaimer=True,
        )

    def supported_formats(self) -> tuple[ReportFormat, ...]:
        return (ReportFormat.HTML_EMAIL, ReportFormat.PLAIN_TEXT)

    @staticmethod
    def _build_context(analysis: BriefAnalysis, subject: str) -> dict[str, object]:
        return {
            "subject": subject,
            "brief_date": analysis.generated_at.strftime("%A, %d %B %Y"),
            "headline": analysis.headline,
            "yield_curve_summary": analysis.yield_curve_summary,
            "key_signals": analysis.key_signals,
            "macro_context": analysis.macro_context,
            "watch_today": analysis.watch_today,
            "full_narrative": analysis.full_narrative,
            "confidence_pct": round(analysis.confidence * 100),
            "model_used": analysis.model_used,
            "generated_at": analysis.generated_at.strftime("%d %b %Y %H:%M UTC"),
            "disclaimer": DISCLAIMER,
        }
