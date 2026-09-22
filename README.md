<h1 align="center">Morning Brief</h1>

<p align="center">
  <a href="https://github.com/adark-d/morning-brief/actions/workflows/ci.yml"><img src="https://github.com/adark-d/morning-brief/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.13+"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/Package_manager-uv-6E56CF" alt="uv"></a>
  <a href="https://aws.amazon.com/lambda/"><img src="https://img.shields.io/badge/AWS-Lambda-FF9900" alt="AWS Lambda"></a>
  <a href="https://ai.pydantic.dev/"><img src="https://img.shields.io/badge/Pydantic-AI-E92063" alt="Pydantic AI"></a>
</p>

An AI news email that helps you learn something useful from the headlines.
Morning Brief selects up to five relevant stories and explains the concepts behind
them, with practical examples and links to the original sources.

## What you receive

Each topic includes:

- **What happened** and why it matters.
- **A concept explained** in plain language.
- **A practical example** and a takeaway.
- **Source links**, with a note when only the newsletter summary was available.

Your interests guide the selection. If no stories qualify, the run finishes
without sending an email.

## How it works

```text
Fetch news → select topics → read articles → explain → validate → email
```

TLDR AI is the current news source. Pydantic AI calls Anthropic directly to produce
structured selections and lessons.
The application checks story references and lesson completeness before rendering
the email. The prompt asks for concise explanations based on the supplied sources.

Run it manually from your terminal or schedule it on AWS Lambda. The default AWS
schedule is **weekdays at 07:00, Europe/London**.

## Run locally

You need Python 3.13+, [uv](https://github.com/astral-sh/uv), and an Anthropic API key.
SMTP credentials are needed only when sending email.

### 1. Install and configure

From the repository root:

```bash
uv sync --frozen
cp config/.env.example config/.env
```

Copy the template only if you do not already have `config/.env`. Set your API key
and the Claude models used for each task:

```dotenv
MORNING_BRIEF_ANTHROPIC_API_KEY=your-key
MORNING_BRIEF_SELECTION_MODEL=claude-haiku-4-5
MORNING_BRIEF_EXPLANATION_MODEL=claude-sonnet-4-5-20250929
```

Haiku selects topics and Sonnet writes the explanations. These names are configurable;
both tasks call Anthropic directly. Keep real credentials out of Git.

If `ANTHROPIC_API_KEY` is already exported in your environment, you can leave the
key out of `config/.env`. Environment values take precedence over the file.

### 2. Preview the brief

```bash
uv run brief
```

This fetches live news, calls the models, and prints the email HTML to your terminal.
Logs go to stderr, so `uv run brief > brief.html` saves a clean preview.
It does not send email. Model calls may incur usage charges.

### 3. Send by email

Set the sender, recipients, SMTP host, and credentials in `config/.env`, then run:

```bash
uv run brief --send
```

Use [`config/.env.example`](config/.env.example) for available settings, including
interests, topic count, model budgets, and timeouts. Environment variables override
values in the file. On Lambda, SSM supplies fresh values on each invocation;
explicit environment values take precedence. Omitted settings use the defaults in
[`settings.py`](src/brief_core/settings.py).

## Project layout

| Location | Purpose |
|---|---|
| `src/ai_brief/` | News sources, prompts, analysis, validation, email template, and pipeline. |
| `src/brief_core/` | Shared settings, HTTP, model routing, SMTP, logging, and AWS utilities. |
| `scripts/run_ai_brief.py` | Command-line entry point for manual runs. |
| `config/` | Local settings and their example template. |
| `infra/` | Terraform configuration and AWS deployment instructions. |
| `tests/` | Brief behaviour and workflow tests using mocked external services. |

## Deploy to AWS

EventBridge Scheduler invokes Lambda. SSM supplies credentials, CloudWatch records
logs, and email alerts report failed or missed runs. A weekday check at 08:00
looks for a healthy completion within the previous two hours. GitHub Actions deploys image
updates; Terraform manages infrastructure separately.

Start with the [infrastructure overview](infra/README.md), then follow the
[setup guide](infra/SETUP.md). Scheduling stays disabled until explicitly enabled.

## Development

The committed tests focus on story parsing, lesson rules, email content, and pipeline
outcomes. Use temporary regression checks for plumbing changes rather than adding
permanent tests for every configuration or SDK wrapper.

```bash
uv run ruff check src/ scripts/ tests/
uv run ruff format src/ scripts/ tests/ --check
uv run mypy src/ scripts/ tests/
uv run pyright
uv run pytest
```

## Limits to keep in mind

- TLDR is currently the only news source. With multiple sources configured, a failed
  source is logged and skipped; the run fails if none provides usable stories.
- An unavailable original article falls back to its newsletter summary.
- Structure and citation checks do not establish that every explanation is correct.
- The AI brief keeps no delivery history, so reruns can repeat stories or emails.
