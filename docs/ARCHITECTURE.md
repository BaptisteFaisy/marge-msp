# Architecture — Marge

Detailed architecture, data flows, AWS deployment model, security, running costs, and the 3-minute demo video plan. Companion document to [HLD.md](HLD.md); requirement ids refer to [SPEC.fr.md](SPEC.fr.md).

---

## 1. Deployment Model on AWS

One AWS account, one region (the region where Amazon Quick, its AI features and Bedrock Data Automation are all available — see spec §24 item 2). Every service below is named with its exact AWS service identifier.

| Layer | AWS Service | What it runs |
|---|---|---|
| Orchestration | **AWS Step Functions** | Nightly ingestion state machine: load → classify → compute → refresh |
| Scheduling | **Amazon EventBridge Scheduler** | Nightly trigger (daily), weekly validation digest, monthly review fallback |
| Compute | **AWS Lambda** (Python 3.12) | Ingestion adapters, PII stripping, margin calculation trigger, portal API, MCP tool handlers |
| Raw storage | **Amazon S3** | `s3://marge-raw/` — ticket exports, billing exports, contract PDFs |
| Curated storage | **Amazon S3** | `s3://marge-curated/` — common-model Parquet tables consumed by Quick |
| Catalogue | **AWS Glue Data Catalog** | Table definitions over the curated bucket |
| Query | **Amazon Athena** | Margin re-computation queries, ad-hoc decomposition (ENF-TRA-01) |
| Contract reading | **Amazon Bedrock Data Automation** | Custom field plan → the 16 Annex B fields, with source passages |
| Classification | **Amazon Bedrock** (Flex service tier) | Nightly batch classification of interventions, structured JSON output |
| Operational store | **Amazon DynamoDB** | Validations, matches, rates, allocation rules, decision memory, audit trail |
| Portal | **Amazon CloudFront** + **Amazon S3** (static site), **Amazon API Gateway** + **AWS Lambda** (API), **Amazon Cognito** (auth) | Validation portal (`/v1/*` endpoints, spec §16) |
| Agent actions | **Amazon Bedrock AgentCore Gateway** + **AWS Lambda** | MCP server exposing the three agent tools (spec §14.3) |
| Analytics | **Amazon Quick Sight** (Amazon Quick) | SPICE datasets, 5 dashboards, Quick Topic, row-level security |
| Conversation | **Quick chat agent** + **Quick space** (S3-backed knowledge) | Profitability analyst agent; contract citation |
| Automation | **Quick Flows** (scheduled) | Monthly review, 3rd business day |
| Review fallback | **Amazon Bedrock** + **Amazon SES** | Deterministic review rendering (`src/marge/review/`) emailed when the Flow is unsuitable (EF-REV-03) |
| Observability | **Amazon CloudWatch** (Logs, Metrics, Alarms) + **Amazon SNS** | Per-load supervision, failure alarms (ENF-OBS-01) |
| IaC | **AWS CDK** + Quick asset bundle (`infra/quicksight-assets/`) | One-command deployment (ENF-REP-01) |

Local development uses **SQLite** behind the same `Store` Protocol (`src/marge/store/base.py`): the full pipeline runs offline with zero AWS calls, which is what CI and the offline demo rely on.

---

## 2. Data Flows

### 2.1 Nightly flow (spec §8.2, ENF-PERF-01)

1. **Load.** Step Functions starts at 02:00. Lambda adapters read the day's ticket/hour exports, AWS billing rows and new contract PDFs into `s3://marge-raw/`. `strip_personal_data()` drops `engineer_ref` and keeps the level (ENF-CONF-01).
2. **Match.** New client aliases go through `marge.match.propose_matches()`; proposals above the confidence threshold queue for controller validation (EF-REF-01).
3. **Classify.** Every new intervention is classified against its client's validated contract scope via Bedrock (Flex tier), Annex C structured output. Sub-15-minute out-of-scope hits are counted but not queued (spec §13.2). Decision memory replays past human rulings first (EF-CLS-04).
4. **Compute.** `marge.calc` recomputes the month for each touched client-month; results land as Parquet in `s3://marge-curated/`; Glue partitions are updated.
5. **Refresh.** Quick SPICE ingestion refreshes the five Annex A datasets.
6. **Notify.** Out-of-scope interventions above the threshold are queued in DynamoDB for the weekly digest.

