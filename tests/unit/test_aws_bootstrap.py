from __future__ import annotations

import os
from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from morning_brief.aws_bootstrap import bootstrap_secrets


@pytest.fixture
def restore_environ() -> Iterator[None]:
    """Snapshot and restore os.environ around a test that mutates it directly.

    bootstrap_secrets sets variables via os.environ.setdefault, which monkeypatch
    does not track, so the snapshot is the reliable way to keep tests isolated.
    """
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.mark.usefixtures("restore_environ")
def test_bootstrap_is_noop_outside_lambda() -> None:
    os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
    # Must not touch AWS (no creds/region configured) nor raise.
    bootstrap_secrets()


@pytest.mark.usefixtures("restore_environ")
def test_bootstrap_loads_ssm_params_as_env_vars() -> None:
    os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "morning-brief-batch"
    os.environ["MORNING_BRIEF_ENVIRONMENT"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ.pop("MORNING_BRIEF_LLM__ANTHROPIC_API_KEY", None)

    with mock_aws():
        ssm = boto3.client("ssm", region_name="us-east-1")
        ssm.put_parameter(
            Name="/morning-brief/test/MORNING_BRIEF_LLM__ANTHROPIC_API_KEY",
            Value="sk-ant-from-ssm",
            Type="SecureString",
        )
        bootstrap_secrets()

    assert os.environ["MORNING_BRIEF_LLM__ANTHROPIC_API_KEY"] == "sk-ant-from-ssm"


@pytest.mark.usefixtures("restore_environ")
def test_bootstrap_does_not_override_an_already_set_var() -> None:
    os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "morning-brief-batch"
    os.environ["MORNING_BRIEF_ENVIRONMENT"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["MORNING_BRIEF_LLM__ANTHROPIC_API_KEY"] = "already-set"

    with mock_aws():
        ssm = boto3.client("ssm", region_name="us-east-1")
        ssm.put_parameter(
            Name="/morning-brief/test/MORNING_BRIEF_LLM__ANTHROPIC_API_KEY",
            Value="from-ssm",
            Type="SecureString",
        )
        bootstrap_secrets()

    assert os.environ["MORNING_BRIEF_LLM__ANTHROPIC_API_KEY"] == "already-set"
