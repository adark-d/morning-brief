from __future__ import annotations

from morning_brief.application.composition import Application
from morning_brief.config.settings import ApiSettings


def get_application() -> Application:
    raise NotImplementedError("get_application must be overridden by create_app")


def get_api_settings() -> ApiSettings:
    raise NotImplementedError("get_api_settings must be overridden by create_app")
