# Marge — per-client profitability for MSPs

Marge tells a Managed Service Provider what each of its clients actually earns. It crosses the three sources nobody reconciles — the ticketing tool's logged hours, the AWS bill, and the PDF contracts — and produces a dated, auditable margin per client per month, the hours that were worked but never billed, and a written monthly review an account manager can take into a renewal.

Built for the **AWS MSP AI Hackathon, Track 1 — Run Your MSP Better** (targeting the *Best Amazon Quick Application* prize).

> **Screenshot — Overview dashboard (described, no binary committed yet).**
> The top band shows four tiles: total monthly margin, average margin rate, clients below the 20 % threshold (count in red), and a data-coverage badge at 96 %. Below them, a client ranking table sorted by margin rate — two rows highlighted in red (the seeded loss-makers, one of them with an abnormal ticket volume) — and a six-month margin trend line with the threshold drawn as a dashed horizontal rule. Every row links to the client sheet, which decomposes the margin into revenue by component and cost by nature, down to the source lines. *Drop the real capture at `docs/img/overview.png` once the Quick account is deployed (see [RUNBOOK.md](docs/RUNBOOK.md) §2).*

---

## The problem

An MSP sells fixed-price managed-service contracts while real effort varies enormously from client to client. Almost no MSP knows its margin per client, because the data lives in three tools that never talk: **time spent** in the ITSM tool, **AWS costs** in the billing console, **commitments** in PDF contracts. Loss-making clients stay invisible, out-of-scope work is given away, renewals are negotiated blindly, and producing the number takes days of spreadsheets — so nobody does it.

## Architecture in five lines

1. **Nightly ingestion** (Step Functions + Lambda) loads tickets, billing rows and contract PDFs into S3, stripping engineer names on the way in — only seniority levels survive.
2. **Three AI steps**: Bedrock Data Automation reads contract clauses, a Bedrock model (Flex tier) classifies each intervention against the contract scope, Quick's chat agent answers questions on the numbers.
3. **A human validates each AI step** in the validation portal — client matching, contract fields, out-of-scope work.
4. **Margin is computed by code** (`src/marge/calc`, pure Python, `Decimal`) and published to five Quick SPICE datasets with row-level security.
5. **Quick delivers**: dashboards, a semantic Topic, a scheduled monthly review Flow, and MCP actions that create the renegotiation task in the ITSM tool.

