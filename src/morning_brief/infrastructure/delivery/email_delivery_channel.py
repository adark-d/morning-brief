"""SMTP email DeliveryChannel using aiosmtplib.

Delivers to each recipient independently with a per-recipient timeout, so one
slow or rejected address cannot block or fail the others. Each attempt produces
its own DeliveryResult; the batch never aborts on a single failure.

Implements core.interfaces.delivery_channel.DeliveryChannel.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from email.message import EmailMessage

import aiosmtplib
import structlog

from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.interfaces.delivery_channel import DeliveryChannel
from morning_brief.core.models.audit import DeliveryResult, DeliveryStatus
from morning_brief.core.models.report import RenderedReport, ReportFormat

logger = structlog.get_logger(__name__)

_CHANNEL_NAME = "email"


class EmailDeliveryChannel(DeliveryChannel):
    """Sends RenderedReports as multipart (plain + HTML) email over SMTP."""

    def __init__(
        self,
        *,
        host: str,
        sender: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        start_tls: bool = True,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._host = host
        self._sender = sender
        self._port = port
        self._username = username
        self._password = password
        self._start_tls = start_tls
        self._timeout = timeout_seconds
        logger.info("email_channel_initialised", host=host, port=port, sender=sender)

    async def deliver(
        self,
        report: RenderedReport,
        recipients: tuple[str, ...],
    ) -> tuple[DeliveryResult, ...]:
        results = [await self._deliver_one(report, recipient) for recipient in recipients]
        return tuple(results)

    def supported_format(self) -> ReportFormat:
        return ReportFormat.HTML_EMAIL

    async def health_check(self) -> HealthStatus:
        start = time.perf_counter()
        try:
            client = aiosmtplib.SMTP(
                hostname=self._host,
                port=self._port,
                start_tls=self._start_tls,
                timeout=self._timeout,
            )
            await client.connect()
            await client.quit()
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                component="EmailDeliveryChannel",
                message=f"SMTP not reachable: {exc}",
                latency_ms=elapsed_ms,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return HealthStatus(
            state=HealthState.HEALTHY,
            component="EmailDeliveryChannel",
            message=f"SMTP {self._host}:{self._port} reachable",
            latency_ms=elapsed_ms,
        )

    # ============================================
    # Internal
    # ============================================
    async def _deliver_one(self, report: RenderedReport, recipient: str) -> DeliveryResult:
        attempted_at = datetime.now(UTC)
        try:
            await asyncio.wait_for(
                aiosmtplib.send(
                    self._build_message(report, recipient),
                    hostname=self._host,
                    port=self._port,
                    username=self._username,
                    password=self._password,
                    start_tls=self._start_tls,
                ),
                timeout=self._timeout,
            )
        except Exception as exc:
            # Record and move on — one bad address never aborts the rest.
            logger.warning("email_delivery_failed", recipient=recipient, error=str(exc))
            return DeliveryResult(
                recipient=recipient,
                channel=_CHANNEL_NAME,
                status=DeliveryStatus.FAILED,
                attempted_at=attempted_at,
                completed_at=datetime.now(UTC),
                error_message=str(exc),
            )

        return DeliveryResult(
            recipient=recipient,
            channel=_CHANNEL_NAME,
            status=DeliveryStatus.DELIVERED,
            attempted_at=attempted_at,
            completed_at=datetime.now(UTC),
        )

    def _build_message(self, report: RenderedReport, recipient: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = recipient
        message["Subject"] = report.subject
        message.set_content(report.plain_text_body)
        message.add_alternative(report.html_body, subtype="html")
        return message
