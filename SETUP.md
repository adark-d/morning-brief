# Local setup

You need Python 3.13+, [uv](https://github.com/astral-sh/uv), and an Anthropic API key.
SMTP credentials are needed only when sending email.

## 1. Install and configure

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

## 2. Preview the brief

```bash
uv run brief
```

This fetches live news, calls the models, and prints the email HTML to your terminal.
Logs go to stderr, so `uv run brief > brief.html` saves a clean preview.
It does not send email. Model calls may incur usage charges.

## 3. Send by email

Set the sender, recipients, SMTP host, and credentials in `config/.env`, then run:

```bash
uv run brief --send
```

Use [`config/.env.example`](config/.env.example) for available settings, including
interests, topic count, model budgets, and timeouts. Environment variables override
values in the file. On Lambda, SSM supplies fresh values on each invocation;
explicit environment values take precedence. Omitted settings use the defaults in
[`settings.py`](src/brief_core/settings.py).

For scheduled runs on AWS, follow the [AWS setup guide](infra/SETUP.md).