Budget: < 30 minutes for 200 clients (ENF-PERF-01), measured by CloudWatch on the state machine.

### 2.2 Weekly flow (spec §8.3)

The account manager receives the list of interventions classified `OUT_OF_SCOPE` for their clients (row-level filtered). In the portal they **validate, correct or dismiss** each one. Only validated hours count as "detected unbilled hours" (EF-CLS-03, ENF-IA-02). Decisions feed `DecisionMemory` so the same category on the same contract version is never re-asked.

### 2.3 Monthly flow (spec §8.4)

1. The scheduled **Quick Flow** reads the dashboards and the Topic, drafts the review following the Annex E template, sends it to leadership and files it in the project space (EF-REV-01/02).
2. **Fallback** (EF-REV-03): `marge.review.render_review()` builds the same review deterministically from aggregates; `narrate_review()` polishes it with Bedrock; SES emails it. Numbers always come from the datasets, never from the model.

---

## 3. Security

| Concern | Measure |
|---|---|
| Encryption | S3 SSE, DynamoDB encryption at rest, TLS 1.2+ everywhere (ENF-SEC-01) |
| Identity | Amazon Cognito user pools for the portal; IAM roles for every Lambda; no long-lived keys |
| Roles | Five business roles (spec §6): executive, ops director, account manager, controller, admin — mapped to Cognito groups and Quick row-level security |
| Row-level security | Account managers see only their clients (EF-TDB-06, ENF-CONF-03); hourly costs visible to controller + executives only |
| Labour privacy | Names stripped at load; levels only; no dashboard shows a named employee (ENF-CONF-01/02) |
| Commercial privacy | AWS partner discounts stay out of account-manager datasets (ENF-CONF-04) |
| Client data | Ticket text and contracts never leave the MSP account except to a Bedrock model **in the same region** (spec §17) |
| Prompt injection | Ticket/contract text is fenced data, never instructions; parser rejects task-deviating outputs (ENF-IA-03) |
| Audit | Every validation, rate change and recalculation writes an immutable audit record (author, date, reason) to DynamoDB (EF-VAL-02) |
| Quick admin console | IAM-permissioned only (spec §17, verified); restricted to the admin role |

---

## 4. Costs (spec §18 — exact figures)

### 4.1 Amazon Quick pricing (verified 2026-11-11)

| Item | Price |
|---|---|
| Professional subscription | **20 $** per user per month |
| Enterprise subscription | **40 $** per user per month |
| Infrastructure fee | **250 $** per account per month |
| Included agent hours | **8 h/month** (Professional), **18 h/month** (Enterprise) |
| SPICE | **0.38 $** per GB per month |
| Free trial | **30 days**, up to 25 users, subscriptions and infrastructure fee included |

### 4.2 Production estimate — 50-client MSP

| Item | Monthly cost |
|---|---|
| Quick infrastructure fee | 250 $ |
| 1 Enterprise licence + 6 Professional licences | 160 $ |
| Contract reading + work classification (Bedrock) | a few tens of dollars, volume-dependent |
| Storage and compute (S3/Athena/Lambda/DynamoDB) | a few dollars |
| **Total** | **≈ 450 $** |

Compare with the value of a single recovered unbilled hour per client per month.

### 4.3 Hackathon budget

| Period | Quick cost | Note |
|---|---|---|
| Before the trial | 0 $ | Loading, contracts, classification, calculation and portal are built without Quick |
| 30-day trial (starts **23 November**) | 0 $ | Runs until **23 December** |
| 23 December → 22 January (judging ends) | ≈ **330 $** | 250 $ infrastructure + 1 Enterprise + 2 Professional |

