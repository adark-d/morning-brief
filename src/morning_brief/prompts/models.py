from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _Component(BaseModel):
    """Base for YAML-parsed prompt components.

    Frozen and extra-forbidden (so a typo in a template file fails loudly), but not
    strict: these parse external YAML, where list-to-tuple and similar coercions are
    expected. Domain models use the strict FrozenModel; parsing models do not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class SystemPrompt(_Component):
    """The analyst persona and behaviour, plus explicit guardrail instructions."""

    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    content: Annotated[str, Field(min_length=1)]
    guardrail_instructions: Annotated[str, Field(min_length=1)]


class ContextTemplate(_Component):
    """A format string describing how the market snapshot is laid out for the model."""

    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    template: Annotated[str, Field(min_length=1)]


class OutputSchema(_Component):
    """A human-readable description of the required output fields."""

    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]


class FewShotExample(_Component):
    """A single worked input/output pair."""

    input: Annotated[str, Field(min_length=1)]
    output: Annotated[str, Field(min_length=1)]


class FewShotExamples(_Component):
    """A named, versioned set of worked examples."""

    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    examples: tuple[FewShotExample, ...]


@dataclass(frozen=True, slots=True)
class PromptSelection:
    """Which component name+version to load for each part of the prompt.

    The composition root builds this from PromptSettings; the prompt layer never
    imports config directly (it depends only on core).
    """

    system_name: str = "senior_analyst"
    system_version: str = "v1.0"
    context_name: str = "market_data"
    context_version: str = "v1.0"
    schema_name: str = "brief_schema"
    schema_version: str = "v1.0"
    few_shot_name: str = "examples"
    few_shot_version: str = "v1.0"


@dataclass(frozen=True, slots=True)
class AssembledPrompt:
    """A fully assembled prompt ready for the analysis engine.

    `system` is the stable instruction (persona + schema + examples + rules);
    `context` is the volatile, per-run market data. Keeping them separate lets a
    caller cache the stable prefix and place the data in the user turn.
    `version` is a composite identifier recorded on the audit trail.
    """

    system: str
    context: str
    version: str

    @property
    def full_prompt(self) -> str:
        """System and context joined — for callers that want a single string."""
        return f"{self.system}\n\n---\n\n{self.context}"
