"""Pure-Python Athena SQL and Glue DDL generation (spec 12, 15, Annex A).

Standard library only: generates deterministic DDL and analytical queries
without ``boto3`` or any execution. Every identifier (database, table, S3
bucket, prefix, client id) is validated against an allowlist pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

from .athena_ident import validate_identifier, validate_s3_location


@dataclass(frozen=True, slots=True)
class ColumnDef:
    """One column in an Athena external table."""

    name: str
    sql_type: str
    comment: str = ""


@dataclass(frozen=True, slots=True)
class ExternalTableSpec:
    """Definition of one Annex A analytical external table in Glue/Athena."""

    name: str
    grain: str
    columns: tuple[ColumnDef, ...]
    partition_keys: tuple[ColumnDef, ...] = ()


def _col(name: str, sql_type: str, comment: str = "") -> ColumnDef:
    return ColumnDef(name, sql_type, comment)


_MONTH_PARTITION = (_col("month", "STRING", "Calculation month YYYY-MM"),)
_COMMON_CLIENT = (
    _col("client_id", "STRING", "Common client identifier"),
    _col("client_name", "STRING", "Client commercial name"),
    _col("account_manager_id", "STRING", "Account manager identifier"),
)

ANALYTICAL_TABLES: tuple[ExternalTableSpec, ...] = (
    ExternalTableSpec(
        name="marge_client_mois",
        grain="one client, one month",
        columns=(
            *_COMMON_CLIENT,
            _col("revenue_subscription", "DECIMAL(12,2)", "Managed services subscription"),
            _col("revenue_aws_resale", "DECIMAL(12,2)", "AWS resale margin"),
            _col("revenue_extra_hours_billed", "DECIMAL(12,2)", "Billed extra hours"),
            _col("revenue_projects", "DECIMAL(12,2)", "Billed projects"),
            _col("revenue_total", "DECIMAL(12,2)", "Total revenue"),
            _col("cost_labour", "DECIMAL(12,2)", "Labour cost"),
            _col("cost_tooling", "DECIMAL(12,2)", "Allocated tooling cost"),
            _col("cost_msp_aws", "DECIMAL(12,2)", "MSP-borne AWS cost"),
            _col("cost_penalties", "DECIMAL(12,2)", "SLA penalties paid"),
            _col("cost_total", "DECIMAL(12,2)", "Total cost"),
            _col("margin", "DECIMAL(12,2)", "Revenue minus cost"),
            _col("margin_rate", "DECIMAL(8,4)", "Margin divided by revenue"),
            _col("coverage", "DECIMAL(6,4)", "Share of hours attached to a client"),
            _col("is_estimate", "BOOLEAN", "True when coverage is below threshold"),
            _col("state", "STRING", "COMPLETE, ESTIMATE or INCOMPLETE"),
            _col("calc_version", "INT", "Version of the calculation model"),
        ),
        partition_keys=_MONTH_PARTITION,
    ),
    ExternalTableSpec(
        name="effort_client_mois_categorie",
        grain="one client, one month, one category, one level",
        columns=(
            _col("client_id", "STRING", "Common client identifier"),
            _col("account_manager_id", "STRING", "Account manager identifier"),
            _col("category", "STRING", "Work category"),
            _col("level", "STRING", "Skill level N1/N2/N3/ARCHITECT (ENF-CONF-01)"),
            _col("hours_spent", "DECIMAL(10,2)", "Hours spent"),
            _col("labour_cost", "DECIMAL(12,2)", "Labour cost of the slice"),
            _col("ticket_count", "INT", "Distinct tickets behind the slice"),
            _col("work_class", "STRING", "IN_SCOPE, OUT_OF_SCOPE or UNCERTAIN"),
            _col("hourly_cost", "DECIMAL(10,2)", "Hourly cost of the level in force"),
        ),
        partition_keys=_MONTH_PARTITION,
    ),
    ExternalTableSpec(
        name="heures_non_facturees",
        grain="one client, one month",
        columns=(
            _col("client_id", "STRING", "Common client identifier"),
            _col("account_manager_id", "STRING", "Account manager identifier"),
            _col("out_of_scope_validated_hours", "DECIMAL(10,2)", "Validated OOS hours"),
            _col("over_quota_hours", "DECIMAL(10,2)", "Hours above contract quota"),
            _col("billed_extra_hours", "DECIMAL(10,2)", "Already billed extra hours"),
            _col("unbilled_hours", "DECIMAL(10,2)", "Unbilled hours after validation"),
            _col("contract_hour_rate", "DECIMAL(10,2)", "Contractual hourly rate"),
            _col("unbilled_value", "DECIMAL(12,2)", "Unbilled hours times contract rate"),
            _col("state", "STRING", "DETECTED, VALIDATED, BILLED or WRITTEN_OFF"),
        ),
        partition_keys=_MONTH_PARTITION,
    ),
    ExternalTableSpec(
        name="contrats_actifs",
        grain="one contract",
        columns=(
            _col("contract_id", "STRING", "Contract identifier"),
            _col("version", "INT", "Contract version"),
            *_COMMON_CLIENT,
            _col("monthly_subscription", "DECIMAL(12,2)", "Monthly subscription"),
            _col("included_hours_per_month", "DECIMAL(10,2)", "Included monthly hours"),
            _col("extra_hour_rate", "DECIMAL(10,2)", "Hourly rate beyond quota"),
            _col("end_date", "DATE", "Renewal date of the contract"),
            _col("days_to_renewal", "INT", "Days left before renewal"),
            _col("margin_rate_six_months", "DECIMAL(8,4)", "Six-month margin rate"),
            _col("trend", "STRING", "UP, DOWN or FLAT"),
            _col("status", "STRING", "Contract validation status"),
        ),
    ),
    ExternalTableSpec(
        name="interventions_a_valider",
        grain="one intervention",
        columns=(
            _col("intervention_id", "STRING", "Intervention identifier"),
            _col("ticket_id", "STRING", "ITSM ticket identifier"),
            *_COMMON_CLIENT,
            _col("occurred_on", "DATE", "Date of the intervention"),
            _col("category", "STRING", "Work category"),
            _col("level", "STRING", "Skill level (ENF-CONF-01)"),
            _col("hours_spent", "DECIMAL(10,2)", "Duration spent"),
            _col("proposed_class", "STRING", "Proposed work class"),
            _col("confidence", "DECIMAL(5,4)", "Model confidence"),
            _col("cited_clause", "STRING", "Cited contract clause"),
            _col("reason", "STRING", "Classification justification"),
            _col("needs_human_validation", "BOOLEAN", "Human decision required flag"),
            _col("decision_status", "STRING", "PENDING, APPROVED, CORRECTED or REJECTED"),
        ),
    ),
)

ANALYTICAL_TABLE_NAMES: tuple[str, ...] = tuple(t.name for t in ANALYTICAL_TABLES)


def _format_column(col: ColumnDef) -> str:
    safe_name = validate_identifier(col.name, "column")
    if col.comment:
        escaped = col.comment.replace("'", "''")
        return f"    {safe_name} {col.sql_type} COMMENT '{escaped}'"
    return f"    {safe_name} {col.sql_type}"


JSONL_SERDE = "org.apache.hive.hcatalog.data.JsonSerDe"


def create_external_table_ddl(
    spec: ExternalTableSpec,
    *,
    database: str = "marge",
    bucket: str = "marge-curated",
    prefix: str = "analytical",
    file_format: str = "PARQUET",
) -> str:
    """Render an Athena ``CREATE EXTERNAL TABLE`` DDL for one Annex A table.

    ``file_format`` must match what ``marge.publish`` actually wrote. The
    publisher emits JSON Lines with the standard library (no pyarrow on the CI
    workers); JSONL keeps the column types, unlike the OpenCSV serde which
    forces every column to STRING. A Parquet deployment asks for
    ``file_format="PARQUET"``.
    """
    db = validate_identifier(database, "database")
    tbl = validate_identifier(spec.name, "table")
    base_location = validate_s3_location(bucket, prefix)
    cols_sql = ",\n".join(_format_column(c) for c in spec.columns)
    parts = [f"CREATE EXTERNAL TABLE IF NOT EXISTS {db}.{tbl} (\n{cols_sql}\n)"]
    if spec.partition_keys:
        part_sql = ",\n".join(_format_column(p) for p in spec.partition_keys)
        parts.append(f"PARTITIONED BY (\n{part_sql}\n)")
    if file_format.upper() == "JSONL":
        parts.append(f"ROW FORMAT SERDE '{JSONL_SERDE}'")
        parts.append("STORED AS TEXTFILE")
        parts.append(f"LOCATION '{base_location}{tbl}/'")
    else:
        parts.append("STORED AS PARQUET")
        parts.append(f"LOCATION '{base_location}{tbl}/'")
        parts.append("TBLPROPERTIES ('parquet.compression'='SNAPPY')")
    return "\n".join(parts) + ";"


def all_analytical_ddls(
    *,
    database: str = "marge",
    bucket: str = "marge-curated",
    prefix: str = "analytical",
    file_format: str = "PARQUET",
) -> dict[str, str]:
    """Return ``{table_name: ddl}`` for every Annex A analytical table."""
    return {
        spec.name: create_external_table_ddl(
            spec, database=database, bucket=bucket, prefix=prefix, file_format=file_format
        )
        for spec in ANALYTICAL_TABLES
    }


# Réexport : `marge.store.athena` reste le point d'entrée public des requêtes,
# une seule implémentation (dans athena_sql.py), aucun import circulaire.
from .athena_sql import dataset_query, margin_recalculation_query  # noqa: E402

__all__ = [
    "ANALYTICAL_TABLES",
    "ANALYTICAL_TABLE_NAMES",
    "ColumnDef",
    "ExternalTableSpec",
    "all_analytical_ddls",
    "create_external_table_ddl",
    "dataset_query",
    "margin_recalculation_query",
    "validate_identifier",
]
