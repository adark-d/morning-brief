# Infrastructure (Terraform) — morning-brief production

Implements the AWS deployment decided in [docs/adr/0001-deployment.md](../docs/adr/0001-deployment.md).
Phase 1 ships the **scheduled brief** (batch only); the HTTP API is deferred to Phase 2.

> **Deploying for the first time?** Use the full runbook:
> [docs/deployment-runbook.md](../docs/deployment-runbook.md). It covers everything this
> file assumes (AWS account/identity setup, Resend and DNS, GitHub environment and
> variables), adds a verification command after every step, and documents the failure
> modes hit during the first real deployment with their fixes. This file remains the
> quick reference for the Terraform layout and commands.

```
infra/
├── bootstrap/        # remote-state backend (S3 + DynamoDB lock) — applied once, local state
├── modules/          # kms · ecr · audit_s3 · secrets · iam · batch_lambda · observability · cicd
└── envs/prod/        # the production root: wires the modules, backend "s3"
```

## What it creates

A KMS CMK; an ECR repo; an **Object Lock (COMPLIANCE, 7-year) audit bucket** with SSE-KMS,
versioning, TLS-only policy, and Glacier/Deep-Archive lifecycle; SSM SecureString parameters
for the secrets; least-privilege IAM (batch execution + scheduler roles); the batch **Lambda**
(arm64 image) with a CloudWatch log group, an **SQS DLQ**, and an **EventBridge Scheduler**
(`cron(0 7 ? * MON-FRI *)`, Europe/London); **SNS alerts** (email + optional Slack) with three
alarms (run-failed, DLQ-not-empty, missed-run); and a **GitHub OIDC** deploy role.

Estimated cost: ~$3–5/month + LLM usage.

## What you need to provide

Terraform creates almost all of the AWS infrastructure — including the IAM roles for the
Lambda and for CI (AWS has no "service accounts"; IAM roles are the equivalent, and they are
provisioned for you). A few things must still come from you: the account itself, one admin
identity to run the first deploy, and the secret values. This section is the complete list of
**what to provide, where it goes, and why**.

### Local tooling

Terraform ≥ 1.9, the AWS CLI, and Docker on the machine doing the first deploy.

### 1. An AWS account + one admin identity (for the first deploy only)

> New to AWS? **[AWS_SETUP.md](AWS_SETUP.md)** is a click-by-click guide for this step — create
> the account, make an admin user, and configure the CLI so Terraform authenticates cleanly.

The very first `terraform apply` has to authenticate as *something*, and it cannot be the CI
role (Terraform has not created that yet). So you need:

- **An AWS account** with a billing method attached (this deployment is ~$3–5/month).
- **An admin identity on your machine** to run Terraform once. Either:
  - **Recommended:** enable **IAM Identity Center (SSO)**, grant yourself an admin permission
    set, and run `aws configure sso` — no long-lived keys.
  - **Simplest:** create one **IAM user** with the AWS-managed `AdministratorAccess` policy,
    generate an **access key**, and run `aws configure`.
- **Why admin:** the first apply *creates* IAM roles, a KMS key, the Object Lock bucket, etc.,
  which needs broad rights. You use this identity only for the initial `terraform apply`;
  routine code deploys afterwards use the OIDC role Terraform creates (no keys).

You do **not** create any role for the Lambda or for CI by hand — the `iam` and `cicd` modules do.

### 2. External accounts + secret values

The app needs these at runtime. Terraform creates empty SSM SecureString slots; you set the
values out-of-band (runbook step 6) so they never enter Terraform state.

| What | Where to get it | Goes into | Why |
|---|---|---|---|
| **Anthropic API key** | console.anthropic.com | SSM `…/MORNING_BRIEF_LLM__ANTHROPIC_API_KEY` | the LLM call |
| **Resend account + API key** | resend.com (free tier covers a daily brief) | SSM `…/SMTP_PASSWORD` (username = `resend`) | sends the email over SMTP |
| **A verified sending domain** | add the SPF/DKIM DNS records Resend gives you | the `smtp_from` tfvar | Resend only sends from a verified domain |
| **Recipient list** | you decide | SSM `…/RECIPIENTS` (JSON array) | who receives the brief (kept out of code as PII) |
| **Slack workspace + channel** *(optional)* | your Slack | `slack_team_id` / `slack_channel_id` tfvars | routes CRITICAL alerts to Slack |

### 3. Values you choose (set in `terraform.tfvars`)

- **Region** — `eu-west-2` (default).
- **A globally-unique audit bucket name** — e.g. `morning-brief-audit-prod-<suffix>` (`audit_bucket_name`).
- **GitHub owner/repo** — `adark-d` / `morning-brief` (trust for the CI deploy role).

### 4. One-time manual steps Terraform cannot do (AWS requires a human)

