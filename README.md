
# Morning Brief

A production-grade LLM pipeline that compresses ~60 minutes of pre-market context-assembly into a 3-minute briefing for fixed income desks.

## What this is

This repo implements the architecture, guardrails, and orchestration patterns required to run an LLM-backed decision-support system reliably in a regulated environment. It is intentionally generic — designed to work with any market data provider, any LLM backend, any delivery channel — and intentionally opinionated about the production concerns most demos skip.

## Architectural concerns this addresses

- **Three-tier guardrails** — input validation before the LLM, output verification after, delivery-time recipient checks
- **Prompt versioning** — prompts as YAML configuration, not strings in code; rollback without redeploying
- **Pluggable interfaces** — data providers, LLM backends, delivery channels, and storage are dependency-injected; swap any implementation without changing application logic
- **Immutable audit trail** — every brief, every delivery attempt, every error recorded for compliance retrieval
- **Graceful degradation** — partial data with a warning beats no brief with no notice; the system reports its own health
- **Observable by design** — structured logging, the four golden signals (latency, errors, cost, quality)

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.13 |
| Data validation | Pydantic v2 |
| Config | Pydantic Settings (YAML + env) |
| LLM | Anthropic Claude (default), pluggable via interface |
| API | FastAPI |
| HTTP | httpx (async) |
| Templating | Jinja2 |
| Logging | structlog |
| Retries | tenacity |
| Testing | pytest |
| Tooling | uv, ruff, mypy (strict) |

## Quick start

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                         # install dependencies
uv run pytest                   # run tests
uv run ruff check src/          # lint
uv run mypy src/                # typecheck
```

## Status

Phase 1 (core domain) in progress. See [implementation plan](#implementation-plan) below.

## Implementation plan

| Phase | Focus | Status |
|---|---|---|
| 1 | Core domain — models, interfaces, exceptions | In progress |
| 2 | Configuration | Pending |
| 3 | Infrastructure implementations + mocks | Pending |
| 4 | Prompt layer — registry, builder, validator | Pending |
| 5 | Guardrails — input, output, delivery | Pending |
| 6 | Pipeline orchestrator | Pending |
| 7 | API layer | Pending |
| 8 | Integration and end-to-end testing | Pending |
| 9 | Scheduler and production hardening | Pending |

## Owner

David Adarkwah · [dadark.dev](https://dadark.dev)
