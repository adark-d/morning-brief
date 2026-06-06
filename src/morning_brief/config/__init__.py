"""Public API for configuration.

Import from this package:

    from morning_brief.config import get_settings, Settings
    settings = get_settings()
"""

from morning_brief.config.loader import get_settings, load_settings
from morning_brief.config.settings import (
    AuditSettings,
    DataProviderSettings,
    DeliverySettings,
    EmailChannelSettings,
    Environment,
    GuardrailSettings,
    LLMSettings,
    LogLevel,
    ObservabilitySettings,
    PromptSettings,
    Settings,
)

__all__ = [
    "AuditSettings",
    "DataProviderSettings",
    "DeliverySettings",
    "EmailChannelSettings",
    "Environment",
    "GuardrailSettings",
    "LLMSettings",
    "LogLevel",
    "ObservabilitySettings",
    "PromptSettings",
    "Settings",
    "get_settings",
    "load_settings",
]
