"""
Error hierarchy for the morning-brief pipeline.

Every error in the system inherits from BriefSystemError. Logs and metrics filter
by exception type, so the hierarchy must be precise and vague exceptions are a bug.
"""

from __future__ import annotations


# Root
class BriefSystemError(Exception):
    """Base for every error raised by the morning-brief pipeline."""


# Data fetch
class DataFetchError(BriefSystemError):
    """Errors during external market data fetching."""


class APIUnavailableError(DataFetchError):
    """External API did not respond within timeout."""


class RateLimitError(DataFetchError):
    """External API rate limit exceeded."""


class StaleDataError(DataFetchError):
    """Data older than the configured staleness threshold."""


class DataValidationError(DataFetchError):
    """A numerical value falls outside its plausible range."""


# Analysis (LLM)
class AnalysisError(BriefSystemError):
    """Errors during Claude analysis."""


class ModelUnavailableError(AnalysisError):
    """Claude API not responding."""


class InvalidResponseError(AnalysisError):
    """Claude response is not valid JSON or is missing required fields."""


class AnalysisTimeoutError(AnalysisError):
    """Claude response exceeded the timeout threshold."""


# Guardrails
class GuardrailError(BriefSystemError):
    """Errors raised by any guardrail in the safety layer."""


class InputGuardrailFailedError(GuardrailError):
    """Data was rejected before reaching Claude."""


class OutputGuardrailFailedError(GuardrailError):
    """Analysis was rejected after Claude responded."""


# Rendering
class RenderError(BriefSystemError):
    """Errors during report rendering."""


class TemplateError(RenderError):
    """Jinja2 template failed to render."""


# Delivery
class DeliveryError(BriefSystemError):
    """Errors during report delivery."""


class SMTPError(DeliveryError):
    """SMTP server returned an error."""


class AuthenticationError(DeliveryError):
    """Credential failure when authenticating with a delivery channel."""


class RecipientError(DeliveryError):
    """Recipient is not in the configured whitelist."""


# Configuration
class ConfigError(BriefSystemError):
    """Errors during configuration loading or validation."""


class MissingConfigError(ConfigError):
    """A required configuration key was not found."""


class InvalidConfigError(ConfigError):
    """A configuration value failed validation."""
