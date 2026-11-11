"""Queries the analyst agent answers the 20 reference questions with (R11).

Every figure comes from :class:`~marge.eval.report.MarginReport`, hence from
``marge.calc``: the agent never computes an amount itself (ENF-IA-01). The
question catalogue lives in :mod:`marge.eval.question_set` and calls these
methods, so the ground truth written by the generator and the answers scored by
the harness go through exactly one implementation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..domain import ContractStatus, MarginMonth, MarginState
from .fields import normalise_text
from .report import MarginReport

THRESHOLD = Decimal("0.20")
DEFAULT_MONTH = "2026-10"
DEMO_TODAY = date(2026, 11, 11)
"""The day the demo runs (spec 19.1). Never read from the clock."""


def money(value: Decimal) -> str:
    """Canonical answer form of an amount: ``0.1937`` stays, ``1234.5`` -> ``1234.50``."""
    return f"{value:.2f}"


def _words(text: str) -> set[str]:
    """Significant words of a text, plural-insensitive (``base`` finds ``bases``)."""
    words = set()
    for word in normalise_text(text).replace("-", " ").split():
        word = word.strip(".,;:()«»\"'")
        if len(word) >= 3:
            words.add(word[:-1] if word.endswith("s") else word)
    return words


def rate_text(value: Decimal) -> str:
    """A margin rate answered as a plain ratio with four decimals."""
    return f"{value:.4f}"


class Analyst:
    """Answers the reference questions from the computed margins."""

    def __init__(self, report: MarginReport, today: date = DEMO_TODAY) -> None:
        self.report = report
        self.today = today

    # -- margins -----------------------------------------------------------
    def _row(self, client_id: str, month: str) -> MarginMonth | None:
        return self.report.get(client_id, month)

    def rate(self, client_id: str, month: str = DEFAULT_MONTH) -> Decimal:
        row = self._row(client_id, month)
        return row.margin_rate if row else Decimal("0")

    def below_threshold(self, month: str = DEFAULT_MONTH) -> list[str]:
        """Clients under the 20 % margin threshold for ``month`` (spec 14.5)."""
        return sorted(
            client_id
            for client_id in self.report.client_ids()
            if (row := self._row(client_id, month)) is not None and row.margin_rate < THRESHOLD
        )

    def loss_making(self) -> list[str]:
        """Clients with at least one month of negative margin."""
        return sorted(
            client_id
            for client_id in self.report.client_ids()
            if any(row.margin < 0 for row in self.report.series(client_id))
        )

    def ranking(self, month: str = DEFAULT_MONTH) -> list[str]:
        """Clients sorted by margin rate, best first."""
        scored = [
            (self.rate(client_id, month), client_id)
            for client_id in self.report.client_ids()
            if self._row(client_id, month) is not None
        ]
        return [client_id for _value, client_id in sorted(scored, key=lambda p: (-p[0], p[1]))]

    def delta(self, client_id: str, start: str, end: str) -> Decimal:
        """Change of margin rate between two months."""
        return self.rate(client_id, end) - self.rate(client_id, start)

    def biggest_drop(self, start: str, end: str) -> str:
        """Client whose margin rate fell the most between two complete months.

        A month whose margin is ``INCOMPLETE`` (no validated contract, R4) is
        not comparable with a complete one, so it stays out of the ranking.
        """
        moves = [
            (self.delta(client_id, start, end), client_id)
            for client_id in self.report.client_ids()
            if self.is_complete(client_id, start) and self.is_complete(client_id, end)
        ]
        return min(moves, key=lambda pair: (pair[0], pair[1]))[1]

    def is_complete(self, client_id: str, month: str) -> bool:
        """True when the margin of that client-month is fully computed."""
        row = self._row(client_id, month)
        return row is not None and row.state == MarginState.COMPLETE

    # -- out-of-scope work -------------------------------------------------
    def out_of_scope_hours(self, client_id: str) -> Decimal:
        return self.report.out_of_scope_hours(client_id)

    def top_out_of_scope_category(self, client_id: str) -> str:
        totals = self.report.out_of_scope_by_category(client_id)
        if not totals:
            return ""
        return max(totals, key=lambda name: (totals[name], name))

    def out_of_scope_hours_for(self, client_id: str, category: str) -> Decimal:
        return self.report.out_of_scope_by_category(client_id).get(category, Decimal("0"))

    def unassigned_hours(self, month: str = DEFAULT_MONTH) -> Decimal:
        return self.report.unassigned_hours.get(month, Decimal("0"))

    # -- contracts ---------------------------------------------------------
    def contract_includes(self, client_id: str, keyword: str, month: str = DEFAULT_MONTH) -> str:
        """``oui`` / ``non`` — does the contract list this service (R12)?"""
        contract = self.report.contracts_in_force.get((client_id, month))
        if contract is None:
            return "non"
        needle = _words(keyword)
        included = (_words(item) for item in contract.fields.services_included)
        return "oui" if any(needle <= item for item in included) else "non"

    def exclusion_containing(self, client_id: str, keyword: str, month: str = DEFAULT_MONTH) -> str:
        """The exclusion clause of the contract that matches ``keyword``."""
        contract = self.report.contracts_in_force.get((client_id, month))
        if contract is None:
            return ""
        needle = _words(keyword)
        return next((item for item in contract.fields.exclusions if needle <= _words(item)), "")

    def extra_hour_rate(self, client_id: str, month: str = DEFAULT_MONTH) -> Decimal:
        contract = self.report.contracts_in_force.get((client_id, month))
        return contract.fields.extra_hour_rate if contract else Decimal("0")

    def unvalidated_contracts(self) -> list[str]:
        """Clients whose contract never reached VALIDATED (R4)."""
        return sorted(
            {
                contract.client_id
                for contract in self.report.dataset.contracts
                if contract.status != ContractStatus.VALIDATED
            }
        )

    def estimate_clients(self) -> list[str]:
        """Clients with at least one month flagged ESTIMATE (coverage < 80 %)."""
        return sorted({row.client_id for row in self.report.margins if row.is_estimate})

    # -- renewals ----------------------------------------------------------
    def renewals(self) -> list[str]:
        """Contracts renewing within the 90-day horizon (EF-TDB-04)."""
        return sorted({entry.client_id for entry in self.report.renewals(self.today)})

    def falling_renewals(self) -> list[str]:
        """Renewals whose margin trend over six months is DOWN."""
        return sorted(
            {entry.client_id for entry in self.report.renewals(self.today) if entry.trend == "DOWN"}
        )
