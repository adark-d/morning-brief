"""In-memory mock DeliveryChannel for testing.

Captures what it "delivered" so tests can assert on it, and supports failure
simulation. Its supported_format is configurable so the ChannelRouter's format
negotiation and multi-channel fan-out can be exercised without a real transport.

Implements core.interfaces.delivery_channel.DeliveryChannel.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.interfaces.delivery_channel import DeliveryChannel
from morning_brief.core.models.audit import DeliveryResult, DeliveryStatus
from morning_brief.core.models.report import RenderedReport, ReportFormat


class MockDeliveryChannel(DeliveryChannel):
    """Deterministic DeliveryChannel that records deliveries in memory."""

    def __init__(
        self,
        *,
        name: str = "mock",
        report_format: ReportFormat = ReportFormat.HTML_EMAIL,
        fail: bool = False,
        fail_recipients: Iterable[str] = (),
        unhealthy: bool = False,
    ) -> None:
        """Construct the mock.

        Args:
            name: Channel name recorded on each DeliveryResult.
            report_format: The format this channel advertises (drives router negotiation).
            fail: When True, every recipient is recorded as FAILED.
            fail_recipients: Specific recipients to fail (others succeed).
            unhealthy: health_check returns UNHEALTHY.
        """
        self._name = name
        self._format = report_format
        self._fail = fail
        self._fail_recipients = set(fail_recipients)
        self._unhealthy = unhealthy
        self.delivered: list[tuple[str, RenderedReport]] = []

    async def deliver(
        self,
        report: RenderedReport,
        recipients: tuple[str, ...],
    ) -> tuple[DeliveryResult, ...]:
        results: list[DeliveryResult] = []
        for recipient in recipients:
            now = datetime.now(UTC)
            if self._fail or recipient in self._fail_recipients:
                results.append(
                    DeliveryResult(
                        recipient=recipient,
                        channel=self._name,
                        status=DeliveryStatus.FAILED,
                        attempted_at=now,
                        completed_at=now,
                        error_message="mock configured to fail",
                    )
                )
            else:
                self.delivered.append((recipient, report))
                results.append(
                    DeliveryResult(
                        recipient=recipient,
                        channel=self._name,
                        status=DeliveryStatus.DELIVERED,
                        attempted_at=now,
                        completed_at=now,
                    )
                )
        return tuple(results)

    def supported_format(self) -> ReportFormat:
        return self._format

    async def health_check(self) -> HealthStatus:
        state = HealthState.UNHEALTHY if self._unhealthy else HealthState.HEALTHY
        return HealthStatus(
            state=state,
            component=f"MockDeliveryChannel[{self._name}]",
            message=f"{len(self.delivered)} reports delivered",
            latency_ms=0.0,
        )
