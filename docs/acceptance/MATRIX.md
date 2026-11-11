# Acceptance & Traceability Matrix — Marge

Every requirement of [SPEC.fr.md](../SPEC.fr.md) (chapters 9 and 10) and every acceptance scenario of chapter 23, mapped to the file that implements it and the test that proves it.

**Reading conventions**

- A path in code formatting **exists in this branch today** — each one was checked with `ls` before being written here.
- Status: **implemented** = code + proving test in this branch · **partial** = the code is merged but one step (an AWS console action, a missing automated proof) is still open · **post-hackathon** = spec priority `C`, out of scope by design (spec §5.2) · **manual** = to be done by hand in the AWS console (see [RUNBOOK.md](../RUNBOOK.md) §4).
- The module list of the brief (`store`, `ingest`, `match`, `contracts`, `classify`, `api`, `mcp`, `review`, `quicksight`, `eval`, `pipeline`, `cli`) is honoured: each module is cited with its real path.
- A requirement with no implementation in `main` is written as **not found in main — to implement**; no path is invented for it.

---

## 1. Sources and reference data — EF-SRC, EF-REF

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-SRC-01 | `src/marge/ingest/base.py` (`TicketSource`), `src/marge/ingest/tickets.py` (`load_interventions`, `strip_personal_data`), `src/marge/ingest/loaders.py` (`load_month`) | `tests/unit/ingest/test_ingest.py`, `tests/integration/test_seeded_situations.py` | implemented |
| EF-SRC-02 | `src/marge/ingest/base.py` (`BillingSource`), `src/marge/ingest/billing.py` (`load_aws_costs`, `convert`), `src/marge/ingest/loaders.py` | `tests/unit/ingest/test_ingest.py` (`test_aws_cost_is_converted_to_the_reporting_currency`), `tests/integration/test_seeded_situations.py` (`test_aws_costs_are_converted_before_the_calculation`) | implemented |
| EF-SRC-03 | `src/marge/ingest/base.py` (`ContractSource`), `src/marge/ingest/invoices.py` (`S3ContractSource`), `src/marge/contracts/extraction.py` | `tests/unit/contracts/test_extraction.py`, `tests/integration/test_contracts.py` | implemented |
| EF-SRC-04 | `src/marge/ingest/base.py` (`InvoiceSource`), `src/marge/ingest/invoices.py` (`load_invoices`), `src/marge/ingest/loaders.py` | `tests/unit/ingest/test_ingest.py` (`test_invoices_are_loaded_with_their_hours`) | implemented |
| EF-SRC-05 | not found in main — to implement (marketplace connectors) | — | post-hackathon (priority C, spec §5.2) |
| EF-REF-01 | `src/marge/match/matcher.py`, `src/marge/match/proposal.py` (`propose_matches`), `src/marge/match/normalise.py`, `src/marge/domain/parties.py` (`ClientMatch`) | `tests/unit/match/test_matching.py`, `tests/unit/eval/test_match_accuracy.py`, `tests/unit/api/test_routes_matches.py`; measured by `python3 -m marge.cli eval` (97.30 % vs target 0.80) | implemented |
| EF-REF-02 | `src/marge/domain/costs.py` (`Rate`), `src/marge/calc/rates.py` (`rate_in_force`), `src/marge/ingest/loaders.py` (`load_rates`) | `tests/integration/test_seeded_situations.py` (`test_one_level_changes_rate_on_july_first`) | implemented |
| EF-REF-03 | `src/marge/domain/costs.py` (`ToolingCost`), `src/marge/calc/allocation.py` (`allocate_tooling`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_cost_breakdown` — tooling 340.00 €), `tests/integration/test_seeded_situations.py` (`test_tooling_uses_the_four_allocation_bases`) | implemented |
| EF-REF-04 | `src/marge/domain/enums.py` (`UNASSIGNED_CLIENT_ID`), `src/marge/calc/coverage.py` (`compute_coverage`), `src/marge/eval/report.py` | `tests/unit/ingest/test_ingest.py` (`test_intervention_without_client_lands_in_the_unassigned_bucket`), `tests/integration/test_seeded_situations.py` (`test_hours_without_a_client_stay_visible`) | implemented |

## 2. Contracts — EF-CTR

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-CTR-01 | `src/marge/contracts/extraction.py` (`extract_fields`, `LocalTextExtractor`, `BedrockDataAutomation`), `src/marge/domain/parties.py` (`ContractFields`) | `tests/unit/contracts/test_extraction.py`, `tests/unit/eval/test_clause_accuracy.py`; measured by `python3 -m marge.cli eval` (clause accuracy 100 % vs target 0.90) | implemented |
| EF-CTR-02 | `src/marge/domain/parties.py` (`SourceSpan`, `ExtractedField`), `src/marge/contracts/extraction.py` (`side_by_side`), `src/marge/api/serializers.py` | `tests/unit/contracts/test_extraction.py` (`test_every_extracted_field_has_its_source_passage`), `tests/unit/api/test_routes_contracts.py` (`test_get_contract_shows_span_next_to_value`), `tests/unit/eval/test_fields.py` | implemented |
| EF-CTR-03 | `src/marge/domain/enums.py` (`ContractStatus`), `src/marge/contracts/validation.py` (`validate_contract`), `src/marge/store/sqlite_store.py` (only a validated contract is active) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_month_is_complete`), `tests/unit/store/test_sqlite_store.py` (`test_active_contract_ignores_unvalidated`), `tests/integration/test_seeded_situations.py` (`test_one_contract_is_not_validated_and_makes_the_margin_incomplete`) | implemented |
| EF-CTR-04 | `src/marge/contracts/validation.py` (`new_version`), `src/marge/domain/parties.py` (`Contract.version`) | `tests/unit/contracts/test_extraction.py` (`test_amendment_creates_a_new_version`), `tests/integration/test_seeded_situations.py` (`test_one_contract_has_a_second_version`) | implemented |
| EF-CTR-05 | `src/marge/calc/renewal.py` (`build_renewal_watch`), `src/marge/domain/settings.py` (`renewal_horizon_days = 90`), `src/marge/pipeline/nightly.py` | `tests/unit/quicksight/test_dashboards.py` (`test_renewal_dashboard_filters_on_the_ninety_day_horizon`), `tests/integration/test_seeded_situations.py` (`test_one_profitable_client_renews_in_sixty_days_with_a_falling_margin`) | implemented |

