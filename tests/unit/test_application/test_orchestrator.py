from __future__ import annotations

from datetime import UTC, datetime

import pytest

from morning_brief.application.delivery_router import ChannelRouter, ChannelTarget
from morning_brief.application.orchestrator import BriefOrchestrator
from morning_brief.core.exceptions.errors import IncompletePromptError, StorageError
from morning_brief.core.interfaces.base import HealthState, HealthStatus
from morning_brief.core.interfaces.guardrail import (
    DeliveryGuardrail,
    GuardrailResult,
    GuardrailSeverity,
    InputGuardrail,
    OutputGuardrail,
)
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.audit import BriefRun, DeliveryStatus, RunStatus
from morning_brief.core.models.market_data import MarketSnapshot
from morning_brief.core.models.report import ReportFormat
from morning_brief.guardrails.delivery import RecipientWhitelistGuardrail
from morning_brief.guardrails.input import CompletenessGuardrail
from morning_brief.infrastructure.data.mock_data_provider import MockDataProvider
from morning_brief.infrastructure.delivery.mock_delivery_channel import MockDeliveryChannel
from morning_brief.infrastructure.llm.mock_analysis_engine import MockAnalysisEngine
from morning_brief.infrastructure.rendering.mock_renderer import MockRenderer
from morning_brief.infrastructure.storage.mock_audit_store import MockAuditStore
from morning_brief.prompts import (
    AssembledPrompt,
    PromptBuilder,
    PromptRegistry,
    PromptValidator,
)

_NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


class _CriticalOutputGuardrail(OutputGuardrail):
    """An output rule that always fires CRITICAL — to exercise the abort path."""

    @property
    def name(self) -> str:
        return "always_critical"

    def validate(self, analysis: BriefAnalysis, source_snapshot: MarketSnapshot) -> GuardrailResult:
        _ = (analysis, source_snapshot)
        return GuardrailResult(
            rule_name=self.name,
            severity=GuardrailSeverity.CRITICAL,
            passed=False,
            message="forced critical",
        )


class _DegradedProvider(MockDataProvider):
    """Healthy enough to run, but reports DEGRADED — exercises the warn-and-continue path."""

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.DEGRADED, component="mock", message="degraded feed")


class _FailingAuditStore(MockAuditStore):
    """Raises on record — the run must still return its computed outcome."""

    async def record(self, run: BriefRun) -> None:
        _ = run
        raise StorageError("simulated audit backend outage")


class _RogueProvider(MockDataProvider):
    """Raises an undocumented (non-DataFetchError) exception — exercises the safety net."""

    async def fetch_snapshot(self) -> MarketSnapshot:
        raise RuntimeError("contract violation: provider raised outside its hierarchy")


class _FailingPromptBuilder(PromptBuilder):
    """Raises during build — exercises the prompt-failure abort path."""

    def build(self, snapshot: MarketSnapshot) -> AssembledPrompt:
        _ = snapshot
        raise IncompletePromptError("simulated missing template")


def _make(
    *,
    data_provider: MockDataProvider | None = None,
    analysis_engine: MockAnalysisEngine | None = None,
    renderer: MockRenderer | None = None,
    channel: MockDeliveryChannel | None = None,
    recipients: tuple[str, ...] = ("desk@firm.com",),
    prompt_builder: PromptBuilder | None = None,
    audit_store: MockAuditStore | None = None,
    input_guardrails: tuple[InputGuardrail, ...] = (),
    output_guardrails: tuple[OutputGuardrail, ...] = (),
    delivery_guardrails: tuple[DeliveryGuardrail, ...] = (),
) -> tuple[BriefOrchestrator, MockAuditStore]:
    renderer = renderer or MockRenderer()
    channel = channel or MockDeliveryChannel()
    audit_store = audit_store or MockAuditStore()
    router = ChannelRouter(
        targets=(ChannelTarget(name="mock", channel=channel, recipients=recipients),),
        renderers={ReportFormat.HTML_EMAIL: renderer},
    )
    orchestrator = BriefOrchestrator(
        data_provider=data_provider or MockDataProvider(),
        prompt_builder=prompt_builder or PromptBuilder(PromptRegistry()),
        prompt_validator=PromptValidator(),
        analysis_engine=analysis_engine or MockAnalysisEngine(),
        renderer=renderer,
        router=router,
        audit_store=audit_store,
        input_guardrails=input_guardrails,
        output_guardrails=output_guardrails,
        delivery_guardrails=delivery_guardrails,
        now=lambda: _NOW,
    )
    return orchestrator, audit_store


@pytest.mark.asyncio
async def test_run_succeeds_and_records_audit() -> None:
    orchestrator, audit_store = _make()
    run = await orchestrator.run()

    assert run.status is RunStatus.SUCCESS
    assert run.snapshot is not None
    assert run.analysis is not None
    assert run.delivered_count == 1
    assert run.duration_seconds == 0.0  # fixed clock
    assert audit_store.run_count == 1
    assert (await audit_store.get_by_id(run.run_id)) is not None


@pytest.mark.asyncio
async def test_run_records_audit_even_on_failure() -> None:
    orchestrator, audit_store = _make(data_provider=MockDataProvider(unhealthy=True))
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert audit_store.run_count == 1


