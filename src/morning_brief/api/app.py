"""FastAPI application factory.

``create_app`` is the explicit entry point: it builds (or accepts) the assembled
``Application``, wires the dependency overrides, mounts the routers, and installs
the error handlers that render the shared error envelope. Tests pass a mock
application directly; the deployment entry point calls ``create_app(load_settings())``.
"""

from __future__ import annotations

from importlib.metadata import version as distribution_version

from fastapi import FastAPI

from morning_brief.api import dependencies
from morning_brief.api.errors import register_error_handlers
from morning_brief.api.routes import briefs, health
from morning_brief.application.composition import Application, build_application
from morning_brief.config.settings import Settings

# API identity and docs. The version is a build artifact owned by pyproject.toml,
# read from the installed package metadata so it never drifts (a missing install is
# a deployment fault and is allowed to fail loudly). The prose below is authored
# here — the single place to edit the API's title, summary, description, and tags.
_DISTRIBUTION = "morning-brief"
_TITLE = "morning-brief"
_SUMMARY = "Pre-market fixed-income briefing pipeline."
_DESCRIPTION = (
    "Triggers and retrieves morning-brief pipeline runs. Every run produces an "
    "immutable audit record; failed runs are reported as data (status=failed), not "
    "as HTTP errors. All `/briefs` endpoints require a bearer token."
)
_OPENAPI_TAGS = [
    {"name": "briefs", "description": "Trigger pipeline runs and retrieve audit records."},
    {"name": "health", "description": "Unauthenticated liveness probe."},
]


def create_app(settings: Settings, application: Application | None = None) -> FastAPI:
    """Build the FastAPI app. Pass ``application`` to inject a pre-built one (tests)."""
    application = application if application is not None else build_application(settings)
    app = FastAPI(
        title=_TITLE,
        version=distribution_version(_DISTRIBUTION),
        summary=_SUMMARY,
        description=_DESCRIPTION,
        openapi_tags=_OPENAPI_TAGS,
    )

    app.dependency_overrides[dependencies.get_application] = lambda: application
    app.dependency_overrides[dependencies.get_api_settings] = lambda: settings.api

    app.include_router(health.router)
    app.include_router(briefs.router)
    register_error_handlers(app)
    return app
