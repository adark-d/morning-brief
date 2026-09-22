# AWS setup

Follow this guide to deploy the brief for the first time, then configure later
updates. See the [infrastructure overview](README.md) for the folder layout and defaults.

## Before you start

| Requirement | What you need |
|---|---|
| AWS account | An AWS user or role allowed to create the resources in this project. |
| Local tools | Terraform 1.10+, AWS CLI, and Docker with Buildx. |
| Anthropic | An API key with access to the configured Claude models. |
| Email | SMTP credentials, a verified sender, and recipient addresses. |
| GitHub | The repository that will build and deploy later image updates. |

Enable MFA on the AWS root account and use a separate identity for deployment.
Pydantic AI calls Anthropic directly from Lambda. The API key is read from SSM
on each invocation.

Run all commands from the **repository root**. Terraform apply creates billable AWS
resources. Review its plan before confirming.

## 1. Authenticate and check your tools

A profile is a named set of AWS credentials and settings. List your profiles, then
select the one to use in this terminal:

```bash
aws configure list-profiles
export AWS_PROFILE=your-profile-name
```

Replace `your-profile-name` with an actual profile name. If you need to create a
profile using access keys supplied for your deployment identity, run:

```bash
aws configure --profile morning-brief
export AWS_PROFILE=morning-brief
```

Use your chosen AWS region consistently; this project's default is `eu-west-2`.
Keep access keys private and out of Git. If your account uses IAM Identity Center,
use its existing sign-in process instead of creating another access key.

```bash
aws sts get-caller-identity
terraform version
docker buildx version
```

