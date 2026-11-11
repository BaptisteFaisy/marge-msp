# Architecture Decisions — Marge

Short ADRs. Format: **Context / Decision / Consequences**. Each one is a rule the code base must keep; if a decision is reversed, add a new ADR that supersedes it instead of editing history.

---

## ADR-001 — Margin is computed by code, never by a model

**Context.** An LLM can read a contract and answer a question, but it cannot be trusted with arithmetic: it drifts, it rounds, it invents a plausible number, and the same question gives two answers. Every figure in Marge ends up in a commercial decision (a renegotiation, a billing proposal), so a wrong number is a business incident, not a bug.

**Decision.** All figures come from `marge.calc` (pure Python, standard library only, `Decimal` arithmetic) or are copied verbatim from a source field. No model output is ever parsed into an amount. The `billableHours` field of a classification (Annex C) is copied by code from the logged duration, not produced by the model (ENF-IA-01).

**Consequences.**
- The calculation is deterministic, unit-testable and reproducible offline: the Annex D golden case (4 620 € / 3 725 € / 895 € = 19.4 % / 9 h = 990 €) is asserted on every pull request via `marge.cli smoke`.
- The model cannot answer "approximately" — if the topic does not hold the figure, the agent must say so.
- Every new indicator needs code and a test; there is no "just ask the model" shortcut. Accepted cost: slower to add metrics, faster to defend them.

---

## ADR-002 — AI proposes, a human validates (three gates)

**Context.** Three steps cannot be decided by a fixed rule: matching client identities across three tools, reading clauses out of PDFs, and judging whether a piece of work was inside a contract. All three are probabilistic and all three can damage a client relationship if wrong.

**Decision.** Exactly three human validation gates, each with a named role and an audit record (author, date, reason):
1. **Client matching** — the model proposes with a confidence score, the Financial Controller validates (EF-REF-01).
2. **Contract clauses** — Bedrock Data Automation extracts, the Controller validates field by field with the source passage displayed (EF-CTR-03).
3. **Out-of-scope classifications** — the model proposes with the cited clause, the Account Manager validates above the 15-minute floor (EF-CLS-03).

Nothing AI-produced has financial standing before validation (ENF-IA-02): an unvalidated contract yields `INCOMPLETE` margin, unvalidated hours are never counted as detected unbilled hours, an unvalidated match never merges two clients.

**Consequences.**
- The demo always includes the validation step; the portal is a first-class component, not an admin afterthought.
- Throughput is bounded by human review — mitigated by the confidence threshold, the 15-minute floor and the decision memory (ADR-003 corollary: a ruled category never re-asks).
- Every gate needs an audit row and a test; the acceptance matrix tracks them one by one.

---

## ADR-003 — Levels, never people

**Context.** An effort-tracking tool inside an MSP is easily read as employee surveillance. That kills adoption faster than any technical flaw, and it is also a privacy problem: payroll data would become an input of a commercial calculation.

**Decision.** The system stores `N1 | N2 | N3 | ARCHITECT` and nothing else. The loader strips the engineer identifier on the way in (`strip_personal_data`), hourly costs are kept per level with effective dates, and no dashboard, export, prompt or test may contain a named person (ENF-CONF-01, ENF-CONF-02). The rule is written into the HLD, not only into the code.

**Consequences.**
- Cost of work is computed as hours × level rate; per-person productivity is structurally impossible to produce.
- A future request for individual reporting is a product decision requiring a new ADR, not a data change — the column no longer exists.
- Test doubles and generated data must respect it: the fake sources carry levels only, and the golden fixtures follow the same shape.

---

## ADR-004 — Unattached hours are never spread

**Context.** Real time-tracking is imperfect: some work is logged with no client, or with a client that no longer matches an alias. The easy fix — distributing those hours proportionally across clients — silently distorts every margin and destroys trust in the whole dashboard.

