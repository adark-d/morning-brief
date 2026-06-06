"""End-to-end pipeline integration tests.

These wire the *real* internal pipeline — the full guardrail set, the prompt layer,
the HTML renderer, the channel router, and a real on-disk ``JsonAuditStore`` — and
mock only the network edges (data, LLM, delivery), configured to drive failure and
degradation paths. Each test asserts both the returned outcome and the record
retrieved back from the store, so it exercises the seams between layers and the
audit serialization round-trip, not just a single component's return value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from morning_brief.application.delivery_router import ChannelRouter, ChannelTarget
from morning_brief.application.orchestrator import BriefOrchestrator
from morning_brief.core.interfaces.guardrail import OutputGuardrail
from morning_brief.core.models.audit import RunStatus
from morning_brief.core.models.report import ReportFormat
from morning_brief.guardrails.delivery import (
    DisclaimerGuardrail,
    RecipientWhitelistGuardrail,
    ReportCompletenessGuardrail,
)
from morning_brief.guardrails.input import (
    CompletenessGuardrail,
    StalenessGuardrail,
    YieldRangeGuardrail,
)
from morning_brief.guardrails.output import (
    ConfidenceGuardrail,
    NarrativeLengthGuardrail,
    NumericalGroundingGuardrail,
)
from morning_brief.infrastructure.data.mock_data_provider import MockDataProvider
from morning_brief.infrastructure.delivery.mock_delivery_channel import MockDeliveryChannel
from morning_brief.infrastructure.llm.mock_analysis_engine import MockAnalysisEngine
from morning_brief.infrastructure.rendering.html_email_renderer import HtmlEmailRenderer
from morning_brief.infrastructure.storage.json_audit_store import JsonAuditStore
from morning_brief.prompts import PromptBuilder, PromptRegistry, PromptValidator


def _build(
    tmp_path: Path,
    *,
    data_provider: MockDataProvider | None = None,
    analysis_engine: MockAnalysisEngine | None = None,
    channel: MockDeliveryChannel | None = None,
    recipients: tuple[str, ...] = ("desk@firm.com",),
    output_guardrails: tuple[OutputGuardrail, ...] | None = None,
) -> tuple[BriefOrchestrator, JsonAuditStore]:
    """Wire the real internal pipeline with mock edges and a real JSON audit store."""
    renderer = HtmlEmailRenderer()
    channel = channel or MockDeliveryChannel()
    store = JsonAuditStore(root_path=tmp_path / "audit")
    router = ChannelRouter(
        targets=(ChannelTarget(name="email", channel=channel, recipients=recipients),),
        renderers={ReportFormat.HTML_EMAIL: renderer},
    )
    orchestrator = BriefOrchestrator(
        data_provider=data_provider or MockDataProvider(),
        prompt_builder=PromptBuilder(PromptRegistry()),
        prompt_validator=PromptValidator(),
        analysis_engine=analysis_engine or MockAnalysisEngine(),
        renderer=renderer,
        router=router,
        audit_store=store,
        input_guardrails=(
            YieldRangeGuardrail(0.1, 20.0),
            CompletenessGuardrail(3),
            StalenessGuardrail(warn_after_hours=6.0, reject_after_hours=24.0),
        ),
        output_guardrails=output_guardrails
        or (
            NumericalGroundingGuardrail(),
            ConfidenceGuardrail(0.6),
            NarrativeLengthGuardrail(150, 500),
        ),
        delivery_guardrails=(
            RecipientWhitelistGuardrail(recipients),
            ReportCompletenessGuardrail(),
            DisclaimerGuardrail(),
        ),
    )
    return orchestrator, store


@pytest.mark.asyncio
async def test_full_run_succeeds_and_persists_to_real_store(tmp_path: Path) -> None:
    orchestrator, store = _build(tmp_path)
    run = await orchestrator.run()

    assert run.status is RunStatus.SUCCESS
    assert run.errors == ()  # clean pass through the full real guardrail set
    assert run.delivered_count == 1

    # The record survives the JSON serialization round-trip and is retrievable.
    fetched = await store.get_by_id(run.run_id)
    assert fetched is not None
    assert fetched.run_id == run.run_id
    assert fetched.analysis is not None
    assert fetched.status is RunStatus.SUCCESS


@pytest.mark.asyncio
async def test_partial_data_outage_degrades_but_still_delivers(tmp_path: Path) -> None:
    orchestrator, store = _build(tmp_path, data_provider=MockDataProvider(fail_fx=True))
    run = await orchestrator.run()

    # Yields are present, so the brief still goes out; the FX outage is recorded.
    assert run.status is RunStatus.SUCCESS
    assert run.snapshot is not None
    assert run.snapshot.fx == {}
    assert run.snapshot.data_quality.sources_failed

    fetched = await store.get_by_id(run.run_id)
    assert fetched is not None
    assert fetched.snapshot is not None
    assert fetched.snapshot.data_quality.sources_failed  # persisted faithfully


@pytest.mark.asyncio
async def test_missing_yields_aborts_before_llm_and_records_failed(tmp_path: Path) -> None:
    orchestrator, store = _build(tmp_path, data_provider=MockDataProvider(fail_yields=True))
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.analysis is None  # the LLM was never reached
    assert any(e.component == "guardrail.input" for e in run.errors)

    fetched = await store.get_by_id(run.run_id)
    assert fetched is not None
    assert fetched.status is RunStatus.FAILED


@pytest.mark.asyncio
async def test_analysis_failure_records_failed_run(tmp_path: Path) -> None:
    orchestrator, store = _build(
        tmp_path, analysis_engine=MockAnalysisEngine(fail_unavailable=True)
    )
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.analysis is None
    assert any(e.component == "analysis_engine" for e in run.errors)
    assert (await store.get_by_id(run.run_id)) is not None


@pytest.mark.asyncio
async def test_partial_delivery_records_partial_status(tmp_path: Path) -> None:
    channel = MockDeliveryChannel(fail_recipients=("b@firm.com",))
    orchestrator, store = _build(tmp_path, channel=channel, recipients=("a@firm.com", "b@firm.com"))
    run = await orchestrator.run()

    assert run.status is RunStatus.PARTIAL
    assert run.delivered_count == 1
    assert run.total_recipients == 2

    fetched = await store.get_by_id(run.run_id)
    assert fetched is not None
    assert fetched.delivered_count == 1


@pytest.mark.asyncio
async def test_output_warning_is_recorded_without_blocking_delivery(tmp_path: Path) -> None:
    # The mock analysis has confidence 0.82; a 0.9 threshold makes it WARN — the run
    # must still deliver, with the warning attached to the persisted record.
    orchestrator, store = _build(tmp_path, output_guardrails=(ConfidenceGuardrail(0.9),))
    run = await orchestrator.run()

    assert run.status is RunStatus.SUCCESS
    assert run.delivered_count == 1
    assert any(e.component == "guardrail.output" and e.severity == "warning" for e in run.errors)

    fetched = await store.get_by_id(run.run_id)
    assert fetched is not None
    assert any(e.severity == "warning" for e in fetched.errors)
