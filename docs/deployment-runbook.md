# Deployment runbook — zero to production, verified at every step

This is the complete, battle-tested guide to deploying morning-brief to AWS. It was
written after a real deployment and includes everything the short runbook in
[infra/README.md](../infra/README.md) assumes you know: the account setup, the email
provider setup, the GitHub configuration, the verification command for every step, and
the failures actually hit during the first deployment with their fixes.

Conventions used throughout:

- `<ACCOUNT_ID>` — your 12-digit AWS account ID.
- `<yourdomain.com>` — a domain you own (for the sending address).
- `<you@example.com>` — your alert/recipient email.
- Every phase ends with a **Verify** block. Do not move on until it passes — every
  failure in the first deployment was caught (or would have been) by one of these.

Phases 0–2 are one-time account work with no dependencies between them. Phase 3 onward
is strictly ordered.

---

## Phase 0 — Accounts, identity, and tools

### 0.1 What you must already have

| Thing | Why | Where it ends up |
|---|---|---|
| A domain you own | Resend only sends from a domain you can prove you control | DNS records + `smtp_from` |
| An Anthropic API key | the LLM call | SSM SecureString |
| A password manager | three secrets below are shown exactly once | — |
| An AWS account | everything | — |

### 0.2 Protect the AWS root user

The root user can do anything, including closing the account, and cannot be
permission-limited or deleted. It gets MFA and is then set aside.

1. Sign in as root → search **IAM** → follow the dashboard prompt to **Add MFA**
   (authenticator app).
2. That is root's last routine use. Day-to-day work happens as the IAM user below.

### 0.3 Create the CLI admin identity

1. IAM → **Users** → **Create user** → name `terraform-admin`.
2. Leave **"Provide user access to the AWS Management Console" unchecked** — a
   CLI-only identity cannot be phished through a login page.
3. Permissions → **Attach policies directly** → **`AdministratorAccess`**. (Genuinely
   needed: the first apply creates IAM roles, a KMS key, and the audit bucket.)
4. Open the user → **Security credentials** → **Create access key** → type **CLI** →
   create. **Copy both values to your password manager now** — the secret is shown once.

This long-lived key exists only for the first `terraform apply` from your machine.
After the deployment is stable, deactivate it (Phase 10) — routine deploys use GitHub
OIDC with no stored keys.

### 0.4 Install and configure the tools

```bash
brew install awscli
brew install hashicorp/tap/terraform     # terraform is not in brew core
# Docker Desktop: https://www.docker.com/products/docker-desktop/
```

```bash
aws configure
#   AWS Access Key ID     : <the access key ID>
#   AWS Secret Access Key : <the secret>
#   Default region name   : eu-west-2
#   Default output format : json
```

**Verify:**

```bash
aws --version && terraform -version && docker --version
aws sts get-caller-identity
```

The last command must return an `Arn` ending in **`user/terraform-admin`** (not
`root`). If it errors, the keys were mistyped — re-run `aws configure`.

---

## Phase 1 — Resend (the email sender)

### 1.1 Account and domain

1. Sign up at resend.com. The free tier (100 emails/day, 3,000/month) covers a daily
   brief permanently.
2. **Domains** → **Add Domain** → enter `<yourdomain.com>`.
   - Verify the apex domain; a reputation-isolating subdomain is over-engineering for
     one daily brief.
   - **Do not enable "receiving".** This system only sends. Receiving adds an MX
     record at the domain root that will conflict with any future real mailbox.
3. Resend displays a table of DNS records: an **MX** and a **TXT** on
   `send.<yourdomain.com>` (SPF / bounce routing), a **TXT** on
   `resend._domainkey.<yourdomain.com>` (DKIM signing key), and a **TXT** on
   `_dmarc.<yourdomain.com>` (DMARC policy — marked recommended; add it).

### 1.2 Create the records (Route 53 instructions)

Route 53 → Hosted zones → your domain → **Create record**, once per row. Three Route
53 quirks that cause silent failures:

