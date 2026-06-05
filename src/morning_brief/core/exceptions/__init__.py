"""
Exception hierarchy. All exceptions are re-exported here for convenient import:
    from morning_brief.core.exceptions import DataFetchError, AnalysisError
"""

from morning_brief.core.exceptions.errors import (
    AnalysisError,
    AnalysisTimeoutError,
    APIUnavailableError,
    AuthenticationError,
    BriefSystemError,
    ConfigError,
    DataFetchError,
    DataValidationError,
    DeliveryError,
    GuardrailError,
    InputGuardrailFailedError,
    InvalidConfigError,
    InvalidResponseError,
    MissingConfigError,
    ModelUnavailableError,
    OutputGuardrailFailedError,
    RateLimitError,
    RecipientError,
    RenderError,
    SMTPError,
    StaleDataError,
    TemplateError,
)

__all__ = [
    "APIUnavailableError",
    "AnalysisError",
    "AnalysisTimeoutError",
    "AuthenticationError",
    "BriefSystemError",
    "ConfigError",
    "DataFetchError",
    "DataValidationError",
    "DeliveryError",
    "GuardrailError",
    "InputGuardrailFailedError",
    "InvalidConfigError",
    "InvalidResponseError",
    "MissingConfigError",
    "ModelUnavailableError",
    "OutputGuardrailFailedError",
    "RateLimitError",
    "RecipientError",
    "RenderError",
    "SMTPError",
    "StaleDataError",
    "TemplateError",
]