## 3. Work classification — EF-CLS

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-CLS-01 | `src/marge/classify/service.py`, `src/marge/classify/bedrock.py`, `src/marge/eval/local_classifier.py`, `src/marge/domain/work.py` (`Classification`, `WorkClass`) | `tests/unit/classify/test_classification.py`, `tests/unit/eval/test_local_classifier.py`; measured by `python3 -m marge.cli eval` (classification agreement 100 % vs target 0.90) | implemented |
| EF-CLS-02 | `src/marge/domain/work.py` (`Classification.cited_clause`), `src/marge/domain/parties.py` (`SourceSpan`), `src/marge/classify/service.py` | `tests/unit/classify/test_classification.py` (`test_out_of_scope_work_is_queued_with_its_clause`) | implemented |
| EF-CLS-03 | `src/marge/domain/settings.py` (`Settings.needs_validation`, 15-minute floor), `src/marge/pipeline/nightly.py`, `src/marge/pipeline/weekly.py`, `src/marge/api/routes_validation.py` | `tests/unit/pipeline/test_pipeline.py` (`test_weekly_queues_group_by_account_manager`), `tests/unit/api/test_routes_classifications.py`, `tests/unit/classify/test_classification.py` (`test_in_scope_work_is_not_queued`) | implemented |
| EF-CLS-04 | `src/marge/classify/memory.py`, `src/marge/domain/work.py` (`CategoryDecision`), `src/marge/api/routes_validation.py` | `tests/unit/classify/test_classification.py` (`test_decision_memory_reuses_a_past_decision`), `tests/unit/api/test_routes_classifications.py` (`test_decide_classification_remembers_category`) | implemented |
| EF-CLS-05 | `src/marge/calc/hours.py` (`compute_hours_summary`), `src/marge/domain/results.py` (`HoursSummary.over_quota_hours`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_unbilled_hours` — over-quota 0.00) | implemented |

## 4. Calculation — EF-CAL

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-CAL-01 | `src/marge/calc/margin.py` (`compute_margin_month`), `src/marge/calc/inputs.py`, `src/marge/domain/results.py` (`MarginMonth`, `RevenueBreakdown`, `CostBreakdown`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_revenue_breakdown`, `test_golden_cost_breakdown`, `test_golden_margin_and_rate`) | implemented |
| EF-CAL-02 | `src/marge/calc/hours.py` (`compute_hours_summary`), `src/marge/domain/results.py` (`HoursSummary`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_unbilled_hours` — 9 h, 990 €) | implemented |
| EF-CAL-03 | `src/marge/calc/versioning.py` (`CalcVersion`, `VersionHistory`), `src/marge/api/recalculate.py` (`_next_calc_version`), `src/marge/store/migrations.py` | `tests/unit/api/test_routes_admin.py` (`test_recalculate_bumps_calc_version`), `tests/integration/test_seeded_situations.py` (`test_one_level_changes_rate_on_july_first`) | implemented |
| EF-CAL-04 | `src/marge/calc/margin.py` (`compute_margin_month`, `incomplete_reason`), `src/marge/domain/enums.py` (`MarginState.ESTIMATE` / `INCOMPLETE`), `src/marge/domain/settings.py` (`coverage_floor = 0.80`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_month_is_complete`), `tests/integration/test_seeded_situations.py` (`test_one_client_month_has_poor_coverage_and_is_an_estimate`) | implemented |
| EF-CAL-05 | `src/marge/calc/effort.py` (`compute_effort_slices`), `src/marge/domain/results.py` (`EffortSlice`) | `tests/unit/api/test_routes_admin.py` (`test_recalculate_writes_hours_and_effort`), `tests/unit/quicksight/test_datasets.py` (`test_effort_dataset_is_split_by_category_and_level`) | implemented |

