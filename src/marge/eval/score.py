"""Accuracy measurement primitives (spec 13.3, R2/R3/R5/R11).

A :class:`Score` is the single shape every harness returns: the measured value,
the target it must beat, the verdict and the human-readable reasons. All
arithmetic is :class:`Decimal` — the model never computes a figure
(ENF-IA-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class Score:
    """One measured indicator: value, target, verdict, explanations."""

    value: Decimal
    target: Decimal
    passed: bool
    detail: list[str] = field(default_factory=list)

    @property
    def percent(self) -> Decimal:
        return (self.value * 100).quantize(Decimal("0.01"))

    @property
    def gap(self) -> Decimal:
        return (self.value - self.target).quantize(Decimal("0.0001"))

    def as_dict(self) -> dict:
        return {
            "value": str(self.value),
            "target": str(self.target),
            "passed": self.passed,
            "percent": str(self.percent),
            "detail": list(self.detail),
        }


def ratio(numerator: int, denominator: int) -> Decimal:
    """``numerator / denominator`` with four decimals, ``0`` when empty."""
    if denominator <= 0:
        return ZERO
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


def score_of(
    correct: int,
    total: int,
    target: Decimal,
    detail: list[str] | None = None,
    forced_failure: bool = False,
) -> Score:
    """Build a :class:`Score` from a hit count and a target ratio.

    ``forced_failure`` marks a hard rule that fails the measure whatever the
    ratio is — the R6 "never out of scope on clearly included work" rule.
    """
    value = ratio(correct, total)
    passed = value > target and not forced_failure
    lines = list(detail or [])
    lines.append(f"{correct}/{total} = {value * 100:.2f}% (target > {target * 100:.2f}%)")
    if forced_failure:
        lines.append("FAILED: a hard rule was violated")
    return Score(value=value, target=target, passed=passed, detail=lines)


def format_report(title: str, scores: dict[str, Score]) -> str:
    """Printable table of several scores (used by the harness and the CLI)."""
    lines = [title, "=" * len(title)]
    for name, score in scores.items():
        flag = "OK  " if score.passed else "KO  "
        lines.append(f"{flag}{name:<28} {score.percent:>7}%  target > {score.target * 100:.1f}%")
        lines.extend(f"      - {item}" for item in score.detail)
    return "\n".join(lines)
