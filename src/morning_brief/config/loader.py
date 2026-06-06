"""Settings loader — single entry point for fetching the application settings.

Settings are loaded once and cached for the lifetime of the process. Tests can
override this by passing kwargs to get_settings(), which forces a fresh load.

Usage:
    from morning_brief.config import get_settings

    settings = get_settings()
    print(settings.llm.model)
"""

from __future__ import annotations

from functools import cache

from morning_brief.config.settings import Settings


@cache
def get_settings() -> Settings:
    """Return the application Settings.

    Cached for the lifetime of the process. The first call loads from YAML +
    env vars; subsequent calls return the same instance.

    For tests that need fresh settings, call `get_settings.cache_clear()` first,
    or pass kwargs to bypass the cache:

        from morning_brief.config import Settings
        test_settings = Settings(environment="test", ...)
    """
    return Settings()
