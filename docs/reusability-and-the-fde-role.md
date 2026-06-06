# Reusable AI Solutions and the Forward Deployed Engineer Role

A mental model for how an AI Forward Deployed Engineer (FDE) builds, reuses, and
contributes AI solutions — using this project (the morning brief) as the worked
example. Written to be re-read on its own.

---

## The six responsibilities this maps to

For reference throughout this document:

| # | Responsibility |
|---|---|
| **R1** | Translate business problems into AI solution designs with objectives, metrics, and rollout plans. |
| **R2** | Build AI agents, tools, and workflows using the firm's central AI platform. |
| **R3** | Demonstrate the art of the possible and drive AI adoption across investment teams. |
| **R4** | Run working sessions with business users, gather feedback, and iterate on solutions. |
| **R5** | Build and document reusable artifacts (prompt templates, workflows, configurable components). |
| **R6** | Contribute code, tools, and patterns back to the central AI platform as firm-wide reusable assets. |

---

## 1. The most important misconception to clear up

> "If the platform provides the plumbing, do I even write code?"

**Yes — you write a lot of code.** The question is never *how much* code, it's *which layer*:

| Kind of code | How often | What it is | Responsibility |
|---|---|---|---|
| **Solution code** | Most of the time | The agent / tool / workflow for one team, which *calls* the platform | R2, R3, R4 |
| **Platform code** | Now and then | A reusable piece you promote *into* the platform so the whole firm can call it | R6 |

You are not writing less code. You are writing **higher-leverage** code: the
recipe and the plating, not the oven.

---

## 2. The kitchen analogy

The central AI platform is the **kitchen**: ovens, gas, electricity, extractor
fans, the delivery van. You don't rebuild the oven every time you cook.

