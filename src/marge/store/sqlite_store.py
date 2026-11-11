"""SQLite implementation of the ``Store`` protocol.

Design: one table per aggregate, complex values kept as JSON text (written and
read by ``marge.store.serde``), indexed key columns for the queries the portal
and the pipeline actually run. This keeps the file small and the round trip
exact, and lets DynamoDB reuse the very same encoding.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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
    MarginLine,
    MarginMonth,
    Month,
    Penalty,
    Rate,
    RenewalWatch,
    Settings,
    ToolingCost,
)
from . import serde
from .migrations import MIGRATIONS, apply_migrations

TABLE_OF = {
    "clients": Client,
    "matches": ClientMatch,
    "contracts": Contract,
    "interventions": Intervention,
    "classifications": Classification,
    "category_decisions": CategoryDecision,
    "rates": Rate,
    "tooling_costs": ToolingCost,
    "aws_costs": AwsCost,
    "invoices": Invoice,
    "penalties": Penalty,
    "margin_months": MarginMonth,
    "effort_slices": EffortSlice,
    "hours_summaries": HoursSummary,
    "renewal_watch": RenewalWatch,
    "margin_lines": MarginLine,
    "audit": AuditEntry,
}


class SqliteStore:
    """Persistent ``Store`` backed by a single SQLite file."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        apply_migrations(self._conn)
        self.calls: list[str] = []

    # ------------------------------------------------------------ plumbing
    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        finally:
            cur.close()

    def _put(self, table: str, key: str, payload: dict[str, Any]) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO {table} (key, payload) VALUES (?, ?) "
                f"ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",
                (key, json.dumps(serde.encode(payload), ensure_ascii=False)),
            )

    def _put_many(self, table: str, rows: Sequence[tuple[str, Any]]) -> int:
        for key, row in rows:
            self._put(table, key, serde.encode(row))
        return len(rows)

    def _get(self, table: str, key: str) -> dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(f"SELECT payload FROM {table} WHERE key = ?", (key,))
            row = cur.fetchone()
        return json.loads(row["payload"]) if row else None

    def _all(self, table: str, where: str = "", params: tuple = ()) -> list[dict[str, Any]]:
        sql = f"SELECT payload FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY key"
        with self._cursor() as cur:
            cur.execute(sql, params)
            return [json.loads(row["payload"]) for row in cur.fetchall()]

    def _delete(self, table: str, where: str, params: tuple) -> None:
        with self._cursor() as cur:
            cur.execute(f"DELETE FROM {table} WHERE {where}", params)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------- clients
    def upsert_clients(self, clients: Sequence[Client]) -> int:
        return self._put_many("clients", [(c.client_id, c) for c in clients])

    def get_client(self, client_id: str) -> Client | None:
        raw = self._get("clients", client_id)
        return serde.decode(Client, raw) if raw else None

    def list_clients(self, account_manager_id: str | None = None) -> list[Client]:
        rows = serde.decode_many(Client, self._all("clients"))
        if account_manager_id:
            rows = [c for c in rows if c.account_manager_id == account_manager_id]
        return rows

    # -------------------------------------------------------------- matches
    def save_matches(self, matches: Sequence[ClientMatch]) -> int:
        return self._put_many("matches", [(m.match_id, m) for m in matches])

    def list_matches(self, pending_only: bool = False) -> list[ClientMatch]:
        rows = serde.decode_many(ClientMatch, self._all("matches"))
        if pending_only:
            rows = [m for m in rows if m.status.value == "PENDING"]
        return rows

    def get_match(self, match_id: str) -> ClientMatch | None:
        raw = self._get("matches", match_id)
        return serde.decode(ClientMatch, raw) if raw else None

    # ------------------------------------------------------------ contracts
    def save_contract(self, contract: Contract) -> None:
        self._put("contracts", f"{contract.contract_id}:{contract.version}", contract)

    def get_contract(self, contract_id: str, version: int | None = None) -> Contract | None:
        if version is not None:
            raw = self._get("contracts", f"{contract_id}:{version}")
            return serde.decode(Contract, raw) if raw else None
        owned = [c for c in self.list_contracts() if c.contract_id == contract_id]
        return max(owned, key=lambda c: c.version) if owned else None

    def list_contracts(self, client_id: str | None = None) -> list[Contract]:
        rows = serde.decode_many(Contract, self._all("contracts"))
        if client_id:
            rows = [c for c in rows if c.client_id == client_id]
        return rows

    def active_contract(self, client_id: str, at: Month) -> Contract | None:
        candidates = [
            c
            for c in self.list_contracts(client_id)
            if c.status.value == "VALIDATED"
            and (c.effective_from is None or Month.of(c.effective_from) <= at)
        ]
        return max(candidates, key=lambda c: c.version, default=None)

    # ----------------------------------------------------------------- work
    def save_interventions(self, interventions: Sequence[Intervention]) -> int:
        return self._put_many("interventions", [(i.intervention_id, i) for i in interventions])

    def list_interventions(
        self, month: Month | None = None, client_id: str | None = None
    ) -> list[Intervention]:
        rows = serde.decode_many(Intervention, self._all("interventions"))
        if month is not None:
            rows = [i for i in rows if i.month == month]
        if client_id:
            rows = [i for i in rows if i.client_id == client_id]
        return rows

    def save_classification(self, classification: Classification) -> None:
        self._put("classifications", classification.intervention_id, classification)

    def list_classifications(
        self, status: str | None = None, client_id: str | None = None, month: Month | None = None
    ) -> list[Classification]:
        rows = serde.decode_many(Classification, self._all("classifications"))
        if status:
            rows = [c for c in rows if c.status.value == status]
        if client_id:
            rows = [c for c in rows if c.client_id == client_id]
        if month is not None:
            ids = {i.intervention_id for i in self.list_interventions(month=month)}
            rows = [c for c in rows if c.intervention_id in ids]
        return rows

    def save_category_decision(self, decision: CategoryDecision) -> None:
        key = f"{decision.contract_id}:{decision.contract_version}:{decision.category}"
        self._put("category_decisions", key, decision)

    def find_category_decision(
        self, contract_id: str, contract_version: int, category: str
    ) -> CategoryDecision | None:
        raw = self._get("category_decisions", f"{contract_id}:{contract_version}:{category}")
        return serde.decode(CategoryDecision, raw) if raw else None

    # ------------------------------------------------------------------ cost
    def save_rates(self, rates: Sequence[Rate]) -> int:
        rows = [(f"{r.level.value}:{r.effective_from.isoformat()}", r) for r in rates]
        return self._put_many("rates", rows)

    def list_rates(self) -> list[Rate]:
        return serde.decode_many(Rate, self._all("rates"))

    def save_tooling_costs(self, costs: Sequence[ToolingCost]) -> int:
        rows = [(f"{c.tool}:{i}", c) for i, c in enumerate(costs)]
        return self._put_many("tooling_costs", rows)

    def list_tooling_costs(self) -> list[ToolingCost]:
        return serde.decode_many(ToolingCost, self._all("tooling_costs"))

    def save_aws_costs(self, costs: Sequence[AwsCost]) -> int:
        rows = [(f"{c.aws_account_id}:{c.month}:{i}", c) for i, c in enumerate(costs)]
        return self._put_many("aws_costs", rows)

    def list_aws_costs(self, month: Month | None = None) -> list[AwsCost]:
        rows = serde.decode_many(AwsCost, self._all("aws_costs"))
        return [c for c in rows if month is None or c.month == month]

    def save_invoices(self, invoices: Sequence[Invoice]) -> int:
        return self._put_many("invoices", [(i.invoice_id, i) for i in invoices])

    def list_invoices(self, month: Month | None = None) -> list[Invoice]:
        rows = serde.decode_many(Invoice, self._all("invoices"))
        return [i for i in rows if month is None or i.month == month]

    def save_penalties(self, penalties: Sequence[Penalty]) -> int:
        rows = [(f"{p.client_id}:{p.month}:{i}", p) for i, p in enumerate(penalties)]
        return self._put_many("penalties", rows)

    def list_penalties(self, month: Month | None = None) -> list[Penalty]:
        rows = serde.decode_many(Penalty, self._all("penalties"))
        return [p for p in rows if month is None or p.month == month]

    # ------------------------------------------------------------- analytics
    def save_margin_months(self, rows: Sequence[MarginMonth]) -> int:
        keys = [(f"{r.client_id}:{r.month}:{r.calc_version}", r) for r in rows]
        return self._put_many("margin_months", keys)

    def list_margin_months(
        self, client_id: str | None = None, month: Month | None = None
    ) -> list[MarginMonth]:
        rows = serde.decode_many(MarginMonth, self._all("margin_months"))
        if client_id:
            rows = [r for r in rows if r.client_id == client_id]
        if month is not None:
            rows = [r for r in rows if r.month == month]
        return rows

    def save_effort_slices(self, rows: Sequence[EffortSlice]) -> int:
        keys = [
            (f"{r.client_id}:{r.month}:{r.category}:{r.level.value}:{r.work_class.value}:{i}", r)
            for i, r in enumerate(rows)
        ]
        return self._put_many("effort_slices", keys)

    def list_effort_slices(self, client_id: str | None = None) -> list[EffortSlice]:
        rows = serde.decode_many(EffortSlice, self._all("effort_slices"))
        return [r for r in rows if client_id is None or r.client_id == client_id]

    def save_hours_summaries(self, rows: Sequence[HoursSummary]) -> int:
        return self._put_many("hours_summaries", [(f"{r.client_id}:{r.month}", r) for r in rows])

    def list_hours_summaries(self, client_id: str | None = None) -> list[HoursSummary]:
        rows = serde.decode_many(HoursSummary, self._all("hours_summaries"))
        return [r for r in rows if client_id is None or r.client_id == client_id]

    def save_renewal_watch(self, rows: Sequence[RenewalWatch]) -> int:
        with self._cursor() as cur:
            cur.execute("DELETE FROM renewal_watch")
        return self._put_many("renewal_watch", [(f"{r.contract_id}:{r.client_id}", r) for r in rows])

    def list_renewal_watch(self, horizon_days: int = 90) -> list[RenewalWatch]:
        rows = serde.decode_many(RenewalWatch, self._all("renewal_watch"))
        return [w for w in rows if w.days_to_renewal <= horizon_days]

    def save_margin_lines(self, client_id: str, month: Month, rows: Sequence[MarginLine]) -> None:
        self._delete("margin_lines", "key LIKE ?", (f"{client_id}:{month}:%",))
        keys = [(f"{client_id}:{month}:{i}", r) for i, r in enumerate(rows)]
        self._put_many("margin_lines", keys)

    def margin_lines(self, client_id: str, month: Month) -> list[MarginLine]:
        raw = self._all("margin_lines", "key LIKE ?", (f"{client_id}:{month}:%",))
        return serde.decode_many(MarginLine, raw)

    # ----------------------------------------------------------------- audit
    def append(self, entry: AuditEntry) -> None:
        key = f"{entry.at.isoformat()}:{entry.entity_kind}:{entry.entity_id}:{len(self._all('audit'))}"
        self._put("audit", key, entry)

    def list_entries(self, entity_kind: str | None = None, entity_id: str | None = None) -> list[AuditEntry]:
        rows = serde.decode_many(AuditEntry, self._all("audit"))
        if entity_kind:
            rows = [e for e in rows if e.entity_kind == entity_kind]
        if entity_id:
            rows = [e for e in rows if e.entity_id == entity_id]
        return rows

    # -------------------------------------------------------------- settings
    def load(self) -> Settings:
        raw = self._get("settings", "current")
        return serde.decode(Settings, raw) if raw else Settings()

    def save(self, settings: Settings, author: str, reason: str) -> None:
        self._put("settings", "current", settings)
        self.append(AuditEntry.now("settings", "current", "update", author, reason))


__all__ = ["MIGRATIONS", "TABLE_OF", "SqliteStore"]
