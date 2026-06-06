"""Concrete ReportRenderer implementations.

The composition root selects which implementation to use at startup.
"""

from morning_brief.infrastructure.rendering.html_email_renderer import HtmlEmailRenderer
from morning_brief.infrastructure.rendering.mock_renderer import MockRenderer

__all__ = [
    "HtmlEmailRenderer",
    "MockRenderer",
]
