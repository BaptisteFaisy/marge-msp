"""Agent accuracy (R11) over the 20 reference questions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from marge.eval.agent_accuracy import Answer, agent_accuracy

REFERENCE = [
    {
        "id": "q01",
        "question": "Quels clients sont sous 20 % de marge ?",
        "expected_kind": "table",
        "expected_client_ids": ["c-004", "c-009"],
        "expected_period": "2026-10",
        "dashboard": "overview",
    },
    {
        "id": "q02",
        "question": "Quel est le taux de marge du client Durand ?",
        "expected_kind": "scalar",
        "expected_value": "0.1940",
        "dashboard": "overview",
    },
    {
        "id": "q03",
        "question": "Quelle clause exclut les développements ?",
        "expected_kind": "contract_clause",
        "expected_value": "les développements applicatifs",
        "dashboard": "contracts",
    },
]


def _answer(**kwargs) -> Answer:
    defaults = {"question_id": "q01", "kind": "table"}
    defaults.update(kwargs)
    return Answer(**defaults)


def test_agent_accuracy_is_one_when_every_answer_matches():
    answers = [
        _answer(question_id="q01", client_ids=("c-009", "c-004"), period="2026-10", dashboard="overview"),
        _answer(question_id="q02", kind="scalar", value="0.194", dashboard="overview"),
        _answer(
            question_id="q03",
            kind="contract_clause",
            value="Les développements applicatifs",
            dashboard="contracts",
        ),
    ]
    score = agent_accuracy(answers, REFERENCE)
    assert score.value == Decimal("1")
    assert score.passed is True


def test_agent_accuracy_is_order_insensitive_on_client_ids():
    answers = [_answer(client_ids=("c-009", "c-004"), period="2026-10", dashboard="overview")]
    score = agent_accuracy(answers, REFERENCE[:1])
    assert score.value == Decimal("1")


def test_agent_accuracy_rejects_a_wrong_client_list():
    answers = [_answer(client_ids=("c-004",), period="2026-10", dashboard="overview")]
    score = agent_accuracy(answers, REFERENCE[:1])
    assert score.value == Decimal("0")
    assert "clients" in " ".join(score.detail)


def test_agent_accuracy_rejects_a_wrong_period():
    answers = [_answer(client_ids=("c-004", "c-009"), period="2026-09", dashboard="overview")]
    score = agent_accuracy(answers, REFERENCE[:1])
    assert score.value == Decimal("0")
    assert "period" in " ".join(score.detail)


def test_agent_accuracy_rejects_a_wrong_dashboard_link():
    answers = [_answer(client_ids=("c-004", "c-009"), period="2026-10", dashboard="clients")]
    score = agent_accuracy(answers, REFERENCE[:1])
    assert score.value == Decimal("0")
    assert "dashboard" in " ".join(score.detail)


def test_agent_accuracy_compares_amounts_as_decimals():
    answers = [_answer(question_id="q02", kind="scalar", value="0.194", dashboard="overview")]
    assert agent_accuracy(answers, REFERENCE[1:2]).passed is True
    wrong = [_answer(question_id="q02", kind="scalar", value="0.195", dashboard="overview")]
    assert agent_accuracy(wrong, REFERENCE[1:2]).passed is False


def test_agent_accuracy_compares_text_without_accents_or_case():
    answers = [
        _answer(
            question_id="q03",
            kind="contract_clause",
            value="les developpements applicatifs",
            dashboard="contracts",
        )
    ]
    assert agent_accuracy(answers, REFERENCE[2:]).passed is True


def test_agent_accuracy_counts_a_missing_answer_as_wrong():
    score = agent_accuracy([], REFERENCE)
    assert score.value == Decimal("0")
    assert sum("no answer" in line for line in score.detail) == 3


@pytest.mark.parametrize("wrong_kind", ["scalar", "client", "list"])
def test_agent_accuracy_rejects_an_answer_of_the_wrong_shape(wrong_kind):
    answers = [_answer(kind=wrong_kind, client_ids=("c-004", "c-009"), period="2026-10")]
    score = agent_accuracy(answers, REFERENCE[:1])
    assert score.value == Decimal("0")
    assert "kind" in " ".join(score.detail)
