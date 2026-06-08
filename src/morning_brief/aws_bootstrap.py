from __future__ import annotations

import os
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.config import Config

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient

logger = structlog.get_logger(__name__)

_SSM_PATH = "/morning-brief/{environment}/"
# Bounded so a cold-start secrets fetch cannot hang Lambda initialisation.
_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=5, read_timeout=10
)


def bootstrap_secrets() -> None:
    """Load SSM SecureString secrets into the process environment at Lambda start.

    Reads every parameter under ``/morning-brief/<env>/`` (decrypted) and exports
    each by its basename, so ``/morning-brief/production/MORNING_BRIEF_LLM__ANTHROPIC_API_KEY``
    becomes the ``MORNING_BRIEF_LLM__ANTHROPIC_API_KEY`` variable that ``Settings``
    then reads — the parameter name *is* the env var name (identity mapping). Uses
    ``setdefault`` so an already-set variable wins (a local override, or a warm
    re-invocation).

    No-op unless running in Lambda *with* a resolvable AWS region: the Lambda
    runtime always sets ``AWS_LAMBDA_FUNCTION_NAME`` and ``AWS_REGION``, whereas
    local, dev, and test runs (including the container under the Lambda Runtime
    Interface Emulator, which sets the function name but no region) leave the region
    unset. Guarding on both keeps every real invocation bootstrapping while letting
    an offline emulator run the pipeline on mocks without reaching for AWS.
    """
    if "AWS_LAMBDA_FUNCTION_NAME" not in os.environ or not (
        os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    ):
        return
    environment = os.environ.get("MORNING_BRIEF_ENVIRONMENT", "production")
    path = _SSM_PATH.format(environment=environment)
    secrets = _read_parameters(path)
    for name, value in secrets.items():
        os.environ.setdefault(name, value)
    logger.info("ssm_secrets_loaded", path=path, count=len(secrets))


def _read_parameters(path: str) -> dict[str, str]:
    client: SSMClient = boto3.client("ssm", config=_CONFIG)  # pyright: ignore[reportUnknownMemberType]
    paginator = client.get_paginator("get_parameters_by_path")
    secrets: dict[str, str] = {}
    for page in paginator.paginate(Path=path, Recursive=True, WithDecryption=True):
        for parameter in page.get("Parameters", []):
            name = parameter.get("Name")
            value = parameter.get("Value")
            if name is not None and value is not None:
                secrets[name.rsplit("/", 1)[-1]] = value
    return secrets
