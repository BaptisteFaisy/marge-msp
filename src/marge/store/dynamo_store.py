"""DynamoDB implementation of the ``Store`` protocol (spec 15, ENF-REP-01).

Single-table design on table ``marge``, composite key ``(pk, sk)``: ``pk`` is
the entity kind (``clients``, ``contracts``, …) and ``sk`` the natural key of
the row (same key strings as ``SqliteStore``). Three sparse GSIs serve the
Protocol queries without ever scanning the table:

- ``gsi_client`` (``client_pk``, ``sk``) — per-client reads: contracts,
  interventions, classifications, margins, effort, hours.
- ``gsi_month`` (``month_pk``, ``sk``) — per-month reads: interventions, AWS
  costs, invoices, penalties, margins.
- ``gsi_status`` (``status_pk``, ``sk``) — per-status reads: pending matches,
  classifications by decision status.

GSI keys carry the entity kind (``clients#CLIENT#c-001``) so one index serves
every entity without collisions. Every payload goes through
``marge.store.serde`` — no mapping logic is duplicated from ``SqliteStore``.
``boto3`` is imported lazily inside ``_default_client()`` only, so the module
and its tests run without ``boto3`` installed (CONTRACT rule 4).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any
from uuid import uuid4

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
from . import serde

_BATCH_SIZE = 25  # DynamoDB BatchWriteItem hard limit

from .dynamo_schema import (  # noqa: E402
    DEFAULT_TABLE_NAME,
    GSI_OF,
    create_table_resources,
)


def _default_client(region_name: str | None = None) -> Any:
    """Lazily import ``boto3`` so CI runners without it never fail."""
    import boto3

    return boto3.client("dynamodb", region_name=region_name)


def _s(value: str) -> dict[str, str]:
    return {"S": value}


def _decode_item(cls: type, item: dict[str, Any]) -> Any:
    return serde.decode(cls, json.loads(item["payload"]["S"]))


class DynamoStore:
    """Persistent ``Store`` backed by a single DynamoDB table."""

    def __init__(
        self,
        table_name: str = DEFAULT_TABLE_NAME,
        client: Any | None = None,
        region_name: str | None = None,
    ) -> None:
        self.table_name = table_name
        # An injected client is used as-is: boto3 is never imported in tests.
        self._client = client if client is not None else _default_client(region_name)

    # ------------------------------------------------------------ plumbing
    def _item(
        self,
        entity: str,
        sk: str,
        value: Any,
        *,
        client_id: str | None = None,
        month: Month | str | None = None,
        status: str | None = None,
    ) -> dict[str, dict[str, str]]:
        item: dict[str, dict[str, str]] = {
            "pk": _s(entity),
            "sk": _s(sk),
            "payload": _s(json.dumps(serde.encode(value), ensure_ascii=False)),
        }
        for kind, key_value in (("CLIENT", client_id), ("MONTH", month), ("STATUS", status)):
            if key_value:
                item[GSI_OF[kind][1]] = _s(f"{entity}#{kind}#{key_value}")
        return item

    def _put_item(self, item: dict[str, dict[str, str]]) -> None:
        self._client.put_item(TableName=self.table_name, Item=item)

    def _put_batch(self, items: Iterable[dict[str, dict[str, str]]]) -> int:
        batch = list(items)
        for chunk in _chunks(batch):
            requests = [{"PutRequest": {"Item": item}} for item in chunk]
            self._client.batch_write_item(RequestItems={self.table_name: requests})
        return len(batch)

    def _get_item(self, entity: str, sk: str) -> dict[str, Any] | None:
        resp = self._client.get_item(TableName=self.table_name, Key={"pk": _s(entity), "sk": _s(sk)})
        return resp.get("Item")

    def _query(
        self,
        pk_attr: str,
        pk_value: str,
        *,
        index_name: str | None = None,
        sk_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        expr = f"{pk_attr} = :pk"
        values: dict[str, dict[str, str]] = {":pk": _s(pk_value)}
        if sk_prefix is not None:
            expr += " AND begins_with(sk, :prefix)"
            values[":prefix"] = _s(sk_prefix)
        kwargs: dict[str, Any] = {
            "TableName": self.table_name,
            "KeyConditionExpression": expr,
            "ExpressionAttributeValues": values,
        }
        if index_name is not None:
            kwargs["IndexName"] = index_name
        items: list[dict[str, Any]] = []
        while True:
            resp = self._client.query(**kwargs)
            items.extend(resp.get("Items", []))
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                return items
            kwargs["ExclusiveStartKey"] = last_key

    def _rows(
        self,
        entity: str,
        cls: type,
        *,
        gsi_kind: str | None = None,
        gsi_value: str | None = None,
        sk_prefix: str | None = None,
    ) -> list[Any]:
        """Decoded rows of one entity partition, optionally through a GSI."""
        if gsi_kind is not None and gsi_value is not None:
            index, attr = GSI_OF[gsi_kind]
            items = self._query(attr, f"{entity}#{gsi_kind}#{gsi_value}", index_name=index)
        else:
            items = self._query("pk", entity, sk_prefix=sk_prefix)
        return [_decode_item(cls, item) for item in items]

    def _delete_rows(self, items: Sequence[dict[str, Any]]) -> None:
        for chunk in _chunks(items):
            requests = [{"DeleteRequest": {"Key": {"pk": it["pk"], "sk": it["sk"]}}} for it in chunk]
            self._client.batch_write_item(RequestItems={self.table_name: requests})

    def _replace_partition(self, entity: str, sk_prefix: str | None = None) -> None:
        self._delete_rows(self._query("pk", entity, sk_prefix=sk_prefix))

    # ------------------------------------------------------------- clients
    def upsert_clients(self, clients: Sequence[Client]) -> int:
        return self._put_batch(self._item("clients", c.client_id, c, client_id=c.client_id) for c in clients)

    def get_client(self, client_id: str) -> Client | None:
        item = self._get_item("clients", client_id)
        return _decode_item(Client, item) if item else None

    def list_clients(self, account_manager_id: str | None = None) -> list[Client]:
        rows = self._rows("clients", Client)
        if account_manager_id:
            rows = [c for c in rows if c.account_manager_id == account_manager_id]
        return rows

    # -------------------------------------------------------------- matches
    def save_matches(self, matches: Sequence[ClientMatch]) -> int:
        return self._put_batch(
            self._item("matches", m.match_id, m, client_id=m.client_id, status=m.status.value)
            for m in matches
        )

    def list_matches(self, pending_only: bool = False) -> list[ClientMatch]:
        if pending_only:
            return self._rows("matches", ClientMatch, gsi_kind="STATUS", gsi_value="PENDING")
        return self._rows("matches", ClientMatch)

    def get_match(self, match_id: str) -> ClientMatch | None:
        item = self._get_item("matches", match_id)
        return _decode_item(ClientMatch, item) if item else None

    # ------------------------------------------------------------ contracts
    def save_contract(self, contract: Contract) -> None:
        self._put_item(
            self._item(
                "contracts",
                f"{contract.contract_id}:{contract.version}",
                contract,
                client_id=contract.client_id,
                status=contract.status.value,
            )
        )

    def get_contract(self, contract_id: str, version: int | None = None) -> Contract | None:
        if version is not None:
            item = self._get_item("contracts", f"{contract_id}:{version}")
            return _decode_item(Contract, item) if item else None
        owned = self._rows("contracts", Contract, sk_prefix=f"{contract_id}:")
        return max(owned, key=lambda c: c.version) if owned else None

    def list_contracts(self, client_id: str | None = None) -> list[Contract]:
        if client_id:
            return self._rows("contracts", Contract, gsi_kind="CLIENT", gsi_value=client_id)
        return self._rows("contracts", Contract)

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
        return self._put_batch(
            self._item("interventions", i.intervention_id, i, client_id=i.client_id, month=i.month)
            for i in interventions
        )

    def list_interventions(
        self, month: Month | None = None, client_id: str | None = None
    ) -> list[Intervention]:
        if month is not None:
            rows = self._rows("interventions", Intervention, gsi_kind="MONTH", gsi_value=str(month))
            return [i for i in rows if not client_id or i.client_id == client_id]
        if client_id:
            return self._rows("interventions", Intervention, gsi_kind="CLIENT", gsi_value=client_id)
        return self._rows("interventions", Intervention)

    def save_classification(self, classification: Classification) -> None:
        self._put_item(
            self._item(
                "classifications",
                classification.intervention_id,
                classification,
                client_id=classification.client_id,
                status=classification.status.value,
            )
        )

    def list_classifications(
        self, status: str | None = None, client_id: str | None = None, month: Month | None = None
    ) -> list[Classification]:
        rows = self._classification_rows(status, client_id)
        if month is not None:
            ids = {i.intervention_id for i in self.list_interventions(month=month)}
            rows = [c for c in rows if c.intervention_id in ids]
        return rows

    def _classification_rows(self, status: str | None, client_id: str | None) -> list[Classification]:
        if status:
            return self._rows("classifications", Classification, gsi_kind="STATUS", gsi_value=status)
        if client_id:
            return self._rows("classifications", Classification, gsi_kind="CLIENT", gsi_value=client_id)
        return self._rows("classifications", Classification)

    def save_category_decision(self, decision: CategoryDecision) -> None:
        sk = f"{decision.contract_id}:{decision.contract_version}:{decision.category}"
        self._put_item(self._item("category_decisions", sk, decision))

    def find_category_decision(
        self, contract_id: str, contract_version: int, category: str
    ) -> CategoryDecision | None:
        item = self._get_item("category_decisions", f"{contract_id}:{contract_version}:{category}")
        return _decode_item(CategoryDecision, item) if item else None

    # ------------------------------------------------------------------ cost
    def save_rates(self, rates: Sequence[Rate]) -> int:
        return self._put_batch(
            self._item("rates", f"{r.level.value}:{r.effective_from.isoformat()}", r) for r in rates
        )

    def list_rates(self) -> list[Rate]:
        return self._rows("rates", Rate)

    def save_tooling_costs(self, costs: Sequence[ToolingCost]) -> int:
        return self._put_batch(
            self._item("tooling_costs", f"{c.tool}:{i}", c, client_id=c.client_id)
            for i, c in enumerate(costs)
        )

    def list_tooling_costs(self) -> list[ToolingCost]:
        return self._rows("tooling_costs", ToolingCost)

    def save_aws_costs(self, costs: Sequence[AwsCost]) -> int:
        return self._put_batch(
            self._item(
                "aws_costs",
                f"{c.aws_account_id}:{c.month}:{i}",
                c,
                client_id=c.client_id,
                month=c.month,
            )
            for i, c in enumerate(costs)
        )

    def list_aws_costs(self, month: Month | None = None) -> list[AwsCost]:
        return self._rows_by_month("aws_costs", AwsCost, month)

    def save_invoices(self, invoices: Sequence[Invoice]) -> int:
        return self._put_batch(
            self._item("invoices", i.invoice_id, i, client_id=i.client_id, month=i.month) for i in invoices
        )

    def list_invoices(self, month: Month | None = None) -> list[Invoice]:
        return self._rows_by_month("invoices", Invoice, month)

    def save_penalties(self, penalties: Sequence[Penalty]) -> int:
        return self._put_batch(
            self._item("penalties", f"{p.client_id}:{p.month}:{i}", p, client_id=p.client_id, month=p.month)
            for i, p in enumerate(penalties)
        )

    def list_penalties(self, month: Month | None = None) -> list[Penalty]:
        return self._rows_by_month("penalties", Penalty, month)

    def _rows_by_month(self, entity: str, cls: type, month: Month | None) -> list[Any]:
        if month is not None:
            return self._rows(entity, cls, gsi_kind="MONTH", gsi_value=str(month))
        return self._rows(entity, cls)

    # ------------------------------------------------------------- analytics
    def save_margin_months(self, rows: Sequence[MarginMonth]) -> int:
        return self._put_batch(
            self._item(
                "margin_months",
                f"{r.client_id}:{r.month}:{r.calc_version}",
                r,
                client_id=r.client_id,
                month=r.month,
            )
            for r in rows
        )

    def list_margin_months(
        self, client_id: str | None = None, month: Month | None = None
    ) -> list[MarginMonth]:
        if client_id:
            rows = self._rows("margin_months", MarginMonth, gsi_kind="CLIENT", gsi_value=client_id)
            return [r for r in rows if month is None or r.month == month]
        return self._rows_by_month("margin_months", MarginMonth, month)

    def save_effort_slices(self, rows: Sequence[EffortSlice]) -> int:
        return self._put_batch(
            self._item(
                "effort_slices",
                f"{r.client_id}:{r.month}:{r.category}:{r.level.value}:{r.work_class.value}:{i}",
                r,
                client_id=r.client_id,
                month=r.month,
            )
            for i, r in enumerate(rows)
        )

    def list_effort_slices(self, client_id: str | None = None) -> list[EffortSlice]:
        return self._rows_by_client("effort_slices", EffortSlice, client_id)

    def save_hours_summaries(self, rows: Sequence[HoursSummary]) -> int:
        return self._put_batch(
            self._item("hours_summaries", f"{r.client_id}:{r.month}", r, client_id=r.client_id, month=r.month)
            for r in rows
        )

    def list_hours_summaries(self, client_id: str | None = None) -> list[HoursSummary]:
        return self._rows_by_client("hours_summaries", HoursSummary, client_id)

    def _rows_by_client(self, entity: str, cls: type, client_id: str | None) -> list[Any]:
        if client_id:
            return self._rows(entity, cls, gsi_kind="CLIENT", gsi_value=client_id)
        return self._rows(entity, cls)

    def save_renewal_watch(self, rows: Sequence[RenewalWatch]) -> int:
        self._replace_partition("renewal_watch")
        return self._put_batch(
            self._item("renewal_watch", f"{r.contract_id}:{r.client_id}", r, client_id=r.client_id)
            for r in rows
        )

    def list_renewal_watch(self, horizon_days: int = 90) -> list[RenewalWatch]:
        rows = self._rows("renewal_watch", RenewalWatch)
        return [w for w in rows if w.days_to_renewal <= horizon_days]

    def save_margin_lines(self, client_id: str, month: Month, rows: Sequence[MarginLine]) -> None:
        prefix = f"{client_id}:{month}:"
        self._replace_partition("margin_lines", sk_prefix=prefix)
        self._put_batch(
            self._item("margin_lines", f"{prefix}{i}", r, client_id=client_id, month=month)
            for i, r in enumerate(rows)
        )

    def margin_lines(self, client_id: str, month: Month) -> list[MarginLine]:
        return self._rows("margin_lines", MarginLine, sk_prefix=f"{client_id}:{month}:")

    # ----------------------------------------------------------------- audit
    def append(self, entry: AuditEntry) -> None:
        sk = f"{entry.at.isoformat()}:{entry.entity_kind}:{entry.entity_id}:{uuid4().hex}"
        self._put_item(self._item("audit", sk, entry))

    def list_entries(self, entity_kind: str | None = None, entity_id: str | None = None) -> list[AuditEntry]:
        rows = self._rows("audit", AuditEntry)
        if entity_kind:
            rows = [e for e in rows if e.entity_kind == entity_kind]
        if entity_id:
            rows = [e for e in rows if e.entity_id == entity_id]
        return rows

    # ------------------------------------------------------- calc versions
    def save_calc_version(self, version: CalcVersion) -> None:
        self._put_item(self._item("calc_versions", str(version.version), version))

    def list_calc_versions(self) -> list[CalcVersion]:
        rows = self._rows("calc_versions", CalcVersion)
        return sorted(rows, key=lambda v: v.version)

    # ------------------------------------------------------------- llm log
    def append_llm_call(self, call: LlmCall) -> None:
        """Append-only: one item per call, sorted by timestamp."""
        sk = f"{call.at.isoformat()}:{call.purpose}:{call.entity_id}:{uuid4().hex}"
        item = self._item("llm_calls", sk, call, client_id=call.client_id or None)
        self._put_item(item)

    def list_llm_calls(
        self, purpose: str | None = None, client_id: str | None = None, model_id: str | None = None
    ) -> list[LlmCall]:
        rows = self._rows("llm_calls", LlmCall)
        if purpose:
            rows = [c for c in rows if c.purpose == purpose]
        if client_id:
            rows = [c for c in rows if c.client_id == client_id]
        if model_id:
            rows = [c for c in rows if c.model_id == model_id]
        return rows

    # -------------------------------------------------------------- settings
    def load(self) -> Settings:
        item = self._get_item("settings", "current")
        return _decode_item(Settings, item) if item else Settings()

    def save(self, settings: Settings, author: str, reason: str) -> None:
        self._put_item(self._item("settings", "current", settings))
        self.append(AuditEntry.now("settings", "current", "update", author, reason))


def _chunks(items: Sequence[Any], size: int = _BATCH_SIZE) -> Iterable[Sequence[Any]]:
    for offset in range(0, len(items), size):
        yield items[offset : offset + size]


__all__ = ["DEFAULT_TABLE_NAME", "DynamoStore", "create_table_resources"]
