# Test Instructions — Marge

Step-by-step instructions for judges and evaluators to run, inspect and verify Marge. Covers the offline local walk-through, the live AWS/Quick demonstration, demo credentials (EF-ADM-03), and the R1..R15 acceptance checklist (spec §23).

---

## 1. Quick Local Walk-Through (Zero AWS Credentials Needed)

The repository is designed to run 100 % offline with SQLite and pre-recorded fakes. The full walk-through below — `generate` → `demo --auto-validate --review` → `eval` — was measured end to end at **1 min 54 s** on a fresh dataset.

### 1.0 CLI commands — all merged into `main`

The CLI (`src/marge/cli.py`) discovers commands from `src/marge/commands/`; each module registers its own. Every command below runs today in a fresh clone (`make smoke`, `make test` and `make demo` need nothing else):

| Command | What it does |
|---|---|
| `smoke` | Recomputes the Annex D golden case offline (4 620 € / 3 725 € / 895 € / 19.4 % / 9 h = 990 €) |
| `version` | Prints the package version |
| `generate` | Writes the synthetic dataset — 12 clients, 6 months (2026-05 → 2026-10), 3 922 interventions, 13 contract versions, 150 labelled interventions, 20 reference questions |
| `demo` | Full offline pipeline: load → match → contracts → classify → compute → margin table → MCP tools. `--auto-validate` simulates the human gates, `--review` also prints the Annex E review, `--db` keeps the SQLite file |
| `load-demo` | The same pipeline against any store — `--backend dynamo --table marge-validations --region eu-west-1` fills the deployed environment, replayable. Leaves the three human gates open (matches PENDING, `ctr-010` EXTRACTED, the out-of-scope queue) |
| `eval` | Accuracy harnesses R2/R3/R5/R11 on a generated dataset |
| `nightly` | Nightly cadence: classify the new work, recompute the margins, refresh the analytics tables |
| `weekly` | Weekly digest: the out-of-scope work waiting for a decision, per account manager |
| `monthly` | Monthly review text (Annex E) for one month |
| `assets` | Writes the Quick asset bundle, or verifies the committed one (`--check`) |
| `mcp` | MCP server over stdin/stdout (JSON-RPC 2.0, one message per line); `--self-test` prints the three tools |
| `serve` | Portal API (FastAPI, spec ch.16) over uvicorn — requires the `api` extra |

### 1.1 Requirements
- Python 3.12+
- `git`
- (Optional) `make`

```bash
git clone git@github.com:BaptisteFaisy/marge-msp.git
cd marge-msp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,api]"
```

### 1.2 Step-by-Step Command Walk-Through

```bash
# 0. Smoke check (verifies the Annex D golden numbers offline)
python3 -m marge.cli smoke

# 1. Generate the synthetic MSP dataset (12 clients, 6 months, seeded situations)
python3 -m marge.cli generate --out data/generated

# 2. Full offline pipeline: load → match → contracts → classify → compute → margins → MCP tools
#    --auto-validate simulates the three human gates, --review prints the Annex E review
python3 -m marge.cli demo --data data/generated --db /tmp/marge.sqlite3 --auto-validate --review

# 3. Accuracy harnesses (R2 matching, R3 clauses, R5 classification, R11 agent)
python3 -m marge.cli eval --data data/generated

# 4. The three cadences against the same SQLite database
python3 -m marge.cli nightly --db /tmp/marge.sqlite3 --month 2026-10
python3 -m marge.cli weekly --db /tmp/marge.sqlite3
python3 -m marge.cli monthly --db /tmp/marge.sqlite3 --month 2026-10

# 5. Quick asset bundle (verify the committed one) and the MCP tools
python3 -m marge.cli assets --check
python3 -m marge.cli mcp --self-test

# 6. Fill a store with the demonstration dataset, gates left open (see §1.4)
python3 -m marge.cli load-demo --backend sqlite --db /tmp/marge.sqlite3 --data data/generated
```

Or run the pipeline in one shot:
```bash
make demo   # = python3 -m marge.cli demo, without --auto-validate: margins stay
            # INCOMPLETE until the human gates are passed — that is exactly R4
```

Reference scores printed by `eval` on the seeded dataset: clause accuracy (R3) **100.00 %** vs target 0.90, classification agreement (R5/R6) **100.00 %** vs target 0.90, client match accuracy (R2) **97.30 %** vs target 0.80, agent accuracy (R11) **100.00 %** vs target 0.90.

### 1.3 Open the Validation Portal (Local)

Two processes — the API and the static front-end (no build step):

```bash
# 1. Portal API (dev auth mode trusts the X-Actor-* headers)
python3 -m marge.cli serve --db /tmp/marge.sqlite3 --port 8000

# 2. Portal front-end: any static file server
python3 -m http.server 8080 --directory portal
# Open http://localhost:8080 — the API field in the header points at http://localhost:8000
```

The local portal exposes four screens:

