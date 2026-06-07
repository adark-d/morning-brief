from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from morning_brief.application.composition import build_application
from morning_brief.config import load_settings
from morning_brief.config.settings import Settings
from morning_brief.core.models.audit import RunStatus
from morning_brief.observability.logging import configure_logging


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch. Returns a process exit code."""
    settings = load_settings()
    configure_logging(settings.observability)
    args = _build_parser().parse_args(argv)
    if args.command == "run":
        return run_once(settings)
    return serve(settings, host=args.host, port=args.port)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="morning-brief", description="Pre-market briefing pipeline."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Execute one brief and exit")
    serve_parser = sub.add_parser("serve", help="Run the HTTP API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    return parser


def run_once(settings: Settings) -> int:
    """Run one brief and exit. 0 if it ran and delivered, 1 if the run failed."""
    application = build_application(settings)
    run = asyncio.run(application.orchestrator.run())
    return 1 if run.status is RunStatus.FAILED else 0


def serve(settings: Settings, *, host: str, port: int) -> int:
    """Run the HTTP API (blocks until shutdown)."""
    import uvicorn

    from morning_brief.api.app import create_app

    uvicorn.run(create_app(settings), host=host, port=port)
    return 0
