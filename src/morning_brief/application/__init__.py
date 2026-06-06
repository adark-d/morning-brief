"""Application layer — orchestration that composes the interfaces into a pipeline."""

from morning_brief.application.delivery_router import ChannelRouter, ChannelTarget
from morning_brief.application.orchestrator import BriefOrchestrator

__all__ = [
    "BriefOrchestrator",
    "ChannelRouter",
    "ChannelTarget",
]
