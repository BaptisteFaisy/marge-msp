# Test Instructions — Marge

Step-by-step instructions for judges and evaluators to run, inspect and verify Marge. Covers the offline local walk-through, the live AWS/Quick demonstration, demo credentials (EF-ADM-03), and the R1..R15 acceptance checklist (spec §23).

---

## 1. Quick Local Walk-Through (Zero AWS Credentials Needed)

The repository is designed to run 100 % offline with SQLite and pre-recorded fakes. The full sequence takes under 3 minutes once the pipeline modules are merged.

### 1.0 CLI availability in this branch — read this first

The CLI (`src/marge/cli.py`) discovers commands from `src/marge/commands/`; each module registers its own. As of this documentation branch:

| Command | Available now | Arrives with |
|---|---|---|
| `smoke` | **yes** — recomputes the Annex D golden case (4 620 € / 3 725 € / 895 € / 19.4 % / 9 h = 990 €) | — |
| `version` | **yes** | — |
| `generate` | no | data generator (lot6) |
| `load`, `match`, `contracts`, `classify` | no | ingest / match / contracts / classify (lot1, lot2) |
| `compute`, `review`, `mcp`, `portal` | no | pipeline, review, mcp, api (lot3, lot4) |
| `assets`, `quicksight deploy` | no | quicksight (lot5) |
| `demo` (the `make demo` target) | no — it chains all of the above | all of the above |

So today, in a fresh clone, the two commands that run are `make smoke` and `make test`. The rest of this section is the **target walk-through** — the exact sequence the merged repository executes; commands are listed in dependency order so the demo can be replayed step by step as the modules land.

### 1.1 Requirements
- Python 3.12+
- `git`
- (Optional) `make`

```bash
git clone git@github.com:BaptisteFaisy/marge-msp.git
cd marge-msp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 1.2 Step-by-Step Command Walk-Through

```bash
# 0. Smoke check (verifies the Annex D golden numbers offline)
python3 -m marge.cli smoke

# 1. Generate the fake MSP data (12 clients, 6 months, 12 PDF contracts, seeded cases)
python3 -m marge.cli generate --seed 20261111

# 2. Ingest raw data into the local SQLite store (PII stripped on the way in)
python3 -m marge.cli load --source data/generated/

# 3. Propose client matching across ITSM, billing and contracts
python3 -m marge.cli match --propose

# 4. Extract contract clauses and review them
python3 -m marge.cli contracts --extract data/generated/contracts/

# 5. Classify interventions against validated contract scopes
python3 -m marge.cli classify --month 2026-10

# 6. Compute margin per client per month
python3 -m marge.cli compute --month 2026-10

# 7. Render the monthly executive review (Annex E)
python3 -m marge.cli review --month 2026-10

# 8. Run the MCP server locally (inspect the three tools)
python3 -m marge.cli mcp --inspect
```

Or run everything in one shot:
```bash
make demo
```

### 1.3 Open the Validation Portal (Local)

```bash
python3 -m marge.cli portal --port 8080
# Open http://localhost:8080 in your browser
```

The local portal exposes the three human gates:
1. **Client matching:** approve proposed cross-source aliases.
2. **Contracts:** review extracted Annex B clauses side-by-side with contract text; click *Validate*.
3. **Classifications:** approve/reject out-of-scope interventions for account managers.

---

## 2. Live Demo Access (AWS / Quick)

For online evaluation of the hosted system:

- **Portal URL:** `https://portal.marge-msp.demo.aws` *(placeholder — the final CloudFront URL is filled in at deployment and pasted into the Devpost form; Cognito-authenticated)*
- **Amazon Quick Console:** the Quick account URL of the deployment region *(placeholder — filled in at deployment)*

### Demo Credentials (EF-ADM-03)

> Login names below are the planned demo identities; the shared password is
> provisioned at deployment and pasted into the Devpost test instructions.
> Placeholder shown here: `Marge-Hackathon-2026!` — rotated after judging ends
> (22 January 2027).

| Role | Portal Login | Quick Login | What they can see / do |
|---|---|---|---|
| **Executive** | `exec@marge-demo.internal` | `marge-exec` (Professional) | All clients; full margin, high-level review, scenarios |
| **Ops Director** | `ops@marge-demo.internal` | `marge-ops` (Professional) | All clients; effort by category and level, ticket breakdown |
| **Account Manager 1** | `am1@marge-demo.internal` | `marge-am1` (Professional + RLS) | **Only assigned clients** (Durand, Acme…); validates out-of-scope hits; hourly costs hidden |
| **Account Manager 2** | `am2@marge-demo.internal` | `marge-am2` (Professional + RLS) | **Only assigned clients**; completely disjoint view from AM 1 |
| **Financial Controller** | `ctrl@marge-demo.internal` | `marge-ctrl` (Enterprise) | All clients; rate cards, tooling rules, contract validation, client matching |
| **Administrator** | `admin@marge-demo.internal` | `marge-admin` (Enterprise) | Technical settings, data coverage KPI, ingestion triggers |

*Password for all demo accounts:* `Marge-Hackathon-2026!` (rotated after the judging period on 22 January 2027).

---

## 3. What to Test in Amazon Quick

