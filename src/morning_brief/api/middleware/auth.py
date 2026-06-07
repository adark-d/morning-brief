from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from morning_brief.api.dependencies import get_api_settings
from morning_brief.api.errors import AuthNotConfiguredError, UnauthenticatedError
from morning_brief.config.settings import ApiSettings

_bearer_scheme = HTTPBearer(auto_error=False, description="Bearer token issued to the desk")


def require_auth(
    api_settings: Annotated[ApiSettings, Depends(get_api_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> None:
    """Reject the request unless it carries the configured bearer token."""
    token = api_settings.auth_token
    if token is None:
        raise AuthNotConfiguredError("authentication is not configured")
    presented = credentials.credentials if credentials else None
    if presented is None or not secrets.compare_digest(presented, token.get_secret_value()):
        raise UnauthenticatedError("invalid or missing credentials")