- **Type only the name prefix** (`send`, `resend._domainkey`, `_dmarc`) — Route 53
  appends the domain itself. Typing the full name creates the broken
  `send.yourdomain.com.yourdomain.com`.
- **MX values combine priority and host in one field**: `10 feedback-smtp.…amazonses.com`
  (Resend shows the priority in a separate column).
- **Don't add quotes to TXT values** — Route 53 quotes them itself.

Adding these records cannot affect an existing website on the domain: they are new
entries at new names, not edits to existing ones.

### 1.3 Verify and collect credentials

1. Back in Resend → **Verify**. Route 53 propagates fast; expect green within
   minutes (give it up to an hour). If one record stays red, the usual culprits are
   the doubled-domain name or a truncated DKIM value.
2. **API Keys** → **Create API Key** → permission **Sending access** only, scoped to
   the domain if offered. The `re_…` value is shown **once** → password manager.
3. Decide the from-address, e.g. `brief@<yourdomain.com>`. Nothing to configure — any
   address at the verified domain works.

**Verify / outputs of this phase:**

| Collected | Used in |
|---|---|
| Domain shows **Verified** in Resend | — |
| API key `re_…` (password manager) | SSM `…SMTP_PASSWORD` (Phase 6) |
| Username — literally the string `resend` | SSM `…SMTP_USERNAME` (Phase 6) |
| From-address | `smtp_from` tfvar (Phase 3) |

---

## Phase 2 — GitHub repository configuration

### 2.1 The `production` environment

The deploy job runs inside a GitHub environment; the AWS trust policy only accepts
OIDC tokens minted for it. Without the environment, deploys cannot authenticate.

Settings → Environments → **New environment** → name `production` → under
**Deployment branches**, restrict to `main`. Or via CLI:

```bash
gh api -X PUT repos/<owner>/<repo>/environments/production \
  -F "deployment_branch_policy[protected_branches]=false" \
  -F "deployment_branch_policy[custom_branch_policies]=true"
gh api -X POST repos/<owner>/<repo>/environments/production/deployment-branch-policies \
  -f name=main
```

Note: the editor's GitHub Actions extension flags `environment: production` in
deploy.yml as "not valid" until this environment exists — that warning is the check
working, not a YAML problem.

### 2.2 Branch protection on `main`

Deploys certify gated commits; protection makes "only gated commits reach main"
enforced rather than conventional. Required status check: **`gate / gate`** (the
reusable-workflow name), strict (branch must be up to date), enforced for admins,
force pushes and deletion blocked. No required reviewer approvals on a solo repo —
GitHub won't let you approve your own PR, so requiring one deadlocks every merge.

### 2.3 Repository variables

Settings → Variables → Actions. Set now:

```bash
gh variable set AWS_REGION --body "eu-west-2"
```

The other three (`AWS_DEPLOY_ROLE_ARN`, `ECR_REPOSITORY`, `LAMBDA_FUNCTION`) are
Terraform outputs — they get set in Phase 9, and the deploy workflow deliberately
no-ops until `AWS_DEPLOY_ROLE_ARN` exists.

---

## Phase 3 — Terraform state backend and prod configuration

### 3.1 Bootstrap the state backend (once)

```bash
cd infra/bootstrap
terraform init
terraform apply -var state_bucket_name=morning-brief-tf-state-<ACCOUNT_ID>
```

Bucket names are globally unique across AWS — suffixing the account ID is the
standard trick. Expect a short plan (state bucket + DynamoDB lock table); type `yes`.

**Verify:** the apply prints `state_bucket` and `lock_table` outputs.

### 3.2 Configure the prod environment

```bash
cd ../envs/prod
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
```

Fill `backend.hcl` with the two bootstrap outputs. In `terraform.tfvars` (gitignored —
deployment-specific decisions live here, never in committed code):

