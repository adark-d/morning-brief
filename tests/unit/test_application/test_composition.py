from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from morning_brief.application.composition import build_orchestrator
from morning_brief.config.settings import (
    AuditSettings,
    DataProviderSettings,
    DeliverySettings,
    EmailChannelSettings,
    LLMSettings,
    Settings,
)
from morning_brief.core.exceptions.errors import InvalidConfigError, MissingConfigError
from morning_brief.core.models.audit import RunStatus


def _mock_settings(
    *,
    data: DataProviderSettings | None = None,
    llm: LLMSettings | None = None,
    audit: AuditSettings | None = None,
    delivery: DeliverySettings | None = None,
) -> Settings:
    """A fully in-memory configuration; override one sub-model per test."""
    return Settings(
        data=data or DataProviderSettings(name="mock"),
        llm=llm or LLMSettings(provider="mock", model="mock-model"),
        audit=audit or AuditSettings(backend="mock"),
        delivery=delivery
        or DeliverySettings(
            channels=("mock",),
            email=EmailChannelSettings(recipients=("desk@firm.com",)),
        ),
    )


@pytest.mark.asyncio
async def test_mock_pipeline_runs_end_to_end() -> None:
    orchestrator = build_orchestrator(_mock_settings())
    run = await orchestrator.run()

    assert run.status is RunStatus.SUCCESS
    assert run.snapshot is not None
    assert run.analysis is not None
    assert run.delivered_count == 1
    assert run.errors == ()  # the happy path is genuinely clean — no guardrail warnings


def test_build_orchestrator_returns_a_wired_instance() -> None:
    orchestrator = build_orchestrator(_mock_settings())
    assert orchestrator is not None


def test_production_implementations_wire_without_error(tmp_path: Path) -> None:
    # Selects every real implementation (yfinance, anthropic, json store, email).
    # Construction touches no network; the json store writes only under tmp_path.
    settings = _mock_settings(
        data=DataProviderSettings(name="yfinance"),
        llm=LLMSettings(provider="anthropic", model="claude-x", anthropic_api_key=SecretStr("k")),
        audit=AuditSettings(backend="json", json_store_path=tmp_path / "audit"),
        delivery=DeliverySettings(
            channels=("email",),
            email=EmailChannelSettings(recipients=("desk@firm.com",)),
        ),
    )
    assert build_orchestrator(settings) is not None


def test_unknown_data_provider_raises() -> None:
    with pytest.raises(InvalidConfigError, match="data provider"):
        build_orchestrator(_mock_settings(data=DataProviderSettings(name="bogus")))


def test_unknown_llm_provider_raises() -> None:
    with pytest.raises(InvalidConfigError, match="LLM provider"):
        build_orchestrator(_mock_settings(llm=LLMSettings(provider="bogus", model="x")))


def test_anthropic_without_api_key_raises_missing_config() -> None:
    # Pass the key explicitly as None so the ambient environment cannot supply one.
    llm = LLMSettings(provider="anthropic", model="claude-x", anthropic_api_key=None)
    with pytest.raises(MissingConfigError, match="ANTHROPIC_API_KEY"):
        build_orchestrator(_mock_settings(llm=llm))


def test_unsupported_audit_backend_raises() -> None:
    with pytest.raises(InvalidConfigError, match="audit backend"):
        build_orchestrator(_mock_settings(audit=AuditSettings(backend="postgres")))


def test_unknown_delivery_channel_raises() -> None:
    with pytest.raises(InvalidConfigError, match="delivery channel"):
        build_orchestrator(
            _mock_settings(
                delivery=DeliverySettings(
                    channels=("carrier_pigeon",),
                    email=EmailChannelSettings(recipients=("desk@firm.com",)),
                )
            )
        )
