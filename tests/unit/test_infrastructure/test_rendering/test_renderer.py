"""Tests for ReportRenderer implementations.

The contract tests run against both HtmlEmailRenderer and MockRenderer to prove
substitutability. HTML-specific behaviour (autoescaping, section structure) is
tested separately against the real renderer.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC

import pytest
from tests.fixtures import make_brief_analysis

from morning_brief.core.exceptions.errors import TemplateError
from morning_brief.core.interfaces.report_renderer import ReportRenderer
from morning_brief.core.models.report import ReportFormat
from morning_brief.infrastructure.rendering.html_email_renderer import HtmlEmailRenderer
from morning_brief.infrastructure.rendering.mock_renderer import MockRenderer

_RENDERERS: list[Callable[[], ReportRenderer]] = [HtmlEmailRenderer, MockRenderer]


# ============================================
# Contract — both implementations
# ============================================
@pytest.fixture(params=_RENDERERS, ids=lambda f: f.__name__)
def renderer(request: pytest.FixtureRequest) -> ReportRenderer:
    factory: Callable[[], ReportRenderer] = request.param
    return factory()


def test_render_produces_valid_report_with_both_bodies(renderer: ReportRenderer) -> None:
    report = renderer.render(make_brief_analysis())

    assert len(report.html_body) >= 50
    assert len(report.plain_text_body) >= 50
    assert len(report.subject) >= 5
    assert report.rendered_at.tzinfo == UTC


def test_render_includes_headline_in_plain_text(renderer: ReportRenderer) -> None:
    analysis = make_brief_analysis(headline="Bunds rally as German CPI undershoots forecasts")
    report = renderer.render(analysis)
    assert "Bunds rally as German CPI undershoots forecasts" in report.plain_text_body


def test_supported_formats_includes_html_and_plain_text(renderer: ReportRenderer) -> None:
    formats = renderer.supported_formats()
    assert ReportFormat.HTML_EMAIL in formats
    assert ReportFormat.PLAIN_TEXT in formats


# ============================================
# HtmlEmailRenderer specifics
# ============================================
def test_html_renderer_includes_all_sections() -> None:
    analysis = make_brief_analysis(
        key_signals=("Curve flattening", "Risk-off equities"),
        watch_today=("CPI at 13:30", "30Y auction at 18:00"),
    )
    report = HtmlEmailRenderer().render(analysis)

    assert "Curve flattening" in report.html_body
    assert "CPI at 13:30" in report.html_body
    # A clean substring of the narrative (apostrophes elsewhere get autoescaped).
    assert "Markets enter the session" in report.html_body
    assert report.contains_disclaimer is True
    assert "investment advice" in report.html_body


def test_html_renderer_escapes_markup_but_plain_text_stays_literal() -> None:
    analysis = make_brief_analysis(headline="Yields <fall> & curve flattens after the CPI surprise")
    report = HtmlEmailRenderer().render(analysis)

    # HTML output neutralises the markup...
    assert "<fall>" not in report.html_body
    assert "&lt;fall&gt;" in report.html_body
    assert "&amp;" in report.html_body
    # ...while plain text keeps it literal.
    assert "<fall>" in report.plain_text_body
    assert "&" in report.plain_text_body


def test_html_renderer_subject_carries_the_brief_date() -> None:
    report = HtmlEmailRenderer().render(make_brief_analysis())
    assert report.subject.startswith("Morning Brief —")


# ============================================
# MockRenderer specifics
# ============================================
def test_mock_renderer_can_simulate_failure() -> None:
    with pytest.raises(TemplateError):
        MockRenderer(fail=True).render(make_brief_analysis())
