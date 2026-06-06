"""PromptValidator — completeness and token-budget checks before calling the LLM.

Catches two failure modes before they reach Claude: a prompt missing a required
component, and a prompt that would blow the token budget.

Token counting here is a deliberately rough heuristic (~4 chars per token) so the
check runs offline with no API call. For a precise count, the Anthropic
``messages.count_tokens`` endpoint is the production option — tiktoken must NOT be
used, as it is calibrated for a different tokenizer and undercounts Claude tokens.
"""

from __future__ import annotations

import structlog

from morning_brief.core.exceptions.errors import IncompletePromptError
from morning_brief.prompts.models import AssembledPrompt

logger = structlog.get_logger(__name__)

_CHARS_PER_TOKEN = 4


class PromptValidator:
    """Validates assembled prompts for completeness and token budget."""

    def __init__(self, max_tokens: int = 8000) -> None:
        self._max_tokens = max_tokens

    def validate(self, prompt: AssembledPrompt) -> None:
        """Raise IncompletePromptError if a required component is missing."""
        if not prompt.system.strip():
            raise IncompletePromptError("Assembled prompt has no system content")
        if not prompt.context.strip():
            raise IncompletePromptError("Assembled prompt has no context content")

    def estimate_tokens(self, prompt: AssembledPrompt) -> int:
        """Rough token estimate for the full prompt (heuristic, not exact)."""
        return len(prompt.full_prompt) // _CHARS_PER_TOKEN

    def within_budget(self, prompt: AssembledPrompt) -> bool:
        """True if the estimated token count is within the configured budget."""
        estimate = self.estimate_tokens(prompt)
        if estimate > self._max_tokens:
            logger.warning(
                "prompt_exceeds_token_budget",
                estimate=estimate,
                budget=self._max_tokens,
            )
            return False
        return True
