from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NoReturn

import structlog

from morning_brief.application.delivery_router import ChannelRouter
from morning_brief.core.exceptions.errors import (
    AnalysisError,
    DataFetchError,
    PromptError,
    RenderError,
)
from morning_brief.core.interfaces.analysis_engine import AnalysisEngine
from morning_brief.core.interfaces.audit_store import AuditStore
from morning_brief.core.interfaces.base import HealthState
from morning_brief.core.interfaces.data_provider import DataProvider
from morning_brief.core.interfaces.guardrail import (
    DeliveryGuardrail,
    GuardrailResult,
    GuardrailSeverity,
    InputGuardrail,
    OutputGuardrail,
)
from morning_brief.core.interfaces.report_renderer import ReportRenderer
from morning_brief.core.models.analysis import BriefAnalysis
from morning_brief.core.models.audit import (
    BriefError,
    BriefRun,
    DeliveryResult,
    DeliveryStatus,
    ErrorSeverity,
    RunStatus,
)
from morning_brief.core.models.market_data import MarketSnapshot
from morning_brief.guardrails.runner import run_delivery, run_input, run_output
from morning_brief.observability.timing import log_duration
from morning_brief.prompts import PromptBuilder, PromptValidator

logger = structlog.get_logger(__name__)

_GUARDRAIL_TO_ERROR: dict[GuardrailSeverity, ErrorSeverity] = {
    GuardrailSeverity.WARNING: ErrorSeverity.WARNING,
    GuardrailSeverity.CRITICAL: ErrorSeverity.CRITICAL,
}


class _PipelineAbortedError(Exception):
    """Internal sentinel to unwind a linear pipeline to the finaliser.

    Never escapes ``run()``. The reason is recorded on the run state as a
    BriefError before this is raised; it only short-circuits the remaining steps.
    """


@dataclass
class _RunState:
    """Mutable accumulator for a single run. Finalised into an immutable BriefRun."""

    run_id: str
    triggered_at: datetime
    snapshot: MarketSnapshot | None = None
    analysis: BriefAnalysis | None = None
    delivery_results: tuple[DeliveryResult, ...] = ()
    errors: list[BriefError] = field(default_factory=list[BriefError])
    aborted: bool = False


