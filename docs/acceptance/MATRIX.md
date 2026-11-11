# Acceptance & Traceability Matrix — Marge

Every requirement of [SPEC.fr.md](../SPEC.fr.md) (chapters 9 and 10) and every acceptance scenario of chapter 23, mapped to the file that implements it and the test that proves it.

**Reading conventions**

- A path in `backticks` **exists in this branch today** — each one was checked with `ls` before being written here.
- A path written as plain `planned: src/marge/<module>/<file>.py` is the **contracted location** from [CONTRACT.md](../CONTRACT.md) §2–§3: the module belongs to another lot and is not merged into `main` yet. The row is marked **planned**.
- Status: **implemented** = code + proving test in this branch · **partial** = the domain model or Protocol exists, the behaviour is planned · **planned** = nothing in `main` yet, contracted · **post-hackathon** = spec priority `C`, out of scope by design (spec §5.2).
- The module list of the brief (`store`, `ingest`, `match`, `contracts`, `classify`, `api`, `mcp`, `review`, `quicksight`, `eval`, `pipeline`, `cli`) is honoured: what exists is cited with its real path, what does not exist yet is cited with its contracted path and marked planned.

---

## 1. Sources and reference data — EF-SRC, EF-REF

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-SRC-01 | `src/marge/ingest/base.py` (`TicketSource`), `src/marge/domain/work.py` (`Intervention`); loader planned: src/marge/ingest/loaders.py | `tests/fakes/fake_sources.py` (fake `TicketSource`); loader test planned: tests/unit/ingest/test_load_interventions.py | partial |
| EF-SRC-02 | `src/marge/ingest/base.py` (`BillingSource`), `src/marge/domain/costs.py` (`AwsCost`); loader planned: src/marge/ingest/loaders.py | planned: tests/unit/ingest/test_load_aws_costs.py | partial |
| EF-SRC-03 | `src/marge/ingest/base.py` (`ContractSource`, `DocumentExtractor`), `src/marge/domain/parties.py` (`Contract`) | planned: tests/unit/ingest/test_contract_source.py | partial |
| EF-SRC-04 | `src/marge/ingest/base.py` (`InvoiceSource`), `src/marge/domain/costs.py` (`Invoice`) | planned: tests/unit/ingest/test_load_invoices.py | partial |
| EF-SRC-05 | planned: src/marge/ingest/connectors.py | — | post-hackathon (priority C, spec §5.2) |
| EF-REF-01 | `src/marge/domain/parties.py` (`ClientMatch`); matcher planned: src/marge/match/propose.py | planned: tests/unit/match/test_propose_matches.py | partial |
| EF-REF-02 | `src/marge/domain/costs.py` (`Rate`), `src/marge/calc/rates.py` (`rate_in_force`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_cost_breakdown`) | implemented |
| EF-REF-03 | `src/marge/domain/costs.py` (`ToolingCost`), `src/marge/calc/allocation.py` (`allocate_tooling`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_cost_breakdown` — tooling 340.00 €) | implemented |
| EF-REF-04 | `src/marge/domain/enums.py` (`UNASSIGNED_CLIENT_ID`), `src/marge/calc/coverage.py` (`compute_coverage`) | planned: tests/unit/calc/test_coverage.py | partial |

