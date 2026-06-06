"""The API's error subsystem, in one place.

Everything about how the API reports failure lives here so the contract is easy to
read and extend: the machine-readable code enum, the response envelope, the typed
exceptions the routes raise, the handlers that render them, and a helper that
derives each endpoint's OpenAPI error docs from those same exception classes — so a
status code and its description are declared exactly once.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import ClassVar

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from morning_brief.core.exceptions.errors import BriefSystemError

logger = structlog.get_logger(__name__)


# ============================================
# Error contract
# ============================================
class ApiErrorCode(StrEnum):
    """Stable, machine-readable error identifiers returned in every error body."""

    NOT_FOUND = "not_found"
    UNAUTHENTICATED = "unauthenticated"
    AUTH_NOT_CONFIGURED = "auth_not_configured"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"


class ErrorResponse(BaseModel):
    """Uniform body for every non-2xx response; clients branch on ``code``."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"code": "not_found", "detail": "run 'abc123' not found"}}
    )

    code: ApiErrorCode = Field(description="Stable, machine-readable error identifier")
    detail: str = Field(description="Human-readable explanation of the error")


# ============================================
# Typed exceptions the routes raise
# ============================================
class ApiError(Exception):
    """An error that maps to a deliberate HTTP response.

    Subclasses set ``status_code`` and ``code``; the docstring's first line is the
    OpenAPI description. ``detail`` is the per-instance human-readable message.
    """

    status_code: ClassVar[HTTPStatus] = HTTPStatus.INTERNAL_SERVER_ERROR
    code: ClassVar[ApiErrorCode] = ApiErrorCode.INTERNAL_ERROR
    headers: ClassVar[Mapping[str, str] | None] = None

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(ApiError):
    """No matching resource exists"""

    status_code = HTTPStatus.NOT_FOUND
    code = ApiErrorCode.NOT_FOUND


class UnauthenticatedError(ApiError):
    """Missing or invalid credentials"""

    status_code = HTTPStatus.UNAUTHORIZED
    code = ApiErrorCode.UNAUTHENTICATED
    headers: ClassVar[Mapping[str, str] | None] = {"WWW-Authenticate": "Bearer"}


class AuthNotConfiguredError(ApiError):
    """Authentication is not configured"""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = ApiErrorCode.AUTH_NOT_CONFIGURED


# ============================================
# OpenAPI documentation
# ============================================
def error_responses(*errors: type[ApiError]) -> dict[int | str, dict[str, object]]:
    """Derive an OpenAPI ``responses`` map from exception classes.

    The status code comes from the class and the description from its docstring, so
    routes document their failure modes by naming the exceptions they raise rather
    than restating status codes and prose.
    """
    return {
        int(error.status_code): {
            "model": ErrorResponse,
            "description": (error.__doc__ or "").strip(),
        }
        for error in errors
    }


# ============================================
# Handlers
# ============================================
def register_error_handlers(app: FastAPI) -> None:
    """Install the handlers that render every error as an ``ErrorResponse``."""
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(BriefSystemError, _handle_domain_error)
    app.add_exception_handler(Exception, _handle_unexpected)


def _render(
    status_code: HTTPStatus,
    code: ApiErrorCode,
    detail: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, detail=detail)
    return JSONResponse(
        status_code=int(status_code),
        content=body.model_dump(),
        headers=dict(headers) if headers else None,
    )


async def _handle_api_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):  # registered only for ApiError; defensive
        raise exc  # pragma: no cover
    return _render(exc.status_code, exc.code, exc.detail, exc.headers)


async def _handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc  # pragma: no cover
    detail = "; ".join(
        f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return _render(
        HTTPStatus.UNPROCESSABLE_ENTITY, ApiErrorCode.VALIDATION_ERROR, detail or "invalid request"
    )


async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    return _log_and_render_500("api_domain_error", request, exc)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    return _log_and_render_500("api_unhandled_error", request, exc)


def _log_and_render_500(event: str, request: Request, exc: Exception) -> JSONResponse:
    # Log the specifics server-side; return a generic body so internals never leak.
    logger.error(
        event,
        component="api",
        severity="error",
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        error=str(exc),
    )
    return _render(
        HTTPStatus.INTERNAL_SERVER_ERROR, ApiErrorCode.INTERNAL_ERROR, "an internal error occurred"
    )
