"""File-based JSON implementation of the AuditStore interface.

Production reliability features:
    - Atomic writes (write to temp file, rename) — no partially-written records
    - Idempotent on run_id — re-recording the same run is a no-op
    - Date-partitioned directory structure for human inspection
    - Structured logging on every operation

This is the default audit backend for development and pre-production. For
high-volume production use, a database-backed implementation (Postgres) will
be added as a separate AuditStore implementation.

Implements core.interfaces.audit_store.AuditStore.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from pathlib import Path

import structlog
from pydantic import ValidationError

from morning_brief.core.exceptions.errors import (
    CorruptRecordError,
    ImmutableRecordError,
    StorageError,
)
from morning_brief.core.interfaces.audit_store import AuditStore
from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.models.audit import BriefRun
from morning_brief.infrastructure.storage.json_serialization import (
    deserialize_run,
    serialize_run,
)

logger = structlog.get_logger(__name__)


class JsonAuditStoreError(StorageError):
    """Operational errors specific to the JSON audit store (e.g. path collision)."""


class JsonAuditStore(AuditStore):
    """Audit store that persists BriefRun records as JSON files on disk.

    Directory structure:
        <root>/<YYYY-MM-DD>/run_<uuid>.json

    The date partition uses the run's `triggered_at` field, normalized to UTC.
    """

    def __init__(self, root_path: Path) -> None:
        """Initialise the store at the given root path.

        Args:
            root_path: Directory where audit records will live. Created if missing.
        """
        self._root = root_path
        self._root.mkdir(parents=True, exist_ok=True)
        logger.info("audit_store_initialised", root=str(self._root))

    # ============================================
    # Public interface — implements AuditStore
    # ============================================
    async def record(self, run: BriefRun) -> None:
        target_path = self._path_for_run(run)
        existing = await self._read_if_exists(target_path)

        if existing is not None:
            if existing.run_id != run.run_id:
                raise JsonAuditStoreError(
                    f"Path collision: {target_path} exists with a different run_id"
                )
            if serialize_run(existing) != serialize_run(run):
                raise ImmutableRecordError(
                    f"Refusing to overwrite existing record for run_id={run.run_id}; "
                    "audit records are immutable"
                )
            logger.debug("audit_record_already_exists", run_id=run.run_id)
            return

        await asyncio.to_thread(self._write_atomic, target_path, serialize_run(run))
        logger.info(
            "audit_record_written",
            run_id=run.run_id,
            status=run.status,
            path=str(target_path),
        )

    async def get_by_id(self, run_id: str) -> BriefRun | None:
        match = await asyncio.to_thread(self._find_by_id, run_id)
        if match is None:
            return None
        return await self._read_if_exists(match)

    async def query_by_date(self, target_date: date) -> tuple[BriefRun, ...]:
        date_dir = self._root / target_date.isoformat()
        if not date_dir.is_dir():
            return ()

        paths = await asyncio.to_thread(lambda: list(date_dir.glob("run_*.json")))
        runs: list[BriefRun] = []
        for path in paths:
            run = await self._read_if_exists(path)
            if run is not None:
                runs.append(run)
        # Sort by triggered_at — filename order is alphabetical (UUIDs), not chronological
        return tuple(sorted(runs, key=lambda r: r.triggered_at))

    async def get_latest(self) -> BriefRun | None:
        # Date partitions are ISO-named, so iterating newest-first and returning
        # the last run of the first non-empty day gives the run with the greatest
        # triggered_at — not merely the most recently written file.
        for date_dir in await asyncio.to_thread(self._date_dirs_newest_first):
            runs = await self.query_by_date(date.fromisoformat(date_dir.name))
            if runs:
                return runs[-1]
        return None

    async def health_check(self) -> HealthStatus:
        start = time.perf_counter()
        try:
            await asyncio.to_thread(self._verify_writable)
        except OSError as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                component="JsonAuditStore",
                message=f"Storage not writable: {exc}",
                latency_ms=elapsed_ms,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return HealthStatus(
            state=HealthState.HEALTHY,
            component="JsonAuditStore",
            message=f"Root path {self._root} is writable",
            latency_ms=elapsed_ms,
        )

    # ============================================
    # Internal helpers — synchronous, called via asyncio.to_thread
    # ============================================
    def _path_for_run(self, run: BriefRun) -> Path:
        date_partition = run.triggered_at.date().isoformat()
        return self._root / date_partition / f"run_{run.run_id}.json"

    def _write_atomic(self, target: Path, payload: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(target)  # atomic on POSIX

    def _find_by_id(self, run_id: str) -> Path | None:
        matches = list(self._root.rglob(f"run_{run_id}.json"))
        return matches[0] if matches else None

    def _date_dirs_newest_first(self) -> list[Path]:
        return sorted(
            (d for d in self._root.iterdir() if d.is_dir()),
            key=lambda d: d.name,
            reverse=True,
        )

    def _verify_writable(self) -> None:
        """Touch a probe file and remove it to verify write access."""
        probe = self._root / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()

    async def _read_if_exists(self, path: Path) -> BriefRun | None:
        if not await asyncio.to_thread(path.is_file):
            return None
        try:
            payload = await asyncio.to_thread(path.read_text, encoding="utf-8")
            return deserialize_run(payload)
        except ValidationError as exc:
            raise CorruptRecordError(f"Audit record at {path} is corrupted: {exc}") from exc
