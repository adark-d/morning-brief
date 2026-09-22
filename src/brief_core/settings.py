from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from brief_core.aws import read_secrets


class SsmSettingsSource(EnvSettingsSource):
    """Decode SSM values using the same rules as environment variables."""

    def _load_env_vars(self) -> Mapping[str, str | None]:
        return {name.lower(): value for name, value in read_secrets().items()}


class Settings(BaseSettings):
    """Runtime configuration shared by brief workflows."""

    model_config = SettingsConfigDict(
        env_prefix="MORNING_BRIEF_",
        env_file="config/.env",
        env_ignore_empty=True,
        extra="forbid",
        hide_input_in_errors=True,
        validate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Prefer explicit values, environment, local files, then fresh AWS secrets."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            SsmSettingsSource(settings_cls),
            file_secret_settings,
        )

    selection_model: str = "claude-haiku-4-5"
    explanation_model: str = "claude-sonnet-4-5-20250929"
    anthropic_api_key: Annotated[
        SecretStr | None,
        Field(
            validation_alias=AliasChoices("MORNING_BRIEF_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
        ),
    ] = None

    interests: str = "Applied AI engineering, agents, evaluation, and useful research"
    source_names: tuple[str, ...] = ("tldr",)
    topic_count: Annotated[int, Field(ge=1, le=5)] = 5
    max_age_hours: Annotated[int, Field(ge=1, le=168)] = 96
    selection_max_tokens: Annotated[int, Field(ge=100, le=4_000)] = 1_000
    explanation_max_tokens: Annotated[int, Field(ge=500, le=16_000)] = 6_000
    agent_retries: Annotated[int, Field(ge=0, le=3)] = 1
    model_request_limit: Annotated[int, Field(ge=1, le=5)] = 2

    http_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 20
    model_timeout_seconds: Annotated[float, Field(gt=0, le=600)] = 130
    pipeline_timeout_seconds: Annotated[float, Field(gt=0, le=600)] = 420
    fetch_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30
    selection_timeout_seconds: Annotated[float, Field(gt=0, le=180)] = 45
    enrichment_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 20
    explanation_timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 260
    source_content_min_chars: Annotated[int, Field(ge=1, le=2_000)] = 200
    source_content_max_chars: Annotated[int, Field(ge=2_000, le=100_000)] = 16_000
    source_hosts: tuple[str, ...] = (
        "www.anthropic.com",
        "anthropic.com",
        "openai.com",
        "huggingface.co",
        "arxiv.org",
        "github.com",
        "raw.githubusercontent.com",
        "deepmind.google",
        "research.google",
        "blog.google",
        "x.ai",
        "www.testingcatalog.com",
        "www.interconnects.ai",
        "devin.ai",
        "www.alphaxiv.org",
        "www.aikido.dev",
    )
    send_email: bool = False
    email_subject: str = "Your daily AI learning brief"
    recipients: tuple[str, ...] = ()
    smtp_host: str = "localhost"
    smtp_port: Annotated[int, Field(ge=1, le=65_535)] = 587
    smtp_start_tls: bool = True
    smtp_use_tls: bool = False
    smtp_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    sender: str = ""

    @model_validator(mode="after")
    def validate_runtime_limits(self) -> Self:
        """Keep content bounds and model correction budgets consistent."""

        if self.source_content_min_chars > self.source_content_max_chars:
            raise ValueError("source_content_min_chars cannot exceed source_content_max_chars")
        if self.model_request_limit < self.agent_retries + 1:
            raise ValueError("model_request_limit must allow the initial request and agent_retries")
        if self.smtp_start_tls and self.smtp_use_tls:
            raise ValueError("Choose STARTTLS or implicit TLS, not both")
        if self.smtp_port == 465 and not self.smtp_use_tls:
            raise ValueError("SMTP port 465 requires smtp_use_tls=true and smtp_start_tls=false")
        if self.smtp_password is not None and not (self.smtp_start_tls or self.smtp_use_tls):
            raise ValueError("SMTP credentials require an encrypted connection")
        stage_budget = (
            self.fetch_timeout_seconds
            + self.selection_timeout_seconds
            + self.enrichment_timeout_seconds
            + self.explanation_timeout_seconds
            + self.smtp_timeout_seconds
        )
        if stage_budget >= self.pipeline_timeout_seconds:
            raise ValueError("pipeline_timeout_seconds must exceed the combined stage budgets")
        return self
