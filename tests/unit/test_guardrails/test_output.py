from __future__ import annotations

from tests.fixtures import make_brief_analysis, make_market_snapshot

from morning_brief.core.interfaces.guardrail import GuardrailSeverity
from morning_brief.guardrails.output import (
    ConfidenceGuardrail,
    NarrativeLengthGuardrail,
    NumericalGroundingGuardrail,
)


def _narrative_of(word_count: int) -> str:
    """A narrative with exactly `word_count` words (>= 150 chars to satisfy the model)."""
    return " ".join(["bond"] * word_count)


def test_grounding_passes_when_figures_trace_to_snapshot() -> None:
    snapshot = make_market_snapshot()  # 10Y = 4.42
    analysis = make_brief_analysis()  # narrative cites 4.42
    result = NumericalGroundingGuardrail().validate(analysis, snapshot)
    assert result.severity is GuardrailSeverity.PASS


def test_grounding_warns_on_ungrounded_decimal() -> None:
    snapshot = make_market_snapshot()  # 10Y = 4.42
    analysis = make_brief_analysis(key_signals=("Bund printed a 9.99 handle", "Risk-off"))
    result = NumericalGroundingGuardrail().validate(analysis, snapshot)
    assert result.severity is GuardrailSeverity.WARNING
    assert "9.99" in (result.context or {}).get("ungrounded", "")


def test_confidence_passes_above_threshold() -> None:
    analysis = make_brief_analysis(confidence=0.82)
    result = ConfidenceGuardrail(0.6).validate(analysis, make_market_snapshot())
    assert result.severity is GuardrailSeverity.PASS


def test_confidence_warns_below_threshold() -> None:
    analysis = make_brief_analysis(confidence=0.4)
    result = ConfidenceGuardrail(0.6).validate(analysis, make_market_snapshot())
    assert result.severity is GuardrailSeverity.WARNING


def test_narrative_length_passes_within_band() -> None:
    analysis = make_brief_analysis(full_narrative=_narrative_of(300))
    result = NarrativeLengthGuardrail(150, 500).validate(analysis, make_market_snapshot())
    assert result.severity is GuardrailSeverity.PASS


def test_narrative_length_warns_when_too_short() -> None:
    analysis = make_brief_analysis(full_narrative=_narrative_of(80))
    result = NarrativeLengthGuardrail(150, 500).validate(analysis, make_market_snapshot())
    assert result.severity is GuardrailSeverity.WARNING
    assert (result.context or {}).get("word_count") == "80"


def test_narrative_length_warns_when_too_long() -> None:
    analysis = make_brief_analysis(full_narrative=_narrative_of(600))
    result = NarrativeLengthGuardrail(150, 500).validate(analysis, make_market_snapshot())
    assert result.severity is GuardrailSeverity.WARNING


def test_default_fixture_narrative_is_production_valid() -> None:
    """The canonical fixture must pass the live 150-500 word band, not just the model
    char cap — otherwise every happy-path test runs against a brief the real guardrail
    would flag. Locks the fixture against silent regression below the band."""
    result = NarrativeLengthGuardrail(150, 500).validate(
        make_brief_analysis(), make_market_snapshot()
    )
    assert result.severity is GuardrailSeverity.PASS


def test_narrative_length_passes_on_band_boundaries() -> None:
    guardrail = NarrativeLengthGuardrail(150, 500)
    snapshot = make_market_snapshot()
    assert (
        guardrail.validate(
            make_brief_analysis(full_narrative=_narrative_of(150)), snapshot
        ).severity
        is GuardrailSeverity.PASS
    )
    assert (
        guardrail.validate(
            make_brief_analysis(full_narrative=_narrative_of(500)), snapshot
        ).severity
        is GuardrailSeverity.PASS
    )
