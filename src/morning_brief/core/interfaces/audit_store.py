from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from morning_brief.core.interfaces.base import HealthStatus
from morning_brief.core.models.audit import BriefRun


class AuditStore(ABC):
    """Abstract storage for BriefRun audit records.

    Append-only. There is no update() or delete() — by design. Records are
    immutable once written; corrections happen via new records, not by editing.

    Every concrete implementation:
        - is async (storage is I/O-bound)
        - persists BriefRun records as immutable JSON-serialisable data
        - supports query by date and retrieval of the most recent run
        - returns None (not raises) when a queried record doesn't exist
    """

    @abstractmethod
    async def record(self, run: BriefRun) -> None:
        """Persist a BriefRun. Idempotent on the run_id.

        Re-recording an identical run is a no-op. Recording a different run under
        an existing run_id raises ImmutableRecordError — runs are constructed once
        and never edited. Every implementation honours this contract identically.
        """
        ...

    @abstractmethod
    async def get_by_id(self, run_id: str) -> BriefRun | None:
        """Retrieve a run by its UUID. Returns None if not found."""
        ...

    @abstractmethod
    async def query_by_date(self, target_date: date) -> tuple[BriefRun, ...]:
        """Retrieve all runs that triggered on a given UTC calendar date."""
        ...

    @abstractmethod
    async def get_latest(self) -> BriefRun | None:
        """Retrieve the most recent run. Returns None if no runs exist."""
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Test whether the storage backend is reachable and writable."""
        ...