- You bring the **recipe** (the prompt).
- You bring the **ingredients** (the team's data).
- You **plate the dish** for a specific customer (the team's workflow).
- If you invent a sauce everyone wants, you hand the recipe to the central
  kitchen so every chef can use it (**that's R6**).

In this project, you *built an oven from scratch* (`AnthropicAnalysisEngine`) —
on purpose, to learn how ovens work. On the job, the oven already exists; you
cook with it.

---

## 3. The platform provides the plumbing; you build on top

### What the platform almost certainly provides (you call it, you don't rebuild it)

- **LLM gateway** — model access, retries, fallback chain, cost tracking, caching.
  (In this project: everything inside `AnthropicAnalysisEngine`.)
- **Auth & permissions** — who may use which model and which data.
- **Observability** — logging, cost dashboards, usage metrics.
- **Possibly:** a document store / retrieval, delivery channels (Slack/Teams/email),
  a baseline guardrail layer.

### What you build on top (your actual deliverable)

- The **prompt template** (versioned) — the domain instruction.
- The **output schema** — the shape of the answer you want back.
- The **workflow** — fetch data → call the platform's LLM → format → deliver.
- The **domain logic** specific to the business problem.
- The **trust and quality work** — what "good" looks like, the guardrails,
  the metrics, the iteration with users.

---

## 4. Worked scenario: "Flag the top 3 risk-factor changes in this 10-K vs last year"

> An equity analyst asks for a tool that compares a company's latest 10-K filing
> against last year's and flags the most important risk-factor changes.

Here is what you'd actually write — annotated with **who built what**:

```python
# ---- YOU write the solution (the workflow) ----
filing_now  = platform.documents.fetch(ticker, "10-K", year=2026)   # platform tool — you CALL it
filing_prev = platform.documents.fetch(ticker, "10-K", year=2025)   # platform tool — you CALL it

result = platform.llm.analyze(                  # the LLM gateway — you CALL it (do NOT rebuild it)
    prompt = RISK_DIFF_PROMPT,                  # <-- YOUR artifact: a versioned prompt template
    inputs = {"current": filing_now, "prior": filing_prev},
    schema = RiskSummary,                       # <-- YOUR artifact: the output shape you want
)

platform.deliver.slack("#equity-research", result)   # platform delivery — you CALL it
```

That ~15 lines plus a prompt and a schema is a **complete, valuable AI tool.**
You didn't write 500 lines of gateway plumbing, because the platform has it.

### Mapping the scenario to this project

| Scenario piece | Built by | Equivalent in the morning-brief project |
|---|---|---|
| `platform.llm.analyze(...)` | **Platform** | `AnthropicAnalysisEngine` (retries, fallback, cost, auth — all inside) |
| `RISK_DIFF_PROMPT` | **You** | the prompt YAML templates (Phase 4) |
| `RiskSummary` schema | **You** | `BriefAnalysis` (the structured output shape) |
| the workflow wiring | **You** | the pipeline orchestrator (Phase 6) |
| `platform.deliver.slack(...)` | **Platform** | `DeliveryChannel` / `ChannelRouter` |

### Which responsibilities this scenario exercises

- **R2** — you built an AI tool on the platform.
- **R3** — a working, trustworthy tool an analyst will actually adopt.
- **R4** — you'll run sessions with the analyst and iterate `RISK_DIFF_PROMPT`.
- **R1** — before any of this, you framed the problem ("compare risk sections,
  surface the 3 most material changes") with a clear success measure.

---

## 5. You have TWO reuse audiences — and they need different things

Conflating these is the most common FDE mistake.

| Audience | What they reuse | How they consume it | Responsibility |
|---|---|---|---|
| **Investment / trading teams** (non-engineers) | Prompt templates, workflows, **configurable components** | **Configuration, never code** — they change a YAML, a threshold, a recipient list | **R5** |
| **The central AI platform** (engineers) | Code, tools, **patterns** | You contribute it back as a shared library / tool | **R6** |

**Example of R5 (team reuse via config):** the same "document-diff-and-summarize"
workflow you built for the equity team is adopted by the credit team by pointing
it at credit agreements instead of 10-Ks — they change configuration, not code.

**Example of R6 (platform reuse via code):** you notice every FDE keeps writing
their own messy "fetch a filing and split it into sections" helper. You write a
clean, configurable, documented, tested version and contribute it:

```python
# Now it's a platform capability everyone calls:
sections = platform.documents.extract_sections(filing, kind="risk_factors")
```

That is you writing **platform code** — promoting a one-off helper into a
firm-wide asset.

---

## 6. What makes an artifact actually reusable / contributable

When the goal is "reusable across teams" or "contributable to the platform," an
artifact needs four properties. Practice all four:

1. **Configurable, not forked** — behaviour varies by config (YAML/params), so a
   new team adopts it without editing code. *(In this project: model choice,
   guardrail thresholds, channels, recipients, prompt name+version all live in
   config, not code.)* → **R5**
2. **Interface-bounded** — it depends on an abstraction, not a concrete, so it
   drops into a different context. *(In this project: `core/interfaces`.)* → **R6**
3. **Contract-tested** — a parametrized test suite proves any implementation
   honours the contract. *(In this project: the audit-store contract tests run
   against both the JSON and mock implementations.)* → **R6**
4. **Documented for the consumer** — a non-author can adopt it from the docs
   alone. The half people skip; your role names it explicitly. → **R5, R6**

---

## 7. The reusability tiers of what we built here

Not everything is reusable — and that's by design. The architecture deliberately
separates the reusable plumbing from the bespoke domain.

| Tier | Reusability | Examples from this project | Reuse target |
|---|---|---|---|
| **Tier 1** | Drop-in (domain-agnostic) | `FrozenModel` + `UtcDatetime`; the layered config machinery (Settings + YAML + env + `SecretStr`); `HealthStatus` + health-check convention; the Jinja2 safe-render boundary | **Platform (R6)** |
| **Tier 2** | Reusable with light genericization | `JsonAuditStore` mechanics (→ `JsonStore[T]`); the AnalysisEngine recipe (structured output + validation retry + fallback + cost); the `ChannelRouter` fan-out; the DataProvider resilience pattern | **Platform (R6)** |
| **Tier 3** | Domain-specific (rewritten per project) | `MarketSnapshot`, `BriefAnalysis`, yfinance tickers, the prompt content, the email copy, guardrail thresholds | **One team (R5) / bespoke** |

The seam that makes this split possible is `core/interfaces` + dependency
inversion. That is not academic — it is the line along which you hand things to
the platform (Tier 1/2) versus keep them team-specific (Tier 3).

> **Note on "packaged" vs "reusable in principle":** today all of this lives in
> one project package. It is reusable *as patterns and copyable code*, but it is
> not yet *extracted into a shared library*. That is correct — you extract when a
> **second** project actually needs it, not speculatively. The seams already exist,
> so extraction later is a copy-or-lift job, not a rewrite.

---

## 8. Everything mapped to your responsibilities

| Responsibility | Where it shows up in practice |
|---|---|
| **R1** — translate business problems into designs | The reframing + metrics + discovery questions (this project's architecture doc reframed "email data at 7am" into "compress 60 min of context into 3 min of decision support"). That framing artifact is itself reusable across engagements. |
| **R2** — build agents/tools/workflows on the platform | The scenario's workflow: fetch → `platform.llm.analyze(...)` → format → deliver. You write the solution; you call the platform's plumbing. |
| **R3** — demonstrate value, drive adoption | The user-facing artifact (the brief, the risk summary) *plus* the trust mechanics that make people adopt it: audit trail, "wrong numbers are worse than no numbers," confidence scores, graceful degradation, disclaimers. |
| **R4** — working sessions, feedback, iterate | Prompt versioning is the literal infrastructure for this: iterate prompts from user feedback without code deploys; `prompt_version` metadata lets you prove v2 beat v1. |
| **R5** — build & document reusable artifacts for teams | Configurable components + prompt templates other teams adopt by changing config. The **document** half matters — docs so a non-author can adopt it. |
| **R6** — contribute back to the platform | Promote Tier 1/2 patterns into shared platform tools (e.g. `extract_sections`, a `JsonStore[T]`, the contract-test harness). Less frequent, high leverage. |

---

## 9. Why build the plumbing by hand in Projects 1–10 if the platform provides it?

Because the value isn't the code — it's the **calibrated judgment** it gives you:

1. **Consume the platform well** — you know what retry/fallback/cost-tracking
   *should* do, so you use the platform's knobs correctly instead of guessing.
2. **Spot what's missing** — when the platform lacks something (say, per-source
   partial-failure handling, or a delivery router), you recognise the gap and can
   contribute the pattern back. *(R6)*
3. **Design to the platform's grain** — your solutions fit because you understand
   the abstractions underneath them.

You build the oven once so that, forever after, you are excellent at cooking with
one — and you know when the kitchen needs a new appliance.

---

## 10. One-line summary

> Most of the time you write **solution code** — prompts, schemas, and workflows
> that *call* the platform and deliver value to one team (R2–R5). Occasionally you
> write **platform code** — promoting a reusable pattern back so the whole firm
> benefits (R6). The architecture you practise in Projects 1–10 trains the
> judgment to know which is which.
</content>
