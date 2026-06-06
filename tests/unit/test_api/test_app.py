"""Tests for the HTTP API.

A mock-configured app (mock pipeline + shared in-memory audit store) is driven via
TestClient. Covers the trigger/read endpoints, the round-trip from a triggered run
to its audit record, the fail-closed auth gate, and the open health probe.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from morning_brief.api.app import create_app
from morning_brief.application.composition import Application, build_orchestrator
from morning_brief.config.settings import (
    ApiSettings,
    AuditSettings,
    DataProviderSettings,
    DeliverySettings,
    EmailChannelSettings,
    LLMSettings,
    Settings,
)
from morning_brief.core.exceptions.errors import StorageError
from morning_brief.core.models.audit import BriefRun
from morning_brief.infrastructure.storage.mock_audit_store import MockAuditStore

_AUTH = {"Authorization": "Bearer secret"}


def _settings(*, auth_token: str | None = "secret") -> Settings:
    return Settings(
        data=DataProviderSettings(name="mock"),
        llm=LLMSettings(provider="mock", model="mock-model"),
        audit=AuditSettings(backend="mock"),
        delivery=DeliverySettings(
            channels=("mock",),
            email=EmailChannelSettings(recipients=("desk@firm.com",)),
        ),
        api=ApiSettings(auth_token=SecretStr(auth_token) if auth_token is not None else None),
    )


def _make_app(*, auth_token: str | None = "secret") -> FastAPI:
    return create_app(_settings(auth_token=auth_token))


# ============================================
# Health (unauthenticated)
# ============================================
def test_health_is_open_and_ok() -> None:
    client = TestClient(_make_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ============================================
# Trigger + retrieve round-trip
# ============================================
def test_trigger_run_returns_summary() -> None:
    client = TestClient(_make_app())
    response = client.post("/briefs/run", headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["delivered"] == 1
    assert body["run_id"]


def test_triggered_run_is_retrievable_by_id() -> None:
    client = TestClient(_make_app())
    run_id = client.post("/briefs/run", headers=_AUTH).json()["run_id"]

    fetched = client.get(f"/briefs/{run_id}", headers=_AUTH)
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == run_id


def test_get_unknown_run_returns_404() -> None:
    client = TestClient(_make_app())
    assert client.get("/briefs/does-not-exist", headers=_AUTH).status_code == 404


def test_latest_returns_404_when_no_runs() -> None:
    client = TestClient(_make_app())
    assert client.get("/briefs/latest", headers=_AUTH).status_code == 404


def test_latest_returns_most_recent_run() -> None:
    client = TestClient(_make_app())
    run_id = client.post("/briefs/run", headers=_AUTH).json()["run_id"]

    latest = client.get("/briefs/latest", headers=_AUTH)
    assert latest.status_code == 200
    assert latest.json()["run_id"] == run_id


def test_list_by_date_includes_a_triggered_run() -> None:
    client = TestClient(_make_app())
    client.post("/briefs/run", headers=_AUTH)

    today = datetime.now(UTC).date().isoformat()
    listed = client.get("/briefs", params={"on": today}, headers=_AUTH)
    assert listed.status_code == 200
    assert len(listed.json()) >= 1


def test_list_by_date_empty_for_a_date_with_no_runs() -> None:
    client = TestClient(_make_app())
    listed = client.get("/briefs", params={"on": "2000-01-01"}, headers=_AUTH)
    assert listed.status_code == 200
    assert listed.json() == []


# ============================================
# Auth (fail-closed)
# ============================================
def test_protected_route_rejects_missing_credentials() -> None:
    client = TestClient(_make_app())
    assert client.post("/briefs/run").status_code == 401


def test_protected_route_rejects_wrong_token() -> None:
    client = TestClient(_make_app())
    response = client.post("/briefs/run", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_protected_route_refuses_when_auth_not_configured() -> None:
    client = TestClient(_make_app(auth_token=None))
    response = client.post("/briefs/run", headers=_AUTH)
    assert response.status_code == 503


def test_malformed_authorization_header_is_rejected() -> None:
    client = TestClient(_make_app())
    response = client.post("/briefs/run", headers={"Authorization": "Basic abc123"})
    assert response.status_code == 401


# ============================================
# Domain-error mapping
# ============================================
class _FailingStore(MockAuditStore):
    async def get_by_id(self, run_id: str) -> BriefRun | None:
        _ = run_id
        raise StorageError("simulated storage fault")


class _RogueStore(MockAuditStore):
    async def get_latest(self) -> BriefRun | None:
        raise RuntimeError("undocumented fault outside the domain hierarchy")


def test_domain_error_maps_to_500_with_error_envelope() -> None:
    settings = _settings()
    app = create_app(
        settings,
        application=Application(
            orchestrator=build_orchestrator(settings), audit_store=_FailingStore()
        ),
    )
    response = TestClient(app).get("/briefs/anything", headers=_AUTH)

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert "StorageError" not in body["detail"]  # internals are not leaked to the client


def test_unexpected_error_maps_to_generic_500() -> None:
    # A non-domain exception goes through the catch-all. raise_server_exceptions is
    # disabled so the test observes the produced 500 rather than the re-raise that
    # surfaces such bugs loudly in normal test runs.
    settings = _settings()
    app = create_app(
        settings,
        application=Application(
            orchestrator=build_orchestrator(settings), audit_store=_RogueStore()
        ),
    )
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/briefs/latest", headers=_AUTH)

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"


def test_invalid_date_returns_422_validation_error() -> None:
    client = TestClient(_make_app())
    response = client.get("/briefs", params={"on": "not-a-date"}, headers=_AUTH)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_unauthenticated_error_uses_the_shared_envelope() -> None:
    client = TestClient(_make_app())
    response = client.post("/briefs/run")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
