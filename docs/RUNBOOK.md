# Runbook — Marge

Operational procedures: deployment order, configuration and secrets, the Quick elements that cannot be created by API, asset-bundle updates, and troubleshooting. Everything here is written for the person on call, not for the demo.

Companion documents: [ARCHITECTURE.md](ARCHITECTURE.md) (service map), [DECISIONS.md](DECISIONS.md) (why), [TEST-INSTRUCTIONS.md](TEST-INSTRUCTIONS.md) (how to demo).

---

## 1. Prerequisites

| Item | Value |
|---|---|
| AWS account | the MSP's own account, one region where Quick, its AI features and Bedrock Data Automation are all available (spec §24 item 2 — confirm before deploying) |
| AWS Partner Network membership | required for the Quick trial and for the resale-margin logic to be meaningful (spec §24 item 1) |
| Tooling | Python 3.12+, Node 20+ (CDK), AWS CDK v2, `git`, `gh` CLI |
| Access | an IAM role allowed to create S3, Lambda, Step Functions, DynamoDB, Glue, Athena, CloudFront, API Gateway, Cognito, Bedrock, CloudWatch and Quick resources |
| Quick | trial started (30 days, up to 25 users, subscriptions + infrastructure fee included) |

Local development needs nothing but Python: SQLite and the fakes under `tests/fakes/` make the whole pipeline run offline.

---

## 2. Deployment Order

Deploy strictly in this order; each step depends on the previous one.

1. **Bootstrap.** `cdk bootstrap aws://<account>/<region>` once per account/region.
2. **Data lake and catalogue.** `infra/cdk/data_lake.py` — the raw bucket, the curated bucket, the Glue database and the Athena workgroup.
3. **Operational store.** DynamoDB tables for clients, matches, contracts, classifications, rates, tooling rules, audit. Point-in-time recovery on, deletion protection on.
4. **AI stacks.** `infra/cdk/contracts_ai.py` (Bedrock Data Automation profile with the Annex B field plan) then the classification Lambda (Bedrock model, Flex tier).
5. **Portal.** `infra/cdk/portal.py` — CloudFront distribution, S3 static site, API Gateway, Lambda, Cognito user pool and the five role groups.
6. **MCP action server.** `infra/cdk/mcp.py` — AgentCore Gateway + Lambda exposing `create_renegotiation_task`, `draft_extra_billing_proposal`, `get_margin_breakdown`.
7. **Observability.** `infra/cdk/observability.py` — CloudWatch dashboards, alarms, SNS topic.
8. **Quick asset bundle.** `make assets` writes `infra/quicksight-assets/`, then `python3 -m marge.cli quicksight deploy` pushes datasets, topic, dashboards, RLS rules and scenarios through the Quick Sight API.
9. **Manual Quick elements.** Create the chat agent, the contract space and the scheduled flow by hand — see §4. They cannot be created by API.
10. **First full run.** `python3 -m marge.cli load`, `match`, `contracts --extract`, `classify`, `compute` on the last six months, then refresh SPICE.
11. **Validation pass.** Controller validates matches and contracts; account managers validate the out-of-scope queue (§5).
12. **Enable the schedule.** EventBridge Scheduler nightly trigger at 02:00 local; weekly digest Monday 07:00; monthly review Flow on the 3rd working day.

`deploy-check.yml` runs the asset bundle and CDK synth after every merge on `main` — a red `cdk-synth` job means the infrastructure no longer describes itself.

---

## 3. Configuration and Secrets

Defaults live in `src/marge/domain/settings.py` (`Settings`) and are edited through the portal (`/v1/rates`, `/v1/allocation-rules`), never by patching code. Environment variables only carry deployment wiring:

| Variable | Purpose | Example |
|---|---|---|
| `MARGE_ENV` | Deployment stage | `demo`, `prod` |
| `MARGE_REGION` | AWS region (default `eu-west-3`) | `eu-west-3` |
| `MARGE_RAW_BUCKET` | Raw S3 bucket | `marge-raw-<account>` |
| `MARGE_CURATED_BUCKET` | Curated S3 bucket | `marge-curated-<account>` |
| `MARGE_STORE_BACKEND` | `sqlite` (local) or `dynamo` (AWS) | `dynamo` |
| `MARGE_CURRENCY` / `MARGE_BILLING_CURRENCY` | Reporting vs billing currency (conversion happens at load) | `EUR` / `USD` |
| `MARGE_CLASSIFIER_MODEL_ID` | Bedrock model used for classification | model id, not a secret |
| `MARGE_BDA_PROFILE_ID` | Bedrock Data Automation field-plan profile | `marge-contract-fields-v1` |
| `MARGE_MARGIN_THRESHOLD` | Below this margin rate a client is reported | `0.20` |
| `MARGE_COVERAGE_FLOOR` | Below this coverage a month is `ESTIMATE` | `0.80` |

