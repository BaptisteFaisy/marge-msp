"""In-memory ``Store`` double shared by every test.

Implements the whole ``marge.store.base.Store`` protocol with plain dicts so
no test ever touches sqlite, DynamoDB or the network.
"""

from __future__ import annotations

from collections.abc import Sequence

from marge.calc.versioning import CalcVersion
from marge.domain import (
    AuditEntry,
    AwsCost,
    CategoryDecision,
    Classification,
    Client,
    ClientMatch,
    Contract,
    EffortSlice,
    HoursSummary,
    Intervention,
    Invoice,
    LlmCall,
    MarginLine,
    MarginMonth,
    Month,
    Penalty,
    Rate,
    RenewalWatch,
    Settings,
    ToolingCost,
)


def _effort_key(row: EffortSlice) -> tuple:
    return (row.client_id, row.month, row.category, row.level, row.work_class)


class FakeStore:
    """Deterministic, dependency-free persistence double.

    Writers upsert on the natural key of each aggregate, like ``SqliteStore``
    does with its primary key: recomputing a month must replace the rows, not
    add a second copy.
    """

    def __init__(self) -> None:
        self.clients: dict[str, Client] = {}
        self.matches: dict[str, ClientMatch] = {}
        self.contracts: dict[tuple[str, int], Contract] = {}
        self.interventions: dict[str, Intervention] = {}
        self.classifications: dict[str, Classification] = {}
        self.category_decisions: dict[tuple[str, int, str], CategoryDecision] = {}
        self.rates: list[Rate] = []
        self.tooling_costs: list[ToolingCost] = []
        self.aws_costs: list[AwsCost] = []
        self.invoices: list[Invoice] = []
        self.penalties: list[Penalty] = []
        self.margin_months: dict[tuple[str, Month, int], MarginMonth] = {}
        self.effort_slices: list[EffortSlice] = []
        self.hours_summaries: list[HoursSummary] = []
        self.renewal_watch: list[RenewalWatch] = []
        self.lines: dict[tuple[str, Month], list[MarginLine]] = {}
        self.audit: list[AuditEntry] = []
        self.llm_calls: list[LlmCall] = []
        self.calc_versions: list[CalcVersion] = []
        self.settings = Settings()
        self.calls: list[str] = []

    # ------------------------------------------------------------- clients
    def upsert_clients(self, clients: Sequence[Client]) -> int:
        self.calls.append("upsert_clients")
        for client in clients:
            self.clients[client.client_id] = client
        return len(clients)

    def get_client(self, client_id: str) -> Client | None:
        return self.clients.get(client_id)

    def list_clients(self, account_manager_id: str | None = None) -> list[Client]:
        rows = list(self.clients.values())
        if account_manager_id:
            rows = [c for c in rows if c.account_manager_id == account_manager_id]
        return sorted(rows, key=lambda c: c.client_id)

    # -------------------------------------------------------------- matches
    def save_matches(self, matches: Sequence[ClientMatch]) -> int:
        for match in matches:
            self.matches[match.match_id] = match
        return len(matches)

    def list_matches(self, pending_only: bool = False) -> list[ClientMatch]:
        rows = list(self.matches.values())
        if pending_only:
            from marge.domain import DecisionStatus

            rows = [m for m in rows if m.status == DecisionStatus.PENDING]
        return sorted(rows, key=lambda m: m.match_id)

    def get_match(self, match_id: str) -> ClientMatch | None:
        return self.matches.get(match_id)

    # ------------------------------------------------------------- contracts
    def save_contract(self, contract: Contract) -> None:
        self.contracts[(contract.contract_id, contract.version)] = contract

    def get_contract(self, contract_id: str, version: int | None = None) -> Contract | None:
        if version is not None:
            return self.contracts.get((contract_id, version))
        owned = [c for (cid, _), c in self.contracts.items() if cid == contract_id]
        return max(owned, key=lambda c: c.version) if owned else None

    def list_contracts(self, client_id: str | None = None) -> list[Contract]:
        rows = list(self.contracts.values())
        if client_id:
            rows = [c for c in rows if c.client_id == client_id]
        return sorted(rows, key=lambda c: (c.contract_id, c.version))

    def active_contract(self, client_id: str, at: Month) -> Contract | None:
        from marge.domain import ContractStatus

        candidates = [
            c
            for c in self.list_contracts(client_id)
            if c.status == ContractStatus.VALIDATED
            and (c.effective_from is None or Month.of(c.effective_from) <= at)
        ]
        return max(candidates, key=lambda c: c.version, default=None)

    # ------------------------------------------------------------------ work
    def save_interventions(self, interventions: Sequence[Intervention]) -> int:
        for item in interventions:
            self.interventions[item.intervention_id] = item
        return len(interventions)

    def list_interventions(
        self, month: Month | None = None, client_id: str | None = None
    ) -> list[Intervention]:
        rows = list(self.interventions.values())
        if month is not None:
            rows = [i for i in rows if i.month == month]
        if client_id:
            rows = [i for i in rows if i.client_id == client_id]
        return sorted(rows, key=lambda i: i.intervention_id)

    def save_classification(self, classification: Classification) -> None:
        self.classifications[classification.intervention_id] = classification

    def list_classifications(
        self, status: str | None = None, client_id: str | None = None, month: Month | None = None
    ) -> list[Classification]:
        rows = list(self.classifications.values())
        if status:
            rows = [c for c in rows if c.status.value == status]
        if client_id:
            rows = [c for c in rows if c.client_id == client_id]
        if month is not None:
            ids = {i.intervention_id for i in self.list_interventions(month=month)}
            rows = [c for c in rows if c.intervention_id in ids]
        return sorted(rows, key=lambda c: c.intervention_id)

    def save_category_decision(self, decision: CategoryDecision) -> None:
        self.category_decisions[decision.key] = decision

    def find_category_decision(
        self, contract_id: str, contract_version: int, category: str
    ) -> CategoryDecision | None:
        return self.category_decisions.get((contract_id, contract_version, category))

    # ------------------------------------------------------------------ cost
    def save_rates(self, rates: Sequence[Rate]) -> int:
        self.rates.extend(rates)
        return len(rates)

    def list_rates(self) -> list[Rate]:
        return sorted(self.rates, key=lambda r: (r.level.value, r.effective_from))

    def save_tooling_costs(self, costs: Sequence[ToolingCost]) -> int:
        self.tooling_costs.extend(costs)
        return len(costs)

    def list_tooling_costs(self) -> list[ToolingCost]:
        return list(self.tooling_costs)

    def save_aws_costs(self, costs: Sequence[AwsCost]) -> int:
        self.aws_costs.extend(costs)
        return len(costs)

    def list_aws_costs(self, month: Month | None = None) -> list[AwsCost]:
        rows = self.aws_costs
        if month is not None:
            rows = [c for c in rows if c.month == month]
        return list(rows)

    def save_invoices(self, invoices: Sequence[Invoice]) -> int:
        self.invoices.extend(invoices)
        return len(invoices)

    def list_invoices(self, month: Month | None = None) -> list[Invoice]:
        rows = self.invoices
        if month is not None:
            rows = [i for i in rows if i.month == month]
        return list(rows)

    def save_penalties(self, penalties: Sequence[Penalty]) -> int:
        self.penalties.extend(penalties)
        return len(penalties)

    def list_penalties(self, month: Month | None = None) -> list[Penalty]:
        rows = self.penalties
        if month is not None:
            rows = [p for p in rows if p.month == month]
        return list(rows)

    # ------------------------------------------------------------- analytics
    def save_margin_months(self, rows: Sequence[MarginMonth]) -> int:
        for row in rows:
            self.margin_months[(row.client_id, row.month, row.calc_version)] = row
        return len(rows)

    def list_margin_months(
        self, client_id: str | None = None, month: Month | None = None
    ) -> list[MarginMonth]:
        rows = list(self.margin_months.values())
        if client_id:
            rows = [r for r in rows if r.client_id == client_id]
        if month is not None:
            rows = [r for r in rows if r.month == month]
        return sorted(rows, key=lambda r: (r.client_id, r.month, r.calc_version))

    def save_effort_slices(self, rows: Sequence[EffortSlice]) -> int:
        """Upsert on the natural key, exactly like the SQLite backend does."""
        for row in rows:
            key = (row.client_id, row.month, row.category, row.level, row.work_class)
            self.effort_slices = [r for r in self.effort_slices if _effort_key(r) != key]
            self.effort_slices.append(row)
        return len(rows)

    def list_effort_slices(self, client_id: str | None = None) -> list[EffortSlice]:
        rows = self.effort_slices
        if client_id:
            rows = [r for r in rows if r.client_id == client_id]
        return list(rows)

    def save_hours_summaries(self, rows: Sequence[HoursSummary]) -> int:
        """Upsert on (client, month): recomputing must not duplicate a row."""
        for row in rows:
            key = (row.client_id, row.month)
            self.hours_summaries = [r for r in self.hours_summaries if (r.client_id, r.month) != key]
            self.hours_summaries.append(row)
        return len(rows)

    def list_hours_summaries(self, client_id: str | None = None) -> list[HoursSummary]:
        rows = self.hours_summaries
        if client_id:
            rows = [r for r in rows if r.client_id == client_id]
        return list(rows)

    def list_renewal_watch(self, horizon_days: int = 90) -> list[RenewalWatch]:
        return [w for w in self.renewal_watch if w.days_to_renewal <= horizon_days]

    def set_renewal_watch(self, rows: Sequence[RenewalWatch]) -> None:
        self.renewal_watch = list(rows)

    # Alias used by the pipeline: ``save_*`` is the writer name of the protocol.
    save_renewal_watch = set_renewal_watch

    def margin_lines(self, client_id: str, month: Month) -> list[MarginLine]:
        return self.lines.get((client_id, month), [])

    def set_margin_lines(self, client_id: str, month: Month, rows: Sequence[MarginLine]) -> None:
        self.lines[(client_id, month)] = list(rows)

    save_margin_lines = set_margin_lines

    # ----------------------------------------------------------------- audit
    def append(self, entry: AuditEntry) -> None:
        self.audit.append(entry)

    def list_entries(self, entity_kind: str | None = None, entity_id: str | None = None) -> list[AuditEntry]:
        rows = self.audit
        if entity_kind:
            rows = [e for e in rows if e.entity_kind == entity_kind]
        if entity_id:
            rows = [e for e in rows if e.entity_id == entity_id]
        return list(rows)

    # ------------------------------------------------------- calc versions
    def save_calc_version(self, version: CalcVersion) -> None:
        self.calc_versions = [v for v in self.calc_versions if v.version != version.version]
        self.calc_versions.append(version)

    def list_calc_versions(self) -> list[CalcVersion]:
        return sorted(self.calc_versions, key=lambda v: v.version)

    # ------------------------------------------------------------- llm log
    def append_llm_call(self, call: LlmCall) -> None:
        self.llm_calls.append(call)

    def list_llm_calls(
        self, purpose: str | None = None, client_id: str | None = None, model_id: str | None = None
    ) -> list[LlmCall]:
        rows = list(self.llm_calls)
        if purpose:
            rows = [c for c in rows if c.purpose == purpose]
        if client_id:
            rows = [c for c in rows if c.client_id == client_id]
        if model_id:
            rows = [c for c in rows if c.model_id == model_id]
        return rows

    # -------------------------------------------------------------- settings
    def load(self) -> Settings:
        return self.settings

    def save(self, settings: Settings, author: str, reason: str) -> None:
        self.settings = settings
        self.append(AuditEntry.now("settings", "current", "update", author, reason))
