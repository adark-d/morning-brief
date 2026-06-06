"""Shared, channel-agnostic content snippets used across renderers.

Reusable text assets (disclaimer, etc.) live here so every renderer — HTML email,
Slack, PDF — uses the identical wording. One source of truth for compliance text.
"""

from __future__ import annotations

from typing import Final

DISCLAIMER: Final = (
    "This briefing is generated automatically for informational purposes only and "
    "does not constitute investment advice or a recommendation to transact."
)
