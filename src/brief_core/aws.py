from __future__ import annotations

import os
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.config import Config

from brief_core import BriefCoreError

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient

logger = structlog.get_logger(__name__)

_SSM_PATH = "/morning-brief/"
_SSM_CLIENT_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=5, read_timeout=10
)


def read_secrets() -> dict[str, str]:
    """Read fresh SSM values without changing the process environment."""

    running_in_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")

    # Skip AWS lookups during local runs and tests.
    if not running_in_lambda or region is None:
        return {}

    secrets = _read_parameters(_SSM_PATH)
    if any(value == "PLACEHOLDER_SET_OUT_OF_BAND" for value in secrets.values()):
        raise BriefCoreError("Replace the SSM placeholders before running the brief")

    logger.info("ssm_secrets_loaded", path=_SSM_PATH, count=len(secrets))
    return secrets


def _read_parameters(path: str) -> dict[str, str]:
    """Read and decrypt every parameter directly under the project path."""

    client: SSMClient = boto3.client("ssm", config=_SSM_CLIENT_CONFIG)  # pyright: ignore[reportUnknownMemberType]
    paginator = client.get_paginator("get_parameters_by_path")
    secrets: dict[str, str] = {}

    for page in paginator.paginate(Path=path, Recursive=False, WithDecryption=True):
        for parameter in page.get("Parameters", []):
            name = parameter.get("Name")
            value = parameter.get("Value")
            if name is not None and value is not None:
                secrets[name.rsplit("/", 1)[-1]] = value
    return secrets
