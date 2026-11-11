"""Shared helpers of the fake MSP generator (spec 19.1).

Everything here is deterministic: the seed is fixed and no wall-clock value is
read. Amounts are plain decimals written with a ``.`` separator (canonical
interchange format), while the generated *prose* uses French formatting.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from marge.eval.analyst import DEMO_TODAY

SEED = 20261111
"""Fixed seed: the whole dataset is reproducible byte for byte."""

TODAY = DEMO_TODAY
"""The day the demo runs (spec 19.1). Never read from the clock."""

MONTHS: tuple[str, ...] = ("2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10")
"""The six generated months, in order."""

GENERATED_AT = "2026-11-11T00:00:00Z"

_CENT = Decimal("0.01")
_HUNDREDTH = Decimal("0.01")

_FRENCH_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def money(value: object) -> Decimal:
    """Round an amount to cents (HALF_UP)."""
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def hours(value: object) -> Decimal:
    """Round a duration to hundredths of an hour."""
    return Decimal(str(value)).quantize(_HUNDREDTH, rounding=ROUND_HALF_UP)


def month_of(day: date) -> str:
    """``2026-05-17`` -> ``2026-05``."""
    return f"{day.year:04d}-{day.month:02d}"


def month_first(month: str) -> date:
    year, index = month.split("-")
    return date(int(year), int(index), 1)


def month_last(month: str) -> date:
    first = month_first(month)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def month_days(month: str) -> list[date]:
    """Every calendar day of ``month``."""
    first, last = month_first(month), month_last(month)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def business_days(month: str) -> list[date]:
    """Monday-to-Friday days of ``month`` (tickets land on working days)."""
    return [d for d in month_days(month) if d.weekday() < 5]


def french_date(day: date) -> str:
    """``2026-05-01`` -> ``1er mai 2026`` (French contract style)."""
    label = _FRENCH_MONTHS[day.month - 1]
    head = "1er" if day.day == 1 else str(day.day)
    return f"{head} {label} {day.year}"


def french_money(value: object, currency: str = "EUR") -> str:
    """``4000`` -> ``4 000,00 EUR`` (thin space thousands separator)."""
    text = f"{money(value):,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} {currency}"


def french_hours(value: object) -> str:
    """``2.5`` -> ``2,5 heures``."""
    return f"{hours(value):.2f}".replace(".", ",") + " heures"


def decimal_text(value: object) -> str:
    """Canonical CSV form: ``4000.00``."""
    return f"{Decimal(str(value)):.2f}"


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    """Write a UTF-8 CSV with a header, ``\\n`` line endings and no quoting noise."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(["" if cell is None else str(cell) for cell in row])


def write_json(path: Path, payload: object) -> None:
    """Write indented UTF-8 JSON, deterministic key order preserved."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    """Write one compact JSON object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
