# Marge — canonical interchange formats

These formats are the contract between the data generator (`data/generator/`),
the connectors (`src/marge/ingest/`) and the evaluation harnesses
(`src/marge/eval/`). **Do not invent a new column name**: if a field is
missing, add it at the end and update this file in the same pull request.

All files live under `data/generated/` (gitignored, reproducible with
`python3 -m marge.cli generate`). All dates are ISO (`YYYY-MM-DD`), all months
are `YYYY-MM`, all amounts are plain decimals with a `.` separator, all
durations are decimal **hours** (`2.5` = 2 h 30).

## 1. Files

| Path | Format | Grain |
|---|---|---|
| `clients.json` | JSON array | one client |
| `aliases.json` | JSON array | one (client, source) alias |
| `interventions.csv` | CSV with header | one ticket intervention |
| `aws_costs.csv` | CSV with header | one account, one month |
| `invoices.csv` | CSV with header | one invoice line |
| `rates.csv` | CSV with header | one level, one effective date |
| `tooling.csv` | CSV with header | one tool |
| `penalties.csv` | CSV with header | one client, one month |
| `contracts/<id>-v<n>.pdf` | PDF | one contract version |
| `contracts/<id>-v<n>.txt` | UTF-8 text | same content, machine readable |
| `expected/contract_fields.json` | JSON object | ground truth per contract |
| `labels/interventions.jsonl` | JSON lines | expected class per intervention |
| `questions/reference_questions.json` | JSON array | 20 agent questions + answers |
| `manifest.json` | JSON object | generation seed, counts, checksums |

## 2. Columns

### `clients.json`
```json
{
  "client_id": "c-001",
  "name": "Durand Industries",
  "account_manager_id": "am-01",
  "sector": "industry",
  "onboarded_on": "2024-03-01",
  "managed_resource_count": 40
}
```

### `aliases.json` — what each source calls the client (drives EF-REF-01)
```json
{"client_id": "c-001", "source": "itsm", "source_id": "DURIND", "name_variant": "Durand Ind."}
{"client_id": "c-001", "source": "billing", "source_id": "111122223333", "name_variant": "durand-industries-prod"}
{"client_id": "c-001", "source": "contract", "source_id": "ctr-001", "name_variant": "DURAND INDUSTRIES SAS"}
```
`source` is one of `itsm | billing | contract | invoice`.

### `interventions.csv`
```
intervention_id,ticket_id,customer_ref,occurred_on,category,ticket_type,level,engineer_ref,hours_spent,description,aws_account_id,managed_resource_id
```
- `customer_ref` — the client **as named in the ITSM tool** (an alias, never
  the common id): the connector resolves it through `aliases.json`.
- `engineer_ref` — a person identifier. It **must be dropped on load** and
  replaced by `level` (ENF-CONF-01). No test, dashboard or export may keep it.
- `level` — `N1 | N2 | N3 | ARCHITECT`.
- `hours_spent` — decimal hours.
- Empty `customer_ref` is legal and must land in the `UNASSIGNED` bucket
  (EF-REF-04, spec 12.4). It must stay visible, never silently spread.

### `aws_costs.csv`
```
aws_account_id,month,cost,currency,rebilled_amount,kind,managed_resource_count,client_ref
```
- `kind` — `CLIENT_ACCOUNT | MSP_TOOLING_ACCOUNT`.
- `rebilled_amount` — what the MSP re-bills to the client (resale margin =
  `rebilled_amount - cost`). `0` when nothing is re-billed.
- `currency` — `USD` for raw billing exports. The connector converts to the
  reporting currency using `fx.csv` **before** the calculation: `marge.calc`
  only ever sees one currency.
- `client_ref` — the account name as it appears in the billing export (an
  alias), empty for MSP tooling accounts.

### `fx.csv`
```
month,from,to,rate
2026-10,USD,EUR,0.92
```

### `invoices.csv`
```
invoice_id,customer_ref,month,kind,amount,hours_billed,currency
```
`kind` — `EXTRA_HOURS | PROJECT | SUBSCRIPTION`.

