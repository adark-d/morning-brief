"""FastAPI dependency providers.

These are placeholders: ``create_app`` overrides them with the concrete instances
it built. Declaring them as overridable dependencies (rather than reading from
``app.state``) keeps every consumer fully typed and lets tests substitute a mock
application or settings without monkeypatching.
"""

from __future__ import annotations

from morning_brief.application.composition import Application
from morning_brief.config.settings import ApiSettings


def get_application() -> Application:
    """Provide the assembled application. Overridden in ``create_app``."""
    raise NotImplementedError("get_application must be overridden by create_app")


def get_api_settings() -> ApiSettings:
    """Provide the API settings. Overridden in ``create_app``."""
    raise NotImplementedError("get_api_settings must be overridden by create_app")
