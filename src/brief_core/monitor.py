from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.config import Config

from brief_core import BriefCoreError

if TYPE_CHECKING:
    from mypy_boto3_cloudwatch import CloudWatchClient


class MissingBriefError(BriefCoreError):
    """No successful delivery or quiet-day completion was recorded on time."""


def check_completion() -> None:
    """Check the previous scheduled run without reading secrets or sending a brief."""
    name = os.environ.get("BRIEF_COMPLETION_METRIC_NAME")
    try:
        lookback = int(os.environ.get("BRIEF_COMPLETION_LOOKBACK_MINUTES", "120"))
    except ValueError as exc:
        raise MissingBriefError("Invalid completion-check window") from exc
    if not name or not 10 <= lookback <= 1440:
        raise MissingBriefError("Configure the completion metric and a 10-1440 minute window")

    now = datetime.now(UTC)
    client: CloudWatchClient = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "cloudwatch", config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2})
    )
    result = client.get_metric_statistics(
        Namespace="MorningBrief",
        MetricName=name,
        StartTime=now - timedelta(minutes=lookback),
        EndTime=now,
        Period=60,
        Statistics=["Sum"],
    )
    completions = sum(point.get("Sum", 0) for point in result.get("Datapoints", []))
    if completions < 1:
        # The existing Lambda error alarm and failure queue report this failure.
        raise MissingBriefError("No healthy brief completed before the scheduled check")
    structlog.get_logger().info("completion_check_passed", completions=completions)
