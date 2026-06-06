"""Brief analysis — the structured output from Claude.

Section 10.2 of the architecture. Every field is defined in the output schema
YAML (Phase 4) and validated by the output guardrail (Section 13.2) before use.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from morning_brief.core.models.base import FrozenModel, UtcDatetime


class BriefAnalysis(FrozenModel):
    """Claude's structured output for a single morning brief.

    The shape here matches the output schema in
    prompts/templates/output_schemas/brief_schema_v1.yaml.
    """

    headline: Annotated[
        str,
        Field(
            min_length=10,
            max_length=150,
            description="Single most important overnight development (one sentence)",
        ),
    ]
    yield_curve_summary: Annotated[
        str,
        Field(
            min_length=20,
            max_length=300,
            description="Interpretation of curve shape and signal for the day",
        ),
    ]
    key_signals: Annotated[
        tuple[str, ...],
        Field(
            min_length=2,
            max_length=5,
            description="Most important signals from the data",
        ),
    ]
    macro_context: Annotated[
        str,
        Field(
            min_length=20,
            max_length=400,
            description="How oil, dollar, and risk sentiment connect to fixed income",
        ),
    ]
    watch_today: Annotated[
        tuple[str, ...],
        Field(
            min_length=2,
            max_length=3,
            description="Specific things to monitor during the session",
        ),
    ]
    full_narrative: Annotated[
        str,
        Field(
            min_length=150,
            max_length=500,
            description="Complete morning brief narrative",
        ),
    ]
    confidence: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description="Quality score based on data completeness and analysis confidence",
        ),
    ]
    model_used: Annotated[str, Field(min_length=1, description="Model identifier")]
    prompt_version: Annotated[str, Field(min_length=1, description="Prompt version used")]
    generated_at: UtcDatetime
    cost_usd: Annotated[float | None, Field(ge=0, description="LLM cost for this run")] = None