## 2. Contracts — EF-CTR

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-CTR-01 | `src/marge/domain/parties.py` (`ContractFields`), `src/marge/ingest/base.py` (`DocumentExtractor`); Bedrock Data Automation planned: src/marge/contracts/extraction.py | planned: tests/unit/contracts/test_extract_fields.py | partial |
| EF-CTR-02 | `src/marge/domain/parties.py` (`SourceSpan`, `ExtractedField`) | planned: tests/unit/contracts/test_source_span.py | partial |
| EF-CTR-03 | `src/marge/domain/enums.py` (`ContractStatus`), `src/marge/domain/parties.py` (`Contract`), `src/marge/calc/margin.py` (only a `VALIDATED` contract feeds revenue) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_month_is_complete`) | implemented |
| EF-CTR-04 | `src/marge/domain/parties.py` (`Contract.version`); amendment planned: src/marge/contracts/versioning.py | planned: tests/unit/contracts/test_new_version.py | partial |
| EF-CTR-05 | `src/marge/calc/renewal.py` (`build_renewal_watch`), `src/marge/domain/settings.py` (`renewal_horizon_days = 90`) | planned: tests/unit/calc/test_renewal_watch.py | implemented (untested in this branch) |

## 3. Work classification — EF-CLS

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-CLS-01 | `src/marge/domain/work.py` (`Classification`), `src/marge/domain/enums.py` (`WorkClass`); classifier planned: src/marge/classify/classifier.py | planned: tests/unit/classify/test_classify.py | partial |
| EF-CLS-02 | `src/marge/domain/work.py` (`Classification.cited_clause`), `src/marge/domain/parties.py` (`SourceSpan`) | planned: tests/unit/classify/test_cited_clause.py | partial |
| EF-CLS-03 | `src/marge/domain/settings.py` (`Settings.needs_validation`, 15-minute floor), `src/marge/domain/enums.py` (`DecisionStatus`); queue planned: src/marge/pipeline/weekly.py | planned: tests/unit/pipeline/test_weekly_queue.py | partial |
| EF-CLS-04 | `src/marge/domain/work.py` (`CategoryDecision`), `src/marge/store/base.py` (`WorkRepository.find_category_decision`); memory planned: src/marge/classify/memory.py | planned: tests/unit/classify/test_decision_memory.py | partial |
| EF-CLS-05 | `src/marge/calc/hours.py` (`over_quota_hours`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_unbilled_hours` — over-quota 0.00) | implemented |

## 4. Calculation — EF-CAL

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-CAL-01 | `src/marge/calc/margin.py` (`compute_margin_month`), `src/marge/domain/results.py` (`MarginMonth`, `RevenueBreakdown`, `CostBreakdown`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_revenue_breakdown`, `test_golden_cost_breakdown`, `test_golden_margin_and_rate`) | implemented |
| EF-CAL-02 | `src/marge/calc/hours.py` (`compute_hours_summary`), `src/marge/domain/results.py` (`HoursSummary`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_unbilled_hours` — 9 h, 990 €) | implemented |
| EF-CAL-03 | `src/marge/calc/versioning.py` (`CalcVersion`, `VersionHistory`) | planned: tests/unit/calc/test_versioning.py | implemented (untested in this branch) |
| EF-CAL-04 | `src/marge/calc/margin.py` (`MarginState.ESTIMATE` / `INCOMPLETE`, `incomplete_reason`), `src/marge/domain/settings.py` (`coverage_floor = 0.80`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_month_is_complete`) | implemented |
| EF-CAL-05 | `src/marge/calc/effort.py` (`compute_effort_slices`), `src/marge/domain/results.py` (`EffortSlice`) | planned: tests/unit/calc/test_effort_slices.py | implemented (untested in this branch) |

## 5. Dashboards, agent, review — EF-TDB, EF-AGT, EF-REV

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-TDB-01..05 | planned: src/marge/quicksight/dashboards.py, planned: src/marge/quicksight/datasets.py, planned: src/marge/quicksight/topic.py | planned: tests/unit/quicksight/test_dashboards.py | planned |
| EF-TDB-06 | planned: src/marge/quicksight/rls.py, planned: src/marge/api/rls.py | planned: tests/unit/quicksight/test_rls.py | planned |
| EF-AGT-01..03 | planned: src/marge/quicksight/agent.py, planned: src/marge/quicksight/topic.py | planned: tests/unit/quicksight/test_agent.py | planned |
| EF-AGT-04 | `src/marge/ingest/base.py` (`ItsmActions`); MCP server planned: src/marge/mcp/tools.py | planned: tests/unit/mcp/test_tools.py | partial |
| EF-AGT-05 | planned: src/marge/quicksight/scenarios.py | planned: tests/unit/quicksight/test_scenarios.py | planned |
| EF-REV-01 | planned: src/marge/quicksight/flows.py | planned: tests/unit/quicksight/test_flows.py | planned |
| EF-REV-02 | planned: src/marge/review/render.py | planned: tests/unit/review/test_render_review.py | planned |
| EF-REV-03 | planned: src/marge/review/narrate.py | planned: tests/unit/review/test_narrate_fallback.py | planned |

## 6. Validation and administration — EF-VAL, EF-ADM

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-VAL-01 | planned: src/marge/api/routes_validation.py, planned: portal/index.html | planned: tests/unit/api/test_routes_validation.py | planned |
| EF-VAL-02 | `src/marge/domain/audit.py` (`ValidationRecord`, `AuditEntry`), `src/marge/store/base.py` (`AuditRepository`) | planned: tests/unit/store/test_audit.py | partial |
| EF-ADM-01 | `src/marge/domain/settings.py` (`Settings`); API planned: src/marge/api/routes_admin.py | planned: tests/unit/api/test_routes_admin.py | partial |
| EF-ADM-02 | `src/marge/calc/coverage.py` (`compute_coverage`), `src/marge/domain/results.py` (`Coverage`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_month_is_complete` — coverage 1.0000) | implemented |
| EF-ADM-03 | [TEST-INSTRUCTIONS.md](../TEST-INSTRUCTIONS.md) §2 — portal roles + Quick roles, demo credentials | manual — judging checklist | implemented (doc) |

