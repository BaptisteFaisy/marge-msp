"""Reference tables of the fake MSP (EF-REF-02/03, spec 9.1).

Writes ``clients.json``, ``aliases.json``, ``rates.csv``, ``tooling.csv``,
``invoices.csv`` and ``penalties.csv``. The hourly costs carry a mid-history
change on 2026-07-01, which is the R9 scenario: past months must keep the rate
in force at the time.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .common import MONTHS, decimal_text
from .profile_data import LEGACY_ALIAS, LEGACY_ALIAS_TRUTH
from .profiles import ClientProfile

RATE_COLUMNS = ("level", "hourly_cost", "effective_from", "currency")
TOOLING_COLUMNS = ("tool", "monthly_cost", "basis", "client_id", "aws_account_id", "currency")
INVOICE_COLUMNS = ("invoice_id", "customer_ref", "month", "kind", "amount", "hours_billed", "currency")
PENALTY_COLUMNS = ("client_id", "month", "amount", "reason", "currency")

RATE_HISTORY: tuple[tuple[str, str, str], ...] = (
    ("N1", "50.00", "2026-01-01"),
    ("N2", "70.00", "2026-01-01"),
    ("N3", "80.00", "2026-01-01"),
    ("ARCHITECT", "110.00", "2026-01-01"),
    ("N1", "52.50", "2026-07-01"),
)
"""``N1`` costs 2,50 EUR more from 2026-07-01 (R9): past months must not move."""

TOOLING: tuple[tuple[str, str, str, str], ...] = (
    ("supervision-plateforme", "1200.00", "PER_LABOUR_HOUR", ""),
    ("soc-manage", "900.00", "PER_MANAGED_RESOURCE", ""),
    ("licences-portail", "480.00", "PER_CLIENT", ""),
    ("monitoring-comptes", "260.00", "PER_ACCOUNT", ""),
    ("sauvegarde-dediee", "340.00", "PER_CLIENT", "c-005"),
)
"""The four allocation bases of spec 12.2, plus one dedicated tool."""


@dataclass(frozen=True, slots=True)
class ReferenceTables:
    """Every reference file, ready to be written."""

    clients: list[dict]
    aliases: list[dict]
    rates: list[tuple]
    tooling: list[tuple]
    invoices: list[tuple]
    penalties: list[tuple]


def _clients(profiles: tuple[ClientProfile, ...]) -> list[dict]:
    return [
        {
            "client_id": profile.client_id,
            "name": profile.name,
            "account_manager_id": profile.account_manager_id,
            "sector": profile.sector,
            "onboarded_on": profile.onboarded_on.isoformat(),
            "managed_resource_count": profile.managed_resource_count,
        }
        for profile in profiles
    ]


def _aliases(profiles: tuple[ClientProfile, ...]) -> list[dict]:
    rows: list[dict] = []
    for profile in profiles:
        for source, source_id, variant in profile.aliases:
            rows.append(
                {
                    "client_id": profile.client_id,
                    "source": source,
                    "source_id": source_id,
                    "name_variant": variant,
                }
            )
    source, source_id, variant = LEGACY_ALIAS
    rows.append(
        {
            "client_id": LEGACY_ALIAS_TRUTH,
            "source": source,
            "source_id": source_id,
            "name_variant": variant,
        }
    )
    return sorted(rows, key=lambda row: (row["client_id"], row["source"], row["source_id"]))


def _rates() -> list[tuple]:
    return [(level, cost, effective, "EUR") for level, cost, effective in RATE_HISTORY]


def _tooling() -> list[tuple]:
    return [(tool, cost, basis, client_id or None, None, "EUR") for tool, cost, basis, client_id in TOOLING]


def _invoices(profiles: tuple[ClientProfile, ...]) -> list[tuple]:
    rows: list[tuple] = []
    number = 0
    for profile in profiles:
        for month in MONTHS:
            number += 1
            rows.append(
                (
                    f"inv-{number:05d}",
                    profile.invoice_alias,
                    month,
                    "SUBSCRIPTION",
                    decimal_text(profile.contract.monthly_subscription),
                    "0.00",
                    "EUR",
                )
            )
        for month, hours, amount in profile.extra_hours:
            number += 1
            rows.append(
                (
                    f"inv-{number:05d}",
                    profile.invoice_alias,
                    month,
                    "EXTRA_HOURS",
                    decimal_text(amount),
                    decimal_text(hours),
                    "EUR",
                )
            )
        for month, amount in profile.projects:
            number += 1
            rows.append(
                (
                    f"inv-{number:05d}",
                    profile.invoice_alias,
                    month,
                    "PROJECT",
                    decimal_text(amount),
                    "0.00",
                    "EUR",
                )
            )
    return rows


def _penalties(profiles: tuple[ClientProfile, ...]) -> list[tuple]:
    rows: list[tuple] = []
    for profile in profiles:
        for month, amount, reason in profile.penalties:
            rows.append((profile.client_id, month, decimal_text(amount), reason, "EUR"))
    return rows


def build(profiles: tuple[ClientProfile, ...]) -> ReferenceTables:
    """Every reference table of the dataset."""
    return ReferenceTables(
        clients=_clients(profiles),
        aliases=_aliases(profiles),
        rates=_rates(),
        tooling=_tooling(),
        invoices=_invoices(profiles),
        penalties=_penalties(profiles),
    )


def monthly_rate_evolution() -> dict[str, list[tuple[str, Decimal]]]:
    """``level -> [(month, hourly cost in force)]`` — used by the R9 test."""
    from .common import month_first

    evolution: dict[str, list[tuple[str, Decimal]]] = {}
    for level in ("N1", "N2", "N3", "ARCHITECT"):
        values: list[tuple[str, Decimal]] = []
        for month in MONTHS:
            in_force = [
                (effective, Decimal(cost))
                for lvl, cost, effective in RATE_HISTORY
                if lvl == level and month_first(month) >= month_first(effective)
            ]
            in_force.sort()
            values.append((month, in_force[-1][1]))
        evolution[level] = values
    return evolution
