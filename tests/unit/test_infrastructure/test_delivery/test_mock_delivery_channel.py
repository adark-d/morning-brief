"""Tests for MockDeliveryChannel."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from morning_brief.core.interfaces.base import HealthState
from morning_brief.core.models.audit import DeliveryStatus
from morning_brief.core.models.report import RenderedReport, ReportFormat
from morning_brief.infrastructure.delivery.mock_delivery_channel import MockDeliveryChannel


def _report() -> RenderedReport:
    return RenderedReport(
        subject="Morning Brief — test",
        html_body="<p>" + "body " * 20 + "</p>",
        plain_text_body="body " * 20,
        rendered_at=datetime.now(UTC),
        template_version="v1.0",
    )


@pytest.mark.asyncio
async def test_records_successful_deliveries() -> None:
    channel = MockDeliveryChannel()
    results = await channel.deliver(_report(), ("a@x.com", "b@x.com"))

    assert all(r.status == DeliveryStatus.DELIVERED for r in results)
    assert [recipient for recipient, _ in channel.delivered] == ["a@x.com", "b@x.com"]


@pytest.mark.asyncio
async def test_fail_flag_fails_every_recipient() -> None:
    channel = MockDeliveryChannel(fail=True)
    results = await channel.deliver(_report(), ("a@x.com",))

    assert results[0].status == DeliveryStatus.FAILED
    assert channel.delivered == []


@pytest.mark.asyncio
async def test_fail_recipients_isolates_failures() -> None:
    channel = MockDeliveryChannel(fail_recipients=("bad@x.com",))
    results = await channel.deliver(_report(), ("good@x.com", "bad@x.com"))

    by_recipient = {r.recipient: r.status for r in results}
    assert by_recipient["good@x.com"] == DeliveryStatus.DELIVERED
    assert by_recipient["bad@x.com"] == DeliveryStatus.FAILED


@pytest.mark.asyncio
async def test_supported_format_is_configurable() -> None:
    channel = MockDeliveryChannel(report_format=ReportFormat.SLACK_BLOCKS)
    assert channel.supported_format() == ReportFormat.SLACK_BLOCKS


@pytest.mark.asyncio
async def test_unhealthy_flag() -> None:
    channel = MockDeliveryChannel(unhealthy=True)
    status = await channel.health_check()
    assert status.state == HealthState.UNHEALTHY