| Variable | Value | Notes |
|---|---|---|
| `audit_bucket_name` | `morning-brief-audit-prod-<ACCOUNT_ID>` | globally unique |
| `object_lock_mode` | **decide deliberately** | `COMPLIANCE` = records undeletable by anyone until retention expires — right for a real desk, irreversible. `GOVERNANCE` = WORM against the application (its role has no delete/bypass), but an admin can tear down — right for a time-boxed deployment |
| `retention_years` | `7` (compliance) or `1` (governance) | |
| `image_tag` | the **full SHA of current main** (`git rev-parse origin/main`) | must equal the tag pushed in Phase 4, or the Lambda creation fails with "image not found" |
| `smtp_from` | `brief@<yourdomain.com>` | the Resend-verified domain |
| `alert_email` | `<you@example.com>` | receives alarm notifications |
| `slack_channel_id` / `slack_team_id` | empty | enables later with one re-apply |
| `github_owner` / `github_repo` | your repo | deploy-role trust |

```bash
terraform init -backend-config=backend.hcl
```

---

## Phase 4 — ECR repository and the bootstrap image

The Lambda is created *from* an image, so the repository and image must exist first.

### 4.1 Create the repository alone

```bash
terraform apply -target=module.ecr
```

Terraform warns about targeted applies — expected; this is the legitimate use case.

### 4.2 Build and push — three things matter here

Build from a clean checkout of the exact commit in `image_tag`:

```bash
git switch main && git pull --ff-only
git rev-parse HEAD        # must equal image_tag in terraform.tfvars
```

```bash
cd infra/envs/prod
REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region eu-west-2 \
  | docker login --username AWS --password-stdin "${REPO%/*}"
docker build --platform linux/arm64 --provenance=false -t "$REPO:<the-sha>" ../../..
docker push "$REPO:<the-sha>"
```

The three load-bearing details:

1. **`--platform linux/arm64`** — the Lambda runs on Graviton. On Apple Silicon this
   builds natively and fast.
2. **`--provenance=false`** — without it, Docker attaches a build attestation that
   turns the pushed artifact into a multi-manifest image. **ECR accepts it; Lambda
   rejects it** at function creation with
   `InvalidParameterValueException: The image manifest, config or layer media type …
   is not supported`. This failed the first real deployment.
3. **The tag must equal `image_tag`** in tfvars.

