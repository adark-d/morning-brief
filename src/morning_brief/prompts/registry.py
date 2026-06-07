from __future__ import annotations

from pathlib import Path
from typing import Final, cast

import structlog
import yaml

from morning_brief.core.exceptions.errors import PromptError, PromptNotFoundError
from morning_brief.prompts.models import (
    ContextTemplate,
    FewShotExamples,
    OutputSchema,
    SystemPrompt,
)

logger = structlog.get_logger(__name__)

_SUBDIRS: Final[dict[str, str]] = {
    "system": "system",
    "context": "context",
    "output_schema": "output_schemas",
    "few_shot": "few_shot",
}


class PromptRegistry:
    """Loads prompt components from the bundled templates directory."""

    def __init__(self, templates_root: Path | None = None) -> None:
        self._root = templates_root or (Path(__file__).resolve().parent / "templates")
        self._cache: dict[tuple[str, str, str], dict[str, object]] = {}
        logger.info("prompt_registry_initialised", root=str(self._root))

    def system(self, name: str, version: str) -> SystemPrompt:
        return SystemPrompt.model_validate(self._load("system", name, version))

    def context(self, name: str, version: str) -> ContextTemplate:
        return ContextTemplate.model_validate(self._load("context", name, version))

    def output_schema(self, name: str, version: str) -> OutputSchema:
        return OutputSchema.model_validate(self._load("output_schema", name, version))

    def few_shot(self, name: str, version: str) -> FewShotExamples:
        return FewShotExamples.model_validate(self._load("few_shot", name, version))

    def list_versions(self, kind: str, name: str) -> tuple[str, ...]:
        """Return the available versions for a component, sorted ascending."""
        directory = self._root / self._subdir(kind)
        if not directory.is_dir():
            return ()
        prefix = f"{name}_"
        versions = [path.stem.removeprefix(prefix) for path in directory.glob(f"{prefix}*.yaml")]
        return tuple(sorted(versions))

    def _subdir(self, kind: str) -> str:
        if kind not in _SUBDIRS:
            raise PromptError(f"Unknown prompt component kind: {kind!r}")
        return _SUBDIRS[kind]

    def _load(self, kind: str, name: str, version: str) -> dict[str, object]:
        key = (kind, name, version)
        if key in self._cache:
            return self._cache[key]

        path = self._root / self._subdir(kind) / f"{name}_{version}.yaml"
        if not path.is_file():
            raise PromptNotFoundError(f"No {kind} prompt '{name}' version '{version}' at {path}")

        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise PromptError(f"Prompt file {path} is not a valid YAML mapping")

        data = cast("dict[str, object]", raw)
        self._cache[key] = data
        return data
