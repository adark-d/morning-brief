# Deploying morning-brief on AWS — an engineer's learning guide

This guide teaches the **whole deployment from first principles** — the cloud concepts, every
AWS service we use, Infrastructure-as-Code with Terraform, what OIDC is, and a file-by-file tour
of the actual Terraform in this repo. It assumes you can read code but have not done much cloud
work. Read it top to bottom; each part builds on the last.

The goal is not just to deploy *this* project, but for you to understand the **patterns** so you
can reason about them on any team.

## Table of contents

0. [How to use this guide](#part-0--how-to-use-this-guide)
1. [The mental model: what we're deploying and why "serverless"](#part-1--the-mental-model)
2. [Cloud & AWS fundamentals (the vocabulary)](#part-2--cloud--aws-fundamentals)
3. [IAM and OIDC, from zero](#part-3--iam-and-oidc-from-zero)
4. [Infrastructure as Code & Terraform fundamentals](#part-4--infrastructure-as-code--terraform)
5. [The services in our stack, one by one](#part-5--the-services-in-our-stack)
6. [Walking our Terraform, file by file](#part-6--walking-our-terraform-file-by-file)
7. [The application side that makes it deployable](#part-7--the-application-side)
8. [The end-to-end flow](#part-8--the-end-to-end-flow)
9. [Security model summary](#part-9--security-model-summary)
10. [Architectural decisions & trade-offs](#part-10--architectural-decisions--trade-offs)
11. [How to practice, extend, and what to learn next](#part-11--how-to-practice-and-learn-next)

---

## Part 0 — How to use this guide

- **Concepts first, our code second.** Each AWS service is explained generically (what it is, why
  it exists, alternatives) *before* we look at how we wired it. That way you learn the transferable
  idea, not just our config.
- **Look things up as you go.** Keep the [AWS Glossary](https://docs.aws.amazon.com/glossary/latest/reference/glos-chap.html)
  open. When you hit a term, find it here first, then the AWS docs.
- **The repo is the lab.** Everything described lives in [`infra/`](../infra) and the runbook in
  [`infra/README.md`](../infra/README.md). The setup steps are in [`infra/AWS_SETUP.md`](../infra/AWS_SETUP.md).
- **You can't break anything by reading.** `terraform validate`, `terraform plan`, and reading code
  are all safe. Only `terraform apply` and `aws ... put/create/delete` change real resources.

---

## Part 1 — The mental model

### What morning-brief actually is, operationally

Two workloads, both tiny and bursty:

1. **The daily brief** — runs once on weekday mornings, takes ~30–60 seconds (the LLM call
   dominates), writes an audit record, sends an email, and exits. *This is the product.*
2. **An optional HTTP API** — to trigger a run on demand or read past records. Low traffic.

Notice what this is **not**: it is not a website with constant traffic, not a service that must be
"up" 24/7. It's a scheduled job plus a trickle of requests. **The shape of the workload determines
the right architecture** — this is the single most important lesson in the whole guide.

### "Serverless" and "scale-to-zero"

A traditional deployment runs a **server** (a virtual machine) that's always on, waiting for work.
You pay for it 24/7 even though our job runs for one minute a day. That's ~99.9% waste.

**Serverless** means you hand AWS your *code* and it runs it *on demand*, provisioning compute only
for the duration of each execution, then tearing it down. **Scale-to-zero** means when nothing is
happening, you run zero compute and pay (almost) nothing. For a once-a-day job this is the natural
fit: no idle server, no patching an OS, no capacity planning.

The trade-off is **cold starts**: the first execution after idle has to spin up the runtime
(a few seconds). For a daily batch where one LLM call takes 30+ seconds, a 2-second cold start is
irrelevant. For a high-frequency, latency-critical API it might matter — *shape of the workload again.*

### The cost argument (why this matters to a business)

| Design | ~Monthly | Why |
|---|---|---|
| **Our serverless design** | ~$3–5 + LLM | pay per execution; no idle anything |
| Always-on container + load balancer + managed DB | ~$80–100 | paying 24/7 for 1 min/day of work |

Choosing the wrong *shape* (a always-on server for a batch job) is the most common and most
expensive cloud mistake. The skill is matching the architecture to the workload.

---

## Part 2 — Cloud & AWS fundamentals

### Account, regions, availability zones

- An **AWS account** is the top-level container and billing boundary. Everything you create lives
  in one account (large orgs use *many* accounts via AWS Organizations for isolation).
- A **Region** is a geographic location (e.g. `eu-west-2` = London). You pick one; your resources
  live there. We use **eu-west-2** to match a London desk and the schedule's timezone.
- An **Availability Zone (AZ)** is an isolated datacenter within a region. Managed services like
  Lambda and S3 span AZs automatically for you — you rarely think about AZs unless you run your own
  servers/databases (which we don't).

### Managed services vs servers (the core trade)

A **managed service** is one where AWS operates the undifferentiated heavy lifting (the servers,
patching, scaling, replication) and gives you an API. S3 (storage), Lambda (compute), SQS (queues)
are managed. You give up some control; you gain not having to operate anything. Our entire design is
managed services glued together — there is **no server we log into**.

### How you talk to AWS

Three ways, all hitting the same APIs:
- **Console** — the web UI (good for learning, looking around, one-off clicks).
- **CLI** — `aws ...` commands (good for scripts and the one-off `put-parameter`).
- **SDKs / IaC** — code that calls the APIs. Our app uses the **boto3** Python SDK (e.g. to write to
  S3); our infrastructure uses **Terraform** (which calls AWS APIs to create resources).

Everything you do — click, CLI, or Terraform — is ultimately an authenticated API call. Which
brings us to the most important AWS topic: **who is allowed to make which calls.**

---

## Part 3 — IAM and OIDC, from zero

**IAM (Identity and Access Management)** is AWS's permission system. If you learn one AWS topic
deeply, make it this — it's where most real-world confusion and most security incidents live.

### The four-part question every API call answers

Every request is allowed or denied by evaluating policies that answer:

- **Principal** — *who* is asking? (a user, a role, a service)
- **Action** — *what* do they want to do? (e.g. `s3:PutObject`)
- **Resource** — *on what*? (e.g. a specific bucket ARN)
- **Condition** — *under what constraints*? (e.g. only over TLS, only from this account)

A **policy** is a JSON document of `Allow`/`Deny` statements over those four. Default is **deny**;
you must explicitly allow. An explicit `Deny` always wins.

```json
{
  "Effect": "Allow",
  "Action": ["s3:PutObject", "s3:GetObject"],
  "Resource": "arn:aws:s3:::morning-brief-audit-prod/runs/*"
}
```

> **ARN** = Amazon Resource Name, the globally-unique id of a resource, like
> `arn:aws:s3:::my-bucket` or `arn:aws:lambda:eu-west-2:123456789012:function:my-fn`. You'll see ARNs
> everywhere; they're how policies point at exactly one thing.

### Users vs roles (this trips everyone up)

- An **IAM user** is a long-lived identity with credentials (a password, and/or an access key). Think
  "a person's login" or "a static API key." Long-lived keys are a liability — if leaked, they work
  until rotated.
- An **IAM role** is an identity with **no permanent credentials**. Instead, a trusted principal
  *assumes* the role and receives **temporary** credentials (valid minutes to hours). Roles are how
  you give permissions to *things* — a Lambda function, an EC2 instance, a CI pipeline — without
  embedding secrets.

**Two policies attach to a role:**
1. **Trust policy** (a.k.a. assume-role policy) — *who is allowed to become this role?*
2. **Permission policy** — *what can the role do once assumed?*

Example from our project: the batch Lambda has an **execution role**. Its *trust policy* says
"the Lambda service may assume me"; its *permission policy* says "write to the audit bucket, read
the secrets, decrypt with the KMS key." The function never holds an access key — at runtime AWS
hands it temporary credentials for that role. This is the right way to give code permissions.

### What is OIDC, and why we use it for CI

**The problem:** GitHub Actions needs to deploy to AWS (push an image, update the Lambda). The naive
way is to store an AWS access key as a GitHub secret. That's a **long-lived credential sitting in a
third-party system** — exactly what we want to avoid. If it leaks, an attacker has standing AWS
access.

**OIDC (OpenID Connect)** is an identity protocol built on OAuth 2.0. In one sentence: *it lets one
system prove "I am who I say I am" to another using short-lived, cryptographically-signed tokens
instead of shared passwords.* You've used it without knowing — "Sign in with Google" is OIDC.

**How it works for GitHub → AWS (federation):**

1. You tell AWS to **trust GitHub as an identity provider** (an `aws_iam_openid_connect_provider`
   pointing at `token.actions.githubusercontent.com`). This is a one-time setup per account.
2. When a workflow runs, GitHub mints a short-lived **OIDC token (a JWT)** describing the run — which
   repo, which branch, etc. — and signs it.
3. The workflow calls AWS STS `AssumeRoleWithWebIdentity`, presenting that token.
4. AWS verifies the signature against GitHub's public keys, checks the token's claims against the
   role's **trust policy**, and if they match, returns **temporary** credentials (valid ~1 hour).
5. The workflow uses those to deploy. They expire automatically. **Nothing long-lived is stored.**

The trust policy is where you constrain *which* GitHub workflows can assume the role. Ours says:

```hcl
condition {
  test     = "StringEquals"
  variable = "token.actions.githubusercontent.com:aud"
  values   = ["sts.amazonaws.com"]               # the audience must be AWS STS
}
condition {
  test     = "StringLike"
  variable = "token.actions.githubusercontent.com:sub"
  values   = ["repo:adark-d/morning-brief:*"]    # only THIS repo's workflows
}
```

- `aud` (audience) = who the token is *for* (AWS STS).
- `sub` (subject) = who the token is *about* (our repo; you can tighten to a branch or
  GitHub Environment, e.g. `repo:owner/repo:ref:refs/heads/main`).

That's the whole magic: **a deploy identity with zero stored secrets, scoped to exactly one repo.**
This pattern (OIDC federation) is now the standard way to connect any CI system to any cloud.

### Least privilege

Grant the *minimum* permissions needed, nothing more. In our `iam` module the batch role can
`PutObject`/`GetObject`/`ListBucket` on the audit bucket but **not** `DeleteObject` (the store never
deletes; Object Lock would block it anyway, but we don't even grant it). The CI deploy role can push
to *one* ECR repo and update *one* Lambda — not "admin." When something is compromised, least
privilege is what limits the blast radius.

---

## Part 4 — Infrastructure as Code & Terraform

### Why IaC instead of clicking in the console ("ClickOps")

If you build infra by clicking, you get: no record of what exists, no review, no easy reproduction,
and "it works on my account but not the new one." **Infrastructure as Code** means your
infrastructure is *declared in version-controlled files*. Benefits:

- **Reproducible** — `terraform apply` recreates the same stack in any account/region.
- **Reviewable** — changes go through PRs like any code; `terraform plan` shows the diff *before* it
  happens.
- **Auditable** — git history is the record of every infra change and why.
- **Self-documenting** — the files *are* the documentation of what exists.

### What Terraform is

Terraform (by HashiCorp) is the most common IaC tool. You **declare the desired end state** in files
written in **HCL** (HashiCorp Configuration Language); Terraform figures out the API calls to make
reality match. It's **declarative** (you describe the *what*, not the step-by-step *how*).

**Core concepts:**

- **Provider** — a plugin that knows how to talk to a platform's API. We use the `aws` provider. (There
  are providers for GCP, Azure, GitHub, Datadog, Cloudflare… hundreds.)
- **Resource** — one managed object, e.g. `resource "aws_s3_bucket" "audit" { ... }`. Syntax is
  `resource "<type>" "<local-name>" { <arguments> }`. You reference it elsewhere as
  `aws_s3_bucket.audit.arn`.
- **Data source** — a *read-only* lookup of something that exists, e.g. `data "aws_caller_identity"
  "current" {}` to get your account id.
- **Variable** — an input (`var.region`). **Output** — a value the config exposes after apply
  (`output "bucket_name"`). **Local** — a computed value reused within a module (`local.name_prefix`).
- **State** — Terraform records *what it created* in a **state file**, mapping your config to real
  resource ids. This is how it knows, on the next run, what already exists and what changed.
- **`plan`** computes the diff (create/change/destroy) without doing anything. **`apply`** executes
  it. **`fmt`** formats. **`validate`** checks syntax/types.

### HCL in 60 seconds

```hcl
variable "region" {                     # an input, with a default
  type    = string
  default = "eu-west-2"
}

resource "aws_sqs_queue" "dlq" {        # declare a queue
  name                      = "my-dlq"
  message_retention_seconds = 1209600   # 14 days
}

output "dlq_arn" {                      # expose its ARN to callers
  value = aws_sqs_queue.dlq.arn         # reference another resource's attribute
}
```

Interpolation is `${...}`; e.g. `"arn:aws:lambda:${local.region}:${local.account_id}:function:${var.name}"`.

### Modules — reusable building blocks

A **module** is a folder of `.tf` files you can call with inputs, like a function. A *root module*
(what you actually `apply`) calls *child modules*. We split our infra into child modules
(`modules/kms`, `modules/audit_s3`, …) and a root (`envs/prod`) that wires them together. This is
exactly how you'd structure dev/uat/prod sharing the same building blocks (we discussed you don't
need multiple envs here — but the structure is ready for it).

```hcl
module "audit_s3" {                     # call the child module
  source          = "../../modules/audit_s3"
  bucket_name     = var.audit_bucket_name
  kms_key_arn     = module.kms.key_arn  # pass another module's output in
  retention_years = 7
}
```

### Remote state and locking (and the chicken-and-egg)

By default the state file is local (`terraform.tfstate`). For real projects you store it
**remotely** so a team shares one source of truth and so it survives your laptop. The standard AWS
pattern is **state in an S3 bucket + a DynamoDB table for locking** (the lock stops two people
applying at once and corrupting state).

**The chicken-and-egg:** the bucket that *holds* state must exist *before* you can use it as the
backend. So we have a tiny separate config — [`infra/bootstrap/`](../infra/bootstrap) — applied
**once with local state**, whose only job is to create the state bucket + lock table. After that, the
main config (`envs/prod`) uses `backend "s3"` pointing at them. You'll see this pattern on every
serious Terraform project.

### Terraform vs the alternatives (so you can speak to it)

- **CloudFormation** — AWS's native IaC (YAML/JSON). AWS-only; no separate state to manage (AWS
  tracks it). Terraform is multi-cloud and has a nicer language and ecosystem; most teams pick it.
- **AWS CDK / Pulumi** — write infra in a real programming language (TypeScript, Python). Powerful,
  but more moving parts. Terraform's declarative HCL is the lingua franca you'll meet most often.
- **Ansible** — config management (configuring servers), not really provisioning; different job.

---

## Part 5 — The services in our stack

For each: *what it is · why we chose it · how we use it · alternatives · gotchas.*

### ECR — Elastic Container Registry

- **What:** a private registry for Docker/OCI **container images** (like a private Docker Hub).
- **Why:** our app ships as a container image (it's too big for Lambda's zip limit because of
  pandas/numpy). The image has to live *somewhere* Lambda can pull it; that's ECR.
- **Our use:** one repository, `scan_on_push` (CVE scanning), `IMMUTABLE` tags (a tag can't be moved
  to a different image — deploys are traceable), a lifecycle rule to expire old images, KMS-encrypted.
- **Alternatives:** Docker Hub (public/rate-limited), GitHub Container Registry. For Lambda, ECR in
  the same account/region is simplest and fastest.
- **Gotcha:** Lambda image functions need the image to exist *before* the function is created — hence
  the "apply ECR first, push, then apply the rest" runbook ordering.

### Lambda — serverless functions

- **What:** run code without managing servers. You give Lambda a handler (an entry function); it runs
  it per-invocation, scales automatically, and you pay per request + compute-millisecond.
- **Why:** perfect for a daily batch — scale-to-zero, no idle cost, no server to operate.
- **Our use:** a **container-image** function (`package_type = "Image"`), architecture **arm64**
  (Graviton — cheaper and matches our build), `memory_size = 1024` (pandas is memory-hungry),
  `timeout = 180`s, env vars for non-secret config, `CMD` set to `run_handler`.
- **The handler model:** AWS invokes a function you name (`module.function`). Ours is
  `morning_brief.aws_handlers.run_handler` — it runs the pipeline once and returns. The *same image*
  can also serve the API via `api_handler` (Mangum) by overriding the `CMD`.
- **Cold start:** first invoke after idle pulls/optimises the image (~seconds). Irrelevant for a batch.
- **Alternatives:** **Fargate** (serverless containers, for long-running/always-on work — adds a load
  balancer for HTTP), **EC2** (raw VMs you manage). We don't need either; our job is < 1 min.
- **Gotcha:** Lambda's filesystem is read-only except `/tmp`. That's why production must write the
  audit record to **S3**, not a local path.

### S3 — object storage (+ Object Lock = WORM)

- **What:** virtually-infinite, durable (11 nines) object storage. You store "objects" (files) under
  "keys" (paths) in "buckets."
- **Why:** our audit records are write-once documents read rarely — a perfect fit, far cheaper and
  simpler than a database, and S3 offers storage-enforced immutability.
- **Our use:** one object per run, key `runs/<date>/run_<uuid>.json`. The bucket has:
  - **Versioning** — every write is a new version (required for Object Lock).
  - **Object Lock, COMPLIANCE mode, 7 years** — **WORM** (Write Once Read Many). Once written, an
    object version **cannot be deleted or overwritten by anyone — including the AWS root user —**
    until the retention expires. This is storage-*enforced* immutability for compliance, on top of
    the app's frozen-model guarantee. **It can only be enabled at bucket creation and cannot be
    undone** — which is why we treated the retention period as a deliberate, irreversible decision.
  - **SSE-KMS** encryption at rest, **TLS-only** bucket policy, **all public access blocked**,
    lifecycle to **Glacier → Deep Archive** for cheap long-term storage.
- **Alternatives we rejected:** **Postgres/RDS** (over-provisioned, ~$15–45/mo always-on, weaker
  policy-based immutability, and forces a VPC + NAT), **DynamoDB** (great for keyed access but weaker
  WORM and a 400KB item ceiling). See the ADR for the full reasoning.
- **Gotcha:** because Object Lock writes a *new version* rather than rejecting a duplicate key, the
  app *also* enforces idempotency at write time (`PutObject IfNoneMatch`), which we verified.

### KMS — Key Management Service (and "envelope encryption")

- **What:** managed encryption keys. A **customer-managed key (CMK)** is a key you own; AWS services
  use it to encrypt your data, and access to *use* the key is itself an IAM-controlled permission.
- **Envelope encryption (the concept):** you don't encrypt big data directly with the master key.
  Instead the service asks KMS to **generate a data key** (`GenerateDataKey`), encrypts the data with
  that, and stores the encrypted data key alongside. To read, it asks KMS to **`Decrypt`** the data
  key, then decrypts the data. That's why our batch role needs *both* `kms:GenerateDataKey*` (to
  write encrypted objects) and `kms:Decrypt` (to read them, and to decrypt SSM SecureStrings).
- **Why a CMK (not the free AWS-managed key):** control over the key policy, rotation, and a clean
  audit trail of key use. We enable automatic rotation.
- **Our use:** one CMK encrypts both the audit bucket (SSE-KMS) and the SSM secrets. One key keeps
  the policy surface small.
- **Gotcha:** "encrypted" and "who can decrypt" are separate. Encrypting data is useless if the wrong
  principals can call `Decrypt` — the key's usage permissions are the real control.

### SSM Parameter Store — configuration & secrets

- **What:** a key-value store for config. **SecureString** parameters are encrypted with KMS.
- **Why:** secrets (the Anthropic key, Resend password, recipients) must not live in code, YAML, or
  the image. They live here, encrypted, and the Lambda reads them at startup.
- **Our use:** parameters under `/morning-brief/production/<EXACT_ENV_VAR_NAME>`. At cold start the
  app's `bootstrap_secrets()` reads them and injects them as environment variables. The parameter's
  *basename is the exact env var name*, so the mapping is identity.
- **Secrets-in-Terraform trap & our fix:** if Terraform set the *values*, they'd be stored in the
  state file (plaintext-ish) — a leak. So Terraform creates the parameter *resources* with a
  placeholder and `lifecycle { ignore_changes = [value] }`; a human sets the real value out-of-band
  with `aws ssm put-parameter`. **Terraform owns the slot; you own the secret.** Remember this — it's
  a common interview question and a real-world footgun.
- **Alternatives:** **Secrets Manager** (built-in rotation, slightly pricier ~$0.40/secret/mo). SSM
  SecureString is free for standard params and fine when you don't need automated rotation yet.

### EventBridge Scheduler — the cron

- **What:** a managed scheduler that invokes a target on a cron/rate expression. The modern successor
  to "EventBridge rules with a schedule."
- **Why:** we need "run the Lambda at 07:00 London on weekdays" without operating our own cron server.
- **Our use:** `cron(0 7 ? * MON-FRI *)` with **timezone `Europe/London`** (so it's 07:00 *local*
  year-round, handling BST automatically — a subtle but important detail), a **retry policy**, and a
  **dead-letter queue** for invocations it can't deliver.
- **Alternatives:** classic EventBridge rule (older, no native timezone); a cron on a server (defeats
  serverless). Scheduler is the right modern choice.

### SQS — Simple Queue Service (used here as a DLQ)

- **What:** a managed message queue.
- **Why here:** a **dead-letter queue (DLQ)**. If the Scheduler tries to invoke the Lambda and fails
  even after retries, the failed event is parked in the DLQ instead of vanishing — so you can see and
  alarm on "a scheduled run never got delivered."
- **Our use:** one queue, 14-day retention, SSE on; the Scheduler's role may `SendMessage` to it; an
  alarm fires if it's ever non-empty.

### CloudWatch — logs, metrics, alarms

- **What:** AWS's observability service. **Logs** (our app's JSON logs land here automatically),
  **Metrics** (numeric time series like Lambda `Errors`), **Alarms** (fire an action when a metric
  crosses a threshold), and **metric filters** (turn matching log lines into a metric).
- **Our use — three alarms (the "reliability trio"):**
  1. **Run failed** — Lambda `Errors ≥ 1` (a run threw).
  2. **Retries exhausted** — DLQ depth `≥ 1` (Scheduler gave up).
  3. **Missed run** — a **metric filter** counts our success log line
     (`{ $.event = "run_finished" && $.status = "success" }`) into a metric; an alarm fires if a day
     passes with **zero** successes (`treat_missing_data = breaching`). This catches the sneaky case
     where the schedule never fired at all — *absence* of success, which a failure-only alarm misses.
- **Gotcha:** alarming on *absence* needs `treat_missing_data = "breaching"`, otherwise "no data"
  reads as "fine."

### SNS + Chatbot — alert delivery

- **SNS (Simple Notification Service):** pub/sub topics. Alarms publish to an SNS **topic**; the topic
  fans out to **subscriptions**.
- **Our use:** one topic; an **email** subscription (you must click "confirm" once — AWS won't email
  strangers), and an optional **Slack** route via **AWS Chatbot** (needs a one-time workspace
  authorization in the console to get the workspace id).
- **Alternatives:** SNS → Lambda → any webhook; PagerDuty for real on-call paging.

---

## Part 6 — Walking our Terraform, file by file

### Layout

```
infra/
├── bootstrap/        # remote-state backend (run once, local state)
├── modules/          # reusable building blocks (one concern each)
│   ├── kms/  ecr/  audit_s3/  secrets/  iam/  batch_lambda/  observability/  cicd/
└── envs/prod/        # the root you apply: wires the modules with prod values
```

Each module has the same four files by convention:
- `main.tf` — the resources.
- `variables.tf` — its inputs.
- `outputs.tf` — what it exposes to callers.
- `versions.tf` — required Terraform + provider versions (no provider *config* — that's the root's job).

This **module = inputs + resources + outputs** shape is the single most useful Terraform habit.

### `bootstrap/` — the state backend

Creates the S3 state bucket (versioned, encrypted, public-access-blocked, TLS-only) and the DynamoDB
lock table. Has `prevent_destroy = true` so you can't accidentally delete the thing holding all your
state. Applied **once**, with local state, before anything else. ([infra/bootstrap/main.tf](../infra/bootstrap/main.tf))

### `modules/kms` — the encryption key

One CMK with rotation on and a key policy that gives the **account root** admin (so the key is never
orphaned) while *usage* is granted to roles via their IAM policies (kept out of the key policy so it
stays stable as roles change). Plus a friendly `alias/morning-brief-prod`. ([infra/modules/kms/main.tf](../infra/modules/kms/main.tf))

### `modules/ecr` — the image registry

The repository with scan-on-push, immutable tags, KMS encryption, and a lifecycle policy keeping the
last N images. Outputs the repo URL (used as the Lambda's `image_uri`). ([infra/modules/ecr/main.tf](../infra/modules/ecr/main.tf))

### `modules/audit_s3` — the immutable store (the important one)

The bucket with `object_lock_enabled = true` (only settable at creation), versioning, a default
**COMPLIANCE 7-year** retention, SSE-KMS with bucket-key, full public-access block, a TLS-only bucket
policy, and a Glacier/Deep-Archive lifecycle. `prevent_destroy = true`. Read the comments here — this
is where the WORM guarantee is implemented. ([infra/modules/audit_s3/main.tf](../infra/modules/audit_s3/main.tf))

### `modules/secrets` — SSM SecureString slots

Creates one SecureString parameter per secret name, encrypted with the CMK, each with
`ignore_changes = [value]` and a placeholder — so values are set out-of-band and never enter state.
The parameter path basename equals the exact env var name. ([infra/modules/secrets/main.tf](../infra/modules/secrets/main.tf))

### `modules/iam` — least-privilege roles

Two roles:
- **Batch execution role** — logs to its own group; S3 put/get/list on the audit prefix (**no
  delete**); KMS `GenerateDataKey*` + `Decrypt`; SSM read on `/morning-brief/production/*`.
- **Scheduler role** — `lambda:InvokeFunction` on the function + `sqs:SendMessage` on the DLQ, with a
  `SourceAccount` condition to prevent the *confused-deputy* problem (a service being tricked into
  acting for another account).

**A neat trick worth understanding:** this module *constructs* the Lambda/DLQ/log-group ARNs from
their **names** (passed in as strings) rather than referencing the `batch_lambda` module's outputs.
Why? If `iam` depended on `batch_lambda` and `batch_lambda` depended on `iam` (for the role), you'd
have a **dependency cycle** Terraform can't resolve. By deriving ARNs from agreed names, `iam` depends
on nothing downstream, the Lambda consumes the role, and the graph stays acyclic. Recognising and
breaking cycles like this is a real Terraform skill. ([infra/modules/iam/main.tf](../infra/modules/iam/main.tf))

### `modules/batch_lambda` — the function + schedule

The container Lambda (arm64, memory/timeout, env vars, `CMD`), an explicitly-created **log group**
(so *we* own its retention rather than letting Lambda auto-create it forever), the **SQS DLQ**, and
the **EventBridge Scheduler** (cron + timezone + retry + dead-letter). ([infra/modules/batch_lambda/main.tf](../infra/modules/batch_lambda/main.tf))

### `modules/observability` — alarms + alerts

The SNS topic, email + optional Slack subscriptions, and the three alarms described in Part 5
(including the log **metric filter** for missed-run). Slack resources are conditional
(`count = var.slack_channel_id == "" ? 1 : 0`) so the config is valid whether or not you enable Slack
— a useful pattern for optional features. ([infra/modules/observability/main.tf](../infra/modules/observability/main.tf))

### `modules/cicd` — OIDC + deploy role

The GitHub OIDC provider (toggle-able if the account already has one) and the deploy role whose trust
policy is scoped to our repo (Part 3) and whose permissions are scoped to ECR push +
`lambda:UpdateFunctionCode`. ([infra/modules/cicd/main.tf](../infra/modules/cicd/main.tf))

### `envs/prod` — the root that wires it together

This is what you actually `terraform apply`. It:
- declares the **provider** (region, default tags) and the **`backend "s3"`** (partial — you supply
  the bucket/table at `init` time via `backend.hcl`),
- defines **locals** for the shared names (function, DLQ, SSM path) and the split between **secret**
  parameters (SSM) and **non-secret** Lambda env vars,
- calls every module in dependency order, passing one module's outputs as another's inputs,
- exposes **outputs** (ECR URL, function name, deploy-role ARN) that you feed into the GitHub Actions
  variables. ([infra/envs/prod/main.tf](../infra/envs/prod/main.tf))

`terraform.tfvars.example` and `backend.hcl.example` show exactly what you fill in; the real
`terraform.tfvars`/`backend.hcl` are git-ignored.

---

## Part 7 — The application side

Infrastructure is only half of it; a few application choices make the code *deployable*. These live
outside `infra/` but are part of the deployment story.

- **The `Dockerfile`** — multi-stage, on the AWS Lambda Python base image (so native wheels match the
  runtime platform). It **installs the project** (not just copies the source) so its package metadata
  exists — otherwise the API's `importlib.metadata.version("morning-brief")` crashes on cold start.
  One image, two entry points selected by `CMD`. See the
  [container recipe in the README](../README.md#run-as-a-container-aws-lambda-image).
- **Config-dir override** — the app resolves its YAML config from `MORNING_BRIEF_CONFIG_DIR`, which
  the image sets to where it copied `config/`. Without it the source-tree-relative path would break
  once packaged.
- **SSM bootstrap** — `bootstrap_secrets()` runs at cold start, reads the SecureString params, and
  injects them as env vars. It no-ops outside Lambda (and when no region is set), so local/test runs
  never reach for AWS.
- **Mangum (for the API, Phase 2)** — an ASGI-to-Lambda adapter that lets the FastAPI app run on
  Lambda without a web server. We chose it over the Lambda Web Adapter for simplicity (no sidecar);
  the rationale is recorded in [ADR 0001 §4.1](adr/0001-deployment.md).

---

## Part 8 — The end-to-end flow

**Deploy (whenever you merge code):**
1. PR → the CI gate (`ci.yml`) runs ruff/mypy/pyright/pytest/pip-audit. Broken code is stopped here.
2. Merge to `main` → `deploy.yml` triggers.
3. It assumes the AWS deploy role via **OIDC** (no keys), builds the **arm64** image, **pushes to
   ECR** tagged with the commit SHA, then `aws lambda update-function-code` repoints the function.

**Run (every weekday 07:00 London):**
4. **EventBridge Scheduler** invokes the batch Lambda.
5. The handler runs the pipeline: fetch market data → LLM analysis → guardrails → render → **send
   email via Resend** → write the immutable record to **S3**.
6. The desk receives the brief; Lambda scales back to zero.

**When something goes wrong:** the run is recorded as a `FAILED` audit record (not a silent crash),
the Scheduler retries, a persistent failure lands in the **DLQ**, and the **alarms** notify you via
email/Slack. **No downtime concept** — it's a daily batch, so deploying between runs disrupts nothing
(see the earlier walkthrough).

---

## Part 9 — Security model summary

How the requirements in [security.md](security.md) map to AWS controls:

| Requirement | How it's met |
|---|---|
| Secrets never in code/logs/image | SSM SecureString + KMS; injected at runtime; values never in TF state |
| Encrypted, immutable audit storage | S3 SSE-KMS + **Object Lock (WORM)** + versioning + TLS-only + public-access-blocked |
| Least privilege | Per-purpose roles scoped to exact actions/resources; no shared "admin" role at runtime |
| No long-lived CI credentials | **GitHub OIDC** → short-lived assumed role |
| Encryption everywhere | KMS at rest (S3, SSM, ECR); TLS in transit (bucket policy denies non-TLS) |
| Defence in depth | App-level frozen models *and* storage-level WORM; CI gate *and* runtime alarms |

(TLS termination + rate-limiting for the HTTP API are Phase 2, via API Gateway + ACM + WAF.)

---

## Part 10 — Architectural decisions & trade-offs

The full record is [ADR 0001](adr/0001-deployment.md) (an **Architecture Decision Record** — a short
doc capturing *what* was decided and *why*; a habit worth adopting on any team). The headline calls:

- **Lambda over Fargate/EC2** — the workload is a 1-minute daily job. Scale-to-zero beats paying for
  idle compute. *Reconsider if* you ever need >15 min runtime or constant low-latency traffic.
- **Container image over zip** — pandas/numpy exceed Lambda's 250 MB zip limit; images allow 10 GB.
- **S3 + Object Lock over a database** — write-once compliance records suit object storage; a DB would
  be costlier, weaker on immutability, and force a VPC + NAT. *Reconsider if* you need rich relational
  queries (then Athena over the S3 JSON, or a real DB at much higher volume).
- **No VPC / no NAT** — every dependency is reachable over public AWS/HTTPS endpoints, so we avoid the
  ~$32/mo NAT gateway and all the subnet/route-table complexity. *Reconsider if* you introduce a
  private resource (e.g. RDS).
- **SSM SecureString over Secrets Manager** — free and sufficient; no rotation needed yet.
- **OIDC over stored keys** — no long-lived CI credential to leak.
- **Resend SMTP now, native SES later** — ship on the zero-code path; move to credential-less,
  role-based SES sending in Phase 3.

The meta-lesson: **every decision is a trade-off tied to the workload's shape and scale.** "It
depends" is the correct senior answer — this guide gives you the *axes* it depends on.

---

## Part 11 — How to practice and learn next

**Do this hands-on (cheap/free):**
1. Read [`infra/AWS_SETUP.md`](../infra/AWS_SETUP.md), make a personal AWS account, create the admin
   user, `aws configure`.
2. `cd infra/envs/prod && terraform init -backend=false && terraform validate` — read the output.
3. Run `terraform plan` (after a real `init` against a sandbox account) and **read every line** — this
   is the single best way to learn what each resource does.
4. Change one thing (e.g. an alarm threshold), `plan`, and see the diff.
5. Deliberately break something (a wrong ARN) and read the error — error-reading is a core skill.

**Concepts to drill (in priority order):**
1. **IAM** — users vs roles, trust vs permission policies, assume-role, least privilege. Everything
   else sits on this.
2. **Terraform** — resources, state, modules, plan/apply, remote state. Build a toy module.
3. **The service trio you'll meet everywhere** — S3, Lambda, IAM. Then queues (SQS), pub/sub (SNS),
   observability (CloudWatch).
4. **OIDC federation** — once it clicks, you'll use it for every CI→cloud connection.

**Resources:**
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/) — the
  canonical "how to think about cloud design" (the 6 pillars). Read the *Cost* and *Security* pillars.
- [Terraform: Get Started — AWS](https://developer.hashicorp.com/terraform/tutorials/aws-get-started)
  — official, hands-on.
- [AWS IAM docs — policies and permissions](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html).
- [GitHub OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services).
- [AWS Lambda — container images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html).
- [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html).
- This repo's [ADR 0001](adr/0001-deployment.md) and [infra/README.md](../infra/README.md) — your real,
  worked example to keep coming back to.

**Questions to be able to answer (self-check):**
- Why a role and not an access key for the Lambda? For CI?
- What exactly is in an OIDC token, and what stops *another* repo from assuming our deploy role?
- Why can't Object Lock be turned on after the bucket exists? What does COMPLIANCE vs GOVERNANCE mean?
- Why does the batch role need *both* `GenerateDataKey*` and `Decrypt`?
- Where do secret *values* live, and why not in Terraform state?
- What breaks if you deploy a bad image at 06:59, and what catches it?
- Why no VPC? When *would* you need one?

If you can answer those without notes, you understand this deployment at a level you can defend in a
team. Come back to the code with the questions in mind — the `infra/` files will read like prose.