**Decision.** Hours with no resolved client go into an explicit `UNASSIGNED` bucket (`UNASSIGNED_CLIENT_ID`), displayed separately and counted in the coverage indicator. They are never allocated, never apportioned, never hidden. The same logic applies to coverage: a month below 80 % coverage is flagged `ESTIMATE` rather than being presented as exact (spec 12.4).

**Consequences.**
- Total margin can look "worse" than a smoothed version would — that is the honest figure, and the coverage indicator explains why.
- Fixing the data is the remedy (add the alias, correct the export), so the coverage KPI is on every dashboard (EF-ADM-02).
- Allocation rules exist only for tooling costs, where a documented basis (`PER_CLIENT`, `PER_ACCOUNT`, `PER_MANAGED_RESOURCE`, `PER_LABOUR_HOUR`) is a contractual choice, not a guess.

---

## ADR-005 — One `Store` Protocol, two backends (SQLite local, DynamoDB on AWS)

**Context.** The team needs a full pipeline that runs offline in CI and on a laptop, and a deployed version on AWS with durable, shared state. Two divergent persistence layers would double the surface and let bugs hide in the gap.

**Decision.** A single `Store` Protocol in `src/marge/store/base.py` (composed of `ClientRepository`, `MatchRepository`, `ContractRepository`, `WorkRepository`, `CostRepository`, `AnalyticsRepository`, `AuditRepository`, `SettingsRepository`), implemented twice: SQLite for local/CI/demo, DynamoDB for deployment. Methods take and return domain dataclasses only. boto3 is imported lazily, inside the DynamoDB implementation, so the test suite never needs it.

**Consequences.**
- CI stays offline and fast (≤ 5 minutes, ADR-006) and the demo can run with no AWS account.
- Any new query is added to the Protocol first, then to both backends, with the same test running against both (shared fakes in `tests/fakes/fake_store.py`).
- The Protocol is the seam that keeps the domain and the calculation free of I/O.

---

## ADR-006 — CI verdict in 5 minutes, tests offline

**Context.** A long CI is a CI people bypass. The team rule is a verdict within 5 minutes per job (user rule, 2026-10-24), and the test suite must be usable without AWS credentials or network.

**Decision.** Every GitHub Actions job declares `timeout-minutes: 5`, uses `concurrency` with `cancel-in-progress`, `fetch-depth: 1` and path filters. The pull-request job runs ruff, the size guard (`< 500` lines per file, `< 50` per function), the offline pytest suite and the Annex D smoke. Anything needing node, boto3 or a real AWS call (CDK synth, asset bundle) lives in `deploy-check.yml`, which never runs on a pull request. A `ci-budget` workflow fails the build if any job exceeds the budget, and it is a queue condition in `.mergify.yml`.

**Consequences.**
- No network, no AWS credentials, no sleeps in tests: `tests/fakes/` provides every double, and results are deterministic.
- Slow or end-to-end work is deliberately out of the PR path — a broken native build is caught after merge, which is accepted in exchange for a fast feedback loop.
- Timeouts are never raised to make a job pass; the job is split or moved.

---

## ADR-007 — Hourly costs are effective-dated, and history is immutable

**Context.** Rates change (salary revisions, inflation, a new allocation rule). Recomputing last year's margin with today's rate would make every past review wrong and every comparison meaningless — and it would destroy the audit trail a controller relies on.

**Decision.** Every `Rate` and every allocation rule carries an effective date; `rate_in_force()` returns the value in force at the month being computed. Every recomputation opens a new `CalcVersion` (author, reason, timestamp, parameters fingerprint) instead of overwriting. A past month is never rewritten silently; a correction is a new dated version (EF-CAL-03, spec 12.4).

**Consequences.**
- Two people recomputing the same past month get the same figure, and a margin can be explained months later.
- Storage grows with versions — accepted, the volume is tiny compared with the value of an auditable number.
- Any new parameter that influences a figure must be dated and fingerprinted, or the versioning claim becomes false.
