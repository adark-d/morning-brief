"""Three-tier safety layer: input, output, and delivery guardrails.

Each rule implements one of the guardrail interfaces in core.interfaces.guardrail.
The runner executes a tier and aggregates the verdict; CRITICAL aborts the pipeline,
WARNING flags and continues.
"""

from morning_brief.guardrails.runner import (
    GuardrailReport,
    run_delivery,
    run_input,
    run_output,
)

__all__ = [
    "GuardrailReport",
    "run_delivery",
    "run_input",
    "run_output",
]
