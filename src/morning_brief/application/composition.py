from __future__ import annotations

from dataclasses import dataclass

from morning_brief.application.delivery_router import ChannelRouter, ChannelTarget
from morning_brief.application.orchestrator import BriefOrchestrator
from morning_brief.config.settings import Settings
from morning_brief.core.exceptions.errors import InvalidConfigError, MissingConfigError
from morning_brief.core.interfaces.analysis_engine import AnalysisEngine
from morning_brief.core.interfaces.audit_store import AuditStore
from morning_brief.core.interfaces.data_provider import DataProvider
from morning_brief.core.interfaces.delivery_channel import DeliveryChannel
from morning_brief.core.interfaces.guardrail import (
    DeliveryGuardrail,
    InputGuardrail,
    OutputGuardrail,
)
from morning_brief.core.interfaces.report_renderer import ReportRenderer
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
from morning_brief.infrastructure.data.yfinance_data_provider import YFinanceDataProvider
from morning_brief.infrastructure.delivery.email_delivery_channel import EmailDeliveryChannel
from morning_brief.infrastructure.delivery.mock_delivery_channel import MockDeliveryChannel
from morning_brief.infrastructure.llm.anthropic_analysis_engine import AnthropicAnalysisEngine
from morning_brief.infrastructure.llm.mock_analysis_engine import MockAnalysisEngine
from morning_brief.infrastructure.rendering.html_email_renderer import HtmlEmailRenderer
from morning_brief.infrastructure.storage.json_audit_store import JsonAuditStore
from morning_brief.infrastructure.storage.mock_audit_store import MockAuditStore
from morning_brief.prompts import PromptBuilder, PromptRegistry, PromptSelection, PromptValidator


@dataclass(frozen=True)
class Application:
    """The assembled application: the orchestrator and the audit store it writes to.

    Both share one ``AuditStore`` instance so a run triggered through the API is
    immediately retrievable through the read endpoints.
    """

    orchestrator: BriefOrchestrator
    audit_store: AuditStore


def build_application(settings: Settings) -> Application:
    """Assemble the orchestrator and the audit store it shares, from settings."""
    audit_store = _build_audit_store(settings)
    renderer = HtmlEmailRenderer()
    orchestrator = BriefOrchestrator(
        data_provider=_build_data_provider(settings),
        prompt_builder=_build_prompt_builder(settings),
        prompt_validator=PromptValidator(),
        analysis_engine=_build_analysis_engine(settings),
        renderer=renderer,
        router=_build_router(settings, renderer),
        audit_store=audit_store,
        input_guardrails=_build_input_guardrails(settings),
        output_guardrails=_build_output_guardrails(settings),
        delivery_guardrails=_build_delivery_guardrails(settings),
        llm_max_tokens=settings.llm.max_tokens,
        llm_timeout_seconds=settings.llm.timeout_seconds,
    )
    return Application(orchestrator=orchestrator, audit_store=audit_store)


def build_orchestrator(settings: Settings) -> BriefOrchestrator:
    """Assemble just the orchestrator. Convenience over ``build_application``."""
    return build_application(settings).orchestrator


def _build_data_provider(settings: Settings) -> DataProvider:
    name = settings.data.name.lower()
    if name == "yfinance":
        return YFinanceDataProvider(timeout_seconds=settings.data.timeout_seconds)
    if name == "mock":
        return MockDataProvider()
    raise InvalidConfigError(f"Unknown data provider: {settings.data.name!r}")


def _build_analysis_engine(settings: Settings) -> AnalysisEngine:
    provider = settings.llm.provider.lower()
    if provider == "anthropic":
        if settings.llm.anthropic_api_key is None:
            raise MissingConfigError(
                "anthropic provider requires MORNING_BRIEF_LLM__ANTHROPIC_API_KEY"
            )
        return AnthropicAnalysisEngine(
            model=settings.llm.model,
            api_key=settings.llm.anthropic_api_key.get_secret_value(),
            fallback_model=settings.llm.fallback_model,
            max_retries=settings.llm.max_retries,
        )
    if provider == "mock":
        return MockAnalysisEngine(model=settings.llm.model)
    raise InvalidConfigError(f"Unknown LLM provider: {settings.llm.provider!r}")


def _build_audit_store(settings: Settings) -> AuditStore:
    backend = settings.audit.backend.lower()
    if backend == "json":
        return JsonAuditStore(root_path=settings.audit.json_store_path)
    if backend == "mock":
        return MockAuditStore()
    raise InvalidConfigError(f"Unsupported audit backend: {settings.audit.backend!r}")


def _build_router(settings: Settings, renderer: ReportRenderer) -> ChannelRouter:
    recipients = settings.delivery.email.recipients
    targets = tuple(
        ChannelTarget(
            name=name.lower(),
            channel=_build_channel(name.lower(), settings),
            recipients=recipients,
        )
        for name in settings.delivery.channels
    )
    return ChannelRouter(targets=targets, renderers={ReportFormat.HTML_EMAIL: renderer})


def _build_channel(name: str, settings: Settings) -> DeliveryChannel:
    if name == "email":
        email = settings.delivery.email
        return EmailDeliveryChannel(
            host=email.smtp_host,
            sender=email.smtp_from,
            port=email.smtp_port,
            username=email.smtp_username.get_secret_value() if email.smtp_username else None,
            password=email.smtp_password.get_secret_value() if email.smtp_password else None,
            start_tls=email.start_tls,
            timeout_seconds=email.timeout_seconds,
        )
    if name == "mock":
        return MockDeliveryChannel()
    raise InvalidConfigError(f"Unknown delivery channel: {name!r}")


def _build_prompt_builder(settings: Settings) -> PromptBuilder:
    p = settings.prompt
    selection = PromptSelection(
        system_name=p.system_prompt_name,
        system_version=p.system_prompt_version,
        context_name=p.context_template_name,
        context_version=p.context_template_version,
        schema_name=p.output_schema_name,
        schema_version=p.output_schema_version,
        few_shot_name=p.few_shot_examples_name,
        few_shot_version=p.few_shot_examples_version,
    )
    return PromptBuilder(PromptRegistry(), selection)


def _build_input_guardrails(settings: Settings) -> tuple[InputGuardrail, ...]:
    g = settings.guardrails
    return (
        YieldRangeGuardrail(g.yield_min_pct, g.yield_max_pct),
        CompletenessGuardrail(g.min_yield_maturities_required),
        StalenessGuardrail(
            warn_after_hours=g.staleness_warn_after_hours,
            reject_after_hours=g.staleness_reject_after_hours,
        ),
    )


def _build_output_guardrails(settings: Settings) -> tuple[OutputGuardrail, ...]:
    g = settings.guardrails
    return (
        NumericalGroundingGuardrail(),
        ConfidenceGuardrail(g.confidence_warning_threshold),
        NarrativeLengthGuardrail(g.narrative_min_words, g.narrative_max_words),
    )


def _build_delivery_guardrails(settings: Settings) -> tuple[DeliveryGuardrail, ...]:
    # The configured recipients are also the approved whitelist — defence in depth
    # against ever delivering to an address that was not explicitly configured.
    return (
        RecipientWhitelistGuardrail(settings.delivery.email.recipients),
        ReportCompletenessGuardrail(),
        DisclaimerGuardrail(),
    )
