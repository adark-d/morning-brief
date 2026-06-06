"""Shared Pydantic base for all domain models.

Every domain model in core.models inherits from FrozenModel. This guarantees:
    - Immutability after construction (defends the audit trail)
    - Strict type validation (no silent coercion of bad inputs)
    - Forbid extra fields (typos in field names raise instead of silently passing)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict


def _ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalise aware ones to UTC.

    Every datetime in this codebase is timezone-aware UTC. This is applied via
    the UtcDatetime alias rather than a per-model validator, so the rule lives in
    exactly one place.
    """
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


# Use for every datetime field on a domain model: `field: UtcDatetime` (or
# `UtcDatetime | None` for optional). Enforces tz-aware UTC on construction
# and on deserialisation.
UtcDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]


class FrozenModel(BaseModel):
    """Base class for all immutable domain models.

    Use this for any model that, once constructed, should never change.
    Particularly important for audit records and any model that crosses
    a process boundary (e.g. enters the LLM prompt, gets persisted).
    """

    model_config = ConfigDict(
        frozen=True,  # immutable after construction
        strict=True,  # no silent type coercion
        extra="forbid",  # unknown fields raise ValidationError
        validate_default=True,  # validate Field defaults too
        ser_json_timedelta="iso8601",
    )
