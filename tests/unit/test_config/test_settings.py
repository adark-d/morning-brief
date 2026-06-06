"""Unit tests for configuration loading.

Cover the behaviour layered on Pydantic Settings: the YAML+env load succeeds,
env vars override nested settings, invalid/out-of-range values surface as the
domain ConfigError hierarchy, secrets stay masked, and get_settings caches.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from morning_brief.config import Environment, get_settings, load_settings
from morning_brief.core.exceptions.errors import ConfigError, InvalidConfigError


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Each test loads settings fresh — no leakage through the process cache."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_load_settings_returns_a_valid_settings_object() -> None:
    settings = load_settings()
    assert isinstance(settings.environment, Environment)
    assert settings.llm.model  # non-empty
    assert settings.audit.backend  # non-empty


def test_env_var_overrides_nested_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORNING_BRIEF_LLM__MODEL", "test-model-xyz")
    assert load_settings().llm.model == "test-model-xyz"


def test_cross_field_validation_failure_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # yield_min must be strictly below yield_max.
    monkeypatch.setenv("MORNING_BRIEF_GUARDRAILS__YIELD_MIN_PCT", "10.0")
    monkeypatch.setenv("MORNING_BRIEF_GUARDRAILS__YIELD_MAX_PCT", "5.0")
    with pytest.raises(InvalidConfigError):
        load_settings()


def test_out_of_range_value_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORNING_BRIEF_LLM__MAX_TOKENS", "999999")  # field cap is 8000
    with pytest.raises(ConfigError):
        load_settings()


def test_staleness_warn_must_be_below_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORNING_BRIEF_GUARDRAILS__STALENESS_WARN_AFTER_HOURS", "30")
    monkeypatch.setenv("MORNING_BRIEF_GUARDRAILS__STALENESS_REJECT_AFTER_HOURS", "24")
    with pytest.raises(InvalidConfigError):
        load_settings()


def test_secrets_are_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORNING_BRIEF_LLM__ANTHROPIC_API_KEY", "super-secret-value")
    settings = load_settings()

    assert settings.llm.anthropic_api_key is not None
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.llm)
    assert settings.llm.anthropic_api_key.get_secret_value() == "super-secret-value"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_delivery_is_multi_channel_shaped() -> None:
    settings = load_settings()
    assert settings.delivery.channels == ("email",)
    assert settings.delivery.email.smtp_port == 587


def test_email_recipients_load_via_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS", '["a@b.com","c@d.com"]')
    assert load_settings().delivery.email.recipients == ("a@b.com", "c@d.com")
