from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from morning_brief.api.app import create_app
from morning_brief.config.settings import (
    ApiSettings,
    AuditSettings,
    DataProviderSettings,
    DeliverySettings,
    EmailChannelSettings,
    LLMSettings,
    Settings,
)

_AUTH = {"Authorization": "Bearer secret"}


def test_trigger_then_retrieve_over_http_with_real_store(tmp_path: Path) -> None:
    settings = Settings(
        data=DataProviderSettings(name="mock"),
        llm=LLMSettings(provider="mock", model="mock-model"),
        audit=AuditSettings(backend="json", json_store_path=tmp_path / "audit"),
        delivery=DeliverySettings(
            channels=("mock",),
            email=EmailChannelSettings(recipients=("desk@firm.com",)),
        ),
        api=ApiSettings(auth_token=SecretStr("secret")),
    )
    client = TestClient(create_app(settings))

    triggered = client.post("/briefs/run", headers=_AUTH)
    assert triggered.status_code == 200
    run_id = triggered.json()["run_id"]

    # Retrieve the persisted record back over HTTP.
    fetched = client.get(f"/briefs/{run_id}", headers=_AUTH)
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["run_id"] == run_id
    assert body["status"] == "success"
    # PII-free DTO: delivery outcomes carry channel + status only, no addresses.
    assert body["deliveries"] == [{"channel": "mock", "status": "delivered"}]
    assert "desk@firm.com" not in str(body)

    # And the record is physically on disk under the real store root.
    assert list((tmp_path / "audit").rglob("run_*.json"))