Full detail: [HLD](docs/HLD.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [DECISIONS](docs/DECISIONS.md) · [RUNBOOK](docs/RUNBOOK.md).

## Quick start

```bash
git clone git@github.com:BaptisteFaisy/marge-msp.git && cd marge-msp
python3 -m pip install --user -e ".[dev,api]"
make smoke       # recompute the Annex D golden case offline — no AWS, no credentials
```

`make smoke` prints and asserts the reference figures (revenue 4 620 €, cost 3 725 €, margin 895 € = 19.4 %, 9 h × 110 € = 990 €). `make test` runs the offline suite, `make lint` and `make limits` are what CI runs.

The full local walk-through — `generate` → `load` → `match` → `contracts` → `classify` → `compute` → `portal` → `review` → `mcp`, i.e. `make demo` — is wired by the pipeline, portal, MCP and data-generator modules; each of those commands is registered under `src/marge/commands/` as its module lands. **In this branch the CLI exposes `smoke` and `version` only**; [TEST-INSTRUCTIONS.md](docs/TEST-INSTRUCTIONS.md) §1 states, command by command, what runs today and what arrives with the remaining modules.

Step-by-step demo and judge credentials: [docs/TEST-INSTRUCTIONS.md](docs/TEST-INSTRUCTIONS.md).

## Specification

The authoritative requirements document is the French cahier des charges: **[docs/SPEC.fr.md](docs/SPEC.fr.md)** (chapters 1–25 + annexes A–F). Every requirement id quoted in code (`EF-*`, `ENF-*`, `R*`) refers to it, and the traceability matrix maps each one to its implementation and test: [docs/acceptance/MATRIX.md](docs/acceptance/MATRIX.md).

Interchange formats between the generator, the connectors and the evaluation harnesses: [docs/DATA-FORMATS.md](docs/DATA-FORMATS.md). Module ownership and public API: [docs/CONTRACT.md](docs/CONTRACT.md).

## Repository structure

```
marge-msp/
├── src/marge/
│   ├── domain/     # frozen pure dataclasses: money, periods, parties, work, results, settings, audit
│   ├── calc/       # margin model (spec ch.12): rates, hours, allocation, coverage, margin, effort, renewal, trace, versioning
│   ├── ingest/     # TicketSource / BillingSource / ContractSource Protocols, PII stripping
│   ├── store/      # Store Protocol: SQLite (local, CI) + DynamoDB (AWS)
│   ├── match/ contracts/ classify/   # AI steps: client identity, Annex B fields, Annex C classifications
│   ├── api/        # FastAPI validation portal API (spec ch.16), auth, row-level filtering
│   ├── mcp/        # MCP server: create_renegotiation_task, draft_extra_billing_proposal, get_margin_breakdown
│   ├── review/     # monthly review, Annex E template, SES/Bedrock fallback
│   ├── quicksight/ # datasets, topic, dashboards, RLS, scenarios, agent, flows, asset bundle
│   ├── pipeline/   # nightly / weekly / monthly orchestration
│   ├── eval/       # accuracy harnesses (R2, R3, R5, R11)
│   └── cli.py      # one entry point
├── data/generator/ # fake MSP: 12 clients, 6 months, seeded situations, 12 PDF contracts
├── portal/         # static validation portal (vanilla HTML/CSS/JS, no build step)
├── infra/cdk/      # AWS CDK stacks
├── tests/          # offline deterministic tests, shared doubles in tests/fakes/
└── docs/           # spec, HLD, architecture, runbook, submission, acceptance matrix
```

## CI, Mergify and Hermes

- **`ci`** (GitHub Actions): ruff check + format, size guard (`< 500` lines per file, `< 50` per function), offline pytest, Annex D smoke. **5-minute budget per job**, enforced by the **`ci-budget`** workflow; both checks are queue conditions.
- **Runner pool**: every workflow reads `runs-on: ${{ fromJSON(vars.CI_RUNNER) }}`. The default is the four self-hosted workers of the R630 (`r630-marge-msp-01..04`, label `marge-msp-worker`); the repository variable `CI_RUNNER` switches the whole pool in one call, e.g. to `["ubuntu-latest"]` when the shared R630 is unreachable or overloaded. The value in force is the one the job actually used, visible in the run log.
- **Mergify**: merge queue with rebase, batching 1–3, `urgent` / `priority-low` labels. `main` is protected — no direct pushes, the queue is the only merge pilot.
- **hermes-lite**: freshness gate (`.github/workflows/hermes-lite.yml` + `.github/hermes/gate.py`), running in dry-run (`HERMES_LITE_DRY_RUN=1`); it labels and evaluates, it does not merge. **`stale-base-guard`**: informative branch-lag check.
- **`deploy-check`**: CDK synth + Quick asset bundle, after merge on `main` only — never on a pull request, so the PR path stays inside the budget.

## Licence

MIT — see [pyproject.toml](pyproject.toml).

---

## Hackathon deliverables status (spec ch.20.1)

- [x] Track 1 selected; AWS AI services declared (Amazon Quick, Amazon Bedrock, Bedrock Data Automation, AgentCore Gateway)
- [x] English description: features, problem, measured efficiency gains — [docs/SUBMISSION.md](docs/SUBMISSION.md)
- [x] Architecture diagram — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/HLD.md](docs/HLD.md) (Mermaid, overview + nightly sequence)
- [x] High-level design document — [docs/HLD.md](docs/HLD.md)
- [x] Test instructions with demo credentials for the portal and for Quick — [docs/TEST-INSTRUCTIONS.md](docs/TEST-INSTRUCTIONS.md)
- [x] Private repository shared with `testing@devpost.com` and `aws-msp@amazon.com`
- [x] Code calls real AWS AI services at runtime (Bedrock Data Automation, a Bedrock model, the Quick Sight API, an MCP server loaded by the agent)
- [ ] ~3-minute public YouTube video in English, no third-party branding or music — script and shot list in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §5
- [ ] Public portal URL filled into the Devpost form after deployment (see [RUNBOOK.md](docs/RUNBOOK.md) §2)
