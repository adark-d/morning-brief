from __future__ import annotations

from urllib.parse import urljoin, urlsplit

import httpx

from brief_core import BriefCoreError

DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MAX_REDIRECTS = 3


class HttpFetchError(BriefCoreError):
    """A remote document failed shared retrieval policy."""


def validate_https_url(url: str, allowed_hosts: tuple[str, ...]) -> None:
    """Allow only well-formed HTTPS URLs on explicitly trusted hosts."""

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise HttpFetchError("Malformed source URL") from exc

    if (
        parts.scheme != "https"
        or parts.hostname not in allowed_hosts
        or port not in (None, 443)
        or parts.username
        or parts.password
    ):
        raise HttpFetchError("Source URL is outside the configured HTTPS host allowlist")


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    allowed_hosts: tuple[str, ...],
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> str:
    """Fetch bounded text, checking every redirect against the host allowlist."""

    for _ in range(max_redirects + 1):
        validate_https_url(url, allowed_hosts)
        async with client.stream("GET", url, follow_redirects=False) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise HttpFetchError("Redirect response omitted its destination")
                try:
                    url = urljoin(url, location)
                except ValueError as exc:
                    raise HttpFetchError("Malformed redirect destination") from exc
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if not any(value in content_type for value in ("text/", "xml", "xhtml")):
                raise HttpFetchError("Unsupported source content type")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise HttpFetchError("Source exceeded the response size limit")
            return body.decode("utf-8", errors="replace")
    raise HttpFetchError("Too many source redirects")