## 7. Non-functional requirements — ENF

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| ENF-CONF-01 | `src/marge/domain/enums.py` (`WorkLevel`), `src/marge/ingest/base.py`; PII stripping planned: src/marge/ingest/pii.py (`strip_personal_data`) | planned: tests/unit/ingest/test_strip_personal_data.py | partial |
| ENF-CONF-02 | planned: src/marge/quicksight/datasets.py, planned: src/marge/api/serializers.py | planned: tests/unit/quicksight/test_datasets.py | planned |
| ENF-CONF-03 | planned: src/marge/api/rls.py, planned: src/marge/quicksight/rls.py | planned: tests/unit/api/test_rls.py | planned |
| ENF-CONF-04 | planned: src/marge/quicksight/rls.py | planned: tests/unit/quicksight/test_rls.py | planned |
| ENF-SEC-01 | planned: infra/cdk/portal.py, planned: infra/cdk/data_lake.py | CDK assertions — planned | planned |
| ENF-IA-01 | `src/marge/calc/margin.py`, `src/marge/calc/hours.py` — every figure computed in code, no model call anywhere in `calc` | `tests/unit/calc/test_golden_annex_d.py` (golden figures reproduced exactly) | implemented |
| ENF-IA-02 | `src/marge/domain/enums.py` (`DecisionStatus`, `ContractStatus`), `src/marge/domain/work.py` (`needs_human_validation`) | planned: tests/unit/classify/test_validation_required.py | partial |
| ENF-IA-03 | planned: src/marge/classify/prompt.py (fenced untrusted text), planned: src/marge/classify/classifier.py (`parse_model_output`) | planned: tests/unit/classify/test_prompt_injection.py | planned |
| ENF-TRA-01 | `src/marge/calc/trace.py` (`margin_lines`), `src/marge/domain/results.py` (`MarginLine`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_margin_decomposes_to_source_lines`) | implemented |
| ENF-PERF-01 | planned: src/marge/pipeline/nightly.py, planned: infra/cdk/observability.py (duration metric) | planned: tests/integration/test_nightly_200_clients.py (< 30 min budget) | planned |
| ENF-REP-01 | `src/marge/ingest/base.py` + `src/marge/store/base.py` (swappable Protocols); CDK + bundle planned: infra/cdk/app.py, src/marge/quicksight/assets.py | planned: tests/unit/quicksight/test_assets.py | partial |
| ENF-OBS-01 | planned: infra/cdk/observability.py (CloudWatch alarms + SNS) | CDK assertions — planned | planned |

## 8. Acceptance scenarios R1..R15 (spec §23)

| Id | Scenario | Proof (test) | Status |
|---|---|---|---|
| R1 | Load the three sources → coverage > 95 % | planned: tests/integration/test_load_three_sources.py | planned |
| R2 | Client matching → > 80 % right, 100 % after validation | planned: tests/unit/match/test_propose_matches.py | planned |
| R3 | Read 12 contracts → > 90 % fields right, source passage shown | planned: tests/unit/contracts/test_extract_fields.py | planned |
| R4 | Unvalidated contract → margin flagged `INCOMPLETE` | `tests/unit/calc/test_golden_annex_d.py` covers the `COMPLETE` branch; `INCOMPLETE` branch planned: tests/unit/calc/test_margin_state.py | partial |
| R5 | 150 labelled interventions → > 90 % agreement | planned: tests/unit/eval/test_classification_agreement.py | planned |
| R6 | Clearly included intervention → never `OUT_OF_SCOPE` | planned: tests/unit/classify/test_never_out_of_scope.py | planned |
| R7 | Validate out-of-scope hours → unbilled hours and value updated | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_unbilled_hours`); portal path planned: tests/unit/api/test_routes_classifications.py | partial |
| R8 | Margin decomposes to source lines; hand total identical | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_margin_decomposes_to_source_lines`) | implemented |
| R9 | Hourly cost change → past months unchanged, new dated version | planned: tests/unit/calc/test_versioning.py | planned |
| R10 | Account manager sees only own clients, no hourly costs | planned: tests/unit/api/test_rls.py | planned |
| R11 | 20 reference questions → > 90 % correct | planned: tests/unit/eval/test_agent_accuracy.py | planned |
| R12 | Clause question → answer cites the clause | planned: tests/unit/quicksight/test_agent.py | planned |
| R13 | Renegotiation task created in the ITSM tool with dossier | planned: tests/unit/mcp/test_tools.py | planned |
| R14 | Monthly review received, figures identical to dashboards | planned: tests/unit/review/test_render_review.py | planned |
| R15 | Install in a clean account following the README | [RUNBOOK.md](../RUNBOOK.md) §2 + `make demo` on a fresh clone | implemented (procedure) |

---

## 9. Planned modules — paths cited in this matrix that do not exist in `main` yet

These are the contracted locations ([CONTRACT.md](../CONTRACT.md) §2–§3) of modules owned by the other lots. They are listed here in one place so that the gap between "contracted" and "merged" is explicit rather than buried in the tables above. They are written without code formatting on purpose: the automated path check on this file must stay green for real files only.

- src/marge/ingest/loaders.py, src/marge/ingest/pii.py, src/marge/ingest/connectors.py (lot1)
- src/marge/store/sqlite_store.py, src/marge/store/dynamo_store.py (lot1)
- src/marge/match/propose.py, src/marge/contracts/extraction.py, src/marge/contracts/versioning.py, src/marge/classify/classifier.py, src/marge/classify/prompt.py, src/marge/classify/memory.py (lot2)
- src/marge/api/routes_validation.py, src/marge/api/routes_admin.py, src/marge/api/rls.py, src/marge/api/serializers.py, portal/index.html (lot3)
- src/marge/mcp/tools.py, src/marge/mcp/server.py, src/marge/review/render.py, src/marge/review/narrate.py (lot4)
- src/marge/quicksight/datasets.py, src/marge/quicksight/dashboards.py, src/marge/quicksight/topic.py, src/marge/quicksight/rls.py, src/marge/quicksight/agent.py, src/marge/quicksight/scenarios.py, src/marge/quicksight/flows.py, src/marge/quicksight/assets.py, src/marge/pipeline/nightly.py, src/marge/pipeline/weekly.py, infra/cdk/app.py, infra/cdk/portal.py, infra/cdk/data_lake.py, infra/cdk/observability.py (lot5)
- data/generator (lot6), src/marge/eval (lot6)

Test files marked planned in the tables follow the same ownership: `tests/unit/<module>/…` mirrors `src/marge/<module>/…` (CONTRACT.md §4).

---

## 10. How this matrix stays honest

- `python3 -m marge.cli smoke` recomputes the Annex D golden case (4 620 € revenue, 3 725 € cost, 895 € margin = 19.4 %, 9 h × 110 € = 990 €) on every pull request; a drift in the calculation model breaks the build.
- `make limits` guards the size rules, `make lint` guards style — neither replaces a test.
- [CONTRACT.md](../CONTRACT.md) §5 requires that any requirement a module implements appears in this file. A row still marked **planned** after that module merges is a release blocker.
- Planned paths are the contracted locations: if a lot refines a file name, this matrix is updated in the same pull request — never silently.
