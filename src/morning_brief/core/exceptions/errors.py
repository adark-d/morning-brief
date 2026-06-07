from __future__ import annotations


class BriefSystemError(Exception):
    """Base for every error raised by the morning-brief pipeline."""


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


class AnalysisError(BriefSystemError):
    """Errors during Claude analysis."""


class ModelUnavailableError(AnalysisError):
    """Claude API not responding."""


class InvalidResponseError(AnalysisError):
    """Claude response is not valid JSON or is missing required fields."""


class AnalysisTimeoutError(AnalysisError):
    """Claude response exceeded the timeout threshold."""


class GuardrailError(BriefSystemError):
    """Errors raised by any guardrail in the safety layer."""


class InputGuardrailFailedError(GuardrailError):
    """Data was rejected before reaching Claude."""


class OutputGuardrailFailedError(GuardrailError):
    """Analysis was rejected after Claude responded."""


class RenderError(BriefSystemError):
    """Errors during report rendering."""


class TemplateError(RenderError):
    """Jinja2 template failed to render."""


class DeliveryError(BriefSystemError):
    """Errors during report delivery."""


class SMTPError(DeliveryError):
    """SMTP server returned an error."""


class AuthenticationError(DeliveryError):
    """Credential failure when authenticating with a delivery channel."""


class RecipientError(DeliveryError):
    """Recipient is not in the configured whitelist."""


class StorageError(BriefSystemError):
    """Errors during audit-record persistence or retrieval."""


class ImmutableRecordError(StorageError):
    """Attempted to overwrite an existing audit record with different content.

    Audit records are write-once. Every AuditStore implementation raises this
    for the same violation, so callers depend on one type regardless of backend.
    """


class CorruptRecordError(StorageError):
    """A stored audit record could not be parsed back into a BriefRun."""


class PromptError(BriefSystemError):
    """Errors in the prompt layer (registry, builder, validation)."""


class PromptNotFoundError(PromptError):
    """A prompt component was not found for the requested name and version."""


class IncompletePromptError(PromptError):
    """An assembled prompt is missing a required component."""


class ConfigError(BriefSystemError):
    """Errors during configuration loading or validation."""


class MissingConfigError(ConfigError):
    """A required configuration key was not found."""


class InvalidConfigError(ConfigError):
    """A configuration value failed validation."""
