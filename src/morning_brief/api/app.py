from __future__ import annotations

from importlib.metadata import version as distribution_version

from fastapi import FastAPI

from morning_brief.api import dependencies
from morning_brief.api.errors import register_error_handlers
from morning_brief.api.routes import briefs, health
from morning_brief.application.composition import Application, build_application
from morning_brief.config.settings import Settings

_DISTRIBUTION = "morning-brief"
_TITLE = "Morning Brief API"
_SUMMARY = "Trigger and retrieve pre-market fixed-income briefing runs."
_DESCRIPTION = """\
The **Morning Brief API** drives the morning-brief pipeline — an automated workflow
that fetches pre-market market data, generates a fixed-income desk briefing with an
LLM, validates it through three tiers of guardrails, delivers it to recipients, and
records an immutable audit trail of every run.

Use this API to **trigger** a run on demand and to **retrieve** the audit records of
past runs.

## Authentication

Every `/briefs` endpoint requires a **bearer token**, sent as
`Authorization: Bearer <token>`. On this page, click **Authorize** and paste the token
to try the protected endpoints. The `/health` endpoint is open.

Authentication is **fail-closed**: if the server is started without a configured token,
every protected route returns `503 Service Unavailable` rather than serving an
unauthenticated API.

## Conventions

- **Runs are data, not transactions.** A run whose pipeline fails is still a successful
  API call — it returns `200 OK` with `status: "failed"`. HTTP error codes are reserved
  for problems with the *request* itself (authentication, validation, not-found).
- **Every run is audited.** Each run produces an immutable record, retrievable later by
  id or by date.
- **Responses are PII-free.** Audit views expose the delivery channel and status but
  never recipient addresses.
- **Dates are UTC.** All timestamps and date filters use the UTC calendar.

## Error format

Every error response shares one envelope: a stable, machine-readable `code` and a
human-readable `detail`.

```json
{ "code": "not_found", "detail": "run 'a1b2c3' not found" }
```
"""
_OPENAPI_TAGS = [
    {
        "name": "Briefs",
        "description": (
            "Trigger pipeline runs and retrieve their immutable audit records. "
            "All endpoints in this group require a bearer token."
        ),
    },
    {
        "name": "Health",
        "description": "Unauthenticated liveness probe for load balancers and uptime monitors.",
    },
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
