from __future__ import annotations

import pytest

from morning_brief.cli import _build_parser, run_once
from morning_brief.config.settings import (
    AuditSettings,
    DataProviderSettings,
    DeliverySettings,
    EmailChannelSettings,
    LLMSettings,
    Settings,
)


def _mock_settings() -> Settings:
    return Settings(
        data=DataProviderSettings(name="mock"),
        llm=LLMSettings(provider="mock", model="mock-model"),
        audit=AuditSettings(backend="mock"),
        delivery=DeliverySettings(
            channels=("mock",),
            email=EmailChannelSettings(recipients=("desk@firm.com",)),
        ),
    )


def test_run_once_returns_zero_on_success() -> None:
    assert run_once(_mock_settings()) == 0


def test_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args([])


def test_parser_parses_run() -> None:
    assert _build_parser().parse_args(["run"]).command == "run"


def test_parser_serve_has_host_port_defaults() -> None:
    args = _build_parser().parse_args(["serve"])
    assert args.command == "serve"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