**Secrets — never in plain text, never in the repository, never in a document:**

- Store them in **AWS Secrets Manager** (or SSM Parameter Store `SecureString`); Lambda reads them at runtime through its execution role.
- Database credentials, ITSM API tokens and any SES identity credentials follow the same rule.
- `.env` files are local-only and gitignored. A secret that appears in a commit is rotated immediately — deleting the file is not enough.
- Demo credentials for judges are the one deliberate exception, and they are published only in [TEST-INSTRUCTIONS.md](TEST-INSTRUCTIONS.md) §2, rotated when judging ends (22 January 2027).

---

## 4. Manual Quick Elements (not creatable by API)

Spec §22 lists this as a known risk: chat agents, scheduled flows and spaces cannot be created programmatically. One MSP, done once, documented here with the exact labels. **Do this while signed in as the Controller** for the flow (a schedule belongs to the user who creates it — spec §14.4, verified).

### 4.1 Contract space (knowledge base)

1. In Amazon Quick, open **Spaces** → **Create space**. Name it `Marge — Contracts`, description: *Validated MSP contracts for clause citation*.
2. **Add data** → **S3** → point to the contracts prefix of the raw bucket (`contracts/`, PDF only — never the `.txt` twins).
3. Set access to the roles that must cite clauses: Executive, Controller, Account Manager. Never the Administrator-only default.
4. Wait for the ingestion status to reach *Ready*; open one document and search for a known exclusion sentence to confirm the index is usable.

### 4.2 Chat agent "Profitability Analyst"

1. Open **Chat agents** → **Create agent**. Name: `Profitability Analyst`. Icon: any; description: *Per-client MSP margin, contract scope and unbilled hours*.
2. **Knowledge**: add the Quick **Topic** `Marge profitability` (created by the asset bundle) **and** the space `Marge — Contracts`. No other source.
3. **Instructions** (paste verbatim — this is the EF-AGT-01..03 guardrail):
   > Answer only from the Marge topic and the contracts space. Always state the period and the client. Always link the dashboard the figure comes from. When you talk about a contract, quote the clause verbatim. When a value is marked ESTIMATE or INCOMPLETE, say so. Never estimate, compute or round a number yourself — if the topic does not contain the figure, say you do not have it.
4. **Actions**: connect the MCP server from `infra/cdk/mcp.py` (AgentCore Gateway endpoint). Verify the three tools appear: `create_renegotiation_task`, `draft_extra_billing_proposal`, `get_margin_breakdown`.
5. **Test before publishing**: ask *"Which clients are below 20% margin this quarter?"* — the answer must list clients **with** the period and a dashboard link. Ask a contract question — the answer must quote a clause.
6. Publish and grant access to Executive, Operations Director, Account Manager, Controller.

### 4.3 Scheduled flow — monthly review

1. Open **Flows** → **Create flow**. Name: `Marge monthly review`.
2. Steps: **Read data** (dashboards `Overview`, `Unbilled hours`, `Renewals within 90 days` + topic) → **Reason** (draft following the Annex E template in `docs/SPEC.fr.md`) → **Write** (produce the document) → **Send** (email to leadership) → **Save** (project space `Marge — Reviews`).
3. **Schedule**: monthly, day `3` (third working day), 07:00 local timezone. The schedule belongs to the Controller account that creates it.
4. Hard rule in the prompt: *"Take every figure from the dashboards. Never compute a figure. If a value is missing, write 'not available'."*
5. Fallback (EF-REV-03): if the Flow cannot be scheduled as needed, run `python3 -m marge.cli review --month <YYYY-MM> --send`. It renders the Annex E review deterministically from the aggregates and sends it through SES.

### 4.4 Row-level security

1. In Quick, open the dataset `marge_client_mois` → **Row-level security** → **Create rule set**.
2. Rule column `account_manager_id`, values mapped to the Quick user name of each account manager (`marge-am1`, `marge-am2`, …). Apply the same rule set to the other four datasets.
3. Test with an account manager account: only their clients appear, and hourly-cost columns are absent.

---

## 5. Routine Operations

| Cadence | Action |
|---|---|
| Nightly | Step Functions run at 02:00; check the CloudWatch alarm `marge-ingestion-failed` is green and the run duration stays under 30 minutes (ENF-PERF-01) |
| Weekly | Account managers clear the out-of-scope queue; the weekly digest emails them the list |
| Monthly | Review the Flow output against the dashboards (figures must match exactly), then archive |
| On contract amendment | Upload the new PDF, re-run `contracts --extract`, controller validates the new version (the previous one stays readable, EF-CTR-04) |
| On rate change | `PUT /v1/rates` with an effective date; past months are recomputed with the rate in force then, and a new calculation version is opened (EF-CAL-03) |

