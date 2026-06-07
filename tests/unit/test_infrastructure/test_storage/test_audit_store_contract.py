from __future__ import annotations

import stat
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from tests.fixtures import make_brief_run

from morning_brief.core.exceptions.errors import ImmutableRecordError
from morning_brief.core.interfaces.audit_store import AuditStore
from morning_brief.core.interfaces.base import HealthState
from morning_brief.core.models.audit import RunStatus
from morning_brief.infrastructure.storage.json_audit_store import JsonAuditStore
from morning_brief.infrastructure.storage.mock_audit_store import MockAuditStore


def _store_factories() -> list[tuple[str, Callable[[Path], AuditStore]]]:
    return [
        ("mock", lambda _tmp: MockAuditStore()),
        ("json", lambda tmp: JsonAuditStore(root_path=tmp / "audit")),
    ]


@pytest.fixture(params=_store_factories(), ids=lambda p: p[0])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> AuditStore:
    """Returns each AuditStore implementation in turn."""
    _name, factory = request.param
    typed_factory = cast(Callable[[Path], AuditStore], factory)
    return typed_factory(tmp_path)


@pytest.mark.asyncio
async def test_record_and_retrieve_by_id(store: AuditStore) -> None:
    run = make_brief_run()
    await store.record(run)

    retrieved = await store.get_by_id(run.run_id)
    assert retrieved is not None
    assert retrieved.run_id == run.run_id
    assert retrieved.status == run.status


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing_run(store: AuditStore) -> None:
    retrieved = await store.get_by_id("nonexistent-uuid")
    assert retrieved is None


@pytest.mark.asyncio
async def test_get_by_id_does_not_treat_run_id_as_a_glob(store: AuditStore) -> None:
    # Security: a crafted run_id (glob metacharacters) must not match a record the
    # caller never named — the id is a capability, not a search pattern.
    await store.record(make_brief_run())
    assert await store.get_by_id("*") is None
    assert await store.get_by_id("run_*") is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
@pytest.mark.asyncio
async def test_json_store_restricts_permissions_on_sensitive_data(tmp_path: Path) -> None:
    # Security: audit records (analysis + recipients) must not be world-readable.
    root = tmp_path / "audit"
    store = JsonAuditStore(root_path=root)
    await store.record(make_brief_run())

    record_file = next(root.rglob("run_*.json"))
    assert stat.S_IMODE(record_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(root.stat().st_mode) == 0o700


@pytest.mark.asyncio
async def test_record_is_idempotent_for_same_run(store: AuditStore) -> None:
    run = make_brief_run()
    await store.record(run)
    await store.record(run)  # second call should not raise

    retrieved = await store.get_by_id(run.run_id)
    assert retrieved is not None


@pytest.mark.asyncio
async def test_record_rejects_overwrite_with_different_content(store: AuditStore) -> None:
    original = make_brief_run(status=RunStatus.SUCCESS)
    await store.record(original)

    modified = make_brief_run(
        run_id=original.run_id,
        triggered_at=original.triggered_at,
        status=RunStatus.FAILED,
    )

    with pytest.raises(ImmutableRecordError):
        await store.record(modified)


@pytest.mark.asyncio
async def test_query_by_date_returns_runs_for_that_date(store: AuditStore) -> None:
    target_date = datetime(2026, 5, 10, 7, 0, tzinfo=UTC)
    other_date = datetime(2026, 5, 11, 7, 0, tzinfo=UTC)

    run_on_target = make_brief_run(triggered_at=target_date)
    run_on_other = make_brief_run(triggered_at=other_date)

    await store.record(run_on_target)
    await store.record(run_on_other)

    results = await store.query_by_date(target_date.date())
    assert len(results) == 1
    assert results[0].run_id == run_on_target.run_id


@pytest.mark.asyncio
async def test_query_by_date_returns_empty_for_dates_with_no_runs(store: AuditStore) -> None:
    results = await store.query_by_date(datetime(2026, 1, 1, tzinfo=UTC).date())
    assert results == ()


@pytest.mark.asyncio
async def test_query_by_date_returns_multiple_runs_chronologically(store: AuditStore) -> None:
    base = datetime(2026, 5, 10, 7, 0, tzinfo=UTC)
    run1 = make_brief_run(triggered_at=base)
    run2 = make_brief_run(triggered_at=base + timedelta(hours=2))
    run3 = make_brief_run(triggered_at=base + timedelta(hours=1))

    await store.record(run1)
    await store.record(run2)
    await store.record(run3)

    results = await store.query_by_date(base.date())
    assert len(results) == 3
    # Should be ordered chronologically
    assert results[0].triggered_at < results[1].triggered_at < results[2].triggered_at


@pytest.mark.asyncio
async def test_get_latest_returns_most_recent_run(store: AuditStore) -> None:
    older = make_brief_run(triggered_at=datetime(2026, 5, 9, 7, 0, tzinfo=UTC))
    newer = make_brief_run(triggered_at=datetime(2026, 5, 10, 7, 0, tzinfo=UTC))

    await store.record(older)
    await store.record(newer)

    latest = await store.get_latest()
    assert latest is not None
    assert latest.run_id == newer.run_id


@pytest.mark.asyncio
async def test_get_latest_orders_by_triggered_at_not_write_order(store: AuditStore) -> None:
    """A backfilled older run written last must not be reported as the latest.

    Regression guard: ordering must use triggered_at, not file write time.
    """
    newer = make_brief_run(triggered_at=datetime(2026, 5, 10, 7, 0, tzinfo=UTC))
    older = make_brief_run(triggered_at=datetime(2026, 5, 9, 7, 0, tzinfo=UTC))

    await store.record(newer)
    await store.record(older)  # written last, but chronologically earlier

    latest = await store.get_latest()
    assert latest is not None
    assert latest.run_id == newer.run_id


@pytest.mark.asyncio
async def test_get_latest_uses_triggered_at_within_a_single_day(store: AuditStore) -> None:
    base = datetime(2026, 5, 10, 7, 0, tzinfo=UTC)
    first = make_brief_run(triggered_at=base)
    last = make_brief_run(triggered_at=base + timedelta(hours=3))
    middle = make_brief_run(triggered_at=base + timedelta(hours=1))

    await store.record(first)
    await store.record(last)
    await store.record(middle)

    latest = await store.get_latest()
    assert latest is not None
    assert latest.run_id == last.run_id


@pytest.mark.asyncio
async def test_get_latest_returns_none_for_empty_store(store: AuditStore) -> None:
    latest = await store.get_latest()
    assert latest is None


@pytest.mark.asyncio
async def test_health_check_is_healthy_after_initialisation(store: AuditStore) -> None:
    status = await store.health_check()
    assert status.state == HealthState.HEALTHY


@pytest.mark.asyncio
async def test_health_check_reports_latency(store: AuditStore) -> None:
    status = await store.health_check()
    assert status.latency_ms is not None
    assert status.latency_ms >= 0
