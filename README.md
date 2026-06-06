
# Morning Brief

A production-grade LLM pipeline that compresses ~60 minutes of pre-market context-assembly into a 3-minute briefing for fixed income desks.

## What this is

This repo implements the architecture, guardrails, and orchestration patterns required to run an LLM-backed decision-support system reliably in a regulated environment. It is intentionally generic — designed to work with any market data provider, any LLM backend, any delivery channel — and intentionally opinionated about the production concerns most demos skip.

A full walkthrough of the design and the reasoning behind it is in [docs/architecture.md](docs/architecture.md).

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
| Tooling | uv, ruff, mypy + pyright (strict), pip-audit |

## Quick start

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                         # install dependencies
uv run pytest                   # run tests
uv run ruff check src/ tests/   # lint
uv run mypy src/ tests/         # typecheck
uv run pyright                  # second type checker (strict)
```

## Running

```bash
uv run morning-brief run                              # one brief, then exit
uv run morning-brief serve --host 0.0.0.0 --port 8000 # the HTTP API (docs at /docs)
```

Configuration comes from `config/*.yaml` plus `MORNING_BRIEF_*` environment variables (secrets only — copy `.env.example` to `.env`). **Scheduling is owned by the deployment**: point a cron / Kubernetes CronJob / cloud scheduler at `morning-brief run` using the cadence in `schedule_cron` (default 07:00 GMT on weekdays). Required deployment controls (TLS, ingress rate limiting) are documented in [SECURITY.md](SECURITY.md).

## Status

Feature-complete and tested end-to-end: domain model, configuration, pluggable
infrastructure (data, LLM, delivery, storage) with mocks, versioned prompts,
three-tier guardrails, the pipeline orchestrator and composition root, the FastAPI
layer, integration tests, and CI. Deployment controls (TLS, scheduling, ingress
rate limiting) are documented in [SECURITY.md](SECURITY.md).

## What's built

- **Domain** — frozen Pydantic models, dependency-inverted interfaces, a typed
  exception hierarchy
- **Pipeline** — fetch → input guardrails → prompt → analyse → output guardrails →
  render → deliver → immutable audit, with graceful degradation
- **Safety** — input, output, and delivery guardrails; CRITICAL aborts, WARNING
  flags and continues
- **Interfaces** — REST API (trigger + audit retrieval, fail-closed bearer auth)
  and a CLI (`run` for scheduled execution, `serve` for the API)
- **Quality** — strict typing (mypy + pyright), full test suite, and dependency
  scanning, all enforced in CI

## Owner

David Adarkwah · [dadark.dev](https://dadark.dev)
