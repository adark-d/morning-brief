# Morning Brief

A production-grade LLM pipeline that compresses ~60 minutes of pre-market
context-assembly into a 3-minute briefing for fixed-income desks.

On a schedule it fetches market data, validates it, asks an LLM for a structured
analysis, verifies that analysis, renders and delivers it by email, and writes an
immutable audit record of the whole run. It is intentionally generic — any data
provider, any LLM backend, any delivery channel can be swapped in behind an
interface — and opinionated about the production concerns most demos skip.

A full walkthrough of the design lives in [docs/architecture.md](docs/architecture.md).

## Key properties

- **Three-tier guardrails** — input validation before the LLM, output verification
  after, and recipient checks before delivery.
- **Versioned prompts** — prompts are YAML, not strings in code; roll one back
  without redeploying.
- **Pluggable interfaces** — data providers, LLM backends, delivery channels, and
  storage are dependency-injected; swap any one without touching business logic.
- **Immutable audit trail** — every run, delivery attempt, and error is recorded
  for compliance.
- **Graceful degradation** — a partial brief with a warning beats no brief with no
  notice; the system reports its own health.
- **Observable by design** — structured logging plus per-stage and per-provider
  latency and cost on every run.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.13 |
| Validation | Pydantic v2 |
| Config | Pydantic Settings (YAML + env) |
| LLM | Anthropic Claude (default), pluggable via interface |
| API | FastAPI |
| HTTP | httpx (async) |
| Templating | Jinja2 |
| Logging | structlog |
| Retries | tenacity |
| Testing | pytest |
| Tooling | uv, ruff, mypy + pyright (strict), pip-audit |

## Prerequisites

- **Python 3.13**
- **[uv](https://docs.astral.sh/uv/)** — the project and dependency manager

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Try it immediately (no secrets needed)

The `test` environment wires every external dependency to a mock — no API key, no
network, no real email. This is the fastest way to confirm everything works:

```bash
MORNING_BRIEF_ENVIRONMENT=test \
MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS='["you@example.com"]' \
uv run morning-brief run
```

You should see the pipeline run end-to-end and write an audit record under
`audit/test/`. To run for real (live market data, a real LLM call, real email),
configure secrets below.

### 3. Configure secrets (`.env`)

Secrets and recipient lists come **only** from environment variables — never from
YAML or code. The app automatically loads a `.env` file from the project root
(`.env` is gitignored, so your secrets stay local).

Copy the template and fill it in:

```bash
cp .env.example .env
```

Environment variables follow the pattern `MORNING_BRIEF_<SECTION>__<FIELD>` (note
the **double** underscore between section and field).

**Required for a real run:**

| Variable | What it is |
|---|---|
| `MORNING_BRIEF_LLM__ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`). |
| `MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS` | JSON array of recipients, e.g. `["desk@firm.com"]`. |
| `MORNING_BRIEF_API__AUTH_TOKEN` | Bearer token for the HTTP API (see below). Required only when you run `serve`. |

**Required to actually send email** (any SMTP relay; Gmail shown below):

| Variable | Example |
|---|---|
| `MORNING_BRIEF_DELIVERY__EMAIL__SMTP_HOST` | `smtp.gmail.com` |
| `MORNING_BRIEF_DELIVERY__EMAIL__SMTP_PORT` | `587` |
| `MORNING_BRIEF_DELIVERY__EMAIL__START_TLS` | `true` |
| `MORNING_BRIEF_DELIVERY__EMAIL__SMTP_FROM` | `you@gmail.com` |
| `MORNING_BRIEF_DELIVERY__EMAIL__SMTP_USERNAME` | `you@gmail.com` |
| `MORNING_BRIEF_DELIVERY__EMAIL__SMTP_PASSWORD` | your SMTP password / app password |

**Optional:**

| Variable | Default | Notes |
|---|---|---|
| `MORNING_BRIEF_ENVIRONMENT` | `development` | `development` \| `test` \| `production` |

`.env` is read as plain text — do **not** wrap values in quotes, and put nothing
after the value.

#### Generate the API auth token

The API is fail-closed: if no token is configured, every protected endpoint
returns `503`. Generate a strong random token and paste it into `.env`:

```bash
python3 -c "import secrets; print('MORNING_BRIEF_API__AUTH_TOKEN=' + secrets.token_urlsafe(32))" >> .env
```

#### Get a Gmail App Password (for email delivery)

Gmail blocks normal-password SMTP login, so you need an **App Password**:

1. Enable **2-Step Verification** on the Google account (required for the next step).
2. Go to **https://myaccount.google.com/apppasswords** and create a password for
   "Mail". Google shows a 16-character code, often with spaces.