class BriefOrchestrator:
    """Runs one morning-brief pipeline execution and returns its audit record."""

    def __init__(
        self,
        *,
        data_provider: DataProvider,
        prompt_builder: PromptBuilder,
        prompt_validator: PromptValidator,
        analysis_engine: AnalysisEngine,
        renderer: ReportRenderer,
        router: ChannelRouter,
        audit_store: AuditStore,
        input_guardrails: tuple[InputGuardrail, ...],
        output_guardrails: tuple[OutputGuardrail, ...],
        delivery_guardrails: tuple[DeliveryGuardrail, ...],
        llm_max_tokens: int = 2000,
        llm_timeout_seconds: float = 30.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._data_provider = data_provider
        self._prompt_builder = prompt_builder
        self._prompt_validator = prompt_validator
        self._analysis_engine = analysis_engine
        self._renderer = renderer
        self._router = router
        self._audit_store = audit_store
        self._input_guardrails = input_guardrails
        self._output_guardrails = output_guardrails
        self._delivery_guardrails = delivery_guardrails
        self._llm_max_tokens = llm_max_tokens
        self._llm_timeout_seconds = llm_timeout_seconds
        self._now = now or (lambda: datetime.now(UTC))

    async def run(self) -> BriefRun:
        """Execute the pipeline end-to-end. Always returns (and records) a BriefRun."""
        state = _RunState(run_id=str(uuid.uuid4()), triggered_at=self._now())
        logger.info("run_started", run_id=state.run_id, component="orchestrator", severity="info")
        try:
            await self._execute(state)
        except _PipelineAbortedError:
            pass  # an expected abort: its reason is already on state.errors
        except Exception as exc:  # safety net: an unexpected, undocumented failure
            # No component is allowed to break the "every run is auditable" guarantee.
            # Record it as a CRITICAL error and still finalise + persist the run below.
            self._record_unexpected(state, exc)
        run = self._finalise(state)
        await self._record(run)
        logger.info(
            "run_finished",
            run_id=run.run_id,
            component="orchestrator",
            severity="info",
            status=run.status,
            delivered=run.delivered_count,
            recipients=run.total_recipients,
            errors=len(run.errors),
            duration_seconds=run.duration_seconds,
        )
        return run

    async def _execute(self, state: _RunState) -> None:
        with self._timed(state, "preflight"):
            await self._preflight(state)
        with self._timed(state, "fetch_data"):
            snapshot = await self._fetch_snapshot(state)
        state.snapshot = snapshot
        with self._timed(state, "input_guardrails"):
            self._run_input_guardrails(state, snapshot)
        with self._timed(state, "build_prompt"):
            prompt, version = self._build_prompt(state, snapshot)
        with self._timed(state, "analysis"):
            analysis = await self._analyse(state, snapshot, prompt, version)
        state.analysis = analysis
        with self._timed(state, "output_guardrails"):
            self._run_output_guardrails(state, snapshot, analysis)
        with self._timed(state, "delivery"):
            await self._deliver(state, analysis)

    def _timed(self, state: _RunState, stage: str) -> AbstractContextManager[None]:
        """Time a pipeline stage, emitting one ``stage_timing`` log line per stage.

        The event name is deliberately outcome-neutral: a stage that aborts still
        logged its real duration, and its failure is recorded separately.
        """
        return log_duration(
            logger,
            "stage_timing",
            run_id=state.run_id,
            component="orchestrator",
            severity="info",
            stage=stage,
        )

    async def _preflight(self, state: _RunState) -> None:
        health = await self._data_provider.health_check()
        if health.state is HealthState.UNHEALTHY:
            self._abort(
                state,
                component="data_provider",
                error_type="HealthCheckFailed",
                message=health.message or "data provider is unhealthy",
            )
        if health.state is HealthState.DEGRADED:
            self._emit(
                state,
                component="data_provider",
                error_type="HealthDegraded",
                message=health.message or "data provider is degraded",
                severity=ErrorSeverity.WARNING,
            )

    async def _fetch_snapshot(self, state: _RunState) -> MarketSnapshot:
        try:
            return await self._data_provider.fetch_snapshot()
        except DataFetchError as exc:
            self._abort_from_exception(state, "data_provider", exc)

    def _run_input_guardrails(self, state: _RunState, snapshot: MarketSnapshot) -> None:
        report = run_input(self._input_guardrails, snapshot)
        self._record_findings(state, tier="input", findings=report.warnings)
        if report.should_abort:
            self._record_findings(state, tier="input", findings=report.critical)
            self._abort_after_findings(state)

    def _build_prompt(self, state: _RunState, snapshot: MarketSnapshot) -> tuple[str, str]:
        try:
            assembled = self._prompt_builder.build(snapshot)
            self._prompt_validator.validate(assembled)
        except PromptError as exc:
            self._abort_from_exception(state, "prompt", exc)
        return assembled.full_prompt, assembled.version

    async def _analyse(
        self, state: _RunState, snapshot: MarketSnapshot, prompt: str, version: str
    ) -> BriefAnalysis:
        try:
            return await self._analysis_engine.analyse(
                snapshot,
                prompt,
                prompt_version=version,
                max_tokens=self._llm_max_tokens,
                timeout_seconds=self._llm_timeout_seconds,
            )
        except AnalysisError as exc:
            self._abort_from_exception(state, "analysis_engine", exc)

    def _run_output_guardrails(
        self, state: _RunState, snapshot: MarketSnapshot, analysis: BriefAnalysis
    ) -> None:
        report = run_output(self._output_guardrails, analysis, snapshot)
        self._record_findings(state, tier="output", findings=report.warnings)
        if report.should_abort:
            self._record_findings(state, tier="output", findings=report.critical)
            self._abort_after_findings(state)

    async def _deliver(self, state: _RunState, analysis: BriefAnalysis) -> None:
        recipients = self._router.all_recipients
        if not recipients:
            self._abort(
                state,
                component="delivery",
                error_type="NoRecipientsConfigured",
                message="no recipients configured; nothing to deliver",
            )

        try:
            report = self._renderer.render(analysis)
        except RenderError as exc:
            self._abort_from_exception(state, "renderer", exc)

        verdict = run_delivery(self._delivery_guardrails, report, recipients)
        self._record_findings(state, tier="delivery", findings=verdict.warnings)
        if verdict.should_abort:
            self._record_findings(state, tier="delivery", findings=verdict.critical)
            state.delivery_results = self._reject_all(recipients)
            self._abort_after_findings(state)

        state.delivery_results = await self._router.deliver(analysis)

    def _finalise(self, state: _RunState) -> BriefRun:
        completed_at = self._now()
        return BriefRun(
            run_id=state.run_id,
            triggered_at=state.triggered_at,
            completed_at=completed_at,
            status=self._status(state),
            snapshot=state.snapshot,
            analysis=state.analysis,
            delivery_results=state.delivery_results,
            errors=tuple(state.errors),
            duration_seconds=(completed_at - state.triggered_at).total_seconds(),
        )

    @staticmethod
    def _status(state: _RunState) -> RunStatus:
        if state.aborted or state.analysis is None:
            return RunStatus.FAILED
        total = len(state.delivery_results)
        delivered = sum(1 for r in state.delivery_results if r.status is DeliveryStatus.DELIVERED)
        if total == 0 or delivered == 0:
            return RunStatus.FAILED
        if delivered == total:
            return RunStatus.SUCCESS
        return RunStatus.PARTIAL

    async def _record(self, run: BriefRun) -> None:
        try:
            await self._audit_store.record(run)
        except Exception as exc:  # audit must never crash an already-complete run
            # The run is already complete; failing to persist is logged loudly but
            # cannot change the outcome the caller receives.
            logger.critical(
                "audit_record_failed",
                run_id=run.run_id,
                component="audit_store",
                severity="critical",
                error_type=type(exc).__name__,
                error=str(exc),
            )

    def _reject_all(self, recipients: tuple[str, ...]) -> tuple[DeliveryResult, ...]:
        now = self._now()
        return tuple(
            DeliveryResult(
                recipient=recipient,
                channel="*",
                status=DeliveryStatus.REJECTED,
                attempted_at=now,
                completed_at=now,
                error_message="blocked by delivery guardrail",
            )
            for recipient in recipients
        )

    def _emit(
        self,
        state: _RunState,
        *,
        component: str,
        error_type: str,
        message: str,
        severity: ErrorSeverity,
        context: dict[str, str] | None = None,
    ) -> None:
        """Append a BriefError to the run and log it at the matching level."""
        state.errors.append(
            BriefError(
                component=component,
                error_type=error_type,
                message=message,
                severity=severity,
                occurred_at=self._now(),
                context=context or {},
            )
        )
        log = logger.critical if severity is ErrorSeverity.CRITICAL else logger.warning
        log(
            error_type,
            run_id=state.run_id,
            component=component,
            severity=severity.value,
            message=message,
        )

    def _record_findings(
        self, state: _RunState, *, tier: str, findings: tuple[GuardrailResult, ...]
    ) -> None:
        for finding in findings:
            self._emit(
                state,
                component=f"guardrail.{tier}",
                error_type=finding.rule_name,
                message=finding.message or finding.rule_name,
                severity=_GUARDRAIL_TO_ERROR[finding.severity],
                context=dict(finding.context or {}),
            )

    def _abort(
        self, state: _RunState, *, component: str, error_type: str, message: str
    ) -> NoReturn:
        self._emit(
            state,
            component=component,
            error_type=error_type,
            message=message,
            severity=ErrorSeverity.CRITICAL,
        )
        self._abort_after_findings(state)

    def _abort_from_exception(self, state: _RunState, component: str, exc: Exception) -> NoReturn:
        self._abort(state, component=component, error_type=type(exc).__name__, message=str(exc))

    def _record_unexpected(self, state: _RunState, exc: Exception) -> None:
        """Record an undocumented failure so the run is still auditable.

        The typed ``_abort_*`` paths handle the failures each component promises to
        raise; this is the backstop for anything else (a contract violation, a
        leaked third-party error) so it can never skip the audit record.
        """
        state.aborted = True
        self._emit(
            state,
            component="orchestrator",
            error_type=type(exc).__name__,
            message=str(exc) or type(exc).__name__,
            severity=ErrorSeverity.CRITICAL,
        )

    @staticmethod
    def _abort_after_findings(state: _RunState) -> NoReturn:
        state.aborted = True
        raise _PipelineAbortedError
