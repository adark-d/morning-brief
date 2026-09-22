from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from uuid import uuid4

import structlog

from ai_brief.pipeline import execute
from brief_core.logging import configure_logging, log_failure
from brief_core.settings import Settings


def main(argv: Sequence[str] | None = None) -> int:
    """Generate an HTML preview or send the brief by email."""

    parser = argparse.ArgumentParser(description="Your daily AI learning brief")
    parser.add_argument("--send", action="store_true", help="Enable email delivery")
    args = parser.parse_args(argv)

    configure_logging()
    tokens = structlog.contextvars.bind_contextvars(run_id=str(uuid4()))
    try:
        settings = Settings(send_email=bool(args.send))
        run = asyncio.run(execute(settings))
    except Exception as exc:
        log_failure("command_failed", exc)
        return 1
    finally:
        structlog.contextvars.reset_contextvars(**tokens)

    if run.status == "skipped":
        print("No useful stories today; no email sent.")
    else:
        print(f"Brief completed: {run.run_id}" if args.send else run.html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
