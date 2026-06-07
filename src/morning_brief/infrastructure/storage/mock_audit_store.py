from __future__ import annotations

from datetime import date

from morning_brief.core.exceptions.errors import ImmutableRecordError
from morning_brief.core.interfaces.audit_store import AuditStore
from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.models.audit import BriefRun


class MockAuditStore(AuditStore):
    """In-memory AuditStore for testing.

    Thread-unsafe by design — tests are single-threaded.
    """

    def __init__(self) -> None:
        self._runs: dict[str, BriefRun] = {}

    async def record(self, run: BriefRun) -> None:
        existing = self._runs.get(run.run_id)
        if existing is not None and existing != run:
            raise ImmutableRecordError(
                f"Refusing to overwrite run_id={run.run_id}; audit records are immutable"
            )
        self._runs[run.run_id] = run

    async def get_by_id(self, run_id: str) -> BriefRun | None:
        return self._runs.get(run_id)

    async def query_by_date(self, target_date: date) -> tuple[BriefRun, ...]:
        matches = tuple(
            run for run in self._runs.values() if run.triggered_at.date() == target_date
        )
        return tuple(sorted(matches, key=lambda r: r.triggered_at))

    async def get_latest(self) -> BriefRun | None:
        if not self._runs:
            return None
        return max(self._runs.values(), key=lambda r: r.triggered_at)

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            state=HealthState.HEALTHY,
            component="MockAuditStore",
            message=f"In-memory store with {len(self._runs)} runs",
            latency_ms=0.0,
        )

    def clear(self) -> None:
        """Reset the store. Useful for test isolation."""
        self._runs.clear()

    @property
    def run_count(self) -> int:
        return len(self._runs)