**Verify (do not skip — this catches mistake #2 before Phase 5 does):**

```bash
aws ecr describe-images --repository-name morning-brief \
  --query 'imageDetails[].{tags: imageTags, mediaType: imageManifestMediaType}'
```

Correct: **exactly one entry**, your tag, media type
`application/vnd.docker.distribution.manifest.v2+json`.
Wrong: three entries (two untagged) — that's the provenance multi-manifest.

**Recovery if wrong:** ECR tags are immutable, so a corrected push under the same tag
is rejected. Delete first, then rebuild with the flag:

```bash
aws ecr batch-delete-image --repository-name morning-brief --image-ids imageTag=<the-sha>
# then delete any orphaned digests listed by describe-images:
aws ecr batch-delete-image --repository-name morning-brief --image-ids imageDigest=<sha256:…>
```

---

## Phase 5 — The full apply

```bash
terraform apply
```

Review the plan before `yes`:

- Expect roughly **29 to add, 0 to change, 0 to destroy** (the KMS key and ECR repo
  already exist from Phase 4).
- Find the `aws_s3_bucket_object_lock_configuration` block and confirm `mode` and
  `years` are what you decided in Phase 3. **If COMPLIANCE: this is the line you
  cannot take back.**

A failed partial apply is not a disaster — Terraform keeps what succeeded in state;
fix the cause and re-run `terraform apply` (it plans only the remainder).

**Verify:** apply completes and prints outputs including `github_deploy_role_arn`,
`batch_function_name`, `secrets_path`, `alerts_sns_topic_arn`.

---

## Phase 6 — Secrets into SSM

Terraform created the parameters with placeholder values and will never touch the
values again (`ignore_changes`). You set the real values once, out-of-band:

```bash
P=/morning-brief/production
aws ssm put-parameter --overwrite --type SecureString --name "$P/MORNING_BRIEF_LLM__ANTHROPIC_API_KEY"          --value '<sk-ant-…>'
aws ssm put-parameter --overwrite --type SecureString --name "$P/MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS"     --value '["<you@example.com>"]'
aws ssm put-parameter --overwrite --type SecureString --name "$P/MORNING_BRIEF_DELIVERY__EMAIL__SMTP_USERNAME"  --value 'resend'
aws ssm put-parameter --overwrite --type SecureString --name "$P/MORNING_BRIEF_DELIVERY__EMAIL__SMTP_PASSWORD"  --value '<re_…>'
```

- `RECIPIENTS` is a JSON array; add more addresses by re-running that one command.
- The SMTP username is **literally the word `resend`**; the API key is the password.
  There is no separate SMTP password to find.
- Each command must respond `"Version": 2` (or higher).

**Verify (checks versions, never values):**

```bash
aws ssm get-parameters-by-path --path /morning-brief/production \
  --query 'Parameters[].{name: Name, version: Version}' --output table
```

All four must show version ≥ 2. **Version 1 = still a placeholder** = the run will
fail at the LLM or SMTP step.

---

## Phase 7 — Confirm the alerts subscription

The apply subscribed `alert_email` to the SNS alarm topic; AWS emails a confirmation.

**Click only the "Confirm subscription" link.** The same email contains a smaller
deactivate/unsubscribe link — clicking it (then or later, it remains live) silently
kills the subscription, and alarms fire into the void.

**Verify:**

```bash
aws sns list-subscriptions-by-topic \
  --topic-arn $(terraform output -raw alerts_sns_topic_arn)
```

A healthy subscription shows a real ARN. `"PendingConfirmation"` = not yet clicked.
`"Deleted"` = the deactivate link was clicked.

**Recovery from "Deleted":** Terraform does not detect this drift (the API still
returns the subscription's shell), so a plain plan says "no changes". Force the
recreation, which sends a fresh confirmation email:

```bash
terraform taint 'module.observability.aws_sns_topic_subscription.email[0]'
terraform apply        # plan: 1 to add, 1 to destroy
```

---

## Phase 8 — The smoke test

```bash
aws lambda invoke --cli-read-timeout 0 \
  --function-name $(terraform output -raw batch_function_name) /dev/stdout
```

`--cli-read-timeout 0` stops the CLI giving up while the run does real work (1–3
minutes: cold start, data fetch, LLM call, delivery).

**Success** = the response metadata has **no `FunctionError` field**, and the brief
arrives at the recipient address from your verified domain. Check spam the first
time — new sending domains often start there.

**On any failure**, the logs name the stage; read from the bottom up:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/morning-brief-prod-batch \
  --start-time $(($(date +%s)*1000 - 600000)) \
  --query 'events[].message' --output text | tail -40
```

Failure modes actually seen or worth knowing:

| Symptom in logs | Cause | Fix |
|---|---|---|
| `AnalysisTimeoutError: Claude timed out after Ns` | `llm.timeout_seconds` too small for the model to generate the full structured brief (latency varies several-fold between runs) | raise it in `config/environments/production.yaml`; keep the Lambda timeout > worst case (primary + fallback both exhausting the budget) + overhead — both were raised after the first deployment (120s / 360s) |
| SMTP auth failure at delivery | placeholder still in SSM, or wrong key | Phase 6 verify, re-put the parameter |
| `ImageNotFound` / manifest errors at update | Phase 4 mistakes | Phase 4 recovery |

Note the run design: even a failed run writes its audit record to S3 first, then
raises so AWS counts the failure for the alarms. A failed smoke test still proves
most of the system.

**Also verify the audit trail:**

```bash
aws s3 ls s3://$(terraform output -raw audit_bucket_name)/runs/ --recursive
```

One JSON record per run, including failed ones.

---

## Phase 9 — Hand deploys to the pipeline

Until now, image pushes were manual. Set the three remaining variables and the
GitHub Actions workflow owns every future deploy:

```bash
gh variable set AWS_DEPLOY_ROLE_ARN --body "$(terraform output -raw github_deploy_role_arn)"
gh variable set ECR_REPOSITORY      --body "$(terraform output -raw ecr_repository_url)"
gh variable set LAMBDA_FUNCTION     --body "$(terraform output -raw batch_function_name)"
```

From the next merge to `main` touching `src/**`, `config/**`, `pyproject.toml`,
`uv.lock`, `Dockerfile`, or `.dockerignore`, the pipeline runs: quality gate → build
→ push (skipped if the commit's image already exists) → roll the Lambda → **verify
the rollout reached `Successful`**. Manual deploys of the current main: Actions →
Deploy → Run workflow.

**Verify with a real merge:** watch the run in the Actions tab, then confirm the
function runs the merge commit's image:

```bash
aws lambda get-function --function-name $(terraform output -raw batch_function_name) \
  --query 'Code.ImageUri' --output text
```

Division of ownership from here: **the pipeline owns the function's code** (image),
**Terraform owns its configuration** (timeout, memory, env vars) and ignores image
changes (`ignore_changes = [image_uri]`) — so a later `terraform apply` will not
revert a pipeline deploy.

Rollback = `git revert` the offending commit on main; the pipeline redeploys the
reverted state. (Re-deploying an old commit directly is not possible: the protected
environment restricts deploys to main's history.)

---

## Phase 10 — Stabilisation housekeeping

After a few scheduled runs (07:00 Europe/London, weekdays) have succeeded:

1. **Deactivate the `terraform-admin` access key** (IAM → user → Security
   credentials). OIDC handles all routine deploys; reactivate the key only for
   future `terraform apply` sessions.
2. **Dependabot PRs**: arrive weekly, grouped, bumping the SHA-pinned actions.
   The gate exercises `checkout`/`setup-uv` directly; the AWS/Docker actions are only
   proven on the next real deploy — merge while diffs are small.
3. Known cosmetic debt: Terraform warns the S3 backend's `dynamodb_table` parameter
   is deprecated in favour of `use_lockfile` — migrate when convenient.

## Phase 11 — Teardown (GOVERNANCE mode only)

When the deployment has served its purpose:

```bash
# 1. Empty the audit bucket — requires governance bypass (admin has it):
aws s3api list-object-versions --bucket <audit-bucket> …   # delete versions with
#    --bypass-governance-retention on each delete
# 2. Remove the `prevent_destroy` line in infra/modules/audit_s3/main.tf
#    (the deliberate "yes, I mean it" step), commit it.
# 3. cd infra/envs/prod    && terraform destroy
# 4. cd ../../bootstrap    && terraform destroy
# 5. Delete the GitHub variables and the production environment; revoke the
#    Resend key; deactivate/delete terraform-admin.
```

Under COMPLIANCE mode, step 1 is impossible until every record's retention expires —
that is the point of COMPLIANCE. Choose the mode in Phase 3 accordingly.

---

## Appendix — the complete pre-flight checklist

- [ ] Root user has MFA; `terraform-admin` exists; `aws sts get-caller-identity` shows it
- [ ] `aws`, `terraform`, `docker` installed and working
- [ ] Resend domain **Verified**; `re_…` key in password manager
- [ ] GitHub: `production` environment (main only); branch protection with `gate / gate`; `AWS_REGION` variable
- [ ] State backend bootstrapped; `backend.hcl` + `terraform.tfvars` filled; Object Lock mode consciously chosen
- [ ] ECR repo created; image pushed with `--provenance=false`; **describe-images shows one entry, docker manifest v2**
- [ ] Full apply clean; outputs captured
- [ ] All four SSM parameters at **version ≥ 2**
- [ ] SNS subscription shows a **real ARN**
- [ ] Smoke test: no `FunctionError`, email received, audit record in S3
- [ ] Three deploy variables set; one pipeline deploy observed succeeding
