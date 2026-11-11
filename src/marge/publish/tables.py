"""Turning the store into the five analytical tables of Annex A.

The column names and their order come from ``marge.store.athena.ANALYTICAL_TABLES``
— the same source of truth that renders the Athena DDL — so a published CSV can
never drift from the table it is loaded into.

Every amount is rendered as text: no float ever touches a figure.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ..domain import Contract, HoursSummary, MarginMonth, Month
from ..store.athena import ANALYTICAL_TABLES, ExternalTableSpec
from ..store.base import Store

PARTITION_COLUMN = "month"


def table_spec(name: str) -> ExternalTableSpec:
    for spec in ANALYTICAL_TABLES:
        if spec.name == name:
            return spec
    raise KeyError(f"unknown analytical table: {name}")


def columns_of(name: str) -> list[str]:
    """Column names of one table, partition key included, in DDL order."""
    spec = table_spec(name)
    return [c.name for c in spec.columns] + [p.name for p in spec.partition_keys]


def _scale_of(sql_type: str) -> int | None:
    """Scale of a ``DECIMAL(p,s)`` column, ``None`` for any other type."""
    upper = sql_type.upper()
    if not upper.startswith("DECIMAL"):
        return None
    _, _, scale = upper[len("DECIMAL(") :].rstrip(")").partition(",")
    return int(scale or 0)


def column_scales(name: str) -> dict[str, int]:
    """Declared scale of every decimal column: the DDL is the source of truth."""
    return {
        column.name: scale
        for column in _all_columns(name)
        if (scale := _scale_of(column.sql_type)) is not None
    }


def typed_columns(name: str) -> dict[str, bool]:
    """``{column: is_typed}`` — typed means anything but STRING.

    A typed column cannot hold the empty string: Parquet refuses it outright
    ("Could not convert '' to int32") and Athena would read a JSONL "" as a
    cast error. Both formats get ``null`` instead.
    """
    return {column.name: not column.sql_type.upper().startswith("STRING") for column in _all_columns(name)}


def _all_columns(name: str):
    spec = table_spec(name)
    return (*spec.columns, *spec.partition_keys)


def normalise_row(name: str, row: dict) -> dict:
    """Round every amount to the scale its column declares.

    Athena reads a JSONL string or a Parquet decimal against the declared
    ``DECIMAL(p,s)``; a value carrying more decimals is either rejected outright
    (Parquet: "Rescaling Decimal value would cause data loss") or silently
    rounded (JSONL). Rounding here, once, keeps both formats identical to the
    schema — the DDL stays the single source of truth.
    """
    scales = column_scales(name)
    typed = typed_columns(name)
    fixed = dict(row)
    for column, scale in scales.items():
        value = fixed.get(column)
        if isinstance(value, Decimal):
            # ROUND_HALF_UP, comme marge.domain.money : le lac doit contenir
            # exactement ce que le moteur a calculé, pas un arrondi bancaire.
            fixed[column] = value.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
    for column, is_typed in typed.items():
        if is_typed and fixed.get(column) == "":
            fixed[column] = None
    return fixed


def _json_value(value: object) -> object:
    """JSON value of one field, keeping every amount exact.

    A Decimal is written as a *string*: JSON has no decimal type and turning it
    into a float would lose cents. The Athena JsonSerDe coerces the string back
    into the DECIMAL column.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int):
        return value
    if value is None:
        return None
    return str(value)


def _client_row(store: Store, client_id: str) -> tuple[str, str]:
    client = store.get_client(client_id)
    if client is None:
        return ("", "")
    return (client.name, client.account_manager_id)


