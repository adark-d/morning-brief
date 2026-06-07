from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.market_data import MarketSnapshot
from morning_brief.core.models.report import RenderedReport


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