- The **200 $** of hackathon credits expire **31 December 2026**.
- The companion project ("Analytique IA par abonnement") may share the same Quick account to avoid a second 250 $ infrastructure fee.

---

## 5. Three-Minute Video Plan (spec §19.2 — exact timing)

| Time | Content |
|---|---|
| 0:00 – 0:20 | The problem: three tools, no per-client margin, hours given away unknowingly |
| 0:20 – 0:50 | Portal: a contract read, its clauses beside the source text, one-click validation; the proposed client matching |
| 0:50 – 1:25 | Dashboard: client ranking by margin, two clients in the red; client sheet: where the cost comes from |
| 1:25 – 1:55 | Unbilled hours: an intervention classified out of scope, the cited clause, the account manager's validation; the total in hours and value |
| 1:55 – 2:30 | Agent: "Why did this client lose ten margin points?", a price-increase simulation, then creation of the renegotiation task |
| 2:30 – 2:45 | The monthly review received by email |
| 2:45 – 3:00 | Architecture diagram, measured gains, installation at another MSP |

Production rules: English audio/captions, public YouTube link, no third-party branding or music. The video must show the internal accounts **and** the upstream/downstream environments: sources, data lake, Quick console, and the ticketing tool where the renegotiation task is created.

---

## 6. Repository Layout

```
marge-msp/
├── src/marge/
│   ├── domain/        # pure dataclasses (frozen): money, periods, parties, work, results, settings, audit
│   ├── calc/          # margin model (spec §12): inputs, rates, hours, allocation, coverage, margin, effort, renewal, trace, versioning
│   ├── ingest/        # source Protocol + ticket/billing/invoice loaders, PII stripping
│   │                  #   (marketplace connectors of EF-SRC-05: post-hackathon (spec §5.2))
│   ├── store/         # Store Protocol + SQLite implementation (`src/marge/store/sqlite_store.py`);
│   │                  #   the DynamoDB backend is a remaining gap — see docs/acceptance/MATRIX.md §9
│   ├── match/         # client identity matching (merged)
│   ├── contracts/     # Annex B extraction + validation (merged)
│   ├── classify/      # Annex C classification + decision memory (merged)
│   ├── api/           # FastAPI portal API, spec §16 (merged)
│   ├── mcp/           # MCP server, three tools (merged)
│   ├── review/        # monthly review, Annex E (merged)
│   ├── quicksight/    # datasets, topic, dashboards, RLS, flows, asset bundle (merged)
│   ├── pipeline/      # nightly/weekly/monthly orchestration (merged)
│   ├── eval/          # accuracy harnesses R2/R3/R5/R11 (merged)
│   ├── cli.py         # single entry point: smoke, generate, demo, eval, nightly, weekly,
│   │                  #   monthly, assets, mcp, serve, version
│   └── commands/      # CLI command implementations
├── data/generator/    # synthetic MSP: 12 clients, 6 months (2026-05 → 2026-10), 3 922 interventions,
│                      #   13 contract versions, 150 labelled interventions, 20 reference questions
├── data/generated/    # dataset written by `python3 -m marge.cli generate`
├── portal/            # static validation portal, no build step (see `portal/README.md`)
├── infra/cdk/         # CDK app + stacks
├── infra/quicksight-assets/  # committed Quick asset bundle, verified by `python3 -m marge.cli assets --check`
├── scripts/           # repository guards (`scripts/check_limits.py`)
├── tests/             # offline deterministic tests, tests/fakes/ shared doubles
└── docs/              # this documentation set
```

CI: GitHub Actions on self-hosted workers, every job ≤ 5 minutes (`ci-budget` guard), Mergify merge queue, hermes-lite review gate. See [README](../README.md) and [RUNBOOK.md](RUNBOOK.md).
