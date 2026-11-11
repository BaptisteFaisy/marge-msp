"""Agent answer accuracy (spec 13.3, R11): > 90 % right on 20 questions.

Each reference question declares the shape of a correct answer (kind, client
ids, period, dashboard and, when it is a single figure, the value). An answer
is right only when every declared element matches: a table that lists the
wrong clients is wrong even if the sentence around it is convincing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .fields import normalise_amount, normalise_text
from .score import Score, score_of

TARGET = Decimal("0.90")


@dataclass(frozen=True, slots=True)
class Answer:
    """What the agent replied to one reference question."""

    question_id: str
    kind: str
    client_ids: tuple[str, ...] = ()
    period: str = ""
    value: str = ""
    dashboard: str = ""
    text: str = ""


def _ids(value: object) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(sorted(str(item) for item in value))


def _value_matches(expected: str, found: str) -> bool:
    if expected == "":
        return True
    if expected.replace(".", "", 1).isdigit():
        return normalise_amount(expected) == normalise_amount(found)
    return normalise_text(expected) == normalise_text(found)


def _mismatches(answer: Answer, reference: dict) -> list[str]:
    problems: list[str] = []
    if answer.kind != reference["expected_kind"]:
        problems.append(f"kind {answer.kind} != {reference['expected_kind']}")
    if _ids(answer.client_ids) != _ids(reference.get("expected_client_ids")):
        found = list(_ids(answer.client_ids))
        wanted = list(_ids(reference.get("expected_client_ids")))
        problems.append(f"clients {found} != {wanted}")
    if reference.get("expected_period") and answer.period != reference["expected_period"]:
        problems.append(f"period {answer.period} != {reference['expected_period']}")
    if reference.get("dashboard") and answer.dashboard != reference["dashboard"]:
        problems.append(f"dashboard {answer.dashboard} != {reference['dashboard']}")
    if not _value_matches(str(reference.get("expected_value", "")), answer.value):
        problems.append(f"value {answer.value!r} != {reference.get('expected_value')!r}")
    return problems


def agent_accuracy(answers: Sequence[Answer], references: Sequence[dict]) -> Score:
    """Share of reference questions answered exactly right (R11)."""
    by_id = {answer.question_id: answer for answer in answers}
    correct = 0
    detail: list[str] = []
    for reference in references:
        answer = by_id.get(reference["id"])
        if answer is None:
            detail.append(f"{reference['id']}: no answer")
            continue
        problems = _mismatches(answer, reference)
        if problems:
            detail.append(f"{reference['id']}: {'; '.join(problems)}")
        else:
            correct += 1
    detail.insert(0, f"{len(references)} reference question(s), {len(answers)} answered")
    return score_of(correct, len(references), TARGET, detail)