def margin_rows(store: Store, months: list[Month]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for month in months:
        for row in store.list_margin_months(month=month):
            name, manager = _client_row(store, row.client_id)
            rows.append(
                {
                    "client_id": row.client_id,
                    "client_name": name,
                    "account_manager_id": manager or row.account_manager_id,
                    "revenue_subscription": row.revenue.subscription,
                    "revenue_aws_resale": row.revenue.aws_resale_margin,
                    "revenue_extra_hours_billed": row.revenue.extra_hours_billed,
                    "revenue_projects": row.revenue.projects,
                    "revenue_total": row.revenue.total,
                    "cost_labour": row.costs.labour,
                    "cost_tooling": row.costs.tooling,
                    "cost_msp_aws": row.costs.msp_aws,
                    "cost_penalties": row.costs.penalties,
                    "cost_total": row.costs.total,
                    "margin": row.margin,
                    "margin_rate": row.margin_rate,
                    "coverage": row.coverage.value,
                    "is_estimate": row.is_estimate,
                    "state": row.state.value,
                    "calc_version": row.calc_version,
                    PARTITION_COLUMN: str(month),
                }
            )
    return rows


def effort_rows(store: Store, months: list[Month]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for slice_ in store.list_effort_slices():
        if months and slice_.month not in months:
            continue
        _, manager = _client_row(store, slice_.client_id)
        hourly = (
            (slice_.labour_cost / slice_.hours_spent).quantize(Decimal("0.0001"))
            if slice_.hours_spent
            else Decimal("0")
        )
        rows.append(
            {
                "client_id": slice_.client_id,
                "account_manager_id": manager,
                "category": slice_.category,
                "level": slice_.level.value,
                "hours_spent": slice_.hours_spent,
                "labour_cost": slice_.labour_cost,
                "ticket_count": slice_.ticket_count,
                "work_class": slice_.work_class.value,
                "hourly_cost": hourly,
                PARTITION_COLUMN: str(slice_.month),
            }
        )
    return rows


def unbilled_rows(store: Store, months: list[Month]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for summary in store.list_hours_summaries():
        if months and summary.month not in months:
            continue
        _, manager = _client_row(store, summary.client_id)
        rows.append(
            {
                "client_id": summary.client_id,
                "account_manager_id": manager,
                "out_of_scope_validated_hours": summary.out_of_scope_validated_hours,
                "over_quota_hours": summary.over_quota_hours,
                "billed_extra_hours": summary.billed_extra_hours,
                "unbilled_hours": summary.unbilled_hours,
                "contract_hour_rate": summary.contract_hour_rate,
                "unbilled_value": summary.unbilled_value,
                "state": summary.state.value,
                PARTITION_COLUMN: str(summary.month),
            }
        )
    return rows


def contract_rows(store: Store) -> list[dict[str, str]]:
    """One row per validated contract, enriched with the renewal watch."""
    watch = {w.contract_id: w for w in store.list_renewal_watch(horizon_days=10_000)}
    rows: list[dict[str, str]] = []
    for contract in _validated_contracts(store):
        name, manager = _client_row(store, contract.client_id)
        entry = watch.get(contract.contract_id)
        rows.append(_contract_row(contract, name, manager, entry))
    return rows


def _validated_contracts(store: Store) -> list[Contract]:
    return [c for c in store.list_contracts() if c.status.value == "VALIDATED"]


def _contract_row(contract: Contract, name: str, manager: str, entry) -> dict[str, str]:
    fields = contract.fields
    return {
        "contract_id": contract.contract_id,
        "version": contract.version,
        "client_id": contract.client_id,
        "client_name": name,
        "account_manager_id": manager,
        "monthly_subscription": fields.monthly_subscription,
        "included_hours_per_month": fields.included_hours_per_month,
        "extra_hour_rate": fields.extra_hour_rate,
        "end_date": fields.end_date,
        "days_to_renewal": entry.days_to_renewal if entry else "",
        "margin_rate_six_months": entry.margin_rate_six_months if entry else "",
        "trend": entry.trend if entry else "",
        "status": contract.status.value,
    }


def pending_rows(store: Store, months: list[Month]) -> list[dict[str, str]]:
    """The validation queue: one row per intervention awaiting a human."""
    interventions = {i.intervention_id: i for i in store.list_interventions()}
    rows: list[dict[str, str]] = []
    for cls in store.list_classifications(status="PENDING"):
        intervention = interventions.get(cls.intervention_id)
        if intervention is None or not intervention.attributed:
            continue
        if months and intervention.month not in months:
            continue
        name, manager = _client_row(store, cls.client_id)
        rows.append(
            {
                "intervention_id": cls.intervention_id,
                "ticket_id": intervention.ticket_id,
                "client_id": cls.client_id,
                "client_name": name,
                "account_manager_id": manager,
                "occurred_on": intervention.occurred_on,
                "category": intervention.category,
                "level": intervention.level.value,
                "hours_spent": intervention.hours_spent,
                "proposed_class": cls.work_class.value,
                "confidence": cls.confidence,
                "cited_clause": cls.cited_clause,
                "reason": cls.reason,
                "needs_human_validation": cls.needs_human_validation,
                "decision_status": cls.status.value,
            }
        )
    return rows


BUILDERS = {
    "marge_client_mois": margin_rows,
    "effort_client_mois_categorie": effort_rows,
    "heures_non_facturees": unbilled_rows,
}


def rows_of(name: str, store: Store, months: list[Month]) -> list[dict[str, str]]:
    """Dispatch on the table name; the two unpartitioned tables take no month."""
    if name in BUILDERS:
        return BUILDERS[name](store, months)
    if name == "contrats_actifs":
        return contract_rows(store)
    if name == "interventions_a_valider":
        return pending_rows(store, months)
    raise KeyError(f"unknown analytical table: {name}")


def render_jsonl(name: str, rows: list[dict[str, object]]) -> str:
    """JSON Lines, one object per row, keys in the Athena DDL column order."""
    import json

    columns = columns_of(name)
    lines = [
        json.dumps(
            {column: _json_value(row.get(column)) for column in columns},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for row in (normalise_row(name, raw) for raw in rows)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def validate_row(name: str, row: dict[str, str]) -> list[str]:
    """Return the columns of the table that the row does not provide."""
    return [column for column in columns_of(name) if column not in row]


__all__ = [
    "BUILDERS",
    "HoursSummary",
    "MarginMonth",
    "column_scales",
    "columns_of",
    "normalise_row",
    "render_jsonl",
    "rows_of",
    "table_spec",
    "validate_row",
]
