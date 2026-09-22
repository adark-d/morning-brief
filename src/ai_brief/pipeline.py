from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import structlog

from ai_brief.analyse import Analyst, NewsAnalyst
from ai_brief.checks import check_brief, check_ids
from ai_brief.deliver import render, send_email
from ai_brief.fetch import enrich, fetch_issue
from ai_brief.models import Brief, BriefError, Run, Story
from brief_core.email import validate_addresses
from brief_core.http import HttpFetchError
from brief_core.logging import log_failure, log_stage
from brief_core.routing import build_task_models
from brief_core.settings import Settings


async def execute(settings: Settings) -> Run:
    """Run one live brief from source retrieval through email delivery."""

    now = datetime.now(UTC)

    async with (
        httpx.AsyncClient(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "ai-brief/0.1"},
        ) as client,
        build_task_models(settings) as models,
    ):
        return await run_pipeline(
            settings,
            client,
            NewsAnalyst(
                models.selection,
                models.explanation,
                topic_count=settings.topic_count,
                selection_max_tokens=settings.selection_max_tokens,
                explanation_max_tokens=settings.explanation_max_tokens,
                retries=settings.agent_retries,
                request_limit=settings.model_request_limit,
            ),
            send_email,
            now,
        )


async def run_pipeline(
    settings: Settings,
    client: httpx.AsyncClient,
    analyst: Analyst,
    send: Callable[[str, Settings], Awaitable[None]],
    now: datetime,
) -> Run:
    """Fetch, analyse, validate, and optionally deliver one brief."""

    logger = structlog.get_logger(__name__)
    run_id = str(structlog.contextvars.get_contextvars().get("run_id") or uuid4())
    started = time.monotonic()
    warnings: list[str] = []
    stage = "configure"
    context = structlog.contextvars.bind_contextvars(run_id=run_id)
    try:
        async with asyncio.timeout(settings.pipeline_timeout_seconds):
            if settings.send_email:
                validate_addresses(settings.sender, settings.recipients)

            # Fetch the latest stories from the configured sources.
            stage = "fetch"
            with log_stage(stage):
                issue = await fetch_issue(
                    client,
                    now,
                    settings.max_age_hours,
                    settings.source_names,
                    settings.fetch_timeout_seconds,
                )
            warnings.extend(issue.warnings)

            # Select the topics most useful for the reader.
            stage = "select"
            with log_stage(stage):
                async with asyncio.timeout(settings.selection_timeout_seconds):
                    selection = await analyst.select(issue.stories, settings.interests)
            check_ids(selection.story_ids, issue.stories, settings.topic_count)
            brief: Brief | None = None
            html = ""
            status: Literal["preview", "success", "skipped"] = "skipped"

            # A quiet day completes normally without generating or sending a brief.
            if selection.story_ids:
                stories_by_id = {story.id: story for story in issue.stories}
                selected: list[Story] = []

                # Enrich selected stories with readable source content.
                stage = "enrich"
                enrichment_deadline = (
                    asyncio.get_running_loop().time() + settings.enrichment_timeout_seconds
                )
                with log_stage(stage):
                    for story_id in selection.story_ids:
                        story = stories_by_id[story_id]
                        try:
                            if asyncio.get_running_loop().time() >= enrichment_deadline:
                                raise TimeoutError("Article enrichment budget exhausted")
                            async with asyncio.timeout_at(enrichment_deadline):
                                story = await enrich(
                                    client,
                                    story,
                                    settings.source_hosts,
                                    settings.source_content_min_chars,
                                    settings.source_content_max_chars,
                                )
                        except (httpx.HTTPError, HttpFetchError, BriefError, TimeoutError) as exc:
                            warnings.append(
                                f"{story.id}: original unavailable ({type(exc).__name__}); {story.source} summary only"
                            )
                            logger.warning(
                                "article_unavailable",
                                story_id=story.id,
                                source=story.source,
                                host=urlsplit(str(story.url)).hostname,
                                error_type=type(exc).__name__,
                            )
                        selected.append(story)
                issue = issue.model_copy(update={"stories": tuple(selected)})

                # Explain the selected stories and validate the result.
                stage = "analyse"
                with log_stage(stage):
                    async with asyncio.timeout(settings.explanation_timeout_seconds):
                        brief = await analyst.explain(issue.stories, settings.interests)
                check_brief(brief, issue.stories, settings.topic_count)

                # Render the email and deliver it when enabled.
                stage = "render"
                with log_stage(stage):
                    html = render(brief, issue)
                stage = "deliver"
                if settings.send_email:
                    with log_stage(stage):
                        async with asyncio.timeout(settings.smtp_timeout_seconds):
                            await send(html, settings)
                status = "success" if settings.send_email else "preview"

            # Return the completed run details for logging and callers.
            run = Run(
                run_id=run_id,
                started_at=now,
                status=status,
                html=html,
                issue=issue,
                brief=brief,
                warnings=tuple(warnings),
                input_tokens=analyst.input_tokens,
                output_tokens=analyst.output_tokens,
            )
            logger.info(
                "run_finished",
                run_id=run_id,
                status=run.status,
                duration_ms=round((time.monotonic() - started) * 1000),
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                warnings=len(warnings),
                topic_count=len(brief.lessons) if brief else 0,
                selection_model=settings.selection_model,
                explanation_model=settings.explanation_model,
            )
            return run
    except Exception as exc:
        log_failure(
            "run_failed",
            exc,
            run_id=run_id,
            stage=stage,
            input_tokens=analyst.input_tokens,
            output_tokens=analyst.output_tokens,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        raise
    finally:
        structlog.contextvars.reset_contextvars(**context)
