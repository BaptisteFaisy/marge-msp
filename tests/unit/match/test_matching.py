"""Client matching tests (EF-REF-01, spec 13.3)."""

from __future__ import annotations

from decimal import Decimal

from marge.domain import DecisionStatus, SourceKind
from marge.match import Alias, ClientName, MappingResolver, confidence_for, normalise_name
from marge.match.proposal import duplicate_ids, propose_matches

CLIENTS = [
    ClientName("c-001", "Durand Industries"),
    ClientName("c-002", "Leroy & Fils"),
    ClientName("c-003", "Martin Santé"),
]

ALIASES = [
    Alias("c-001", SourceKind.ITSM, "DURIND", "Durand Ind."),
    Alias("c-001", SourceKind.BILLING, "111122223333", "durand-industries-prod"),
    Alias("c-002", SourceKind.ITSM, "LERFILS", "Leroy et Fils"),
    Alias("c-003", SourceKind.ITSM, "MARSAN", "MARTIN SANTE SAS"),
]


def test_normalise_removes_accents_case_and_legal_form() -> None:
    assert normalise_name("MARTIN SANTE SAS") == "martin sante"
    assert normalise_name("Société Générale SA") == "societe generale"


def test_exact_name_has_full_confidence() -> None:
    assert confidence_for("Durand Industries", "durand industries") == Decimal("1.00")


def test_partial_name_is_still_proposed() -> None:
    assert confidence_for("Durand Ind.", "Durand Industries") >= Decimal("0.80")


def test_unrelated_names_have_low_confidence() -> None:
    assert confidence_for("Acme", "Zenith Partners") < Decimal("0.50")


def test_proposals_are_all_pending() -> None:
    proposals = propose_matches(ALIASES, CLIENTS)
    assert len(proposals) == 4
    assert all(p.status == DecisionStatus.PENDING for p in proposals)


def test_proposals_point_to_the_right_client() -> None:
    proposals = {p.source_id: p.client_id for p in propose_matches(ALIASES, CLIENTS)}
    assert proposals["DURIND"] == "c-001"
    assert proposals["LERFILS"] == "c-002"
    assert proposals["MARSAN"] == "c-003"


def test_duplicate_ids_are_flagged() -> None:
    proposals = propose_matches(ALIASES, CLIENTS)
    assert duplicate_ids(proposals) == {}


def test_resolver_only_trusts_approved_matches() -> None:
    proposals = propose_matches(ALIASES, CLIENTS)
    resolver = MappingResolver(ALIASES, [])
    assert resolver.approved_count == 0
    approved = [p for p in proposals if p.source_id == "DURIND"]
    approved[0].status = DecisionStatus.APPROVED
    resolver = MappingResolver(ALIASES, approved)
    assert resolver.approved_count == 1
    assert resolver.resolve(SourceKind.ITSM, "DURIND") == "c-001"


def test_resolver_records_unresolved_identifiers() -> None:
    resolver = MappingResolver(ALIASES, [])
    assert resolver.resolve(SourceKind.ITSM, "INCONNU") is None
    assert (SourceKind.ITSM, "INCONNU") in resolver.unresolved()
