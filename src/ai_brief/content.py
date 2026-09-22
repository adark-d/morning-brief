from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_brief.models import BriefError


def canonical_url(url: str) -> str:
    """Remove tracking parameters and fragments while preserving content parameters."""
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


class TextParser(HTMLParser):
    """Collect visible text and article regions, optionally retaining email links."""

    def __init__(self, *, preserve_links: bool = False) -> None:
        super().__init__()
        self.text: list[str] = []
        self.sections: list[list[str]] = []
        self.preserve_links = preserve_links
        self.stack: list[tuple[str, bool, int | None, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track hidden elements, article regions, and link destinations."""
        attributes = dict(attrs)
        parent_hidden = self.stack[-1][1] if self.stack else False
        section = self.stack[-1][2] if self.stack else None
        style = (attributes.get("style") or "").replace(" ", "").lower()
        hidden = (
            parent_hidden
            or tag in ("head", "script", "style", "noscript", "nav", "footer", "aside")
            or "hidden" in attributes
            or attributes.get("aria-hidden") == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        if not hidden and (tag in ("main", "article") or attributes.get("role") == "main"):
            section = len(self.sections)
            self.sections.append([])
        href = attributes.get("href") or "" if tag == "a" else ""
        if tag not in (
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        ):
            self.stack.append((tag, hidden, section, href))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle self-closing markup without leaving an open region."""
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        """Close the matching region and retain safe link destinations for email."""
        for index in range(len(self.stack) - 1, -1, -1):
            current, hidden, _, href = self.stack[index]
            if current == tag:
                if self.preserve_links and not hidden and href.startswith(("https://", "http://")):
                    self.handle_data(f"({href})")
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        """Keep visible text in document order."""
        if (self.stack and self.stack[-1][1]) or not (value := data.strip()):
            return
        self.text.append(value)
        if self.stack and (section := self.stack[-1][2]) is not None:
            self.sections[section].append(value)


def article_text(html: str, min_chars: int, max_chars: int) -> str:
    """Extract article text or reject an unusable access or consent page."""
    parser = TextParser()
    parser.feed(html)
    visible = " ".join(parser.text)
    introduction = visible[:1000].casefold()
    blocked = (
        "verify you are human",
        "checking your browser",
        "access denied",
        "enable javascript and cookies",
        "browser challenge",
        "just a moment",
        "sign in to continue",
        "subscribe to continue",
        "enable cookies to continue",
        "we value your privacy",
        "please enable javascript",
        "javascript is disabled",
    )
    if any(phrase in introduction for phrase in blocked):
        raise BriefError("Original source is an access or browser challenge page")
    sections = [" ".join(section) for section in parser.sections]
    content = max(sections, key=len) if sections else visible
    content = content[:max_chars]
    if len(content) < min_chars:
        raise BriefError("Original source has insufficient readable article text")
    return content
