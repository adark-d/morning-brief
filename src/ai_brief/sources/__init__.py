from __future__ import annotations

from typing import Final

from ai_brief.models import BriefError
from ai_brief.sources.base import Source
from ai_brief.sources.tldr import TldrSource

SOURCE_REGISTRY: Final[dict[str, type[Source]]] = {
    "tldr": TldrSource,
}


def configured_sources(names: tuple[str, ...]) -> tuple[Source, ...]:
    """Build each configured source once and reject unsupported names."""

    sources: list[Source] = []
    for name in dict.fromkeys(names):
        source_type = SOURCE_REGISTRY.get(name)
        if source_type is None:
            raise BriefError(f"Unsupported news source: {name}")
        sources.append(source_type())
    return tuple(sources)


__all__ = ["SOURCE_REGISTRY", "Source", "TldrSource", "configured_sources"]
