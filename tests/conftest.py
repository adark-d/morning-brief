from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic_ai import models


@pytest.fixture(autouse=True)
def isolate_runtime_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tests configure their own settings and never call a live model."""
    for name in tuple(os.environ):
        if name.startswith("MORNING_BRIEF_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
