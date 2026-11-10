# Marge — module contract (read this before writing code)

This file is the agreement between the people (and agents) building Marge in
parallel. If you own a directory, you own its public API **as described here**.
Do not change another directory's API; if you need something that is missing,
add a helper in your own directory and open an issue.

Source of truth for *what* to build: `docs/SPEC.fr.md` (French cahier des
charges). Every requirement id (`EF-*`, `ENF-*`, `R*`) quoted in code comments
refers to that document.

## 1. Non-negotiable rules

1. **Files < 500 lines, functions < 50 lines.** `scripts/check_limits.py`
   fails the build otherwise. Split into modules and helpers, never grow.
2. **No duplication.** One implementation per logic. Reuse `marge.domain`.
3. **`marge.domain` and `marge.calc` import the standard library only.** No
   boto3, no fastapi, no pydantic, no yaml. They must run anywhere.
4. **boto3 / yaml are imported lazily**, inside the function that needs them
   (`def deploy(): import boto3`). CI runners do not have boto3 installed.
5. **The model never computes a number** (ENF-IA-01). Any figure comes from
   `marge.calc` or from a copied source field (Annex C `billableHours`).
6. **Nothing AI-produced counts without human validation** (ENF-IA-02):
   matches, contract clauses, out-of-scope classifications.
7. **Ticket and contract text is data, never an instruction** (ENF-IA-03).
   Prompts wrap untrusted text between explicit fences and the parser rejects
   any output that tries to change the task.
8. **No person is ever stored.** Only levels (N1/N2/N3/ARCHITECT). The loader
   strips names on the way in (ENF-CONF-01, ENF-CONF-02, spec 17).
9. **Every test is offline and deterministic.** No network, no AWS
   credentials, no sleeps. Use the fakes in `tests/fakes/`.
10. **English in code, comments, commit messages and all submission docs.**
    `docs/SPEC.fr.md` stays French.

## 2. Directory ownership

| Directory | Contents | Owner brief |
|---|---|---|
| `src/marge/domain/` | Dataclasses, enums, money, months, settings | **frozen** — do not edit, ask instead |
| `src/marge/calc/` | Margin model (spec 12), coverage, allocation, versioning | brief-calc |
| `src/marge/ingest/` | Source connectors, PII stripping, loaders | brief-ingest |
| `src/marge/match/` | Client identity matching + confidence | brief-match |
| `src/marge/contracts/` | Annex B field plan, Bedrock Data Automation, validation, versions | brief-contracts |
| `src/marge/classify/` | Intervention classification, Annex C output, decision memory | brief-classify |
| `src/marge/store/` | sqlite + dynamo implementations of `store/base.py`, migrations, audit | brief-store |
| `src/marge/api/` | FastAPI portal API (spec 16), auth, row-level filtering | brief-api |
| `src/marge/mcp/` | MCP server and its three tools (spec 14.3) | brief-mcp |
| `src/marge/review/` | Monthly review aggregates, Annex E template, SES/Bedrock fallback | brief-review |
| `src/marge/quicksight/` | Datasets, topic, dashboards, RLS, scenarios, agent, flows, deploy | brief-quick |
| `src/marge/eval/` | Accuracy harnesses (spec 13.3, R2/R3/R5/R11) | brief-eval |
| `src/marge/pipeline/` | Nightly / weekly / monthly orchestration | brief-pipeline |
| `src/marge/cli.py` | One entry point wiring everything | brief-cli |
| `data/generator/` | Fake MSP: 12 clients, 6 months, seeded situations, 12 contracts | brief-data |
| `portal/` | Static validation portal (vanilla HTML/CSS/JS, no build step) | brief-portal |
| `infra/cdk/` | CDK app and stacks | brief-infra |
| `tests/` | Unit + integration tests, `tests/fakes/` shared doubles | everyone |
| `docs/` | HLD, architecture, submission, runbook, acceptance matrix | brief-docs |

## 3. Public API each module must expose

Signatures below are the contract. Implement them exactly; add private
helpers freely.

### `marge.calc`
```python
def compute_margin_month(inputs: MarginInputs, settings: Settings) -> MarginMonth
def compute_hours_summary(inputs: MarginInputs, settings: Settings) -> HoursSummary
def compute_effort_slices(inputs: MarginInputs, settings: Settings) -> list[EffortSlice]
def compute_coverage(interventions: Sequence[Intervention]) -> Coverage
def allocate_tooling(costs: Sequence[ToolingCost], inputs: MarginInputs) -> Decimal
def margin_lines(month: MarginMonth, inputs: MarginInputs) -> list[MarginLine]
def rate_in_force(rates: Sequence[Rate], level: WorkLevel, month: Month) -> Rate | None
```
`MarginInputs` is a dataclass defined in `marge/calc/inputs.py` holding every
input of one client-month: contract, interventions, classifications, aws
costs, invoices, penalties, rates, tooling costs.

