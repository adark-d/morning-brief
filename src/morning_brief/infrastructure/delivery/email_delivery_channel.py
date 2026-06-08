from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from email.message import EmailMessage

import aiosmtplib
import structlog

# Imported by name (not referenced as aiosmtplib.X) so the retry predicate keeps real
# exception classes even when the aiosmtplib module is patched in tests.
from aiosmtplib import (
    SMTPConnectError,
    SMTPConnectTimeoutError,
    SMTPReadTimeoutError,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.interfaces.delivery_channel import DeliveryChannel
from morning_brief.core.models.audit import DeliveryResult, DeliveryStatus
from morning_brief.core.models.report import RenderedReport, ReportFormat

logger = structlog.get_logger(__name__)

_CHANNEL_NAME = "email"

# Only connection/timeout-class failures are retried — a transient relay blip (e.g. Resend
# briefly unreachable). Permanent failures (auth, recipient/sender refused, 5xx responses)
# are NOT retried: retrying them only delays the recorded failure.
_TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    SMTPConnectError,
    SMTPConnectTimeoutError,
    SMTPReadTimeoutError,
    SMTPTimeoutError,
    SMTPServerDisconnected,
    ConnectionError,  # OS-level connection refused/reset
    TimeoutError,  # asyncio.wait_for timeout (asyncio.TimeoutError aliases this in 3.11+)
)

# Upper bound on a single retry backoff, regardless of the configured base.
_MAX_RETRY_BACKOFF_SECONDS = 8.0


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
        max_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._host = host
        self._sender = sender
        self._port = port
        self._username = username
        self._password = password
        self._start_tls = start_tls
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
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

    async def _deliver_one(self, report: RenderedReport, recipient: str) -> DeliveryResult:
        attempted_at = datetime.now(UTC)
        try:
            await self._send_with_retry(report, recipient)
        except Exception as exc:
            # Retries exhausted, or a permanent (non-transient) failure. Record and move
            # on — one bad address or a briefly-down relay never aborts the rest.
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

    async def _send_with_retry(self, report: RenderedReport, recipient: str) -> None:
        """Send to one recipient, retrying only transient SMTP/connection failures.

        Absorbs a short-lived relay outage (a few seconds) before the run is marked
        failed; permanent failures (auth, refused recipient) are not retried and surface
        immediately.
        """

        def _log_retry(state: RetryCallState) -> None:
            exc = state.outcome.exception() if state.outcome is not None else None
            logger.warning(
                "email_delivery_retry",
                recipient=recipient,
                attempt=state.attempt_number,
                error=str(exc),
            )

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(
                multiplier=self._retry_backoff_seconds, max=_MAX_RETRY_BACKOFF_SECONDS
            ),
            retry=retry_if_exception_type(_TRANSIENT_ERRORS),
            before_sleep=_log_retry,
            reraise=True,
        ):
            with attempt:
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

    def _build_message(self, report: RenderedReport, recipient: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = recipient
        message["Subject"] = report.subject
        message.set_content(report.plain_text_body)
        message.add_alternative(report.html_body, subtype="html")
        return message
