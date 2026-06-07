from __future__ import annotations

import structlog

from morning_brief.core.models.market_data import MarketSnapshot
from morning_brief.prompts.models import (
    AssembledPrompt,
    ContextTemplate,
    FewShotExamples,
    OutputSchema,
    PromptSelection,
    SystemPrompt,
)
from morning_brief.prompts.registry import PromptRegistry

logger = structlog.get_logger(__name__)


class PromptBuilder:
    """Assembles AssembledPrompts from registry components and a market snapshot."""

    def __init__(
        self,
        registry: PromptRegistry,
        selection: PromptSelection | None = None,
    ) -> None:
        self._registry = registry
        self._selection = selection or PromptSelection()

    def build(self, snapshot: MarketSnapshot) -> AssembledPrompt:
        sel = self._selection
        system = self._registry.system(sel.system_name, sel.system_version)
        context = self._registry.context(sel.context_name, sel.context_version)
        schema = self._registry.output_schema(sel.schema_name, sel.schema_version)
        few_shot = self._registry.few_shot(sel.few_shot_name, sel.few_shot_version)

        assembled = AssembledPrompt(
            system=_assemble_system(system, schema, few_shot),
            context=_render_context(context, snapshot),
            version=_compose_version(system, context, schema, few_shot),
        )
        logger.info("prompt_assembled", version=assembled.version)
        return assembled


def _assemble_system(
    system: SystemPrompt,
    schema: OutputSchema,
    few_shot: FewShotExamples,
) -> str:
    sections = [
        system.content.strip(),
        "## Output format\n" + schema.description.strip(),
        "## Worked examples\n" + _render_examples(few_shot),
        "## Rules\n" + system.guardrail_instructions.strip(),
    ]
    return "\n\n".join(sections)


def _render_examples(few_shot: FewShotExamples) -> str:
    blocks = [
        f"Example {i}\nInput:\n{ex.input.strip()}\nOutput:\n{ex.output.strip()}"
        for i, ex in enumerate(few_shot.examples, start=1)
    ]
    return "\n\n".join(blocks)


def _render_context(context: ContextTemplate, snapshot: MarketSnapshot) -> str:
    quality = snapshot.data_quality
    return context.template.format(
        timestamp=snapshot.timestamp.isoformat(),
        yields_block=_section({m: p.yield_pct for m, p in snapshot.yields.items()}),
        instruments_block=_section({s: p.price for s, p in snapshot.instruments.items()}),
        fx_block=_section({pair: p.rate for pair, p in snapshot.fx.items()}),
        succeeded=len(quality.sources_succeeded),
        attempted=len(quality.sources_attempted),
        is_stale=quality.is_stale,
    ).strip()


def _section(values: dict[str, float]) -> str:
    if not values:
        return "  (none available)"
    return "\n".join(f"  {key}: {value}" for key, value in values.items())


def _compose_version(
    system: SystemPrompt,
    context: ContextTemplate,
    schema: OutputSchema,
    few_shot: FewShotExamples,
) -> str:
    return (
        f"{system.name}@{system.version}|{context.name}@{context.version}|"
        f"{schema.name}@{schema.version}|{few_shot.name}@{few_shot.version}"
    )