**Check:** the identity command shows your intended AWS account and user or role,
and both tools report their versions. Start Docker before building the image.
See [AWS profile configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
if you need help choosing credentials.

## 2. Create Terraform's state bucket

Terraform state is its record of the resources it manages. An S3 bucket stores
that record for the main deployment. Create the bucket first:

```bash
terraform -chdir=infra/terraform_state init
terraform -chdir=infra/terraform_state apply
terraform -chdir=infra/terraform_state output -raw state_bucket
```

Enter a globally unique bucket name when prompted. Keep this configuration's local
`infra/terraform_state/terraform.tfstate` file safe: it tracks the bucket itself.

**Check:** the last command prints the bucket name. Use it in the next step.

## 3. Set deployment values

Copy the templates once, then edit the new files:

```bash
cp infra/backend.hcl.example infra/backend.hcl
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

| File | Values to set |
|---|---|
| `backend.hcl` | The bucket from step 2, its region, and the state key. |
| `terraform.tfvars` | Image tag, sender, SMTP host, GitHub owner, and alert email. |

Choose an image tag such as `initial-brief` and keep `schedule_enabled = false`.
OpenID Connect (OIDC) lets GitHub obtain temporary AWS credentials without storing
access keys. In the AWS console, open **IAM → Identity providers**. If
`token.actions.githubusercontent.com` is already listed, set
`create_oidc_provider = false` and copy its ARN into `existing_oidc_provider_arn`.
An ARN is the full AWS identifier shown on the provider's details page.

Both local files are Git-ignored. Keep credentials out of them.

**Check:** all `CHANGEME` and example service addresses have been replaced, and
`schedule_enabled` is still `false`.

## 4. Create the image repository and push the image

Amazon Elastic Container Registry (ECR) stores the container image Lambda runs.
Lambda needs that image before it can be created. Provision ECR and its encryption
key first; this targeted apply is only for the initial setup.

```bash
terraform -chdir=infra init -backend-config=backend.hcl
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra validate
terraform -chdir=infra apply -target=module.ecr
```

Use the same region and image tag you configured in step 3:

```bash
brief_region=eu-west-2
brief_image_tag=initial-brief
brief_repository=$(terraform -chdir=infra output -raw ecr_repository_url)

aws ecr get-login-password --region "$brief_region" |
  docker login --username AWS --password-stdin "${brief_repository%%/*}"

docker buildx build --platform linux/arm64 --provenance=false \
  --tag "$brief_repository:$brief_image_tag" --push .
```

**Check:** the build completes and the ECR repository contains your chosen image tag.

## 5. Create the remaining resources and populate secrets

```bash
terraform -chdir=infra apply
```

AWS Systems Manager (SSM) Parameter Store holds the credentials Lambda reads at
startup. Terraform creates named entries with placeholder values.

1. Open the AWS console and select your deployment region.
2. Open **Systems Manager → Parameter Store** and find `/morning-brief/`.
3. Open each parameter below, choose **Edit**, replace its value, and save.
   Keep its name, `SecureString` type, and encryption key unchanged.

| Parameter | Value |
|---|---|
| `MORNING_BRIEF_ANTHROPIC_API_KEY` | Your Anthropic API key. |
| `MORNING_BRIEF_RECIPIENTS` | JSON array, for example `["reader@example.com"]`. |
| `MORNING_BRIEF_SMTP_USERNAME` | SMTP account username. |
| `MORNING_BRIEF_SMTP_PASSWORD` | SMTP account password. |

Terraform preserves values changed in SSM, but its provider can still store
decrypted secrets in state. Restrict access to state, backups, and saved plans.
Amazon Simple Notification Service (SNS) sends the alert emails. Confirm its
subscription email to activate alerts.

**Check:** all four parameters contain real values, Terraform reports a successful
apply, and the schedule remains disabled. For console help, see
[Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-working-with.html).

## 6. Enable the schedule

Set `schedule_enabled = true` in `infra/terraform.tfvars`, then apply:

```bash
terraform -chdir=infra apply
```

The default is **07:00 every weekday, Europe/London**. A second schedule checks
at **08:00** for a healthy completion within the previous 120 minutes. Missing
completions raise a Lambda error, which uses the existing email alarm and failure
queue. The 74-hour alarm remains a backstop if both schedules stop working.

When changing the briefing schedule, update `completion_check_schedule` too.
Place the check after the delivery window, and keep its lookback shorter than
the interval between briefs so an older run cannot satisfy it. Confirm the SNS
subscription before enabling either schedule; `alert_email` is required.
Weekdays reduce repeated TLDR issues but cannot prevent repeats on holidays,
early runs before publication, or manual reruns without delivery history.

**Check:** after the next run, the email arrives. In the AWS console, open
**CloudWatch → Logs → Log groups**, choose `/aws/lambda/<function-name>`, and find
`run_finished` with `status=success`. Get the function name with:

```bash
terraform -chdir=infra output -raw batch_function_name
```

## 7. Configure GitHub deployments

Display the deployment outputs:

```bash
terraform -chdir=infra output
```

In your GitHub repository, open **Settings → Secrets and variables → Actions →
Variables**. Choose **New repository variable** for each entry below:

| GitHub variable | Value |
|---|---|
| `AWS_REGION` | Your deployment region. |
| `AWS_DEPLOY_ROLE_ARN` | Terraform output `github_deploy_role_arn`. |
| `ECR_REPOSITORY` | Terraform output `ecr_repository_url`, including the registry hostname. |
| `LAMBDA_FUNCTION` | Terraform output `batch_function_name`. |

The AWS role trusts the repository's `main` branch directly. No GitHub environment
or stored AWS access key is needed. Protect `main` with pull requests and required
CI checks before allowing automated deployments.

**Check:** all four repository variables are present and the updated Terraform
OIDC trust policy has been applied before running the deployment workflow.

GitHub Actions builds and updates the Lambda image. For infrastructure or settings
changes, run `terraform -chdir=infra plan`, review it, and then apply separately.

## Change application settings

Use `brief_settings` in `terraform.tfvars` for optional application settings:

```hcl
brief_settings = {
  interests        = "Agents, evaluation, and practical AI engineering"
  topic_count      = 3
  source_names     = ["tldr"]
  smtp_port        = 587
}
```

Omitted values use the defaults in
[`settings.py`](../src/brief_core/settings.py). Terraform converts lists to JSON
for Lambda; the application validates settings at startup.

The default stage budgets are 30 seconds for sources, 45 for selection, 20 for
article enrichment, 260 for explanation, and 30 for delivery. Their total must be
below the 420-second application deadline. Lambda allows 480 seconds including
startup. Enrichment falls back to summaries when its shared budget expires.

Model requests use a separate 130-second HTTP timeout. Selection and explanation
also have their own stage deadlines. Pydantic AI allows one correction attempt
when the output fails validation; automatic SDK transport retries are disabled.
If you change these limits, adjust the stage budgets too.

SMTP defaults to STARTTLS on port 587. For implicit TLS on port 465, set
`smtp_use_tls = true` and `smtp_start_tls = false`. Credentialed SMTP requires TLS.

Apply settings changes with Terraform. See the [default settings](README.md#key-settings)
for schedule and timeout guidance.

A `skipped` run means no stories qualified. It sends no email and counts as a
healthy completion for monitoring. Retrieval and model failures still raise errors.

## Troubleshooting

| Signal | Where to look |
|---|---|
| Lambda error | CloudWatch logs for the failing stage and traceback. |
| Message in the failure queue | Amazon Simple Queue Service (SQS), which holds failed invocation records for inspection. |
| Missing brief | The schedule, Lambda logs, and the missed-run alarm. |

Scheduler delivery retries and Lambda function-error retries are disabled because
an SMTP timeout can occur after an email was accepted. Other AWS retries or duplicate
events can still repeat delivery. Check the email provider before replaying a failure.

The failure queue retains records for 14 days. Both schedules and missing-run notifications pause when
`schedule_enabled = false`.
With no delivery history, the brief may cover the same source issue on days when
no new issue is published.

## Keep deployment access secure

GitHub Actions uses OIDC, so it does not need stored AWS access keys. Local Terraform
changes still require AWS credentials. Deactivate unused long-lived keys and keep
Terraform state, backups, and saved plans private.
