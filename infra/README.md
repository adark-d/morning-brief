# Infrastructure

EventBridge Scheduler starts the Lambda function each weekday. It fetches news, calls Anthropic through
Pydantic AI, and sends the brief through SMTP.

There is one deployment configuration. Email keeps the finished brief; S3 stores
Terraform state only. CloudWatch and SNS provide logs and alerts, while SQS holds
failed invocation records for inspection.

**Start with [AWS setup](SETUP.md)** for authentication, first deployment,
secret configuration, and GitHub deployment instructions.

## Folder guide

| File or folder | Purpose |
|---|---|
| `main.tf` | Connect the infrastructure modules. |
| `variables.tf` | Define deployment settings. |
| `outputs.tf` | Expose resource names and URLs used during setup. |
| `versions.tf` | Define Terraform, provider, and state-backend requirements. |
| `modules/` | Define Lambda, scheduling, IAM permissions, secrets, images, and alerts. |
| `terraform_state/` | Create the S3 bucket that stores Terraform's resource records. |
| `terraform.tfvars.example` | Template for local, non-secret deployment values. |
| `backend.hcl.example` | Template for the Terraform state location. |

The `selection_model` and `explanation_model` variables choose the Claude models.
The application calls Anthropic directly using an API key stored in SSM.

## Key settings

Set deployment values in your local `terraform.tfvars`.

| Setting | Default | Purpose |
|---|---|---|
| `schedule_enabled` | `false` | Keep delivery paused until setup is complete. |
| `schedule_expression` | `cron(0 7 ? * MON-FRI *)` | Run every weekday at 07:00. |
| `schedule_timezone` | `Europe/London` | Interpret the schedule in local time. |
| `completion_check_schedule` | `cron(0 8 ? * MON-FRI *)` | Check that the weekday brief completed. |
| `completion_check_lookback_minutes` | `120` | Search for a healthy completion in the preceding two hours. |
| `missed_run_hours` | `74` | Backstop for prolonged outages, including a failed check schedule. |
| `brief_settings.model_timeout_seconds` | `130` | Allow longer model requests without extending article timeouts. |
| `pipeline_timeout_seconds` | `420` | Limit the application's overall runtime. |
| `lambda_timeout_seconds` | `480` | Allow at least 60 seconds beyond the application deadline. |

`brief_settings` overrides optional values from
[`settings.py`](../src/brief_core/settings.py). Omitted values retain Python defaults.
Credentials and recipients are loaded from SSM under `/morning-brief/`.

## Updates and operations

- **Application changes:** GitHub Actions builds and updates the Lambda image.
- **Infrastructure or settings changes:** review and apply a Terraform plan separately.
- **Failed runs:** inspect CloudWatch logs and the SQS failure queue before retrying.

The AI news brief has no delivery history, so retries can send duplicate emails and consecutive
runs can reuse a source issue. See [troubleshooting](SETUP.md#troubleshooting)
for failure handling and [AWS setup](SETUP.md#7-configure-github-deployments)
for deployment instructions.
