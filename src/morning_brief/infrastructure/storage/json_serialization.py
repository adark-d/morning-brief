"""JSON serialization helpers for the audit store.

Pydantic v2 handles most of this automatically via model_dump_json(), but we
need to verify the BriefRun → JSON → BriefRun round-trip preserves all
constraints — particularly timezone-aware UTC datetimes and tuple immutability.

These helpers are not part of the public API. They're internal to the JSON
audit store implementation.
"""

from __future__ import annotations

from morning_brief.core.models.audit import BriefRun


def serialize_run(run: BriefRun) -> str:
    """Serialize a BriefRun to its canonical JSON representation.

    Uses Pydantic's native JSON serialization with timezone-aware datetimes
    as ISO 8601 strings.
    """
    return run.model_dump_json(indent=2)


def deserialize_run(payload: str) -> BriefRun:
    """Reconstruct a BriefRun from its JSON representation.

    Validates the full structure on parse — same constraints as construction.
    A corrupted file raises pydantic.ValidationError, which the caller
    catches and surfaces as a storage error.
    """
    return BriefRun.model_validate_json(payload)
