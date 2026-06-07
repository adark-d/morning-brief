# ADR 0001 — Production deployment on AWS

- **Status:** Accepted
- **Date:** 2026-06-07
- **Deciders:** Engineering
- **Applies to:** deploying `morning-brief` to production on AWS

This document is both a decision record *and* an implementation guide. A new
engineer should be able to read it top-to-bottom and build the deployment without
further context.

## 1. Context

`morning-brief` is two small, intermittent workloads, not a always-on service:

1. **The daily brief (`morning-brief run`)** — the product. Runs once on weekday
   mornings, takes ~30–60s (the LLM call dominates), and exits with a status code.
   It needs outbound internet (Anthropic, market data, email) and durable storage
   for the audit record.
2. **The HTTP API (`morning-brief serve`)** — an optional, low-traffic internal
   tool to trigger a run on demand and retrieve past audit records.

Because both are tiny and bursty, the guiding principle is **serverless,
scale-to-zero, no idle infrastructure**. Paying for an always-on server, load
balancer, NAT gateway, or database at this volume would dominate the bill while
sitting idle 99.9% of the time.

Constraints carried in from the codebase:
- Secrets come only from `MORNING_BRIEF_*` environment variables (see `.env.example`).
- `SECURITY.md` requires the deployment to provide **TLS**, **rate-limiting on
  `POST /briefs/run`**, **encrypted/restricted audit storage**, and a path for
  **token rotation**.
- The audit trail must be **immutable** (compliance artifact).
- `yfinance` pulls in `pandas`, so the deployment artifact is large — this rules out
  plain Lambda zip packaging and points to a **container image**.

## 2. Decision summary

| Area | Decision |
|---|---|
| Compute | **One container image (ECR)** run on **AWS Lambda** — batch + API |
| Batch trigger | **EventBridge Scheduler** → batch Lambda (`cron`, Europe/London) |
| API | **API Gateway HTTP API** → API Lambda (same image, Lambda Web Adapter) |
| Audit store | **S3** with **Object Lock (WORM)** + SSE-KMS + versioning + lifecycle |
| Email | **SES** for production (native, IAM-role based); **Resend SMTP** as the zero-code on-ramp |
| Secrets | **Secrets Manager** (or SSM Parameter Store SecureString) + **KMS** |
| Networking | **No VPC, no NAT** — Lambda uses managed internet egress |
| Observability | **CloudWatch Logs** (JSON) + **CloudWatch Alarms** → **SNS** |
| IaC | **Terraform** (remote state in S3 + DynamoDB lock) |
| CI/CD | **GitHub Actions** via **OIDC** (no long-lived AWS keys) |

Estimated cost: **~$3–5/month + LLM usage** (≈$1/month of Anthropic calls).

## 3. Architecture

```
        EventBridge Scheduler                         API Gateway (HTTP API)
   cron(0 7 ? * MON-FRI *)  Europe/London        route throttling = rate limit
   (retry policy + DLQ)                            + WAF + ACM TLS + custom domain
                 │                                              │
                 ▼                                              ▼
      Lambda: morning-brief run                     Lambda: FastAPI (Web Adapter)
                 └────────────  ONE container image from ECR  ────────────┘
                 │              │                │                    │
                 ▼              ▼                ▼                    ▼
           Anthropic API    SES (email)    S3 audit bucket      Secrets Manager / SSM
           Market data      (IAM role)     versioning+ObjectLock (KMS-encrypted)
        (internet egress, no VPC / no NAT)  SSE-KMS, lifecycle
                          │
                          ▼
        CloudWatch Logs (JSON) + Alarms ──► SNS ──► email / Slack
```

Everything is regional and managed; there are no servers, subnets, or gateways to
operate.

## 4. Decisions in detail

### 4.1 Compute — one container image on Lambda

- **Single image** built from the repo (`Dockerfile`), pushed to **ECR**, used by
  *both* functions. One artifact, one build, one place for dependencies.
- **Why a container image (not a zip):** `pandas`/`yfinance` exceed Lambda's 250 MB
  zip limit comfortably; container images allow up to 10 GB.
- **Why Lambda (not Fargate/EC2):** the workload is a ~1-minute daily job plus a
  trickle of API calls. Lambda is scale-to-zero with no idle cost, no cluster, and
  no load balancer. The 15-minute limit and cold start (~2–5s with pandas) are
  irrelevant for a daily batch and acceptable for an internal API where the LLM call
  dominates latency anyway.
- **Two entrypoints from one image:**
  - *Batch Lambda* — handler invokes the orchestrator (equivalent of `morning-brief run`).
  - *API Lambda* — runs the FastAPI app via the **AWS Lambda Web Adapter** (the app
    serves normally; the adapter bridges API Gateway ↔ ASGI). The image's `CMD` is
    overridden per function.