## 5. Dashboards, agent, review — EF-TDB, EF-AGT, EF-REV

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-TDB-01..05 | `src/marge/quicksight/dashboards.py` (six dashboards), `src/marge/quicksight/datasets.py` (five datasets), `src/marge/quicksight/topic.py`, `src/marge/quicksight/models.py`, `src/marge/quicksight/quick_api.py` (`create_dashboard`), `src/marge/quicksight/assets.py` | `tests/unit/quicksight/test_dashboards.py`, `tests/unit/quicksight/test_datasets.py`, `tests/unit/quicksight/test_topic.py`, `tests/unit/quicksight/test_quick_api.py`, `tests/unit/quicksight/test_assets.py` | implemented (deployed from the bundle; the console steps are listed in `infra/quicksight-assets/deploy-plan.json`) |
| EF-TDB-06 | `src/marge/quicksight/rls.py` (two Quick rule sets), `src/marge/api/rls.py` (`visible_client_ids`, `redact_rates_for_actor`, `redact_row`), `src/marge/mcp/guards.py` | `tests/unit/quicksight/test_rls.py`, `tests/unit/api/test_rls.py` | implemented |
| EF-AGT-01..03 | `src/marge/quicksight/agent.py` (instructions, rules, examples), `src/marge/quicksight/quick_api.py` (`create_agent`), `src/marge/quicksight/topic.py` (knowledge), `infra/quicksight-assets/marge-assets.json` | `tests/unit/quicksight/test_agent.py` | partial — the bundle and the API call are merged and tested; binding the agent to the topic, the contracts space and the three MCP actions is a console action ([RUNBOOK.md](../RUNBOOK.md) §4.2) |
| EF-AGT-04 | `src/marge/mcp/tools.py` (`create_renegotiation_task`, `draft_extra_billing_proposal`, `get_margin_breakdown`), `src/marge/mcp/server.py`, `src/marge/ingest/base.py` (`ItsmActions`) | `tests/unit/mcp/test_mcp.py` (`test_renegotiation_task_is_created_with_a_dossier`, `test_billing_proposal_is_only_a_draft`) | implemented |
| EF-AGT-05 | `src/marge/quicksight/scenarios.py` (`SC-PRICE-INCREASE`, `SC-EFFORT-REDUCTION`) | `tests/unit/quicksight/test_scenarios.py` | implemented |
| EF-REV-01 | `src/marge/quicksight/flows.py` (monthly review flow), `src/marge/review/aggregates.py`, `src/marge/review/template.py` (Annex E), `src/marge/pipeline/monthly.py` | `tests/unit/quicksight/test_flows.py`, `tests/unit/review/test_review.py`, `tests/unit/pipeline/test_pipeline.py` (`test_monthly_review_produces_text_and_figures`) | partial — the flow and the deterministic review are merged and tested; the scheduled flow itself is created in the console ([RUNBOOK.md](../RUNBOOK.md) §4.3) |
| EF-REV-02 | `src/marge/review/fallback.py` (`publish`, `SesMailer`, `S3Archive`), `src/marge/quicksight/flows.py` (destination: direction + project space), `src/marge/commands/pipeline.py` (`monthly --to`) | `tests/unit/pipeline/test_pipeline.py` (`test_monthly_review_produces_text_and_figures`); no automated test of the SES/S3 delivery — manual on a live account ([RUNBOOK.md](../RUNBOOK.md) §4.3) | partial |
| EF-REV-03 | `src/marge/review/narrate.py` (`narrate_review`, `unknown_figures`), `src/marge/review/fallback.py`, `src/marge/commands/pipeline.py` (`monthly`) | `tests/unit/review/test_review.py` (`test_narration_is_used_when_it_invents_no_figure`, `test_narration_is_dropped_when_it_invents_a_figure`, `test_unknown_figures_detects_an_invented_amount`) | implemented |

