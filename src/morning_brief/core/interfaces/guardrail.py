"""Guardrail interfaces — the contracts for the three-tier safety system.

Sections 13.1, 13.2, 13.3 of the architecture document define the three tiers:
    - InputGuardrail   — runs after data fetch, before LLM call
    - OutputGuardrail  — runs after LLM response, before rendering
    - DeliveryGuardrail — runs after rendering, before delivery

Each tier has its own interface because they operate on different data shapes.
Trying to unify them into a generic Guardrail[T] interface adds ceremony
without buying composability — implementations don't mix between tiers.

Guardrails are synchronous: pure validation logic, no I/O.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.market_data import MarketSnapshot
from morning_brief.core.models.report import RenderedReport


# ============================================
# Outcome types
# ============================================
class GuardrailSeverity(StrEnum):
    """Severity classification for a guardrail finding.

    The pipeline maps these to behaviour:
        - PASS:     continue normally
        - WARNING:  continue but flag the run; downstream gets a warning attached
        - CRITICAL: abort the pipeline; emit alert
    """

    PASS = "pass"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """Outcome of a single guardrail evaluation.

    Frozen dataclass rather than Pydantic — guardrail results don't cross
    process boundaries and don't need validation. Lighter is better here.
    """

    rule_name: str
    severity: GuardrailSeverity
    passed: bool
    message: str = ""
    context: dict[str, str] | None = None


# ============================================
# Tier 1 — Input guardrails (snapshot before LLM)
# ============================================
class InputGuardrail(ABC):
    """Validation applied to MarketSnapshot before it reaches the LLM.

    Examples: yield range validation, staleness check, prompt-injection sanitiser.
    Each rule is its own InputGuardrail implementation.
    """

    @abstractmethod
    def validate(self, snapshot: MarketSnapshot) -> GuardrailResult: ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier used in audit records and logs."""
        ...


# ============================================
# Tier 2 — Output guardrails (analysis after LLM)
# ============================================
class OutputGuardrail(ABC):
    """Validation applied to BriefAnalysis after the LLM responds.

    Examples: numerical claims must trace to input data, hallucination detection,
    confidence threshold checks.

    Takes both the analysis and the source snapshot — many output rules need to
    verify analysis claims against the input that produced them.
    """

    @abstractmethod
    def validate(
        self,
        analysis: BriefAnalysis,
        source_snapshot: MarketSnapshot,
    ) -> GuardrailResult: ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier used in audit records and logs."""
        ...


# ============================================
# Tier 3 — Delivery guardrails (report before send)
# ============================================
class DeliveryGuardrail(ABC):
    """Validation applied to RenderedReport before delivery is attempted.

    Examples: recipient whitelist, duplicate-prevention, compliance disclaimer check.
    Each rule is its own DeliveryGuardrail implementation.
    """

    @abstractmethod
    def validate(
        self,
        report: RenderedReport,
        recipients: tuple[str, ...],
    ) -> GuardrailResult: ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier used in audit records and logs."""
        ...
