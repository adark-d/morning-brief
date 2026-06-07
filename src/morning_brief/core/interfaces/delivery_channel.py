from __future__ import annotations

from abc import ABC, abstractmethod

from morning_brief.core.interfaces.base import HealthStatus
from morning_brief.core.models.audit import DeliveryResult
from morning_brief.core.models.report import RenderedReport, ReportFormat


class DeliveryChannel(ABC):
    """Abstract delivery channel for sending reports to recipients.

    Every concrete implementation:
        - is async (delivery is I/O-bound)
        - delivers to each recipient independently (partial success is recorded)
        - returns one DeliveryResult per recipient — never aggregates outcomes
        - declares supported_format() so the renderer can produce the right thing
    """

    @abstractmethod
    async def deliver(
        self,
        report: RenderedReport,
        recipients: tuple[str, ...],
    ) -> tuple[DeliveryResult, ...]:
        """Deliver a report to multiple recipients.

        Implementations:
            - send to each recipient independently
            - record success/failure per recipient in a DeliveryResult
            - never abort the whole batch on a single failure
            - apply timeouts so a stuck recipient cannot block the rest

        Returns:
            A DeliveryResult per recipient, in the same order as the input.
        """
        ...

    @abstractmethod
    def supported_format(self) -> ReportFormat:
        """The single ReportFormat this channel can deliver."""
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Test whether the delivery transport is reachable."""
        ...