### 3.1 Five Dashboards
1. **Overview (EF-TDB-01):** total margin, client ranking by margin rate, clients below threshold (< 20 %), 6-month trend. Spot the two loss-making clients.
2. **Client Sheet (EF-TDB-02):** pick a client (e.g. Durand Industries); drill into revenue breakdown, cost by nature, hours by seniority level.
3. **Unbilled Hours (EF-TDB-03):** out-of-scope work and allowance overruns in hours and euro value, with their validation status.
4. **Renewals within 90 Days (EF-TDB-04):** identify the profitable client renewing in 60 days with a dropping margin.
5. **Effort Breakdown (EF-TDB-05):** costliest work categories per client.

Check **Row-Level Security (EF-TDB-06)**: sign in as `marge-am1` — only AM 1's clients appear; hourly rate cards are hidden.

### 3.2 Chat Agent Questions (EF-AGT-01..03)

Open the Quick chat agent (*"Profitability Analyst"*) and try these seeded prompts:

- *"Which clients are below 20% margin this quarter?"* → returns ranked list with dashboard links.
- *"Why did client Durand's margin drop in October?"* → decomposes cost: labor spike, ticket count, out-of-scope volume.
- *"Does client Martin's contract include database engine version upgrades?"* → cites the exact exclusion clause from the contract.
- *"What did client Leroy cost us over the last 6 months, and on what topics?"* → breaks down effort by category.
- *"Which contracts renew within 90 days with a falling margin?"* → returns the renewing client.

### 3.3 Scenarios (EF-AGT-05)

- In the agent or scenario panel: simulate an **8 % price increase** on client Durand. Observe the margin recovery.
- Simulate a **20 % reduction in ticket volume** (e.g. after proactive automation).

### 3.4 MCP Actions (EF-AGT-04)

- Ask the agent: *"Create a renegotiation task for client Durand with the cost dossier attached."* → calls `create_renegotiation_task`, returns task id in the ITSM tool.
- Ask the agent: *"Prepare a draft extra billing proposal for client Leroy for October unbilled hours."* → calls `draft_extra_billing_proposal`, returns a draft invoice proposal with cited clauses.

### 3.5 Scheduled Review (EF-REV-01..02)

- View the monthly review in the Quick project space or read the delivered email generated following the Annex E template.

---

## 4. Acceptance Checklist — R1 to R15 (Spec §23)

> **Reading this checklist.** The *How to verify* column gives the definitive procedure for the merged repository. Commands marked **✱ planned** depend on a module that is not merged into `main` yet (see §1.0); the two rows that run today — R8 (golden decomposition) and the Annex D part of R7 — are the ones a reader can execute in this branch right now.

| Id | Scenario | Expected Result | How to verify |
|---|---|---|---|
| **R1** | Ingestion of the three sources | Data coverage > 95 % | ✱ planned — `python3 -m marge.cli eval --target coverage` (or read the coverage KPI on the overview dashboard) |
| **R2** | Client identity matching | > 80 % proposed correctly; 100 % after validation | ✱ planned — `python3 -m marge.cli eval --target match` |
| **R3** | Reading of the 12 contracts | > 90 % fields correct; source passage displayed | ✱ planned — `python3 -m marge.cli eval --target contracts` |
| **R4** | Unvalidated contract | Client margin flagged as `INCOMPLETE` | ✱ planned — `python3 -m marge.cli compute --month 2026-10`, then inspect the client whose contract is still `EXTRACTED` |
| **R5** | 150 labelled interventions | > 90 % classification agreement | ✱ planned — `python3 -m marge.cli eval --target classify` |
| **R6** | Clearly included intervention | **Never** classified as `OUT_OF_SCOPE` | ✱ planned — `pytest tests/unit/classify -k clearly_included` |
| **R7** | Out-of-scope hours validation | Unbilled hours and value update instantly | ✅ today: `make smoke` asserts 9 h → 990 €; ✱ planned: approve an intervention in the portal and watch the total move by exactly its duration |
| **R8** | Client margin decomposition | Decomposes to source lines; matches Annex D golden numbers | ✅ `python3 -m pytest tests/unit/calc/test_golden_annex_d.py -q` |
| **R9** | Hourly rate change | Past months unchanged; new version dated | ✱ planned — `pytest tests/unit/calc -k rate_change` |
| **R10** | Account Manager visibility | Sees only their clients; cannot see hourly costs | ✱ planned — sign in to the portal or Quick as `marge-am1`, verify the RLS filter and the hidden rate columns |
| **R11** | 20 reference questions to agent | > 90 % correct answers | ✱ planned — `python3 -m marge.cli eval --target agent` |
| **R12** | Contract clause question | Response cites the exact clause | Ask the agent about DB engine upgrades on client Martin; verify the quoted clause (live demo only) |
| **R13** | Renegotiation task creation | Task created in ITSM tool with dossier attached | Ask the agent to create the task; check the ITSM mock / API response (live demo only) |
| **R14** | Monthly review | Received; numbers identical to dashboards | ✱ planned — compare `marge.cli review --month 2026-10` output with the overview dashboard figures |
| **R15** | Clean-account installation | Succeeds following the README | ✅ today: fresh clone → `make smoke` → `make test`; ✱ planned: the full `make demo` |