- **Confirm the SNS email subscription** — AWS emails a "click to confirm" link after apply.
- **Authorize Slack in the AWS Chatbot console** (one click) to obtain the workspace `team_id` —
  only if you want Slack alerts.
- **Set the secret values** with `aws ssm put-parameter` (runbook step 6).
- **Set 4 GitHub Actions variables** so CI can deploy — all are Terraform *outputs* (see below).
- **Create the `production` GitHub environment** (Settings → Environments) with
  *Deployment branches* restricted to `main`. The deploy role's trust policy only accepts
  OIDC tokens minted for this environment, so deploys fail until it exists.

### What you do NOT need

No VPC, NAT gateway, subnets, load balancer, database, or domain/TLS certificate — the
all-serverless design avoids them. (A domain + ACM cert would only be needed for the HTTP API,
which is deferred to Phase 2.)

### Build note

The image is built from the repo-root `Dockerfile`. Merge the Dockerfile change and this config
(the `production.yaml` S3 flip) to `main` first, then build from `main`.

## First deploy (manual — creates real, partly irreversible infrastructure)

> ⚠️ **Object Lock is irreversible.** The audit bucket's COMPLIANCE-mode 7-year retention cannot
> be shortened or removed by anyone (including root), and the bucket cannot be deleted until
> locks expire. Review `terraform plan` before applying.

1. **Remote-state backend** (once):
   ```bash
   cd infra/bootstrap
   terraform init
   terraform apply -var state_bucket_name=morning-brief-tf-state-<unique>
   ```
   Note the `state_bucket` and `lock_table` outputs.

2. **Point the prod root at that backend:**
   ```bash
   cd ../envs/prod
   cp backend.hcl.example backend.hcl        # fill in the bucket/table from step 1
   cp terraform.tfvars.example terraform.tfvars  # fill in audit_bucket_name, smtp_from, alert_email, github_*
   terraform init -backend-config=backend.hcl
   ```

3. **Create the ECR repo first** (the image Lambda needs an image to exist):
   ```bash
   terraform apply -target=module.ecr
   ```

4. **Build + push the arm64 image** (tag = a build SHA; set the same `image_tag` in tfvars):
   ```bash
   REPO=$(terraform output -raw ecr_repository_url)
   aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin "${REPO%/*}"
   # --provenance=false: Docker's default build attestation produces a multi-manifest
   # image that ECR stores but Lambda rejects ("image manifest ... not supported").
   docker build --platform linux/arm64 --provenance=false -t "$REPO:<tag>" ../../..   # repo root holds the Dockerfile
   docker push "$REPO:<tag>"
   ```

5. **Apply the rest:**
   ```bash
   terraform apply        # review the plan — note the Object Lock configuration
   ```

6. **Set the real secret values** (never in Terraform; the parameters exist with placeholders):
   ```bash
   P=$(terraform output -raw secrets_path)   # /morning-brief/production
   aws ssm put-parameter --overwrite --type SecureString --name "$P/MORNING_BRIEF_LLM__ANTHROPIC_API_KEY"        --value 'sk-ant-...'
   aws ssm put-parameter --overwrite --type SecureString --name "$P/MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS"   --value '["desk@firm.com"]'
   aws ssm put-parameter --overwrite --type SecureString --name "$P/MORNING_BRIEF_DELIVERY__EMAIL__SMTP_USERNAME" --value 'resend'
   aws ssm put-parameter --overwrite --type SecureString --name "$P/MORNING_BRIEF_DELIVERY__EMAIL__SMTP_PASSWORD" --value 're_...'
   ```

7. **Confirm alerting:** accept the SNS email subscription confirmation; for Slack, authorize the
   workspace once in the AWS Chatbot console, then set `slack_channel_id` / `slack_team_id` and re-apply.

8. **Smoke test:**
   ```bash
   aws lambda invoke --function-name "$(terraform output -raw batch_function_name)" /dev/stdout
   ```
   Expect a `status: success` summary, an object under `runs/<date>/` in the audit bucket, and the
   email to arrive. Then let the 07:00 schedule take over.

## Ongoing deploys

After the first deploy, [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) runs the
quality gate, builds, pushes, rolls the Lambda via the OIDC deploy role, and waits until the
rollout reports `Successful`. Set these repo **Actions variables** from the prod outputs:
`AWS_REGION`, `AWS_DEPLOY_ROLE_ARN` (`github_deploy_role_arn`), `ECR_REPOSITORY`
(`ecr_repository_url`), `LAMBDA_FUNCTION` (`batch_function_name`), and create the `production`
GitHub environment restricted to `main` (one-time step 4 above).

To roll back, revert the offending commit on `main`; the workflow redeploys the reverted state.

## Validate locally (no AWS needed)

```bash
terraform fmt -recursive
cd envs/prod && terraform init -backend=false && terraform validate
```
