"""AnalysisEngine interface — the contract for any LLM analysis backend.

Today's implementation is Anthropic Claude. The architecture also names OpenAI
and local models as fallbacks. Section 9.2 of the architecture document.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from morning_brief.core.interfaces.base import HealthStatus
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.market_data import MarketSnapshot


class AnalysisEngine(ABC):
    """Abstract LLM analysis engine.

    Every concrete implementation:
        - is async (LLM calls are I/O-bound; we never block the event loop)
        - returns a fully-validated BriefAnalysis (the model's constraints enforce schema)
        - raises AnalysisError or a subclass on failure (caller decides what to do)
        - records its model identifier and prompt version on the returned analysis
    """

    @abstractmethod
    async def analyse(
        self,
        snapshot: MarketSnapshot,
        prompt: str,
        *,
        prompt_version: str = "unversioned",
        max_tokens: int = 2000,
        timeout_seconds: float = 30.0,
    ) -> BriefAnalysis:
        """Produce a structured analysis from a market snapshot and assembled prompt.

        Args:
            snapshot: The validated market data the analysis is grounded in.
            prompt: The complete prompt (system + context + schema + examples)
                already assembled by the prompt builder.
            prompt_version: Version of the prompt used, recorded on the analysis
                for the audit trail.
            max_tokens: Upper bound on the response length.
            timeout_seconds: Maximum time to wait for the model.

        Returns:
            A validated BriefAnalysis. If the model's raw response fails
            Pydantic validation, the implementation retries once before raising.

        Raises:
            ModelUnavailableError: when the LLM endpoint is unreachable.
            InvalidResponseError: when the response cannot be parsed as the
                expected schema after retries.
            AnalysisTimeoutError: when the timeout is exceeded.
        """
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Test whether the LLM endpoint is reachable and responding.

        Implementations should send the lightest-possible probe (a single-token
        completion or a /health endpoint), not a full inference call.
        """
        ...
