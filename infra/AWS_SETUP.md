# Setting up AWS for Terraform (one-time manual setup)

This is the manual groundwork to do **once**, before running the Terraform in
[README.md](README.md). It has no Terraform safety net, so it's spelled out click by click.

**Goal:** end up with an admin login on your machine so that this command works:

```bash
aws sts get-caller-identity
```

When that prints your account ID, Terraform can authenticate and you can run the deploy runbook.

Time: ~15 minutes. You only do this once.

---

## Step 1 — Create an AWS account

1. Go to <https://aws.amazon.com> → **Create an AWS Account**.
2. Enter an email, account name (e.g. `morning-brief`), and a payment card (this deployment
   costs ~$3–5/month; new accounts also get a free tier).
3. Verify your phone number and choose the **Basic (free) support** plan.

The email/password you just made is the **root user** — the most powerful login. You'll secure
it next and then stop using it.

## Step 2 — Protect the root user, then set it aside

1. Sign in as root → search **IAM** in the top bar → open it.
2. You may see a warning to add MFA to the root user — do it: **Add MFA** → use an authenticator
   app (Google Authenticator, 1Password, etc.).
3. That's all root is for. Everything from here uses the admin user you create next.

## Step 3 — Create an admin user for Terraform

Terraform's first run creates IAM roles, a KMS key, and the audit bucket, so it needs admin rights.

1. In **IAM** → **Users** → **Create user**.
2. **User name:** `terraform-admin`. Leave "provide console access" **unchecked** (this is a
   CLI-only identity). Click **Next**.
3. **Permissions:** choose **Attach policies directly** → tick **`AdministratorAccess`** → **Next**
   → **Create user**.
4. Open the new `terraform-admin` user → **Security credentials** tab → **Create access key**.
5. Pick **Command Line Interface (CLI)**, tick the acknowledgement, **Next** → **Create access key**.
6. **Copy the Access key ID and the Secret access key now** (the secret is shown only once) —
   or **Download .csv**. Keep them private; never commit them.

> The access key is a long-lived credential. It is only needed for the first `terraform apply`
> from your machine — after that, deploys run through the GitHub OIDC role (no keys). See
> **Cleanup** at the bottom to deactivate it once the deployment is stable.

## Step 4 — Install the tools

On macOS (Homebrew):

```bash
brew install awscli terraform        # terraform: brew tap hashicorp/tap first if needed
# Docker Desktop: https://www.docker.com/products/docker-desktop/  (needed to build/push the image)
```

Verify:

```bash
aws --version
terraform version
docker --version
```

## Step 5 — Configure the CLI

Run `aws configure` and paste the key from Step 3:

```bash
aws configure
# AWS Access Key ID     : <paste the Access key ID>
# AWS Secret Access Key : <paste the Secret access key>
# Default region name   : eu-west-2
# Default output format  : json
```

This writes `~/.aws/credentials` and `~/.aws/config`. **Use `eu-west-2`** — it matches the
deployment's region and the schedule's Europe/London timezone.

## Step 6 — Verify

```bash
aws sts get-caller-identity
```

Expected — your account and the admin user:

```json
{
  "Account": "123456789012",
  "Arn": "arn:aws:iam::123456789012:user/terraform-admin"
}
```

If you see this, AWS is ready. ✅

---

## You're ready — next steps

Go to **[README.md → First deploy](README.md#first-deploy-manual--creates-real-partly-irreversible-infrastructure)**
and run the runbook. Before you start, have these to hand (the README explains where each goes):

- An **Anthropic API key**.
- A **Resend** account + API key and a **verified sending domain** (for the email).
- Your **recipient list**.
- A **globally-unique bucket name** for the audit store, e.g. `morning-brief-audit-prod-<your-suffix>`.

---

## Cleanup / good practice (optional, later)

- Once deploys run through CI (the OIDC role), **deactivate** the `terraform-admin` access key in
  IAM → Users → Security credentials. Re-activate only when you need to run Terraform locally again.
- More secure long-term alternative to an IAM user: enable **IAM Identity Center (SSO)**, give
  yourself an admin permission set, and run `aws configure sso` instead of using an access key.
  Either approach works for Terraform; the access-key path above is the fewest steps to get going.
