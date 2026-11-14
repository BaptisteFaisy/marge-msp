"""Client match accuracy (R2) and the matcher that proposes the matches."""

from __future__ import annotations

from decimal import Decimal

import pytest

from marge.domain import ClientMatch, DecisionStatus, SourceKind
from marge.eval.local_matcher import best_candidate, propose_matches
from marge.eval.match_accuracy import match_accuracy

CLIENTS = (
    ("c-001", "Calder Logistics"),
    ("c-002", "Leroy Logistique"),
    ("c-012", "Martin Formation"),
)


def _match(client_id: str, source_id: str, status: DecisionStatus = DecisionStatus.APPROVED):
    return ClientMatch(
        match_id=f"m-{source_id}",
        client_id=client_id,
        source=SourceKind.ITSM,
        source_id=source_id,
        confidence=Decimal("0.9"),
        status=status,
    )


def test_match_accuracy_is_one_when_every_proposal_is_right():
    score = match_accuracy([_match("c-001", "CALDER")], [("c-001", "CALDER")])
    assert score.value == Decimal("1")
    assert score.passed is True


def test_match_accuracy_tolerates_a_wrong_proposal_but_reports_it():
    matches = [_match("c-001", "CALDER"), _match("c-003", "MARTIN", DecisionStatus.PENDING)]
    truth = [("c-001", "CALDER"), ("c-012", "MARTIN")]
    score = match_accuracy(matches, truth)
    assert score.value == Decimal("0.5000")
    assert score.passed is False
    assert any("wrong proposal" in line for line in score.detail)


def test_match_accuracy_fails_when_a_validated_match_is_wrong():
    """R2 wants 100 % after validation: one wrong approved match fails the measure."""
    matches = [
        _match("c-001", "CALDER"),
        _match("c-002", "MARTIN"),
    ]
    truth = [("c-001", "CALDER"), ("c-012", "MARTIN")]
    score = match_accuracy(matches, truth)
    assert score.passed is False
    assert any("must be 100%" in line for line in score.detail)


def test_match_accuracy_fails_without_any_validated_match():
    score = match_accuracy([_match("c-001", "CALDER", DecisionStatus.PENDING)], [("c-001", "CALDER")])
    assert score.passed is False
    assert any("no validated match" in line for line in score.detail)


def test_best_candidate_finds_the_client_by_name():
    confidence, client_id = best_candidate("Calder Logistics", CLIENTS)
    assert client_id == "c-001"
    assert confidence == Decimal("1.0000")


def test_best_candidate_is_not_confident_on_an_unknown_name():
    confidence, client_id = best_candidate("Zorglub SAS", CLIENTS)
    assert client_id == ""
    assert confidence == Decimal("0")


def test_propose_matches_only_validates_above_the_threshold():
    aliases = [
        {"source": "itsm", "source_id": "CALDER", "name_variant": "Calder Logistics"},
        {"source": "itsm", "source_id": "MARTIN", "name_variant": "MARTIN (ancien code client)"},
    ]
    matches = propose_matches(aliases, CLIENTS)
    by_source = {match.source_id: match for match in matches}
    assert by_source["CALDER"].status == DecisionStatus.APPROVED
    assert by_source["MARTIN"].status == DecisionStatus.PENDING
    assert by_source["MARTIN"].confidence < Decimal("0.80")


def test_propose_matches_never_sees_the_expected_answer():
    """The matcher must work from the name only, never from the client id."""
    aliases = [{"source": "itsm", "source_id": "X1", "name_variant": "Leroy Logistique"}]
    matches = propose_matches(aliases, CLIENTS)
    assert matches[0].client_id == "c-002"


@pytest.mark.parametrize("variant", ["calder-logistics-prod", "CALDER LOGISTICS SAS"])
def test_best_candidate_ignores_legal_forms_and_slugs(variant):
    confidence, client_id = best_candidate(variant, CLIENTS)
    assert client_id == "c-001"
    assert confidence > Decimal("0.5")
