"""Tests for MockDataProvider — the in-memory test fixture.

These verify the mock itself behaves correctly. The mock is used by other
tests, so its own correctness is the foundation of everything else.
"""

from __future__ import annotations

import pytest

from morning_brief.core.exceptions.errors import APIUnavailableError
from morning_brief.core.interfaces.base import HealthState
from morning_brief.infrastructure.data.mock_data_provider import MockDataProvider


@pytest.mark.asyncio
async def test_default_mock_returns_complete_snapshot() -> None:
    provider = MockDataProvider()
    snapshot = await provider.fetch_snapshot()

    assert len(snapshot.yields) > 0
    assert len(snapshot.instruments) > 0
    assert len(snapshot.fx) > 0
    assert snapshot.data_quality.is_complete


@pytest.mark.asyncio
async def test_mock_records_yield_failures_in_data_quality() -> None:
    provider = MockDataProvider(fail_yields=True)
    snapshot = await provider.fetch_snapshot()

    assert len(snapshot.yields) == 0
    assert len(snapshot.instruments) > 0  # instruments still work
    assert not snapshot.data_quality.is_complete
    # All four yield maturities should be in failures
    assert len(snapshot.data_quality.sources_failed) == 4


@pytest.mark.asyncio
async def test_mock_records_fx_failures_in_data_quality() -> None:
    provider = MockDataProvider(fail_fx=True)
    snapshot = await provider.fetch_snapshot()

    assert len(snapshot.fx) == 0
    assert len(snapshot.yields) > 0
    assert not snapshot.data_quality.is_complete


@pytest.mark.asyncio
async def test_mock_raises_when_fail_all_set() -> None:
    provider = MockDataProvider(fail_all=True)

    with pytest.raises(APIUnavailableError):
        await provider.fetch_snapshot()


@pytest.mark.asyncio
async def test_mock_health_check_healthy_by_default() -> None:
    provider = MockDataProvider()
    status = await provider.health_check()
    assert status.state == HealthState.HEALTHY


@pytest.mark.asyncio
async def test_mock_health_check_unhealthy_when_flagged() -> None:
    provider = MockDataProvider(unhealthy=True)
    status = await provider.health_check()
    assert status.state == HealthState.UNHEALTHY


@pytest.mark.asyncio
async def test_mock_uses_consistent_timestamp_across_data() -> None:
    """All data points in a snapshot share the snapshot's fetch time."""
    provider = MockDataProvider()
    snapshot = await provider.fetch_snapshot()

    snapshot_ts = snapshot.timestamp
    for yp in snapshot.yields.values():
        assert yp.timestamp == snapshot_ts
    for pp in snapshot.instruments.values():
        assert pp.timestamp == snapshot_ts
    for fp in snapshot.fx.values():
        assert fp.timestamp == snapshot_ts


@pytest.mark.asyncio
async def test_mock_yields_contain_typical_treasury_maturities() -> None:
    """The default mock should include the maturities the pipeline expects."""
    provider = MockDataProvider()
    snapshot = await provider.fetch_snapshot()
    # The architecture's analysis layer assumes at least these are present
    assert "10Y" in snapshot.yields
