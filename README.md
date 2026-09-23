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

## Project structure

```text
morning-brief/
├── .github/workflows/   # CI checks and deployment
├── src/
│   ├── ai_brief/         # News sources, analysis, validation, and email pipeline
│   └── brief_core/       # Settings, HTTP, model routing, SMTP, logging, and AWS utilities
├── scripts/
│   └── run_ai_brief.py   # Command-line entry point
├── config/              # Local settings and example template
├── infra/               # Terraform configuration and AWS setup guide
├── tests/               # Tests with mocked external services
├── Dockerfile           # Lambda container image
├── pyproject.toml       # Dependencies and tooling configuration
└── SETUP.md             # Local setup guide
```

## Run locally

Follow the [local setup guide](SETUP.md) to configure, preview, and send your briefing.

## Deploy to AWS

GitHub Actions deploys the container image; Terraform manages the AWS resources.

| AWS service | Resources and purpose |
|---|---|
| Lambda | Runs the briefing pipeline and completion check. |
| EventBridge Scheduler | Starts the weekday briefing at 07:00 and checks completion at 08:00, London time, by default. |
| ECR | Stores container images, with cleanup of older versions. |
| Systems Manager Parameter Store | Stores API credentials, SMTP credentials, and recipient addresses. |
| KMS | Encrypts stored secrets and container images. |
| IAM | Controls access for Lambda, Scheduler, and GitHub deployments through OIDC. |
| CloudWatch | Stores logs, counts healthy completions, and monitors errors, queued failures, and missing runs. |
| SNS | Sends alarm notifications to the subscribed email address. |
| SQS | Retains failed invocation records for investigation. |
| S3 | Stores Terraform state in a private, encrypted, versioned bucket. |

Start with the [infrastructure overview](infra/README.md), then follow the
[setup guide](infra/SETUP.md). Scheduling stays disabled until explicitly enabled.

## Limits to keep in mind

- TLDR is currently the only news source. With multiple sources configured, a failed
  source is logged and skipped; the run fails if none provides usable stories.
- An unavailable original article falls back to its newsletter summary.
- Structure and citation checks do not establish that every explanation is correct.
- The AI brief keeps no delivery history, so reruns can repeat stories or emails.
