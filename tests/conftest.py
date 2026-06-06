"""Top-level pytest configuration and shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from morning_brief.infrastructure.storage.json_audit_store import JsonAuditStore
from morning_brief.infrastructure.storage.mock_audit_store import MockAuditStore


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
