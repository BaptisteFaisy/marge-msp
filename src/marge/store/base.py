"""Storage interfaces.

Two implementations exist: ``sqlite_store`` (local development, demo, CI) and
``dynamo_store`` (deployed on AWS). Nothing else in the code base may import
boto3 directly except ``dynamo_store`` and ``marge.quicksight.deploy`` — and
both import it lazily, inside functions, so the test suite never needs it.

Every method takes and returns domain dataclasses only.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..calc.versioning import CalcVersion
from ..domain import (
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


class ClientRepository(Protocol):
    def upsert_clients(self, clients: Sequence[Client]) -> int: ...
    def get_client(self, client_id: str) -> Client | None: ...
    def list_clients(self, account_manager_id: str | None = None) -> list[Client]: ...


class MatchRepository(Protocol):
    def save_matches(self, matches: Sequence[ClientMatch]) -> int: ...
    def list_matches(self, pending_only: bool = False) -> list[ClientMatch]: ...
    def get_match(self, match_id: str) -> ClientMatch | None: ...


class ContractRepository(Protocol):
    def save_contract(self, contract: Contract) -> None: ...
    def get_contract(self, contract_id: str, version: int | None = None) -> Contract | None: ...
    def list_contracts(self, client_id: str | None = None) -> list[Contract]: ...
    def active_contract(self, client_id: str, at: Month) -> Contract | None: ...


class WorkRepository(Protocol):
    def save_interventions(self, interventions: Sequence[Intervention]) -> int: ...
    def list_interventions(
        self, month: Month | None = None, client_id: str | None = None
    ) -> list[Intervention]: ...
    def save_classification(self, classification: Classification) -> None: ...
    def list_classifications(
        self, status: str | None = None, client_id: str | None = None, month: Month | None = None
    ) -> list[Classification]: ...
    def save_category_decision(self, decision: CategoryDecision) -> None: ...
    def find_category_decision(
        self, contract_id: str, contract_version: int, category: str
    ) -> CategoryDecision | None: ...


class CostRepository(Protocol):
    def save_rates(self, rates: Sequence[Rate]) -> int: ...
    def list_rates(self) -> list[Rate]: ...
    def save_tooling_costs(self, costs: Sequence[ToolingCost]) -> int: ...
    def list_tooling_costs(self) -> list[ToolingCost]: ...
    def save_aws_costs(self, costs: Sequence[AwsCost]) -> int: ...
    def list_aws_costs(self, month: Month | None = None) -> list[AwsCost]: ...
    def save_invoices(self, invoices: Sequence[Invoice]) -> int: ...
    def list_invoices(self, month: Month | None = None) -> list[Invoice]: ...
    def save_penalties(self, penalties: Sequence[Penalty]) -> int: ...
    def list_penalties(self, month: Month | None = None) -> list[Penalty]: ...


class AnalyticsRepository(Protocol):
    def save_margin_months(self, rows: Sequence[MarginMonth]) -> int: ...
    def list_margin_months(
        self, client_id: str | None = None, month: Month | None = None
    ) -> list[MarginMonth]: ...
    def save_effort_slices(self, rows: Sequence[EffortSlice]) -> int: ...
    def list_effort_slices(self, client_id: str | None = None) -> list[EffortSlice]: ...
    def save_hours_summaries(self, rows: Sequence[HoursSummary]) -> int: ...
    def list_hours_summaries(self, client_id: str | None = None) -> list[HoursSummary]: ...
    def list_renewal_watch(self, horizon_days: int = 90) -> list[RenewalWatch]: ...
    def margin_lines(self, client_id: str, month: Month) -> list[MarginLine]: ...


class CalcVersionRepository(Protocol):
    """History of calculation versions (EF-CAL-03, idea 28)."""

    def save_calc_version(self, version: CalcVersion) -> None: ...
    def list_calc_versions(self) -> list[CalcVersion]: ...


class LlmLogRepository(Protocol):
    """Append-only log of model calls (idea 18, ENF-IA-01..03)."""

    def append_llm_call(self, call: LlmCall) -> None: ...
    def list_llm_calls(
        self, purpose: str | None = None, client_id: str | None = None, model_id: str | None = None
    ) -> list[LlmCall]: ...


class AuditRepository(Protocol):
    def append(self, entry: AuditEntry) -> None: ...
    def list_entries(
        self, entity_kind: str | None = None, entity_id: str | None = None
    ) -> list[AuditEntry]: ...


class SettingsRepository(Protocol):
    def load(self) -> Settings: ...
    def save(self, settings: Settings, author: str, reason: str) -> None: ...


class Store(
    ClientRepository,
    MatchRepository,
    ContractRepository,
    WorkRepository,
    CostRepository,
    AnalyticsRepository,
    AuditRepository,
    CalcVersionRepository,
    LlmLogRepository,
    SettingsRepository,
    Protocol,
):
    """The whole persistence surface, implemented by both backends."""