## 6. Validation and administration — EF-VAL, EF-ADM

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| EF-VAL-01 | `src/marge/api/routes_validation.py` (matches, contracts, classifications), `src/marge/api/app.py`, `portal/index.html`, `portal/app.js` | `tests/unit/api/test_route_table.py` (`test_route_table_matches_chapter_16`), `tests/unit/api/test_routes_matches.py`, `tests/unit/api/test_routes_contracts.py`, `tests/unit/api/test_routes_classifications.py` | implemented |
| EF-VAL-02 | `src/marge/domain/audit.py` (`ValidationRecord`, `AuditEntry`), `src/marge/store/base.py` (`AuditRepository`), `src/marge/store/sqlite_store.py`, `src/marge/api/routes_validation.py` | `tests/unit/api/test_routes_classifications.py` (`test_decide_classification_approve_and_audit`), `tests/unit/api/test_routes_contracts.py` (`test_update_fields_changes_value_and_audits`), `tests/unit/store/test_sqlite_store.py` (`test_settings_round_trip_and_audit`) | implemented |
| EF-ADM-01 | `src/marge/domain/settings.py` (`Settings`), `src/marge/api/routes_admin.py` (rates, allocation rules, recalculation), `src/marge/quicksight/dashboards.py` (thresholds) | `tests/unit/api/test_routes_admin.py` (`test_put_rates_appends_and_audits`, `test_list_allocation_rules_ok`) | implemented |
| EF-ADM-02 | `src/marge/calc/coverage.py` (`compute_coverage`), `src/marge/domain/results.py` (`Coverage`), `src/marge/quicksight/datasets.py` (`marge_client_mois.coverage`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_month_is_complete` — coverage 1.0000), `tests/unit/api/test_routes_admin.py` (`test_coverage_ok`) | implemented |
| EF-ADM-03 | [TEST-INSTRUCTIONS.md](../TEST-INSTRUCTIONS.md) §2 — portal roles + Quick roles, demo credentials, `src/marge/api/auth.py` (role resolution) | `tests/unit/api/test_auth.py`; credentials consumed by hand during the judging | implemented (doc) |

## 7. Non-functional requirements — ENF

| Req | Implementation | Proof (test) | Status |
|---|---|---|---|
| ENF-CONF-01 | `src/marge/domain/enums.py` (`WorkLevel`), `src/marge/domain/costs.py` (`Rate` per level), `src/marge/ingest/tickets.py` (`strip_personal_data`), `src/marge/quicksight/datasets.py` (levels only, no person field) | `tests/unit/ingest/test_ingest.py` (`test_personal_data_is_stripped_at_the_door`), `tests/unit/quicksight/test_datasets.py` (`test_no_person_field_in_any_dataset`) | implemented |
| ENF-CONF-02 | `src/marge/quicksight/datasets.py`, `src/marge/quicksight/topic.py`, `src/marge/domain/work.py` (levels, never a name) | `tests/unit/quicksight/test_datasets.py` (`test_no_person_field_in_any_dataset`), `tests/unit/quicksight/test_topic.py` | implemented |
| ENF-CONF-03 | `src/marge/api/rls.py` (`visible_client_ids`, `redact_rates_for_actor`), `src/marge/quicksight/rls.py`, `src/marge/api/auth.py` (Cognito groups) | `tests/unit/api/test_rls.py`, `tests/unit/quicksight/test_rls.py` | implemented |
| ENF-CONF-04 | `src/marge/api/rls.py` (`CONFIDENTIAL_KEYS`, `redact_row` — `aws_discount`, `internal_discount` hidden) | `tests/unit/api/test_rls.py` (`test_redact_row_hides_labour_and_discount_keys_for_account_manager`) | implemented |
| ENF-SEC-01 | `infra/cdk/portal.py` (Cognito user pool, one group per role, API Gateway authorizer), `infra/cdk/data_lake.py` (S3 SSE, Athena work group encryption) | no automated CDK assertion test in this branch — verified by deployment ([RUNBOOK.md](../RUNBOOK.md) §2) | partial |
| ENF-IA-01 | `src/marge/calc/margin.py`, `src/marge/calc/hours.py`, `src/marge/domain/money.py` — every figure computed in code, no model call in `calc`; `src/marge/quicksight/agent.py` forbids the agent to compute | `tests/unit/calc/test_golden_annex_d.py` (golden figures reproduced exactly), `tests/unit/quicksight/test_agent.py` (`test_agent_instruction_forbids_inventing_a_number`) | implemented |
| ENF-IA-02 | `src/marge/domain/enums.py` (`DecisionStatus`, `ContractStatus`), `src/marge/domain/work.py` (`needs_human_validation`), `src/marge/contracts/validation.py`, `src/marge/classify/service.py`, `src/marge/domain/audit.py` | `tests/unit/api/test_routes_classifications.py` (`test_approved_out_of_scope_counts_as_unbilled`), `tests/unit/store/test_sqlite_store.py` (`test_active_contract_ignores_unvalidated`), `tests/unit/eval/test_classification_agreement.py` (`test_classification_agreement_fails_on_one_r6_violation`) | implemented |
| ENF-IA-03 | `src/marge/classify/prompt.py` (fenced untrusted text), `src/marge/classify/output.py` (`parse_model_output`) | `tests/unit/classify/test_classification.py` (`test_prompt_fences_untrusted_text`, `test_fence_breaks_are_neutralised`, `test_parser_rejects_an_injection_answer`) | implemented |
| ENF-TRA-01 | `src/marge/calc/trace.py` (`margin_lines`), `src/marge/domain/results.py` (`MarginLine`) | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_margin_decomposes_to_source_lines`) | implemented |
| ENF-PERF-01 | `src/marge/pipeline/nightly.py` (`duration_seconds` on the nightly report), `infra/cdk/observability.py` (alarm on the run duration) | the nightly run measures its own duration (`tests/unit/pipeline/test_pipeline.py`, `test_run_nightly_end_to_end`); the 200-client / 30-minute budget is **not** proven by an automated test on the 12-client dataset — manual on the deployed account ([RUNBOOK.md](../RUNBOOK.md) §5) | partial |
| ENF-REP-01 | `src/marge/store/base.py` (`Store` Protocol), `src/marge/store/sqlite_store.py`, `src/marge/quicksight/assets.py`, `src/marge/commands/assets.py`, `infra/cdk/app.py`, `infra/quicksight-assets/marge-assets.json` | `tests/unit/quicksight/test_assets.py` (`test_committed_bundle_matches_the_code`, `test_deploy_dry_run_writes_a_plan_without_aws`), `tests/unit/store/test_sqlite_store.py` | partial — IaC, batched Quick assets and the swappable Protocol are in place; the DynamoDB store contracted in [CONTRACT.md](../CONTRACT.md) §2 is **not found in main — to implement** |
| ENF-OBS-01 | `infra/cdk/observability.py` (CloudWatch dashboard, failure alarms, SNS topic), `src/marge/pipeline/nightly.py` (run report) | no automated CDK assertion test in this branch — verified by deployment ([RUNBOOK.md](../RUNBOOK.md) §5) | partial |

