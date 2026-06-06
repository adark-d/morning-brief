"""ChannelRouter — fans a brief out to every enabled delivery channel.

The router is the seam that makes the system multi-channel. For each target it:
    1. asks the channel which ReportFormat it needs,
    2. renders that format once (reusing the result across channels that share it),
    3. delivers concurrently, isolating failures so one channel cannot sink another.

It depends only on the DeliveryChannel and ReportRenderer interfaces — never on a
concrete transport — so adding Slack, PDF, or a webhook is purely additive.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from morning_brief.core.exceptions.errors import InvalidConfigError, RenderError
from morning_brief.core.interfaces.delivery_channel import DeliveryChannel
from morning_brief.core.interfaces.report_renderer import ReportRenderer
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.audit import DeliveryResult, DeliveryStatus
from morning_brief.core.models.report import RenderedReport, ReportFormat

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ChannelTarget:
    """A configured channel plus the recipients it should deliver to.

    `name` labels the channel in audit records and in synthesised failures (when
    rendering or the transport fails before the channel can record its own result).
    """

    name: str
    channel: DeliveryChannel
    recipients: tuple[str, ...]


class ChannelRouter:
    """Routes a BriefAnalysis to all configured channels, one renderer per format."""

    def __init__(
        self,
        targets: tuple[ChannelTarget, ...],
        renderers: Mapping[ReportFormat, ReportRenderer],
    ) -> None:
        self._targets = targets
        self._renderers = dict(renderers)
        # Fail fast on a wiring mistake rather than at 07:00: every channel's
        # required format must have a renderer registered.
        for target in targets:
            required = target.channel.supported_format()
            if required not in self._renderers:
                raise InvalidConfigError(
                    f"No renderer registered for format '{required}' "
                    f"required by channel '{target.name}'"
                )

    @property
    def all_recipients(self) -> tuple[str, ...]:
        """The de-duplicated union of recipients across every target, sorted.

        The orchestrator uses this as the single source of truth for the recipient
        set its delivery guardrails validate against.
        """
        seen = {recipient for target in self._targets for recipient in target.recipients}
        return tuple(sorted(seen))

    async def deliver(self, analysis: BriefAnalysis) -> tuple[DeliveryResult, ...]:
        """Render and deliver to every target. Returns all per-recipient results."""
        cache: dict[ReportFormat, RenderedReport] = {}
        batches = await asyncio.gather(
            *(self._deliver_to(target, analysis, cache) for target in self._targets)
        )
        return tuple(result for batch in batches for result in batch)

    async def _deliver_to(
        self,
        target: ChannelTarget,
        analysis: BriefAnalysis,
        cache: dict[ReportFormat, RenderedReport],
    ) -> tuple[DeliveryResult, ...]:
        report_format = target.channel.supported_format()
        report = cache.get(report_format)
        if report is None:
            try:
                report = self._renderers[report_format].render(analysis)
            except RenderError as exc:
                logger.error("render_failed_for_channel", channel=target.name, error=str(exc))
                return self._synthesise_failures(target, f"render failed: {exc}")
            cache[report_format] = report

        try:
            return await target.channel.deliver(report, target.recipients)
        except Exception as exc:
            # The channel contract says deliver() records per-recipient outcomes and
            # never raises; if a transport breaks that, isolate it from the others.
            logger.error("channel_delivery_errored", channel=target.name, error=str(exc))
            return self._synthesise_failures(target, f"channel error: {exc}")

    @staticmethod
    def _synthesise_failures(target: ChannelTarget, message: str) -> tuple[DeliveryResult, ...]:
        now = datetime.now(UTC)
        return tuple(
            DeliveryResult(
                recipient=recipient,
                channel=target.name,
                status=DeliveryStatus.FAILED,
                attempted_at=now,
                completed_at=now,
                error_message=message,
            )
            for recipient in target.recipients
        )
