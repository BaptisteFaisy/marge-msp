# Devpost Submission — Marge

Ready-to-paste submission text (English). Track 1 — *Run Your MSP Better*. Special prize: *Best Amazon Quick Application*. Deadline: Friday 12 December 2026, 12:00 PT.

---

## Name

**Marge** — per-client profitability for Managed Service Providers

## One-liner

Marge crosses your ticketing tool, your AWS bill and your PDF contracts to reveal the margin of every client every month — the hours you give away, the clients you renew blindly — and turns the findings into validated renegotiation actions.

---

## The Problem

An MSP sells managed-service contracts at a fixed monthly price. The real effort varies enormously from one client to another. Yet almost no MSP knows its **margin per client**, because the three required datasets live in three tools that never talk to each other:

1. **Time spent** — inside the ticketing / ITSM tool.
2. **The AWS bill** — inside the billing console.
3. **The commitments** — inside PDF contracts nobody re-reads.

Consequences:

- **Unknown per-client margin.** The global margin is known; its distribution is not.
- **Invisible loss-makers.** A few clients consume a large share of the hours for an average subscription.
- **Work given away unknowingly.** An engineer handles an out-of-contract request because it is faster than checking whether it is included.
- **Blind renewals.** The price is rolled over without ever looking at what the client cost.
- **Painful review.** Producing the number takes days of exports and spreadsheets — so nobody does it.

## The Solution

Marge is an internal profitability system for the MSP's leadership, account managers, ops director and financial controller:

- **The margin of every client, every month, with its explanation** — revenue by component, cost by nature, margin rate, decomposable down to the source lines (tickets, billing rows, contract clauses).
- **Detected unbilled hours** — out-of-scope work and allowance overruns nobody flagged, in hours and in currency value, each justified by the cited contract clause.
- **A written monthly review and a chat agent** — a scheduled Quick Flow drafts the executive review; a "profitability analyst" agent answers questions and runs price/volume simulations before a renewal, and can create the renegotiation task in the ITSM tool through an MCP server.

## What the AI Does — and What It Never Does

The AI intervenes at exactly **three points where a fixed rule is not enough**:

| Step | Who decides | Who validates |
|---|---|---|
| Reading contracts | **Bedrock Data Automation** extracts the 16 clause fields beside their source passage | The financial controller, one click |
| Scoping work | A **Bedrock model** classifies each intervention (`INCLUDED` / `OUT_OF_SCOPE` / `UNCERTAIN`) and cites the governing clause | The account manager, for every out-of-scope hit above 15 minutes |
| Answering questions | The **Quick chat agent**, bound to the Quick Topic semantic layer and the contract space | A 20-question reference suite; every figure links to its dashboard |

The AI **never**:

- **computes a single amount** — every figure comes from the deterministic Python/Athena calculation engine (ENF-IA-01);
- **counts without a human** — no extracted clause and no out-of-scope classification has any effect before validation (ENF-IA-02);
- **receives instructions from data** — ticket and contract text is fenced, untrusted data (ENF-IA-03);
- **sees a person** — engineer names are stripped at ingestion; only seniority levels (N1/N2/N3/architect) exist in the system (ENF-CONF-01/02).

## Against the Four Judging Criteria (25 % each)

| Criterion | What Marge demonstrates |
|---|---|
| **Technical implementation** | Amazon Quick used in breadth: SPICE datasets, 5 dashboards with row-level security, Quick Topic semantic layer, custom chat agent, contract knowledge space, scenarios (price/volume simulation), scheduled Flow (monthly review), MCP actions via AgentCore Gateway. Wired to Bedrock Data Automation (contract reading) and a Bedrock model on the Flex tier (work classification). |
| **Design** | Human validation at every uncertain step; every displayed number decomposes to source lines; social data protected by construction (levels, never people); swappable connectors behind Python Protocols so another MSP can plug its own tools. |
| **Impact** | Three measured figures on the demo dataset (see below). |
| **Innovation** | A problem MSP judges know intimately — nobody reconciles these three sources — solved with dated calculation versions, decision memory for classifications, and an agent that acts (renegotiation task, billing draft) instead of only answering. |

## Expected Impact — the Three Numbers

Measured on the demonstration dataset (12 clients, 6 months, seeded situations):

1. **Review time.** Preparing the monthly profitability review goes from **several days** of exports and spreadsheets to **under 10 minutes** (demo target; production target under 1 hour, validations included).
2. **Value of unbilled hours.** Hours worked but never billed — out-of-scope work and allowance overruns — detected and valued at the contract hourly rate. Golden example from the spec: **9 h × 110 € = 990 €** for a single client-month; the demo seeds three clients with repeated out-of-scope work across at least 3 months each.
3. **Clients below the margin threshold spotted before renewal.** The demo seeds two loss-making clients and one profitable client renewing in **60 days with a falling margin** — each surfaced by the renewals dashboard and the monthly review, with the quantified file attached to the renegotiation task.

Supporting quality targets: data coverage > 95 %, contract fields extracted without correction > 90 %, classification agreement with human labels > 90 % on 150 labelled interventions (never `OUT_OF_SCOPE` on a clearly included one), agent accuracy > 90 % on 20 reference questions.

## How to Test

Full step-by-step guide: [TEST-INSTRUCTIONS.md](TEST-INSTRUCTIONS.md). Summary:

1. Open the public portal URL; sign in with the demo credentials (roles: executive, account manager, controller, admin — EF-ADM-03).
2. Open the Quick demo account (credentials in the test instructions), browse the 5 dashboards, ask the agent the seeded questions, run a scenario.
3. Read the monthly review (email + project space).
4. Or run the offline path in a fresh clone: `make smoke` (Annex D golden case) and `make test`; the full local walk-through `make demo` chains data generation, matching, contract validation, classification, margin computation, portal and review on SQLite — its commands are registered as the pipeline modules merge, and [TEST-INSTRUCTIONS.md](TEST-INSTRUCTIONS.md) §1.0 lists which ones run today.

## Assumed Limitations

- **Synthetic data only.** The demo MSP (12 clients, 6 months, 12 PDF contracts) is generated with seeded situations; no real client data is used.
- **Hackathon scope.** Market connectors (ConnectWise, Autotask, HaloPSA…), issued-invoice ingestion, fixed-price projects, 3-month margin forecasting and quoting assistance are explicitly post-hackathon (spec §5.2). Out of scope by design: general accounting, payroll, invoice emission, client-side AWS cost optimization (spec §5.3).
- **Manual Quick elements.** Chat agents, scheduled flows and contract spaces cannot be created by API; they are created by hand following the documented runbook — acceptable for a single MSP, documented as a risk (spec §22).
- **Time-tracking quality is a precondition.** Where engineers log hours poorly, Marge shows it (coverage indicator, `ESTIMATE` tags) rather than hiding it; it never spreads unassigned hours silently.
- **Scenario simulation** relies on Quick scenario features; if they fall short, the simulation is computed server-side by the same deterministic engine (spec §24, item 6).

---

*Private repository shared with `testing@devpost.com` and `aws-msp@amazon.com`. The code calls real AWS AI services at runtime: Bedrock Data Automation, a Bedrock model, the Quick Sight API, and an MCP server loaded by the agent. Submission checklist: see [README](../README.md).*