1. **Margins** — the margin of every client, month by month, with the two
   loss-makers in red; *Why?* opens the decomposition down to the source lines
   (`GET /v1/margins`, `GET /v1/margins/{client_id}/{month}/why`).
2. **Matches** — approve proposed cross-source aliases.
3. **Contracts** — review extracted Annex B clauses side-by-side with contract
   text; click *Validate*.
4. **Classifications** — approve/reject out-of-scope interventions for account
   managers (the queue of the rows that need a decision).

Dev-mode actor identities (`exec-01`, `ops-01`, `am-01`, `controller-01`, `admin-01`) and what each role sees are documented in `portal/README.md`.

### 1.4 Fill a store with the demonstration dataset (replayable)

```bash
# Local: same result as `marge demo`, on a file you keep
python3 -m marge.cli load-demo --backend sqlite --db /tmp/marge.sqlite3 --data data/generated

# Deployed: the DynamoDB table of the portal API
python3 -m marge.cli load-demo --backend dynamo --table marge-validations --region eu-west-1

# And publish the five analytical tables to the curated bucket
python3 -m marge.cli load-demo --backend dynamo --publish-s3 <curated-bucket>
```

Every row is written on its natural key, so the command can be run again at
any time without duplicating anything. It leaves the three human gates open:
the 49 client matches are PENDING, the seeded contract `ctr-010` stays
EXTRACTED (its margin reads `INCOMPLETE`), and the out-of-scope work waits in
the account manager's queue.

---

## 2. Live Demo Access (AWS / Quick)

For online evaluation of the hosted system:

- **Portal URL:** `https://d3n1e2aqabg966.cloudfront.net` — the CloudFront
  distribution of the deployment: the static portal and the API share one
  origin, so nothing has to be installed. Cognito-authenticated.
- **GitHub Pages mirror:** `https://tradoooo.github.io/marge-msp/` — the same
  static portal, served from the repository.
- **Amazon Quick Console:** the Quick account URL of the deployment region
  *(filled in at deployment — see `docs/RUNBOOK.md` §4)*.

### Demo Credentials (EF-ADM-03)

> The logins and their passwords are **not** in this repository. They are
> provisioned by `scripts/create_judge_account.py`, kept in **AWS Secrets
> Manager**, and transmitted to the judges in the Devpost test-instructions
> form. The script prints the ARN of the secret, never the password:
>
> ```bash
> python3 scripts/create_judge_account.py --region eu-west-1 --rotate-demo-users
> aws secretsmanager get-secret-value --secret-id marge/demo/credentials \
>   --region eu-west-1 --query SecretString --output text
> ```
>
> For the local portal in dev auth mode, the header identities are listed in
> `portal/README.md`.

| Role | Portal Login | Quick Login | What they can see / do |
|---|---|---|---|
| **Judge** | `judge@marge.demo` | — | Read and validate: every client, the margins, the three queues |
| **Executive** | `director-01@marge.demo` | `marge-exec` (Professional) | All clients; full margin, high-level review, scenarios |
| **Ops Director** | `ops-01@marge.demo` | `marge-ops` (Professional) | All clients; effort by category and level, ticket breakdown |
| **Account Manager 1** | `am-01@marge.demo` | `marge-am1` (Professional + RLS) | **Only assigned clients**; validates out-of-scope hits; hourly costs hidden |
| **Financial Controller** | `controller-01@marge.demo` | `marge-ctrl` (Enterprise) | All clients; rate cards, tooling rules, contract validation, client matching |
| **Administrator** | `admin-01@marge.demo` | `marge-admin` (Enterprise) | Technical settings, data coverage KPI, ingestion triggers |

*Passwords: generated at deployment, stored in AWS Secrets Manager, rotated
when the judging period ends (22 January 2027).*

---

## 3. What to Test in Amazon Quick

### 3.1 Five Dashboards
1. **Overview (EF-TDB-01):** total margin, client ranking by margin rate, clients below threshold (< 20 %), 6-month trend. Spot the two loss-making clients.
2. **Client Sheet (EF-TDB-02):** pick a client (e.g. Durand Industries); drill into revenue breakdown, cost by nature, hours by seniority level.
3. **Unbilled Hours (EF-TDB-03):** out-of-scope work and allowance overruns in hours and euro value, with their validation status.
4. **Renewals within 90 Days (EF-TDB-04):** identify the profitable client renewing in 60 days with a dropping margin.
5. **Effort Breakdown (EF-TDB-05):** costiest work categories per client.

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

> **Reading this checklist.** Every command and test below runs today, offline, in a fresh clone (the `make` targets set `PYTHONPATH=src`; for bare pytest use `PYTHONPATH=src:. pytest -q`). Rows that need the deployed AWS account — the live Quick chat agent, the scheduled Quick flow, the Quick row-level rule set — are marked *manual — see `docs/RUNBOOK.md` §4*: those elements cannot be created by an API. The authoritative requirement-by-requirement mapping is [acceptance/MATRIX.md](acceptance/MATRIX.md).

