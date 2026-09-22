from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import aiosmtplib

from brief_core import BriefCoreError


class EmailError(BriefCoreError):
    """Email configuration or delivery failed."""


@dataclass(frozen=True)
class EmailConfig:
    host: str
    sender: str
    recipients: tuple[str, ...]
    port: int = 587
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    start_tls: bool = True
    use_tls: bool = False
    timeout_seconds: float = 30.0


def validate_addresses(sender: str, recipients: tuple[str, ...]) -> None:
    """Reject missing, duplicate, or unsafe email addresses."""

    if not recipients or len(set(recipients)) != len(recipients):
        raise EmailError("Configure distinct delivery recipients")

    for address in (sender, *recipients):
        if any(character in address for character in "\r\n,;") or address.count("@") != 1:
            raise EmailError("Invalid delivery address")

        local, domain = address.split("@")
        if not local or "." not in domain or any(character.isspace() for character in address):
            raise EmailError("Invalid delivery address")


async def send_html_email(
    html: str,
    *,
    subject: str,
    plain_text: str,
    config: EmailConfig,
) -> None:
    """Send plain-text and HTML content to the configured recipients."""

    validate_addresses(config.sender, config.recipients)
    if config.start_tls and config.use_tls:
        raise EmailError("Choose one SMTP TLS mode")
    if config.password is not None and not (config.start_tls or config.use_tls):
        raise EmailError("SMTP credentials require TLS")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid()
    message.set_content(plain_text)
    message.add_alternative(html, subtype="html")

    refused_recipients, _ = await aiosmtplib.send(
        message,
        hostname=config.host,
        port=config.port,
        username=config.username,
        password=config.password,
        start_tls=config.start_tls,
        use_tls=config.use_tls,
        timeout=config.timeout_seconds,
    )

    if refused_recipients:
        raise EmailError("Some recipients were refused; inspect delivery before retrying")