@pytest.mark.asyncio
async def test_unhealthy_provider_aborts_before_analysis() -> None:
    orchestrator, _ = _make(data_provider=MockDataProvider(unhealthy=True))
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.analysis is None
    assert any(e.error_type == "HealthCheckFailed" for e in run.errors)


@pytest.mark.asyncio
async def test_total_data_outage_aborts_with_recorded_error() -> None:
    orchestrator, _ = _make(data_provider=MockDataProvider(fail_all=True))
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.snapshot is None
    assert any(e.component == "data_provider" for e in run.errors)


@pytest.mark.asyncio
async def test_input_critical_aborts_before_llm() -> None:
    # No yields -> CompletenessGuardrail returns CRITICAL.
    orchestrator, _ = _make(
        data_provider=MockDataProvider(fail_yields=True),
        input_guardrails=(CompletenessGuardrail(3),),
    )
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.analysis is None
    assert any(e.component == "guardrail.input" for e in run.errors)


@pytest.mark.asyncio
async def test_input_warning_is_recorded_but_pipeline_continues() -> None:
    # The mock snapshot has 4 maturities; requiring 5 makes completeness WARN
    # (not abort). The run still completes and the warning is attached.
    orchestrator, _ = _make(input_guardrails=(CompletenessGuardrail(5),))
    run = await orchestrator.run()

    assert run.status is RunStatus.SUCCESS
    assert any(e.component == "guardrail.input" and e.severity == "warning" for e in run.errors)


@pytest.mark.asyncio
async def test_analysis_failure_aborts() -> None:
    orchestrator, _ = _make(analysis_engine=MockAnalysisEngine(fail_unavailable=True))
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.analysis is None
    assert any(e.component == "analysis_engine" for e in run.errors)


@pytest.mark.asyncio
async def test_output_critical_aborts_and_skips_delivery() -> None:
    channel = MockDeliveryChannel()
    orchestrator, _ = _make(
        channel=channel,
        output_guardrails=(_CriticalOutputGuardrail(),),
    )
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.analysis is not None  # analysis was produced
    assert run.delivery_results == ()  # but nothing was delivered
    assert channel.delivered == []


@pytest.mark.asyncio
async def test_delivery_guardrail_critical_rejects_all_recipients() -> None:
    channel = MockDeliveryChannel()
    orchestrator, _ = _make(
        channel=channel,
        recipients=("desk@firm.com",),
        delivery_guardrails=(RecipientWhitelistGuardrail(set()),),  # nobody allowed
    )
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert all(r.status is DeliveryStatus.REJECTED for r in run.delivery_results)
    assert channel.delivered == []  # the router was never called


@pytest.mark.asyncio
async def test_no_recipients_configured_fails() -> None:
    orchestrator, _ = _make(recipients=())
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert any(e.error_type == "NoRecipientsConfigured" for e in run.errors)


@pytest.mark.asyncio
async def test_partial_delivery_is_partial_status() -> None:
    channel = MockDeliveryChannel(fail_recipients=("b@firm.com",))
    orchestrator, _ = _make(channel=channel, recipients=("a@firm.com", "b@firm.com"))
    run = await orchestrator.run()

    assert run.status is RunStatus.PARTIAL
    assert run.delivered_count == 1
    assert run.total_recipients == 2


@pytest.mark.asyncio
async def test_all_delivery_failures_is_failed_status() -> None:
    channel = MockDeliveryChannel(fail=True)
    orchestrator, _ = _make(channel=channel, recipients=("a@firm.com", "b@firm.com"))
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.delivered_count == 0


@pytest.mark.asyncio
async def test_render_failure_aborts() -> None:
    orchestrator, _ = _make(renderer=MockRenderer(fail=True))
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert any(e.component == "renderer" for e in run.errors)


@pytest.mark.asyncio
async def test_degraded_provider_warns_but_completes() -> None:
    orchestrator, _ = _make(data_provider=_DegradedProvider())
    run = await orchestrator.run()

    assert run.status is RunStatus.SUCCESS
    assert any(e.error_type == "HealthDegraded" and e.severity == "warning" for e in run.errors)


@pytest.mark.asyncio
async def test_prompt_failure_aborts() -> None:
    orchestrator, _ = _make(prompt_builder=_FailingPromptBuilder(PromptRegistry()))
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert run.analysis is None
    assert any(e.component == "prompt" for e in run.errors)


@pytest.mark.asyncio
async def test_audit_persistence_failure_does_not_crash_the_run() -> None:
    # The run is already complete; a failing audit store is logged, not raised.
    orchestrator, _ = _make(audit_store=_FailingAuditStore())
    run = await orchestrator.run()

    assert run.status is RunStatus.SUCCESS  # delivery succeeded; persistence failed silently


@pytest.mark.asyncio
async def test_undocumented_exception_still_records_failed_run() -> None:
    # A component breaking its contract must not break the "every run is auditable"
    # guarantee: the run is caught, recorded FAILED, and persisted.
    orchestrator, audit_store = _make(data_provider=_RogueProvider())
    run = await orchestrator.run()

    assert run.status is RunStatus.FAILED
    assert audit_store.run_count == 1
    assert any(e.component == "orchestrator" and e.error_type == "RuntimeError" for e in run.errors)