| Id | Scenario | Expected Result | How to verify |
|---|---|---|---|
| **R1** | Ingestion of the three sources | Data coverage > 95 % | `python3 -m marge.cli demo --data data/generated --auto-validate` prints the per-month coverage KPI (97.01 – 99.51 % on the seeded dataset); `python3 -m pytest tests/unit/ingest/test_ingest.py tests/integration/test_seeded_situations.py -q` |
| **R2** | Client identity matching | > 80 % proposed correctly; 100 % after validation | `python3 -m marge.cli eval --data data/generated` → `client match accuracy (R2) 97.30 % (target 0.80)`; `python3 -m pytest tests/unit/eval/test_match_accuracy.py tests/unit/match/test_matching.py -q` |
| **R3** | Reading of the 12 contracts | > 90 % fields correct; source passage displayed | `python3 -m marge.cli eval --data data/generated` → `clause accuracy (R3) 100.00 % (target 0.90)`; `python3 -m pytest tests/unit/eval/test_clause_accuracy.py tests/unit/contracts/test_extraction.py -q` |
| **R4** | Unvalidated contract | Client margin flagged as `INCOMPLETE` | `python3 -m marge.cli demo --data data/generated` (no `--auto-validate`) → the client whose contract is still `EXTRACTED` shows state `INCOMPLETE` in the margin table; `python3 -m marge.cli load-demo --backend sqlite` leaves `ctr-010` EXTRACTED and `c-010` INCOMPLETE; `python3 -m pytest tests/integration/test_seeded_situations.py -k not_validated -q` |
| **R5** | 150 labelled interventions | > 90 % classification agreement | `python3 -m marge.cli eval --data data/generated` → `classification agreement (R5/R6) 100.00 % (target 0.90)`; `python3 -m pytest tests/unit/eval/test_classification_agreement.py -q` |
| **R6** | Clearly included intervention | **Never** classified as `OUT_OF_SCOPE` | `python3 -m pytest tests/unit/classify/test_classification.py -k doubtful -q`; the agreement harness itself fails on any R6 violation (`python3 -m pytest tests/unit/eval/test_classification_agreement.py -q`) |
| **R7** | Out-of-scope hours validation | Unbilled hours and value update instantly | `python3 -m marge.cli smoke` asserts 9 h → 990 €; `python3 -m pytest tests/unit/api/test_routes_classifications.py -k approved_out_of_scope -q`; live: approve an intervention in the local portal (§1.3) and watch the total move by exactly its duration |
| **R8** | Client margin decomposition | Decomposes to source lines; matches Annex D golden numbers | `python3 -m pytest tests/unit/calc/test_golden_annex_d.py -q`; live: open the *Margins* screen of the local portal, click *Why?* on a client (§1.3) — the posts, the hours and the source lines of `GET /v1/margins/{client_id}/{month}/why` |
| **R9** | Hourly rate change | Past months unchanged; new version dated | `python3 -m pytest tests/integration/test_seeded_situations.py -k rate -q`; effective-dated immutable rates in `src/marge/calc/versioning.py`, admin route: `python3 -m pytest tests/unit/api/test_routes_admin.py -q` |
| **R10** | Account Manager visibility | Sees only their clients; cannot see hourly costs | `python3 -m pytest tests/unit/api/test_rls.py tests/unit/quicksight/test_rls.py -q`; live: use the local portal as `am-01` (§1.3). The Quick rule set is manual — see `docs/RUNBOOK.md` §4 |
| **R11** | 20 reference questions to agent | > 90 % correct answers | `python3 -m marge.cli eval --data data/generated` → `agent accuracy (R11) 100.00 % (target 0.90)`; `python3 -m pytest tests/unit/eval/test_agent_accuracy.py -q`. The live Quick chat agent is manual — see `docs/RUNBOOK.md` §4 |
| **R12** | Contract clause question | Response cites the exact clause | `python3 -m pytest tests/unit/quicksight/test_agent.py tests/unit/eval/test_clause_accuracy.py -q`; the live answer on the Quick agent (contracts space) is manual — see `docs/RUNBOOK.md` §4 |
| **R13** | Renegotiation task creation | Task created in ITSM tool with dossier attached | `python3 -m marge.cli mcp --self-test` lists `create_renegotiation_task`; `python3 -m pytest tests/unit/mcp/test_mcp.py -q` (against the ITSM double). The live ITSM call from the Quick agent is manual — see `docs/RUNBOOK.md` §4 |
| **R14** | Monthly review | Received; numbers identical to dashboards | `python3 -m marge.cli monthly --db /tmp/marge.sqlite3 --month 2026-10` (or `demo --auto-validate --review`); `python3 -m pytest tests/unit/review/test_review.py tests/unit/pipeline/test_pipeline.py -q`. Delivery by the Quick flow or SES is manual — see `docs/RUNBOOK.md` §4 |
| **R15** | Clean-account installation | Succeeds following the README | Fresh clone → `make smoke` → `make test` → `make demo` (all run offline); AWS deployment order in `docs/RUNBOOK.md` §2 |
