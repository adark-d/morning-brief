"""HTTP API layer (Layer 1/2) — the only package that knows about HTTP."""

from morning_brief.api.app import create_app

__all__ = ["create_app"]
