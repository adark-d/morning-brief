"""Settings loader — single entry point for fetching the application settings.

Settings are loaded once and cached for the lifetime of the process. Loading
failures (bad or missing values) are surfaced as the domain ConfigError hierarchy
rather than Pydantic's ValidationError, so callers catch one meaningful type.

Usage:
    from morning_brief.config import get_settings

    settings = get_settings()
    settings.llm.model
"""

from __future__ import annotations

from functools import cache

from pydantic import ValidationError

from morning_brief.config.settings import Settings
from morning_brief.core.exceptions.errors import InvalidConfigError, MissingConfigError


def load_settings() -> Settings:
    """Construct Settings, translating validation failures into ConfigError.

    Pydantic raises ValidationError on invalid or missing values. We surface a
    missing required field as MissingConfigError and any other failure as
    InvalidConfigError — both subclasses of ConfigError.
    """
    try:
        return Settings()
    except ValidationError as exc:
        if any(error.get("type") == "missing" for error in exc.errors()):
            raise MissingConfigError(str(exc)) from exc
        raise InvalidConfigError(str(exc)) from exc


@cache
def get_settings() -> Settings:
    """Return the application Settings, cached for the lifetime of the process.

    The first call loads from YAML + env vars; subsequent calls return the same
    instance. Tests that need a fresh load should call ``get_settings.cache_clear()``
    first, or use ``load_settings()`` directly to bypass the cache.
    """
    return load_settings()
