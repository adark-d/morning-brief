from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from morning_brief.config.settings import Settings
from morning_brief.infrastructure.storage.json_audit_store import JsonAuditStore
from morning_brief.infrastructure.storage.mock_audit_store import MockAuditStore


@pytest.fixture(autouse=True)
def _isolate_from_real_dotenv(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Stop every test from reading the developer's real .env.

    Settings declares ``env_file=".env"``, so without this a real .env in the repo
    root would leak live secrets and environment selection into the test process.
    Tests inject their own values via monkeypatch.setenv instead.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.delenv("MORNING_BRIEF_ENVIRONMENT", raising=False)
    yield


@pytest.fixture
def mock_audit_store() -> MockAuditStore:
    """A fresh in-memory audit store per test."""
    return MockAuditStore()


@pytest.fixture
def json_audit_store(tmp_path: Path) -> JsonAuditStore:
    """A JSON audit store rooted at pytest's tmp_path.

    The tmp_path fixture gives each test its own ephemeral directory,
    automatically cleaned up after the test. No file leakage between tests.
    """
    return JsonAuditStore(root_path=tmp_path / "audit")
