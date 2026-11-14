"""The 20 reference questions of the agent, and how each one is answered (R11).

One catalogue, two uses: the generator writes it to
``questions/reference_questions.json`` with the expected answers, and the
harness re-answers it on the reloaded dataset to score the agent. Because both
go through :class:`~marge.eval.analyst.Analyst`, the measure verifies that the
dataset round-trips through the canonical interchange formats and that every
question is answerable from the files — not that a model guessed right.

The five families of spec 14.5 are all covered: margin ranking, month-over-month
change, out-of-scope hours by subject, a contract clause, and renewals within
90 days.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .agent_accuracy import Answer
from .analyst import Analyst, money, rate_text

DASHBOARD_MARGIN = "overview"
DASHBOARD_CLIENTS = "clients"
DASHBOARD_RENEWALS = "renewals"
DASHBOARD_CONTRACTS = "contracts"
DASHBOARD_UNBILLED = "unbilled"

TABLE = "table"
SCALAR = "scalar"
CLIENT = "client"
CLAUSE = "contract_clause"

PERIOD = "2026-10"
PREVIOUS = "2026-09"


@dataclass(frozen=True, slots=True)
class Question:
    """One reference question and the analyst call that answers it."""

    id: str
    text: str
    kind: str
    dashboard: str
    resolve: Callable[[Analyst], dict] = field(repr=False)
    period: str = ""


def _table(ids: list[str]) -> dict:
    return {"client_ids": ids, "period": PERIOD}


def _q01(analyst: Analyst) -> dict:
    return _table(analyst.below_threshold(PERIOD))


def _q02(analyst: Analyst) -> dict:
    return {"client_ids": analyst.loss_making()}


def _q03(analyst: Analyst) -> dict:
    return _table(analyst.ranking(PERIOD))


def _q04(analyst: Analyst) -> dict:
    return {"value": rate_text(analyst.rate("c-001", PERIOD))}


def _q05(analyst: Analyst) -> dict:
    return {"value": rate_text(analyst.rate("c-009", PERIOD))}


def _q06(analyst: Analyst) -> dict:
    return {"value": rate_text(analyst.delta("c-001", PREVIOUS, PERIOD))}


def _q07(analyst: Analyst) -> dict:
    return {"client_ids": [analyst.biggest_drop(PREVIOUS, PERIOD)]}


def _q08(analyst: Analyst) -> dict:
    return {"value": money(analyst.out_of_scope_hours("c-002"))}


def _q09(analyst: Analyst) -> dict:
    return {"value": money(analyst.out_of_scope_hours("c-006"))}


def _q10(analyst: Analyst) -> dict:
    return {"value": money(analyst.out_of_scope_hours("c-008"))}


def _q11(analyst: Analyst) -> dict:
    return {"value": analyst.top_out_of_scope_category("c-002")}


def _q12(analyst: Analyst) -> dict:
    category = analyst.top_out_of_scope_category("c-002")
    return {"value": money(analyst.out_of_scope_hours_for("c-002", category))}


def _q13(analyst: Analyst) -> dict:
    return {"value": analyst.contract_includes("c-003", "base de données")}


def _q14(analyst: Analyst) -> dict:
    return {"value": analyst.exclusion_containing("c-002", "développements applicatifs")}


def _q15(analyst: Analyst) -> dict:
    return _table(analyst.renewals())


def _q16(analyst: Analyst) -> dict:
    return _table(analyst.falling_renewals())


def _q17(analyst: Analyst) -> dict:
    return {"client_ids": analyst.unvalidated_contracts()}


def _q18(analyst: Analyst) -> dict:
    return {"client_ids": analyst.estimate_clients()}


def _q19(analyst: Analyst) -> dict:
    return {"value": money(analyst.unassigned_hours(PERIOD))}


def _q20(analyst: Analyst) -> dict:
    return {"value": money(analyst.extra_hour_rate("c-004", PERIOD))}


QUESTIONS: tuple[Question, ...] = (
    Question(
        "q01",
        "Quels clients sont sous 20 % de marge en octobre 2026 ?",
        TABLE,
        DASHBOARD_MARGIN,
        _q01,
        PERIOD,
    ),
    Question(
        "q02",
        "Quels clients ont eu au moins un mois à marge négative ?",
        TABLE,
        DASHBOARD_MARGIN,
        _q02,
    ),
    Question(
        "q03",
        "Classement des clients par taux de marge en octobre 2026, du meilleur au moins bon",
        TABLE,
        DASHBOARD_MARGIN,
        _q03,
        PERIOD,
    ),
    Question(
        "q04",
        "Quel est le taux de marge du client Calder Logistics en octobre 2026 ?",
        SCALAR,
        DASHBOARD_MARGIN,
        _q04,
    ),
    Question(
        "q05",
        "Quel est le taux de marge du client Blanchard Chimie en octobre 2026 ?",
        SCALAR,
        DASHBOARD_MARGIN,
        _q05,
    ),
    Question(
        "q06",
        "Variation du taux de marge de Calder Logistics entre septembre et octobre 2026 ?",
        SCALAR,
        DASHBOARD_MARGIN,
        _q06,
    ),
    Question(
        "q07",
        "Quel client a la plus forte baisse de taux de marge en octobre 2026 ?",
        CLIENT,
        DASHBOARD_MARGIN,
        _q07,
    ),
    Question(
        "q08",
        "Combien d'heures hors périmètre avons-nous faites pour Leroy Logistique sur six mois ?",
        SCALAR,
        DASHBOARD_UNBILLED,
        _q08,
    ),
    Question(
        "q09",
        "Combien d'heures hors périmètre avons-nous faites pour Girard BTP sur six mois ?",
        SCALAR,
        DASHBOARD_UNBILLED,
        _q09,
    ),
    Question(
        "q10",
        "Combien d'heures hors périmètre avons-nous faites pour Fontaine Média sur six mois ?",
        SCALAR,
        DASHBOARD_UNBILLED,
        _q10,
    ),
    Question(
        "q11",
        "Sur quel sujet portent les heures hors périmètre de Leroy Logistique ?",
        SCALAR,
        DASHBOARD_UNBILLED,
        _q11,
    ),
    Question(
        "q12",
        "Combien d'heures hors périmètre Leroy Logistique a-t-il consommées sur ce sujet ?",
        SCALAR,
        DASHBOARD_UNBILLED,
        _q12,
    ),
    Question(
        "q13",
        "Le contrat de Martin Santé inclut-il les mises à jour de version de base de données ?",
        CLAUSE,
        DASHBOARD_CONTRACTS,
        _q13,
    ),
    Question(
        "q14",
        "Quelle clause du contrat de Leroy Logistique exclut les développements applicatifs ?",
        CLAUSE,
        DASHBOARD_CONTRACTS,
        _q14,
    ),
    Question(
        "q15", "Quels contrats se renouvellent dans les 90 jours ?", TABLE, DASHBOARD_RENEWALS, _q15, PERIOD
    ),
    Question(
        "q16",
        "Quels contrats se renouvellent dans les 90 jours avec une marge en baisse ?",
        TABLE,
        DASHBOARD_RENEWALS,
        _q16,
        PERIOD,
    ),
    Question(
        "q17",
        "Quel client a un contrat non validé par le contrôleur de gestion ?",
        CLIENT,
        DASHBOARD_CONTRACTS,
        _q17,
    ),
    Question(
        "q18",
        "Quels clients ont un mois marqué comme estimation (couverture sous 80 %) ?",
        TABLE,
        DASHBOARD_MARGIN,
        _q18,
    ),
    Question(
        "q19",
        "Combien d'heures n'ont pas pu être rattachées à un client en octobre 2026 ?",
        SCALAR,
        DASHBOARD_UNBILLED,
        _q19,
    ),
    Question(
        "q20",
        "Quel est le tarif horaire hors forfait du contrat de Marchand Distribution ?",
        SCALAR,
        DASHBOARD_CONTRACTS,
        _q20,
    ),
)


def resolve(question: Question, analyst: Analyst) -> dict:
    """Run one question through the analyst."""
    return question.resolve(analyst)


def build_reference(analyst: Analyst) -> list[dict]:
    """``questions/reference_questions.json`` — the catalogue with its answers."""
    rows: list[dict] = []
    for question in QUESTIONS:
        resolved = resolve(question, analyst)
        row: dict = {
            "id": question.id,
            "question": question.text,
            "expected_kind": question.kind,
            "dashboard": question.dashboard,
        }
        if resolved.get("client_ids") is not None:
            row["expected_client_ids"] = list(resolved["client_ids"])
        if question.period:
            row["expected_period"] = question.period
        if resolved.get("value") is not None:
            row["expected_value"] = str(resolved["value"])
        rows.append(row)
    return rows


def answer_all(analyst: Analyst) -> list[Answer]:
    """The agent's answers, in the shape the harness scores (R11)."""
    answers: list[Answer] = []
    for question in QUESTIONS:
        resolved = resolve(question, analyst)
        answers.append(
            Answer(
                question_id=question.id,
                kind=question.kind,
                client_ids=tuple(resolved.get("client_ids") or ()),
                period=question.period,
                value=str(resolved.get("value", "")),
                dashboard=question.dashboard,
            )
        )
    return answers