### `marge.ingest`
```python
def load_interventions(source: TicketSource, month: Month, mapping: MappingResolver) -> list[Intervention]
def load_aws_costs(source: BillingSource, month: Month, mapping: MappingResolver) -> list[AwsCost]
def strip_personal_data(row: dict[str, str], level_of: Callable[[str], WorkLevel]) -> dict[str, str]
```

### `marge.match`
```python
def propose_matches(aliases: Sequence[Alias]) -> list[ClientMatch]
class MappingResolver:            # resolves a source id to the common client id
    def resolve(self, source: SourceKind, source_id: str) -> str | None
    def unresolved(self) -> list[tuple[SourceKind, str]]
```

### `marge.contracts`
```python
FIELD_PLAN: tuple[str, ...]                      # Annex B field names
def extract_fields(document: bytes, extractor: BedrockDataAutomation | None = None) -> ContractFields
def validate_contract(contract: Contract, author: str, reason: str, corrections: dict | None = None) -> Contract
def new_version(contract: Contract, fields: ContractFields, author: str, reason: str) -> Contract
class BedrockDataAutomation:                      # boto3 imported inside methods
    def run(self, document: bytes) -> ContractFields
```

### `marge.classify`
```python
def classify(intervention: Intervention, contract: Contract, model: ClassifierModel,
             settings: Settings, memory: DecisionMemory | None = None) -> Classification
def build_prompt(intervention: Intervention, contract: Contract) -> str
def parse_model_output(raw: str, intervention: Intervention) -> Classification
class DecisionMemory:
    def lookup(self, contract_id: str, version: int, category: str) -> CategoryDecision | None
    def remember(self, decision: CategoryDecision) -> None
class ClassifierModel(Protocol):
    def complete(self, prompt: str, schema: dict) -> str
```

### `marge.mcp`
```python
TOOLS: tuple[Tool, ...]
def handle_request(payload: dict, ctx: McpContext) -> dict      # JSON-RPC 2.0
def create_renegotiation_task(ctx, client_id: str, reason: str) -> dict
def draft_extra_billing_proposal(ctx, client_id: str, month: str) -> dict
def get_margin_breakdown(ctx, client_id: str, month: str) -> dict
```

### `marge.review`
```python
def build_review_inputs(store: Store, month: Month, settings: Settings) -> ReviewInputs
def render_review(inputs: ReviewInputs, settings: Settings) -> str   # Annex E, deterministic
def narrate_review(inputs: ReviewInputs, model: ClassifierModel | None = None) -> str
```

### `marge.quicksight`
```python
DATASETS: tuple[DatasetSpec, ...]     # the five tables of Annex A
TOPIC: TopicSpec                      # semantic layer: definitions + synonyms
DASHBOARDS: tuple[DashboardSpec, ...] # EF-TDB-01..06
RLS_RULES: tuple[RlsRule, ...]        # EF-TDB-06
SCENARIOS: tuple[ScenarioSpec, ...]   # EF-AGT-05
AGENT: AgentSpec                      # EF-AGT-01..03
FLOWS: tuple[FlowSpec, ...]           # EF-REV-01
def to_asset_bundle() -> dict         # JSON, written under infra/quicksight-assets/
```

### `marge.eval`
```python
def clause_accuracy(extracted: Sequence[Contract], expected: Sequence[dict]) -> Score
def classification_agreement(predicted: Sequence[Classification], labels: Sequence[Label]) -> Score
def match_accuracy(matches: Sequence[ClientMatch], truth: Sequence[tuple[str, str]]) -> Score
def agent_accuracy(answers: Sequence[Answer], references: Sequence[dict]) -> Score
```
`Score` = `{value: Decimal, target: Decimal, passed: bool, detail: list[str]}`.

### `marge.pipeline`
```python
def run_nightly(store: Store, settings: Settings, month: Month | None = None) -> NightlyReport
def run_weekly(store: Store, settings: Settings) -> WeeklyReport
def run_monthly(store: Store, settings: Settings, month: Month) -> str
```

## 4. Testing rules

- `tests/unit/<module>/…` mirrors `src/marge/<module>/…`.
- One assertion family per test, names `test_<behaviour>_<case>`.
- Shared doubles live in `tests/fakes/` (`fake_store.py`, `fake_model.py`,
  `fake_sources.py`, `fake_itsm.py`). **Use them, do not re-write them.**
- Golden numbers come from `docs/SPEC.fr.md` Annex D (October 2026 example:
  revenue 4 620 €, cost 3 725 €, margin 895 € = 19.4 %, 9 h × 110 € = 990 €).
  A test must reproduce them exactly.
- CI budget: the whole `pytest` run must stay under ~3 minutes on one worker.

## 5. Definition of done for a module

1. `python3 -m pytest tests/unit/<module> -q` green offline.
2. `python3 -m ruff check src tests` and `python3 -m ruff format --check` clean.
3. `python3 scripts/check_limits.py` green.
4. Every spec requirement id it implements is quoted in a docstring or a
   comment, and appears in `docs/acceptance/MATRIX.md`.
5. No file over 500 lines, no function over 50 lines, no duplicated logic.