3. Paste it into `.env` **with the spaces removed**:

   ```
   MORNING_BRIEF_DELIVERY__EMAIL__SMTP_PASSWORD=abcdefghijklmnop
   ```

Gmail requires the sender to match the authenticated account, so set both
`SMTP_FROM` and `SMTP_USERNAME` to that Gmail address. (Gmail also caps sending at
~500/day — fine for testing; use a transactional relay such as SES/SendGrid for
production volume.)

## Configuration & environments

Non-secret configuration is layered YAML, highest precedence first:

```
env vars  >  .env  >  config/environments/<env>.yaml  >  config/default.yaml  >  defaults
```

`MORNING_BRIEF_ENVIRONMENT` selects which environment file loads on top of
`config/default.yaml`:

| Environment | Data | LLM | Delivery | Logs | Use for |
|---|---|---|---|---|---|
| `development` | live (yfinance) | `claude-haiku` | real (uses your `.env`) | console (readable) | local iteration |
| `test` | mock | mock | mock | console | offline, free, no secrets |
| `production` | live (yfinance) | `claude-opus` | real | JSON (for aggregators) | deployment |

You can override any single value with its env var, e.g. read human-readable logs
while in production:

```bash
MORNING_BRIEF_OBSERVABILITY__JSON_LOGS=false uv run morning-brief serve
```

## Running

### Run one brief (CLI)

```bash
uv run morning-brief run
```

Runs the full pipeline once and exits. The run is always persisted to the audit
store; a failed brief is recorded as data (`status="failed"`), not a crash. This is
the unit a scheduler invokes.

### Serve the HTTP API

```bash
uv run morning-brief serve --host 127.0.0.1 --port 8000
```

Interactive API docs are generated automatically:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **OpenAPI spec:** http://127.0.0.1:8000/openapi.json

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | — | Liveness probe |
| `POST /briefs/run` | bearer | Trigger a run, return its summary |
| `GET /briefs/latest` | bearer | The most recent run |
| `GET /briefs/{run_id}` | bearer | A run by id |
| `GET /briefs?date=YYYY-MM-DD` | bearer | Runs triggered on a UTC date |

### Authenticating API requests

All `/briefs` endpoints require `Authorization: Bearer <token>` (the value of
`MORNING_BRIEF_API__AUTH_TOKEN`).

- **In Swagger UI:** click **Authorize** (top right) and paste the token.
- **With curl:**

  ```bash
  TOKEN=$(grep AUTH_TOKEN .env | cut -d= -f2)
  curl -s http://127.0.0.1:8000/health
  curl -s -X POST http://127.0.0.1:8000/briefs/run -H "Authorization: Bearer $TOKEN"
  ```

## Testing & quality gate

Every check below must pass before a commit is considered ready:

```bash
uv run ruff check src/ tests/          # lint
uv run ruff format src/ tests/ --check # format
uv run mypy src/ tests/                # type check
uv run pyright                         # second, stricter type check
uv run pytest                          # tests
uv run pip-audit                       # dependency vulnerabilities (needs network)
```

## Project structure

```
src/morning_brief/
├── core/            # Domain: models, interfaces, exceptions. Pure Python, no I/O.
├── config/          # Settings (Pydantic Settings, YAML + env)
├── prompts/         # Prompt registry, builder, validator + versioned YAML templates
├── guardrails/      # Input, output, and delivery guardrails
├── infrastructure/  # Concrete implementations + mocks (data, llm, delivery, storage, rendering)
├── application/     # Pipeline orchestrator + composition root (the only place that wires concretes)
├── api/             # FastAPI app — the only layer that knows HTTP
└── observability/   # Logging and timing

config/              # default.yaml + environments/{development,production,test}.yaml
tests/               # unit (mirrors src), integration, fixtures
docs/                # architecture and design notes
```

## Deployment

- **Scheduling is the deployment's job.** Point a cron job / Kubernetes CronJob /
  cloud scheduler at `morning-brief run` using the cadence in `schedule_cron`
  (default: 07:00 GMT on weekdays). There is no in-process daemon to keep alive.
- **Persist the audit store.** Production uses the JSON audit backend; set
  `MORNING_BRIEF_AUDIT__JSON_STORE_PATH` to a persistent volume, or audit records
  are lost on restart.
- **TLS and ingress rate limiting** are deployment-provided. See
  [SECURITY.md](SECURITY.md) for the full set of required controls.

## Documentation

- [docs/architecture.md](docs/architecture.md) — how the system is built and why.
- [docs/reusability-and-the-fde-role.md](docs/reusability-and-the-fde-role.md) —
  the reuse model behind the design.
- [SECURITY.md](SECURITY.md) — security posture and deployment controls.