### 5.1 Updating the Quick asset bundle

1. Edit the specs in `src/marge/quicksight/` (datasets, dashboards, topic, RLS, scenarios, flows).
2. `make assets` → rewrites `infra/quicksight-assets/`; commit the diff with the code change (the bundle is reviewed like code).
3. `python3 -m marge.cli quicksight deploy --check` (dry run, shows the diff), then without `--check` to apply.
4. Re-run the SPICE refresh and spot-check the `Overview` dashboard: client count, threshold list, margin totals.
5. If a dashboard is deleted in the console, redeploy from the bundle — never rebuild it by hand.

---

## 6. Troubleshooting

### 6.1 Load failure (ingestion did not complete)

- **Symptom:** `marge-ingestion-failed` alarm, Step Functions execution failed, SPICE datasets stale.
- **Check:** the failed state in the Step Functions console (which adapter), then the Lambda logs in CloudWatch for the offending record.
- **Most common causes:** a renamed export column (the interchange format in `docs/DATA-FORMATS.md` is a contract — fix the export, do not patch the loader ad hoc), a missing month in the billing export, a contract PDF that is a scan without a text layer.
- **Recovery:** fix the source, re-run only the failed step (`python3 -m marge.cli load --month <YYYY-MM> --source <itsm|billing|contract>`), then re-run `compute` for the affected month. Never hand-edit rows in S3 or DynamoDB: the audit trail is the product.

### 6.2 Client resolution rate too low

- **Symptom:** coverage below 95 % (demo target) or 90 % (production target); a large `UNASSIGNED` bucket.
- **Check:** portal → **Coverage** (`GET /v1/coverage`); group the unresolved aliases by source.
- **Causes and fixes:** new client not yet in `aliases.json` → add the alias; alias renamed in the ITSM tool → update the alias, not the past interventions; genuinely empty `customer_ref` → leave it in `UNASSIGNED` (spec 12.4 — it must stay visible, never be spread silently).
- **Never** raise the matching confidence threshold to hide the problem: a wrong merge is worse than an unassigned hour.

### 6.3 Mass "uncertain" classification

- **Symptom:** most new interventions come back `UNCERTAIN`, the account-manager queue is unmanageable, or out-of-scope detection collapses.
- **Check in this order:** (1) is the client's contract `VALIDATED`? an unvalidated contract gives the model no scope to compare against; (2) does the extracted scope contain the `services_included` / `exclusions` lists in full? (3) did the confidence threshold or the 15-minute floor change? (4) is the model returning Annex C-shaped JSON at all?
- **Fixes:** validate the contract; re-extract with the field plan; restore the threshold from `Settings`; if the model output is malformed, the parser rejects it by design — inspect the raw response in CloudWatch, tighten the prompt in `classify/prompt.py`, and re-run only the affected month.
- **Do not** bulk-approve the queue to make the dashboard look right: unvalidated out-of-scope hours have zero financial standing (ENF-IA-02).

### 6.4 Mergify queue blocked

- **Symptom:** a pull request sits in the queue; nothing merges; the queue shows a failing required check or a conflict.
- **Check:** the PR's checks — `ci` (ruff, size limits, pytest, smoke) and `ci-budget` (≤ 5 minutes per job) are both queue conditions in `.mergify.yml`. A red `ci-budget` means a job declares no timeout or more than 5 minutes: fix the workflow, never raise the budget.
- **Conflict:** the PR is behind `main` — the queue rebases; a real conflict means the branch must be updated by its author.
- **Stale runner:** if `ci` never starts, check the self-hosted worker is online (`r630-marge-msp-01`); a queued job with no runner is an infrastructure issue, not a code issue.
- **Never** merge by pushing to `main` to unblock: `main` is protected and the queue is the only merge pilot (hermes-lite stays in dry-run).

---

## 7. Rollback

1. Application: revert the merge commit on `main` through a pull request (the queue re-runs `ci` and `ci-budget`).
2. Infrastructure: `cdk deploy` the previous tag of the stack; DynamoDB keeps point-in-time recovery — restore to a new table and swap, never overwrite in place.
3. Quick assets: redeploy the previous commit's bundle, then refresh SPICE.
4. Calculation: past calculation versions are immutable (EF-CAL-03) — a wrong rate is fixed by opening a **new** version with an author and a reason, never by rewriting history.
