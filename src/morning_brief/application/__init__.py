"""Application layer — orchestration that composes the interfaces into a pipeline.

``build_orchestrator`` is deliberately NOT re-exported here: it is the composition
root and the only module that imports infrastructure, so pulling it into this
package's ``__init__`` would make importing ``morning_brief.application`` drag in
every concrete dependency. Entry points import it explicitly:
``from morning_brief.application.composition import build_orchestrator``.
"""

from morning_brief.application.delivery_router import ChannelRouter, ChannelTarget
from morning_brief.application.orchestrator import BriefOrchestrator

__all__ = [
    "BriefOrchestrator",
    "ChannelRouter",
    "ChannelTarget",
]
