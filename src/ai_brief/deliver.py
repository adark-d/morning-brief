from __future__ import annotations

from jinja2 import Environment, PackageLoader, StrictUndefined

from ai_brief.content import TextParser
from ai_brief.models import Brief, Issue
from brief_core.email import EmailConfig, send_html_email
from brief_core.settings import Settings


def render(brief: Brief, issue: Issue) -> str:
    """Render a brief as HTML with all source and model text escaped."""

    environment = Environment(
        loader=PackageLoader("ai_brief", "assets"),
        autoescape=True,
        undefined=StrictUndefined,
    )
    template = environment.get_template("email.html.j2")
    return template.render(
        issue=issue,
        lessons=brief.lessons,
        stories={story.id: story for story in issue.stories},
    )


async def send_email(html: str, settings: Settings) -> None:
    """Send the rendered brief using the configured SMTP account."""

    parser = TextParser(preserve_links=True)
    parser.feed(html)

    await send_html_email(
        html,
        subject=settings.email_subject,
        plain_text="\n\n".join(parser.text),
        config=EmailConfig(
            host=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_start_tls,
            use_tls=settings.smtp_use_tls,
            timeout_seconds=settings.smtp_timeout_seconds,
            sender=settings.sender,
            recipients=settings.recipients,
            username=settings.smtp_username,
            password=(
                settings.smtp_password.get_secret_value() if settings.smtp_password else None
            ),
        ),
    )
