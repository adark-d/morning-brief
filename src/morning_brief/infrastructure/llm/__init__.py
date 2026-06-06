"""Concrete AnalysisEngine implementations.

The composition root selects which implementation to use at startup based on
settings.llm.provider.
"""

from morning_brief.infrastructure.llm.anthropic_analysis_engine import AnthropicAnalysisEngine
from morning_brief.infrastructure.llm.mock_analysis_engine import MockAnalysisEngine

__all__ = [
    "AnthropicAnalysisEngine",
    "MockAnalysisEngine",
]