## 8. Acceptance scenarios R1..R15 (spec §23)

| Id | Scenario | Proof (test) | Status |
|---|---|---|---|
| R1 | Load the three sources → coverage > 95 % | `python3 -m marge.cli demo` prints the coverage per month (99.36 %, 97.01 %, 99.38 %) — `tests/unit/ingest/test_ingest.py`, `tests/integration/test_seeded_situations.py` | implemented |
| R2 | Client matching → > 80 % right, 100 % after validation | `python3 -m marge.cli eval` (client match accuracy 97.30 % vs target 0.80) — `tests/unit/eval/test_match_accuracy.py`, `tests/unit/match/test_matching.py`, `tests/unit/api/test_routes_matches.py` | implemented |
| R3 | Read 12 contracts → > 90 % fields right, source passage shown | `python3 -m marge.cli eval` (clause accuracy 100 % vs target 0.90) — `tests/unit/eval/test_clause_accuracy.py`, `tests/unit/contracts/test_extraction.py` | implemented |
| R4 | Unvalidated contract → margin flagged `INCOMPLETE` | `tests/integration/test_seeded_situations.py` (`test_one_contract_is_not_validated_and_makes_the_margin_incomplete`), `tests/unit/calc/test_golden_annex_d.py` | implemented |
| R5 | 150 labelled interventions → > 90 % agreement | `python3 -m marge.cli eval` (classification agreement 100 % vs target 0.90) — `tests/unit/eval/test_classification_agreement.py`, `tests/integration/test_seeded_situations.py` (`test_labels_are_150_and_never_out_of_scope_on_included_work`) | implemented |
| R6 | Clearly included intervention → never `OUT_OF_SCOPE` | `tests/unit/eval/test_classification_agreement.py` (`test_classification_agreement_fails_on_one_r6_violation`), `tests/unit/classify/test_classification.py` (`test_doubtful_case_never_becomes_out_of_scope`) | implemented |
| R7 | Validate out-of-scope hours → unbilled hours and value updated | `tests/unit/api/test_routes_classifications.py` (`test_approved_out_of_scope_counts_as_unbilled`), `tests/unit/calc/test_golden_annex_d.py` (`test_golden_unbilled_hours` — 9 h, 990 €) | implemented |
| R8 | Margin decomposes to source lines; hand total identical | `tests/unit/calc/test_golden_annex_d.py` (`test_golden_margin_decomposes_to_source_lines`) | implemented |
| R9 | Hourly cost change → past months unchanged, new dated version | `tests/integration/test_seeded_situations.py` (`test_one_level_changes_rate_on_july_first`), `src/marge/calc/versioning.py`, `tests/unit/api/test_routes_admin.py` (`test_recalculate_bumps_calc_version`) | implemented |
| R10 | Account manager sees only own clients, no hourly costs | `tests/unit/api/test_rls.py`, `tests/unit/quicksight/test_rls.py`; the Quick rule set is applied in the console ([RUNBOOK.md](../RUNBOOK.md) §4.4) | implemented |
| R11 | 20 reference questions → > 90 % correct | `python3 -m marge.cli eval` (agent accuracy 100 % vs target 0.90) — `tests/unit/eval/test_agent_accuracy.py`, `src/marge/eval/analyst.py` | implemented (measured offline by the analyst; the live Quick agent is a console check) |
| R12 | Clause question → answer cites the clause | `tests/unit/quicksight/test_agent.py` (`test_agent_instruction_requires_the_clause_on_a_contract`), `tests/unit/eval/test_clause_accuracy.py` | implemented (instructions and harness); the live answer on the Quick agent is manual — see docs/TEST-INSTRUCTIONS.md |
| R13 | Renegotiation task created in the ITSM tool with dossier | `tests/unit/mcp/test_mcp.py` (`test_renegotiation_task_is_created_with_a_dossier`), `src/marge/mcp/tools.py` | implemented (against the ITSM double; the live ITSM call is manual) |
| R14 | Monthly review received, figures identical to dashboards | `tests/unit/review/test_review.py` (`test_review_figures_match_the_calculation`), `tests/unit/pipeline/test_pipeline.py` (`test_monthly_review_produces_text_and_figures`), `python3 -m marge.cli monthly --month 2026-10` | partial — the text and its figures are automatic; the receipt by the Quick flow or by SES is manual ([RUNBOOK.md](../RUNBOOK.md) §4.3) |
| R15 | Install in a clean account following the README | [RUNBOOK.md](../RUNBOOK.md) §2 + `make demo` on a fresh clone | manual |

