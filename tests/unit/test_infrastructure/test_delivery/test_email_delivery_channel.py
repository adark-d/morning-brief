"""Tests for EmailDeliveryChannel with aiosmtplib mocked.

No real SMTP traffic. We stub aiosmtplib to verify per-recipient delivery,
failure isolation, per-recipient timeout, and health checks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from morning_brief.core.interfaces.base import HealthState
from morning_brief.core.models.audit import DeliveryStatus
from morning_brief.core.models.report import RenderedReport, ReportFormat
from morning_brief.infrastructure.delivery.email_delivery_channel import EmailDeliveryChannel


def _report() -> RenderedReport:
    return RenderedReport(
        subject="Morning Brief — test",
        html_body="<p>" + "body " * 20 + "</p>",
        plain_text_body="body " * 20,
        rendered_at=datetime.now(UTC),
        template_version="v1.0",
    )


@pytest.fixture
def aiosmtplib_mock() -> Iterator[MagicMock]:
    with patch("morning_brief.infrastructure.delivery.email_delivery_channel.aiosmtplib") as mock:
        mock.send = AsyncMock()
        yield mock


def _channel(**kwargs: object) -> EmailDeliveryChannel:
    params: dict[str, object] = {"host": "smtp.example.com", "sender": "brief@example.com"}
    params.update(kwargs)
    return EmailDeliveryChannel(**params)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_delivers_to_every_recipient(aiosmtplib_mock: MagicMock) -> None:
    channel = _channel()
    results = await channel.deliver(_report(), ("a@x.com", "b@x.com"))

    assert [r.status for r in results] == [DeliveryStatus.DELIVERED, DeliveryStatus.DELIVERED]
    assert [r.recipient for r in results] == ["a@x.com", "b@x.com"]
    assert aiosmtplib_mock.send.await_count == 2


@pytest.mark.asyncio
async def test_one_bad_recipient_does_not_fail_the_others(aiosmtplib_mock: MagicMock) -> None:
    async def send(message: object, **_kwargs: object) -> None:
        if message["To"] == "bad@x.com":  # type: ignore[index]
            raise ConnectionError("mailbox rejected")

    aiosmtplib_mock.send.side_effect = send

    channel = _channel()
    results = await channel.deliver(_report(), ("good@x.com", "bad@x.com"))

    by_recipient = {r.recipient: r for r in results}
    assert by_recipient["good@x.com"].status == DeliveryStatus.DELIVERED
    assert by_recipient["bad@x.com"].status == DeliveryStatus.FAILED
    assert by_recipient["bad@x.com"].error_message is not None


@pytest.mark.asyncio
async def test_delivery_times_out_per_recipient(aiosmtplib_mock: MagicMock) -> None:
    async def slow_send(*_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(5)

    aiosmtplib_mock.send.side_effect = slow_send

    channel = _channel(timeout_seconds=0.05)
    results = await channel.deliver(_report(), ("a@x.com",))

    assert results[0].status == DeliveryStatus.FAILED


def test_supported_format_is_html_email() -> None:
    assert _channel().supported_format() == ReportFormat.HTML_EMAIL


@pytest.mark.asyncio
async def test_health_check_healthy_when_smtp_connects(aiosmtplib_mock: MagicMock) -> None:
    client = MagicMock()
    client.connect = AsyncMock()
    client.quit = AsyncMock()
    aiosmtplib_mock.SMTP.return_value = client

    status = await _channel().health_check()
    assert status.state == HealthState.HEALTHY


@pytest.mark.asyncio
async def test_health_check_unhealthy_when_smtp_unreachable(aiosmtplib_mock: MagicMock) -> None:
    client = MagicMock()
    client.connect = AsyncMock(side_effect=ConnectionError("no route"))
    aiosmtplib_mock.SMTP.return_value = client

    status = await _channel().health_check()
    assert status.state == HealthState.UNHEALTHY
