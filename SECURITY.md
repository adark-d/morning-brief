# Security policy

## Report a vulnerability

Use [GitHub's private vulnerability reporting](https://github.com/adark-d/morning-brief/security/advisories/new).
Do not post security findings in public issues or pull requests.

Include:

- The affected file, component, or commit.
- Steps to reproduce the issue and its possible impact.
- Relevant logs or screenshots, with credentials and personal information removed.

This is a personal project, so response times may vary. Follow-up questions and
updates will stay in the private report.

## Scope

Reports can cover:

| Area | Location |
|---|---|
| Application and shared utilities | `src/` |
| Manual commands | `scripts/` |
| Configuration templates | `config/` |
| Packaging and container builds | `pyproject.toml`, `uv.lock`, `Dockerfile` |
| CI and deployment workflows | `.github/workflows/` |
| AWS resources and permissions | `infra/` |

Dependency vulnerabilities are relevant when they affect this project's use of the
dependency. Include issues in the project's AWS permissions or configuration, even
if exploiting them requires some existing access.

## Supported versions

Security fixes target the latest code on `main`. Older commits and deployed images
are not maintained separately. Rebuild and redeploy to receive fixes.