---

## 9. Remaining gaps — modules contracted but not in `main`

Everything else of the brief is merged. Only two contracted locations are still missing:

- the DynamoDB store — src/marge/store/dynamo_store.py (the SQLite implementation of the `Store` Protocol is in place; the AWS deployment expects the DynamoDB one);
- the marketplace connectors of EF-SRC-05 — src/marge/ingest/connectors.py (spec priority `C`, out of scope for the hackathon).

Two requirements have no automated proof and stay open until the account is deployed: the CDK assertions of ENF-SEC-01 and ENF-OBS-01, and the 200-client duration budget of ENF-PERF-01.

---

## 10. How this matrix stays honest

- `python3 -m marge.cli smoke` recomputes the Annex D golden case (4 620 € revenue, 3 725 € cost, 895 € margin = 19.4 %, 9 h × 110 € = 990 €) on every pull request; a drift in the calculation model breaks the build.
- `python3 -m marge.cli eval` measures the four accuracy targets of spec 13.3 on the generated dataset (clause accuracy, classification agreement, client match accuracy, agent accuracy) and fails when a target is missed; `python3 -m marge.cli demo` prints the margins, the coverage and the monthly review of the 12 fictional clients.
- `make limits` guards the size rules, `make lint` guards style — neither replaces a test.
- [CONTRACT.md](../CONTRACT.md) §5 requires that any requirement a module implements appears in this file. A row still marked **partial** after the AWS deployment is a release blocker for the next iteration.
- Every path in this file was checked against the branch it describes; a path that does not exist is written without code formatting, never as a backticked path.
