from __future__ import annotations

import json
from typing import Any, cast

import pytest
from mangum.types import LambdaContext

from morning_brief.aws_handlers import BriefRunFailedError, _api_app, api_handler, run_handler

# Mangum does not read the context for HTTP responses; a typed None stands in.
_NO_CONTEXT = cast(LambdaContext, None)


def test_run_handler_returns_summary_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORNING_BRIEF_ENVIRONMENT", "test")
    monkeypatch.setenv("MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS", '["desk@example.com"]')

    summary = run_handler({}, None)

    assert summary["status"] == "success"
    assert summary["run_id"]
    assert summary["delivered"] == 1


def test_run_handler_raises_on_failed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORNING_BRIEF_ENVIRONMENT", "test")
    # No recipients -> NoRecipientsConfigured -> FAILED run.
    monkeypatch.setenv("MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS", "[]")

    with pytest.raises(BriefRunFailedError):
        run_handler({}, None)


def test_api_handler_serves_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORNING_BRIEF_ENVIRONMENT", "test")
    _api_app.cache_clear()  # rebuild the cached app under this environment

    event: dict[str, Any] = {
        "version": "2.0",
        "routeKey": "GET /health",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {"host": "test"},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/health",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            }
        },
        "isBase64Encoded": False,
    }

    response = api_handler(event, _NO_CONTEXT)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["status"] == "ok"
    _api_app.cache_clear()