### 4.2 Audit store — S3 with Object Lock (not Postgres)

**Decision:** implement an `S3AuditStore` and use it in production. Keep the existing
`JsonAuditStore` (filesystem) for local/dev/test. Do **not** build a Postgres backend.

- **Layout:** one object per run, key `runs/<YYYY-MM-DD>/run_<uuid>.json`.
  - `record()` → `PutObject` with `IfNoneMatch` for idempotency.
  - `get_by_id()` → resolve via a small index prefix or `ListObjectsV2` by suffix.
  - `query_by_date()` → `ListObjectsV2` on the date prefix.
  - `get_latest()` → list newest date prefix, pick max `triggered_at`.
- **Immutability:** **Object Lock in compliance mode** with a retention period
  (e.g. matching the firm's record-retention policy) — storage-enforced WORM, on top
  of the code's frozen-model guarantee. Requires **versioning** and must be enabled
  **at bucket creation** (cannot be retrofitted).
- **At rest:** **SSE-KMS** (customer-managed key); bucket policy denies non-TLS access
  and blocks all public access.
- **Lifecycle:** transition to Glacier / Deep Archive after N days for cheap long
  retention.
- **Why not Postgres:** at ~22 records/month a relational DB is over-provisioned and
  becomes the single largest cost (~$15–45/mo always-on); it provides weaker
  (policy-based) immutability than Object Lock; and — critically — RDS lives in a VPC,
  which would force the Lambdas into a VPC and reintroduce a NAT gateway (~$32/mo),
  undoing the lean serverless design. If ad-hoc analytical queries are ever needed,
  **Athena over the S3 JSON** answers them serverlessly. Revisit a database only when
  a genuine relational/reporting need appears at much higher volume.

### 4.3 Email — SES for production, Resend to start

Delivery is behind the `DeliveryChannel` interface, so the provider is a swap, not a
rewrite.

- **Production target: SES via a native `SesDeliveryChannel`** (new `DeliveryChannel`
  implementation using `boto3` `ses:SendEmail`). The win is **no stored credential** —
  the Lambda's IAM role grants send permission, so there is no SMTP password to
  manage, rotate, or audit. SES also gives native bounce/complaint handling (SNS),
  in-region sending, and low cost.
  - Setup: verify the sending domain, enable **DKIM**, configure **SPF** and
    **DMARC**, set a custom **MAIL FROM** domain, and request **production access**
    (SES starts in a sandbox).
- **On-ramp: Resend over SMTP (zero code).** The existing `EmailDeliveryChannel`
  works unchanged — point it at `smtp.resend.com` (`username=resend`,
  `password=<RESEND_API_KEY>` from Secrets Manager). Resend's free tier covers a daily
  brief comfortably. Use this to ship before SES production access is granted.
- **Why SES as the destination:** one vendor/IAM/billing/observability surface, no
  third-party processor in the data flow, and a credential-less (role-based) send.
  Resend wins on instant setup and free tier, which is exactly why it's the on-ramp.

### 4.4 Scheduling — EventBridge Scheduler

- A single schedule: `cron(0 7 ? * MON-FRI *)` with **time zone `Europe/London`** so
  the brief lands at 07:00 local year-round (handles BST). This is the source of truth
  for *when*; keep it consistent with `schedule_cron` in config (which documents the
  intended cadence).
- Configure a **retry policy** and a **dead-letter queue (SQS)** so a transient 07:00
  failure retries and a persistent failure is captured and alerted.
- The pipeline already degrades gracefully and always writes an audit record, so a
  partial outage produces a `FAILED`/`PARTIAL` record rather than silence.

### 4.5 API — API Gateway HTTP API

- **HTTP API** (cheaper/simpler than REST API) → API Lambda.
- **Rate limiting** (a `SECURITY.md` requirement) is satisfied by API Gateway
  **route-level throttling** on `POST /briefs/run`, plus an optional **WAF** rate rule.
- **TLS** via **ACM** on a custom domain; HTTP is not exposed.
- App-level auth is unchanged: fail-closed bearer token, constant-time comparison.
- Scale-to-zero: no cost when no one calls it.

### 4.6 Secrets & configuration

- **Secrets** (`MORNING_BRIEF_*`) live in **Secrets Manager** or **SSM Parameter
  Store SecureString** (SSM is free for standard parameters if rotation isn't needed),
  encrypted with **KMS**:
  - `MORNING_BRIEF_LLM__ANTHROPIC_API_KEY`
  - `MORNING_BRIEF_API__AUTH_TOKEN`
  - `MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS`
  - (only if using Resend/SMTP) the SMTP password
- They are injected as environment variables at function start; nothing secret is
  baked into the image.
- **Non-secret config** stays in `config/*.yaml` inside the image; `MORNING_BRIEF_ENVIRONMENT=production` selects `production.yaml`.
- Set `MORNING_BRIEF_AUDIT__BACKEND=s3` and the S3 bucket/region for production once
  `S3AuditStore` exists.

### 4.7 Networking — no VPC, no NAT

Because every dependency is reachable over the public AWS/HTTPS endpoints (S3,
Secrets Manager, SES, KMS) or the internet (Anthropic, market data), the Lambdas run
**outside a VPC** and use **managed internet egress (free)**. This removes the NAT
gateway, subnets, and route tables entirely. (A VPC + S3/KMS gateway/interface
endpoints would only be needed if a future private resource — e.g. RDS — is
introduced, which this design deliberately avoids.)

### 4.8 Observability

- **Logs:** the app already emits structured JSON (per-stage timing, per-provider
  timing, cost per run) → **CloudWatch Logs** natively.
- **Alarms → SNS** (email/Slack/PagerDuty):
  - **Job failure** — batch Lambda errors or the run exits non-zero.
  - **Missed run** — no successful run by, say, 07:15 (alarm on absence of a success
    metric/log).
  - **Error rate** on the API.
  - **LLM cost anomaly** — `cost_usd` exceeds a threshold.
- **Dashboards:** CloudWatch (or ship to Datadog) using the existing `run_id`,
  `stage`, `duration_ms`, `cost_usd`, `severity` fields.

### 4.9 IaC & CI/CD

- **Terraform** with remote state in **S3** and locking in **DynamoDB**. Separate
  state per environment (`dev`, `prod`) via directories or workspaces.
- **GitHub Actions** authenticates to AWS with **OIDC** (a short-lived assumed role —
  no stored AWS keys). Pipeline: run the existing gate (ruff, mypy, pyright, pytest,
  pip-audit) → build image → push to ECR → `terraform apply` (or update function code).

## 5. Security — mapping `SECURITY.md` to AWS controls

| Requirement (SECURITY.md) | AWS implementation |
|---|---|
| TLS required | ACM certificate on API Gateway; no HTTP listener |
| Rate-limit `POST /briefs/run` | API Gateway route throttling + optional WAF rate rule |
| Secrets never on disk/in logs | Secrets Manager/SSM + KMS; injected at runtime; log scrubbing |
| Encrypted, restricted audit storage | S3 SSE-KMS + Object Lock (WORM) + TLS-only, public-access-blocked bucket policy |
| Token rotation path | Secrets Manager rotation; or move to per-caller keys later |
| Least privilege | Separate IAM roles for batch vs API (see §8); no shared role |
| No long-lived CI credentials | GitHub OIDC → scoped deploy role |

## 6. Cost estimate

At one run/day plus a trickle of API calls, there is essentially **no fixed
infrastructure cost** (no NAT, ALB, or always-on compute):

| Item | ~Monthly |
|---|---|
| Anthropic (the real cost) | ~$1 |
| Lambda (batch + API) | ~$0 (well within free tier) |
| API Gateway HTTP API | ~$0 |
| S3 (audit) + KMS | pennies |
| Secrets Manager (~3 secrets) | ~$1.20 (or $0 on SSM standard) |
| CloudWatch, ECR | pennies |
| SES | ~$0 (cheap per email) |
| **Total** | **~$3–5/month + LLM** |

For contrast, a Fargate + ALB + NAT + RDS design would be ~$80–100/month for the same
workload — the cost of choosing the wrong compute and storage shapes.

## 7. Required code changes (prerequisites)

These land in the repo *before* the Terraform, each behind the existing gate:

1. **`Dockerfile`** — multi-stage, `uv`, `python:3.13-slim` (or AWS Lambda base
   image); installs deps, copies `src/` and `config/`, sets the entrypoint. Compatible
   with the Lambda Web Adapter for the API function.
2. **`S3AuditStore`** (`infrastructure/storage/s3_audit_store.py`) — implements the
   `AuditStore` interface against S3 (§4.2), plus an `s3` branch in
   `_build_audit_store` and the relevant `AuditSettings` fields (bucket, region,
   prefix). Local/dev/test keep `json`.
3. **`SesDeliveryChannel`** (`infrastructure/delivery/ses_delivery_channel.py`) —
   implements `DeliveryChannel` via `boto3` `ses:SendEmail`, plus a `ses` branch in
   `_build_channel`. (Skip if starting on Resend-SMTP, which needs no code.)
4. **Lambda handlers** — a thin `handler.py`: one entry that runs the orchestrator
   (batch), and the Web Adapter wiring for the API.
5. **CI extension** — build → push to ECR → deploy, gated on the existing checks.

All of these are additive and use existing extension points (interfaces +
composition root); no business logic changes.

## 8. Terraform layout

```
infra/
├── modules/
│   ├── ecr/             # image repository
│   ├── audit_s3/        # bucket: versioning, Object Lock, SSE-KMS, lifecycle, policy
│   ├── secrets/         # Secrets Manager / SSM params + KMS key
│   ├── batch_lambda/    # batch function + EventBridge Scheduler + DLQ
│   ├── api/             # API Lambda + API Gateway HTTP API + WAF + ACM + domain
│   ├── observability/   # log groups, alarms, SNS topic + subscriptions
│   ├── iam/             # task/execution roles (least privilege)
│   └── cicd/            # GitHub OIDC provider + deploy role
└── envs/
    ├── dev/             # state + var values
    └── prod/
```

- **Remote state:** S3 bucket (versioned, encrypted) + DynamoDB lock table.
- **Roles (least privilege):**
  - *Batch role* — `s3:PutObject`/`GetObject`/`ListBucket` on the audit bucket;
    `secretsmanager:GetSecretValue` (its secrets); `ses:SendEmail`; `kms:Decrypt`;
    CloudWatch Logs.
  - *API role* — `s3:GetObject`/`ListBucket` (read-only audit); read the API token
    secret; CloudWatch Logs. **No** `ses:SendEmail`, **no** S3 write.
  - *CI deploy role* — assumed via OIDC; scoped to ECR push + the specific Terraform-
    managed resources.

## 9. Implementation plan (phased)

**Phase 0 — code prerequisites** (repo PRs, gate green)
1. `Dockerfile` + a local "run in container" check.
2. `S3AuditStore` + composition wiring + contract tests (run the existing audit-store
   contract suite against it with a mocked/`moto` S3).
3. (If going native) `SesDeliveryChannel` + tests. Otherwise configure Resend-SMTP.
4. Lambda handlers.

**Phase 1 — the product in production** (Terraform)
5. Remote state, ECR, KMS, Secrets/SSM.
6. `audit_s3` (Object Lock at creation), `iam`, `batch_lambda` + EventBridge Scheduler
   + DLQ, `observability` (failure + missed-run alarms).
7. First scheduled brief runs in prod, writing to S3. **This alone delivers the value.**

**Phase 2 — the API**
8. `api` module: API Gateway HTTP API + Lambda + throttling + WAF + ACM + custom domain.

**Phase 3 — hardening**
9. Secret rotation, cost alarms, SES production access + DMARC, Glacier lifecycle,
   dashboards.

## 10. Consequences

**Positive**
- Near-zero fixed cost; scales to zero; minimal operational surface.
- Storage-enforced immutable audit trail (WORM) — strong compliance posture.
- One image, one IaC repo, OIDC CI — reproducible and secure by construction.
- Resolves two known gaps: the ephemeral `./audit/prod` path and the unbuilt
  Postgres backend (both replaced by S3).

**Negative / trade-offs**
- Lambda cold starts add a few seconds to the first API call after idle (immaterial
  for an internal tool; the LLM call dominates).
- S3 is not a query engine — analytical queries need Athena or a downstream
  projection (acceptable; not needed today).
- SES requires up-front domain verification and a sandbox-exit request.

**Risks & mitigations**
- *Missed 07:00 run* → EventBridge retries + DLQ + a missed-run alarm.
- *Object Lock retention is irreversible by design* → choose the retention period
  deliberately with compliance before creating the bucket.
- *Cost amplification via a leaked API token* → API Gateway throttling + WAF + cost
  alarm; rotate the token.

## 11. Alternatives considered

| Alternative | Why not (for this workload) |
|---|---|
| **Fargate (scheduled task + service + ALB)** | Container-service semantics, but adds an ALB (~$16/mo) and likely a NAT for no benefit at this scale. Reconsider only if Lambda's 15-min limit or cold starts ever bite. |
| **Postgres / Aurora audit store** | Over-provisioned at ~22 records/mo; largest cost in the system; weaker immutability than Object Lock; forces a VPC + NAT. |
| **DynamoDB audit store** | Great for keyed access and serverless, but S3 Object Lock gives stronger WORM, no 400 KB item ceiling, and a simpler one-object-per-run model. Viable if low-latency keyed reads at scale ever matter. |
| **EFS + existing `JsonAuditStore`** | Zero code change, but no WORM, higher cost than S3, single-filesystem, and would pull Lambda into a VPC. A bridge at best; S3 is the right destination. |
| **Lambda zip packaging** | `pandas`/`yfinance` exceed the 250 MB limit; container image is required. |

## 12. Open questions

- **Audit retention period** for Object Lock — confirm with compliance before bucket
  creation (it cannot be shortened afterward in compliance mode).
- **API exposure** — public (WAF + bearer) vs internal-only (private API / VPN). Decide
  before Phase 2.
- **Alert routing** — email, Slack, or PagerDuty for CRITICAL alarms.
- **Region** — single region assumed; confirm data-residency requirements.
