from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError
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

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import PutObjectRequestTypeDef

logger = structlog.get_logger(__name__)

_ENCODING = "utf-8"


class S3AuditStore(AuditStore):
    """AuditStore backed by Amazon S3 — one immutable object per run.

    Object key: ``<prefix>/<YYYY-MM-DD>/run_<uuid>.json`` (date from ``triggered_at``).
    Records are written with a conditional create (``If-None-Match: *``), so the first
    write wins atomically and races cannot produce a second version: a re-record of
    identical content is a no-op, and different content under the same key raises
    ``ImmutableRecordError``. Pair the bucket with Object Lock for storage-enforced
    WORM. Blocking boto3 calls run in a worker thread to honour the async contract
    (mirrors ``JsonAuditStore``).
    """

    def __init__(
        self,
        *,
        bucket: str,
        region: str | None = None,
        prefix: str = "runs",
        kms_key_id: str | None = None,
        client: S3Client | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._kms_key_id = kms_key_id
        self._client = client if client is not None else _build_client(region)
        logger.info("audit_store_initialised", backend="s3", bucket=bucket, prefix=self._prefix)

    async def record(self, run: BriefRun) -> None:
        key = self._key_for(run)
        payload = serialize_run(run)
        if await asyncio.to_thread(self._put_if_absent, key, payload):
            logger.info(
                "audit_record_written",
                run_id=run.run_id,
                status=run.status,
                bucket=self._bucket,
                key=key,
            )
            return
        # The key already existed: idempotent re-record if identical, else a
        # forbidden overwrite of an immutable record.
        existing = await asyncio.to_thread(self._get_text, key)
        if existing == payload:
            logger.debug("audit_record_already_exists", run_id=run.run_id, key=key)
            return
        raise ImmutableRecordError(
            f"Refusing to overwrite existing record for run_id={run.run_id}; "
            "audit records are immutable"
        )

    async def get_by_id(self, run_id: str) -> BriefRun | None:
        key = await asyncio.to_thread(self._find_key_by_suffix, f"run_{run_id}.json")
        if key is None:
            return None
        return await asyncio.to_thread(self._read_run, key)

    async def query_by_date(self, target_date: date) -> tuple[BriefRun, ...]:
        prefix = f"{self._prefix}/{target_date.isoformat()}/"
        keys = await asyncio.to_thread(self._list_keys, prefix)
        runs = [await asyncio.to_thread(self._read_run, key) for key in keys]
        return tuple(sorted(runs, key=lambda r: r.triggered_at))

    async def get_latest(self) -> BriefRun | None:
        for day in await asyncio.to_thread(self._list_dates_newest_first):
            runs = await self.query_by_date(day)
            if runs:
                return runs[-1]
        return None

    async def health_check(self) -> HealthStatus:
        start = time.perf_counter()
        try:
            await asyncio.to_thread(self._head_bucket)
        except StorageError as exc:
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                component="S3AuditStore",
                message=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        return HealthStatus(
            state=HealthState.HEALTHY,
            component="S3AuditStore",
            message=f"Bucket {self._bucket} reachable",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def _key_for(self, run: BriefRun) -> str:
        partition = run.triggered_at.date().isoformat()
        return f"{self._prefix}/{partition}/run_{run.run_id}.json"

    def _put_if_absent(self, key: str, payload: str) -> bool:
        """Conditionally create the object; return True if written, False if it existed.

        ``If-None-Match: *`` makes the create atomic — a key already present is an
        expected outcome (idempotency / immutability check), not an error.
        """
        params: PutObjectRequestTypeDef = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": payload.encode(_ENCODING),
            "ContentType": "application/json",
            "IfNoneMatch": "*",
        }
        if self._kms_key_id:
            params["ServerSideEncryption"] = "aws:kms"
            params["SSEKMSKeyId"] = self._kms_key_id
        try:
            self._client.put_object(**params)
        except ClientError as exc:
            if _is_precondition_failed(exc):
                return False
            raise StorageError(f"S3 put failed for s3://{self._bucket}/{key}: {exc}") from exc
        return True

    def _read_run(self, key: str) -> BriefRun:
        try:
            return deserialize_run(self._get_text(key))
        except ValidationError as exc:
            raise CorruptRecordError(
                f"Audit record at s3://{self._bucket}/{key} is corrupted: {exc}"
            ) from exc

    def _get_text(self, key: str) -> str:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise StorageError(f"S3 get failed for s3://{self._bucket}/{key}: {exc}") from exc
        return response["Body"].read().decode(_ENCODING)

    def _find_key_by_suffix(self, suffix: str) -> str | None:
        for key in self._list_keys(f"{self._prefix}/"):
            if key.endswith(suffix):
                return key
        return None

    def _list_keys(self, prefix: str) -> list[str]:
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            return [
                obj["Key"]
                for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
                for obj in page.get("Contents", [])
                if "Key" in obj
            ]
        except ClientError as exc:
            raise StorageError(f"S3 list failed for prefix {prefix!r}: {exc}") from exc

    def _list_dates_newest_first(self) -> list[date]:
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            prefixes = {
                common["Prefix"]
                for page in paginator.paginate(
                    Bucket=self._bucket, Prefix=f"{self._prefix}/", Delimiter="/"
                )
                for common in page.get("CommonPrefixes", [])
                if "Prefix" in common
            }
        except ClientError as exc:
            raise StorageError(f"S3 list failed for prefix {self._prefix!r}: {exc}") from exc

        dates: list[date] = []
        for prefix in prefixes:
            name = prefix[len(self._prefix) + 1 :].rstrip("/")
            try:
                dates.append(date.fromisoformat(name))
            except ValueError:
                continue  # ignore non-date prefixes (e.g. a future index/)
        return sorted(dates, reverse=True)

    def _head_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            raise StorageError(f"S3 bucket {self._bucket} not reachable: {exc}") from exc


def _build_client(region: str | None) -> S3Client:
    config = Config(
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=5,
        read_timeout=15,
    )
    # boto3-stubs types client("s3") as S3Client for mypy, but pyright can't narrow
    # the giant client() overload; the suppression is contained to this one call site.
    return boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3", region_name=region, config=config
    )


def _is_precondition_failed(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    metadata = exc.response.get("ResponseMetadata", {})
    return error.get("Code") == "PreconditionFailed" or metadata.get("HTTPStatusCode") == 412