### `rates.csv`
```
level,hourly_cost,effective_from,currency
N1,50.00,2026-01-01,EUR
N1,52.50,2026-07-01,EUR
```
Effective dated: a past month is computed with the rate in force that month
(spec 12.4). Every level must have at least one row before the first month.

### `tooling.csv`
```
tool,monthly_cost,basis,client_id,aws_account_id,currency
supervision,1200.00,PER_LABOUR_HOUR,,,EUR
backup-dedie,340.00,PER_CLIENT,c-001,,EUR
```
`basis` — `PER_CLIENT | PER_ACCOUNT | PER_MANAGED_RESOURCE | PER_LABOUR_HOUR`.
`client_id` is set only for a cost already dedicated to one client.

### `penalties.csv`
```
client_id,month,amount,reason,currency
```

### `expected/contract_fields.json` — ground truth for EF-CTR-01 / R3
Keyed by `"<contract_id>-v<version>"`, values use the Annex B field names in
`snake_case` (`customer_name`, `start_date`, `end_date`, `renewal_terms`,
`termination_notice`, `monthly_subscription`, `currency`,
`included_hours_per_month`, `extra_hour_rate`, `services_included`,
`exclusions`, `service_hours`, `sla_commitments`, `penalties`,
`indexation_clause`, `covered_accounts_or_resources`) plus
`ambiguous_clause` (boolean) for the contract with a deliberately ambiguous
clause (spec 19.1).

### `labels/interventions.jsonl` — ground truth for EF-CLS-01 / R5
```json
{"intervention_id": "wl-000123", "expected_class": "OUT_OF_SCOPE", "clearly_included": false}
```
`clearly_included` marks the interventions that must **never** come back as
`OUT_OF_SCOPE` (R6). 150 lines minimum.

### `questions/reference_questions.json` — R11
```json
{"id": "q01", "question": "Which clients are below 20% margin this quarter?",
 "expected_kind": "table", "expected_client_ids": ["c-004", "c-009"],
 "expected_period": "2026-10", "dashboard": "overview"}
```
20 questions, covering: margin ranking, month-over-month change, out-of-scope
hours by subject, a contract clause question, renewals within 90 days.

### `manifest.json`
```json
{"seed": 20261111, "clients": 12, "months": 6, "first_month": "2026-05",
 "last_month": "2026-10", "interventions": 4200, "contracts": 12,
 "labelled_interventions": 150, "generated_at": "2026-11-11T00:00:00Z"}
```

## 3. Seeded situations (spec 19.1) — the generator must produce all of them

| Situation | Expectation |
|---|---|
| 2 loss-making clients | margin rate < 0 for at least one month; one of the two has an abnormal ticket volume |
| 3 clients with repeated out-of-scope work | ≥ 4 out-of-scope interventions each, spread over ≥ 3 months |
| 1 profitable client renewing in 60 days with a falling margin | `end_date` = today + 60 d, margin rate down over the last 3 months |
| 1 contract with an ambiguous clause | `ambiguous_clause: true`, its interventions are labelled `UNCERTAIN` |
| Hours with no client | ≥ 20 interventions with an empty `customer_ref` (unassigned bucket) |
| One month with poor coverage | coverage < 0.80 for at least one client-month → `ESTIMATE` |
| One unvalidated contract | a client whose contract stays `EXTRACTED` → margin `INCOMPLETE` (R4) |
| A rate change mid-history | at least one level whose `hourly_cost` changes on `2026-07-01` (R9) |
| An amendment | at least one contract with a v2 (EF-CTR-04) |

## 4. Contracts

The generator writes each contract twice: a **PDF** (a minimal, text-only PDF
produced with the standard library — no reportlab on the CI workers) and the
**same text** as `.txt`. The PDF is what the demo shows; the `.txt` is what
tests read, so nothing needs a PDF parser. Both must contain every Annex B
field in prose, in French, with visibly different layouts across the 12
contracts (different clause numbering, different order, at least one with a
table-like layout, one with an ambiguous exclusion).
