# Security

The threat model and controls for morning-brief. Report suspected vulnerabilities
privately to the maintainers — do not open a public issue.

## Secrets & configuration
- All secrets are `SecretStr`, sourced only from `MORNING_BRIEF_*` environment
  variables (see `.env.example`). They never appear in code, YAML, logs, or API
  responses, and are unwrapped only at the composition root.
- Config is strictly namespaced: only `MORNING_BRIEF_<SECTION>__<FIELD>` binds.
  Nested settings are `BaseModel` (not `BaseSettings`), so a stray unprefixed env
  var (e.g. `NAME`, `TIMEOUT_SECONDS`) cannot leak into or corrupt configuration.

## API
- Every `/briefs` endpoint requires a bearer token (`HTTPBearer`). Auth is
  **fail-closed**: with no token configured, protected routes return 503. The token
  is compared in constant time. `/health` is intentionally open.
- Inputs are validated at the edge (`run_id` as `UUID`, `on` as `date`), rejecting
  injection (e.g. glob metacharacters) before it can reach storage. The audit store
  also escapes glob characters as defence in depth.
- Responses use explicit DTOs (`BriefRunResponse`) that never carry recipient
  addresses or the raw market snapshot; errors return a generic `ErrorResponse`
  envelope and never leak internals or stack traces.

## Data at rest
- JSON audit records are written `0600` inside `0700` directories. This is defence
  in depth — the primary control is deployment (a dedicated service user on a
  restricted, encrypted volume). The Postgres backend defers access control to the
  database.

## Dependency scanning
```bash
uvx pip-audit        # ephemeral; run in CI and before each release
```

## Deferred hardening (Phase 9 — deployment)
- **TLS required.** The bearer token is a credential; the API must run behind TLS
  (ingress / reverse proxy). It must not be exposed over plain HTTP.
- **Rate limiting** on `POST /briefs/run` — it triggers a paid LLM call, so a leaked
  token enables cost amplification / DoS.
- **CI gate** running `ruff`, `mypy`, `pyright`, `pytest`, and `pip-audit` on every
  change (no CI exists yet).
- **Token rotation / per-caller identity.** Auth is a single shared token today —
  no per-caller identity and no independent revocation. Revisit if multiple clients
  or audit-by-caller are required.
