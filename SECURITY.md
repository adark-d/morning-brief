# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** via GitHub:
**Security tab → "Report a vulnerability"** (private vulnerability reporting is
enabled on this repository). Do not open a public issue for security findings.

You can expect an acknowledgement within a few days. This is a solo-maintained
project; fixes for confirmed issues are prioritised ahead of all other work.

## Scope

In scope: the application code (`src/`), the GitHub Actions workflows
(`.github/workflows/`), and the Terraform under `infra/`.

Out of scope: vulnerabilities in third-party dependencies with no exploitable
path through this codebase (these are tracked via `pip-audit` in CI and
Dependabot), and issues requiring privileged access to the deployment's AWS
account.

## Supported versions

The `main` branch and the currently deployed image (always built from `main`)
are the only supported versions. There are no maintained release lines.

## Security posture

For how the system handles secrets, authentication, data at rest, and the
controls the deployment provides, see the security design document:
[docs/security.md](docs/security.md).
