"""AWS billing exports and the EUR/USD rate (EF-SRC-02, spec 12.1).

Costs are exported in USD, as a real billing export would be: the connector
converts them to the reporting currency with ``fx.csv`` before the
calculation, so ``marge.calc`` only ever sees one currency.

Two MSP-owned tooling accounts are billed every month; they are not
re-billed to anyone and are spread over the clients by the loader.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .common import MONTHS, decimal_text, money
from .profiles import ClientProfile

COLUMNS = (
    "aws_account_id",
    "month",
    "cost",
    "currency",
    "rebilled_amount",
    "kind",
    "managed_resource_count",
    "client_ref",
)

FX_COLUMNS = ("month", "from", "to", "rate")

TOOLING_ACCOUNTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "999988887777",
        "plateforme-supervision",
        ("430.00", "435.00", "440.00", "445.00", "450.00", "455.00"),
    ),
    (
        "999977776666",
        "coffre-sauvegarde",
        ("260.00", "262.00", "264.00", "266.00", "268.00", "270.00"),
    ),
)
"""MSP-owned accounts: cost to the MSP, re-billed to nobody (spec 12.2)."""

FX_RATES: tuple[tuple[str, str], ...] = (
    ("2026-05", "0.9180"),
    ("2026-06", "0.9210"),
    ("2026-07", "0.9150"),
    ("2026-08", "0.9250"),
    ("2026-09", "0.9300"),
    ("2026-10", "0.9280"),
)


@dataclass(frozen=True, slots=True)
class BillingExport:
    """The two billing artefacts, ready to be written."""

    cost_rows: list[tuple]
    fx_rows: list[tuple]

    @property
    def client_accounts(self) -> int:
        return len({row[0] for row in self.cost_rows if row[5] == "CLIENT_ACCOUNT"})


def _client_rows(profile: ClientProfile) -> list[tuple]:
    rows: list[tuple] = []
    for index, month in enumerate(MONTHS):
        cost = profile.aws_costs_usd[index]
        rebilled = money(cost * (Decimal("1") + profile.aws_markup))
        rows.append(
            (
                profile.billing_alias,
                month,
                decimal_text(cost),
                "USD",
                decimal_text(rebilled),
                "CLIENT_ACCOUNT",
                profile.managed_resource_count,
                profile.billing_alias,
            )
        )
    return rows


def _tooling_rows() -> list[tuple]:
    rows: list[tuple] = []
    for account_id, _label, costs in TOOLING_ACCOUNTS:
        for index, month in enumerate(MONTHS):
            rows.append((account_id, month, costs[index], "USD", "0.00", "MSP_TOOLING_ACCOUNT", 0, ""))
    return rows


def build(profiles: tuple[ClientProfile, ...]) -> BillingExport:
    """AWS costs of every client account and of the MSP tooling accounts."""
    rows: list[tuple] = []
    for profile in profiles:
        rows.extend(_client_rows(profile))
    rows.extend(_tooling_rows())
    rows.sort(key=lambda row: (row[0], row[1]))
    fx = [(month, "USD", "EUR", rate) for month, rate in FX_RATES]
    return BillingExport(cost_rows=rows, fx_rows=fx)
