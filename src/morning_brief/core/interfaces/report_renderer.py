from __future__ import annotations

from abc import ABC, abstractmethod

from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.report import RenderedReport, ReportFormat


class ReportRenderer(ABC):
    """Abstract renderer producing a RenderedReport from a BriefAnalysis.

    Renderers are pure transformations. No network, no file system access
    beyond reading bundled templates at construction time.

    Every concrete implementation:
        - is synchronous (pure transformation; no I/O)
        - returns a RenderedReport with both HTML and plain text bodies
        - declares supported_formats() so the DeliveryChannel can match
        - never raises domain errors; failures are template errors
    """

    @abstractmethod
    def render(self, analysis: BriefAnalysis) -> RenderedReport:
        """Render an analysis into a deliverable report.

        Raises:
            TemplateError: when a Jinja2 template fails to render.
        """
        ...

    @abstractmethod
    def supported_formats(self) -> tuple[ReportFormat, ...]:
        """List the formats this renderer produces.

        Used by the delivery layer to match renderers to channels.
        """
        ...
