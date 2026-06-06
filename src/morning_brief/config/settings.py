"""Application settings — the single source of truth for all configuration.

Uses Pydantic Settings to load values from (in order of precedence):
    1. Environment variables (highest priority)
    2. Environment-specific YAML file (e.g. config/environments/production.yaml)
    3. Default YAML file (config/default.yaml)
    4. Field defaults defined below (lowest priority)

The active environment is determined by the MORNING_BRIEF_ENV environment variable.
Defaults to "development" if not set.

Secrets (API keys, recipient lists) MUST come from environment variables only.
YAML files should never contain credentials.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


# ============================================
# Enums
# ============================================
class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ============================================
# Sub-models (one per concern)
# ============================================
class DataProviderSettings(BaseModel):
    """Configuration for the active data provider."""

    name: Annotated[str, Field(description="Provider implementation, e.g. 'yfinance'")] = "yfinance"
    timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 10.0
    staleness_threshold_hours: Annotated[float, Field(gt=0, le=24)] = 4.0
    alpha_vantage_api_key: SecretStr | None = None


class LLMSettings(BaseModel):
    """Configuration for the analysis engine."""

    provider: Annotated[str, Field(description="LLM provider, e.g. 'anthropic'")] = "anthropic"
    model: Annotated[str, Field(min_length=1)] = "claude-opus-4-7"
    fallback_model: str | None = None
    max_tokens: Annotated[int, Field(gt=0, le=8000)] = 2000
    timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30.0
    max_retries: Annotated[int, Field(ge=0, le=5)] = 1
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None


class EmailChannelSettings(BaseModel):
    """SMTP configuration for the email delivery channel."""

    recipients: tuple[str, ...] = ()
    smtp_host: str = "localhost"
    smtp_port: Annotated[int, Field(gt=0, le=65535)] = 587
    smtp_username: SecretStr | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "noreply@example.com"
    start_tls: bool = True
    timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30.0


class DeliverySettings(BaseModel):
    """Configuration for the delivery layer.

    `channels` lists the active delivery channels; each channel has its own nested
    config block. Adding a channel (e.g. Slack) is additive: append its name here
    and add a matching settings block — no existing channel is touched.
    """

    channels: tuple[str, ...] = ("email",)
    duplicate_prevention_enabled: bool = True
    email: EmailChannelSettings = Field(default_factory=EmailChannelSettings)


class PromptSettings(BaseModel):
    """Configuration for the prompt layer."""

    system_prompt_name: str = "senior_analyst"
    system_prompt_version: str = "v1.0"
    context_template_name: str = "market_data"
    context_template_version: str = "v1.0"
    output_schema_name: str = "brief_schema"
    output_schema_version: str = "v1.0"
    few_shot_examples_name: str = "examples"
    few_shot_examples_version: str = "v1.0"


class GuardrailSettings(BaseModel):
    """Configuration for the safety layer."""

    # Input guardrails
    yield_min_pct: Annotated[float, Field(ge=-5.0, le=25.0)] = 0.1
    yield_max_pct: Annotated[float, Field(ge=-5.0, le=25.0)] = 20.0
    min_yield_maturities_required: Annotated[int, Field(ge=1, le=10)] = 3

    # Staleness (input guardrail): WARNING past warn, CRITICAL abort past reject.
    # Distinct from data.staleness_threshold_hours, which the provider uses to set
    # the is_stale flag at fetch time — the guardrail also honours that flag.
    staleness_warn_after_hours: Annotated[float, Field(gt=0, le=72)] = 6.0
    staleness_reject_after_hours: Annotated[float, Field(gt=0, le=72)] = 24.0

    # Output guardrails
    confidence_warning_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.6
    narrative_min_words: Annotated[int, Field(ge=10, le=1000)] = 150
    narrative_max_words: Annotated[int, Field(ge=10, le=1000)] = 500


class AuditSettings(BaseModel):
    """Configuration for the audit store."""

    backend: Annotated[
        str, Field(description="Backend implementation, e.g. 'json', 'postgres'")
    ] = "json"
    json_store_path: Path = Path("./audit")
    postgres_dsn: SecretStr | None = None


class ObservabilitySettings(BaseModel):
    """Configuration for logging and metrics."""

    log_level: LogLevel = LogLevel.INFO
    json_logs: bool = True
    metrics_enabled: bool = True


class ApiSettings(BaseModel):
    """Configuration for the HTTP API (Layer 1/2).

    Auth is fail-closed: if ``auth_token`` is unset, protected endpoints refuse all
    requests rather than serving an unauthenticated API. Rate limiting is deferred
    to the deployment-hardening phase (it needs state shared across workers).
    """

    auth_token: SecretStr | None = None


# ============================================
# Top-level Settings
# ============================================
class Settings(BaseSettings):
    """Top-level application settings.

    Loaded once at startup. Treat as immutable for the lifetime of the process.
    """

    model_config = SettingsConfigDict(
        env_prefix="MORNING_BRIEF_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    environment: Environment = Environment.DEVELOPMENT
    schedule_cron: Annotated[
        str,
        Field(description="Cron expression for scheduled runs"),
    ] = "0 7 * * 1-5"

    data: DataProviderSettings = Field(default_factory=DataProviderSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    delivery: DeliverySettings = Field(default_factory=DeliverySettings)
    prompt: PromptSettings = Field(default_factory=PromptSettings)
    guardrails: GuardrailSettings = Field(default_factory=GuardrailSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    api: ApiSettings = Field(default_factory=ApiSettings)

    @field_validator("guardrails")
    @classmethod
    def guardrail_thresholds_must_be_ordered(cls, v: GuardrailSettings) -> GuardrailSettings:
        if v.yield_min_pct >= v.yield_max_pct:
            raise ValueError(
                f"yield_min_pct ({v.yield_min_pct}) must be strictly less than "
                f"yield_max_pct ({v.yield_max_pct})"
            )
        if v.staleness_warn_after_hours >= v.staleness_reject_after_hours:
            raise ValueError(
                f"staleness_warn_after_hours ({v.staleness_warn_after_hours}) must be "
                f"strictly less than staleness_reject_after_hours "
                f"({v.staleness_reject_after_hours})"
            )
        if v.narrative_min_words >= v.narrative_max_words:
            raise ValueError(
                f"narrative_min_words ({v.narrative_min_words}) must be strictly less "
                f"than narrative_max_words ({v.narrative_max_words})"
            )
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customise the precedence and sources of settings.

        Resulting order, highest priority first:
            1. init_settings — values passed to Settings(...) explicitly
            2. env_settings — environment variables
            3. dotenv_settings — values from .env file
            4. env-specific YAML — config/environments/<env>.yaml
            5. default YAML — config/default.yaml
        """
        config_dir = Path(__file__).parent.parent.parent.parent / "config"
        default_yaml = config_dir / "default.yaml"

        # Decide which env-specific file to load. An explicit environment passed to
        # Settings(...) wins; otherwise fall back to the env var (defaulting to dev).
        # An explicit environment passed to Settings(...) wins; otherwise fall back to
        # the env var (defaulting to development). Only InitSettingsSource carries
        # init_kwargs, and pydantic-settings leaves it unannotated, so read it
        # defensively via getattr (returns {} for any other source type).
        init_kwargs: dict[str, object] = getattr(init_settings, "init_kwargs", {})
        explicit = init_kwargs.get("environment")
        env_name = str(explicit) if explicit is not None else None
        if env_name is None:
            import os

            env_name = os.environ.get("MORNING_BRIEF_ENVIRONMENT", "development").lower()

        env_yaml = config_dir / "environments" / f"{env_name}.yaml"

        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]

        if env_yaml.exists():
            sources.append(YamlConfigSettingsSource(settings_cls, env_yaml))
        if default_yaml.exists():
            sources.append(YamlConfigSettingsSource(settings_cls, default_yaml))

        return tuple(sources)
