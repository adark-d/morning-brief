"""Tests for ChannelRouter — the multi-channel fan-out and format negotiation.

These prove the system delivers one brief to several channels at once, renders the
right format for each, reuses a render across channels that share a format, and
isolates a failing channel from the rest.
"""

from __future__ import annotations

import pytest
from tests.fixtures import make_brief_analysis

from morning_brief.application.delivery_router import ChannelRouter, ChannelTarget
from morning_brief.core.exceptions.errors import InvalidConfigError
from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.interfaces.delivery_channel import DeliveryChannel
from morning_brief.core.interfaces.report_renderer import ReportRenderer
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.audit import DeliveryResult, DeliveryStatus
from morning_brief.core.models.report import RenderedReport, ReportFormat
from morning_brief.infrastructure.delivery.mock_delivery_channel import MockDeliveryChannel
from morning_brief.infrastructure.rendering.mock_renderer import MockRenderer


class _CountingRenderer(ReportRenderer):
    """Wraps MockRenderer and counts render() calls (to prove render-once)."""

    def __init__(self) -> None:
        self.calls = 0
        self._inner = MockRenderer()

    def render(self, analysis: BriefAnalysis) -> RenderedReport:
        self.calls += 1
        return self._inner.render(analysis)

    def supported_formats(self) -> tuple[ReportFormat, ...]:
        return self._inner.supported_formats()


class _ExplodingChannel(DeliveryChannel):
    """A channel whose deliver() raises — to test router isolation."""

    async def deliver(
        self, _report: RenderedReport, _recipients: tuple[str, ...]
    ) -> tuple[DeliveryResult, ...]:
        raise RuntimeError("transport exploded")

    def supported_format(self) -> ReportFormat:
        return ReportFormat.HTML_EMAIL

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.HEALTHY, component="exploding")


def _renderers() -> dict[ReportFormat, ReportRenderer]:
    return {ReportFormat.HTML_EMAIL: MockRenderer(), ReportFormat.SLACK_BLOCKS: MockRenderer()}


@pytest.mark.asyncio
async def test_fans_out_to_multiple_channels_with_format_negotiation() -> None:
    email = MockDeliveryChannel(name="email", report_format=ReportFormat.HTML_EMAIL)
    slack = MockDeliveryChannel(name="slack", report_format=ReportFormat.SLACK_BLOCKS)
    router = ChannelRouter(
        targets=(
            ChannelTarget("email", email, ("desk@firm.com",)),
            ChannelTarget("slack", slack, ("#fixed-income",)),
        ),
        renderers=_renderers(),
    )

    results = await router.deliver(make_brief_analysis())

    assert all(r.status == DeliveryStatus.DELIVERED for r in results)
    assert [r for r, _ in email.delivered] == ["desk@firm.com"]
    assert [r for r, _ in slack.delivered] == ["#fixed-income"]


@pytest.mark.asyncio
async def test_render_is_reused_across_channels_sharing_a_format() -> None:
    renderer = _CountingRenderer()
    a = MockDeliveryChannel(name="a", report_format=ReportFormat.HTML_EMAIL)
    b = MockDeliveryChannel(name="b", report_format=ReportFormat.HTML_EMAIL)
    router = ChannelRouter(
        targets=(
            ChannelTarget("a", a, ("one@x.com",)),
            ChannelTarget("b", b, ("two@x.com",)),
        ),
        renderers={ReportFormat.HTML_EMAIL: renderer},
    )

    await router.deliver(make_brief_analysis())

    assert renderer.calls == 1  # rendered once, delivered to both


@pytest.mark.asyncio
async def test_render_failure_isolates_to_that_channel() -> None:
    email = MockDeliveryChannel(name="email", report_format=ReportFormat.HTML_EMAIL)
    slack = MockDeliveryChannel(name="slack", report_format=ReportFormat.SLACK_BLOCKS)
    router = ChannelRouter(
        targets=(
            ChannelTarget("email", email, ("desk@firm.com",)),
            ChannelTarget("slack", slack, ("#fixed-income",)),
        ),
        renderers={
            ReportFormat.HTML_EMAIL: MockRenderer(),
            ReportFormat.SLACK_BLOCKS: MockRenderer(fail=True),  # slack render blows up
        },
    )

    results = await router.deliver(make_brief_analysis())
    by_channel = {r.channel: r for r in results}

    assert by_channel["email"].status == DeliveryStatus.DELIVERED
    assert by_channel["slack"].status == DeliveryStatus.FAILED
    assert "render failed" in (by_channel["slack"].error_message or "")


@pytest.mark.asyncio
async def test_channel_exception_isolates_to_that_channel() -> None:
    healthy = MockDeliveryChannel(name="email", report_format=ReportFormat.HTML_EMAIL)
    router = ChannelRouter(
        targets=(
            ChannelTarget("email", healthy, ("desk@firm.com",)),
            ChannelTarget("broken", _ExplodingChannel(), ("ops@firm.com",)),
        ),
        renderers={ReportFormat.HTML_EMAIL: MockRenderer()},
    )

    results = await router.deliver(make_brief_analysis())
    by_channel = {r.channel: r for r in results}

    assert by_channel["email"].status == DeliveryStatus.DELIVERED
    assert by_channel["broken"].status == DeliveryStatus.FAILED
    assert "channel error" in (by_channel["broken"].error_message or "")


def test_missing_renderer_for_a_channel_format_fails_fast() -> None:
    slack = MockDeliveryChannel(name="slack", report_format=ReportFormat.SLACK_BLOCKS)
    with pytest.raises(InvalidConfigError):
        ChannelRouter(
            targets=(ChannelTarget("slack", slack, ("#fi",)),),
            renderers={ReportFormat.HTML_EMAIL: MockRenderer()},  # no SLACK_BLOCKS renderer
        )
