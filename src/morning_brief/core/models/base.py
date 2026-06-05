"""Shared Pydantic base for all domain models.

Every domain model in core.models inherits from FrozenModel. This guarantees:
    - Immutability after construction (defends the audit trail)
    - Strict type validation (no silent coercion of bad inputs)
    - Forbid extra fields (typos in field names raise instead of silently passing)
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
