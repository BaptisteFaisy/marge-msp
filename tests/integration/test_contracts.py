"""The 12 contracts: PDF and text readable, every Annex B field present."""

from __future__ import annotations

import json

import pytest

ANNEX_B_LABELS = (
    "Client",
    "Date d'effet",
    "Date de fin",
    "Reconduction",
    "Préavis de résiliation",
    "Abonnement mensuel",
    "Heures incluses par mois",
    "Tarif horaire hors forfait",
    "Services inclus",
    "Exclusions",
    "Plages de service",
    "Engagements de niveau de service",
    "Pénalités",
    "Clause d'indexation",
    "Comptes et ressources couverts",
)

SECTION_TITLES = (
    "Parties au contrat",
    "Objet du contrat",
    "Durée et reconduction",
    "Comptes et ressources couverts",
    "Conditions financières",
    "Services inclus",
    "Exclusions",
    "Plages de service",
    "Engagements de niveau de service",
    "Pénalités",
    "Indexation",
    "Résiliation",
)


def _texts(dataset_root):
    return {
        path.stem: path.read_text(encoding="utf-8") for path in (dataset_root / "contracts").glob("*.txt")
    }


def _signature(text: str) -> tuple[str, ...]:
    """Section titles in the order they appear (headings, not the recap)."""
    positions: list[tuple[int, str]] = []
    for title in SECTION_TITLES:
        index = text.find(f"— {title}")
        if index < 0:
            index = text.find(f"{title}\n")
        if index >= 0:
            positions.append((index, title))
    return tuple(title for _index, title in sorted(positions))


@pytest.mark.integration
def test_contract_text_carries_every_annex_b_field(dataset_root):
    texts = _texts(dataset_root)
    assert len(texts) == 13
    for stem, text in texts.items():
        missing = [label for label in ANNEX_B_LABELS if label not in text]
        assert not missing, f"{stem} is missing {missing}"


@pytest.mark.integration
def test_contract_pdf_is_readable_by_a_pdf_reader(dataset_root):
    for path in sorted((dataset_root / "contracts").glob("*.pdf")):
        data = path.read_bytes()
        assert data.startswith(b"%PDF-1.4")
        assert data.rstrip().endswith(b"%%EOF")
        assert b"/Type /Catalog" in data
        assert b"/BaseFont /Helvetica" in data
        assert b"startxref" in data


@pytest.mark.integration
def test_contract_pdf_contains_the_contract_text(dataset_root):
    text = (dataset_root / "contracts" / "ctr-001-v1.txt").read_text(encoding="utf-8")
    pdf = (dataset_root / "contracts" / "ctr-001-v1.pdf").read_bytes()
    heading = next(line for line in text.splitlines() if line.startswith("Article 1"))
    assert heading.replace("—", "-").encode("latin-1") in pdf


@pytest.mark.integration
def test_contract_forms_are_visibly_different(dataset_root):
    texts = _texts(dataset_root)
    signatures = {stem: _signature(text) for stem, text in texts.items()}
    assert len(set(signatures.values())) >= 5, "the section order must vary"
    assert any("CLAUSE" in text for text in texts.values())
    assert any("TITRE" in text for text in texts.values())
    assert any("§" in text for text in texts.values())
    assert any("CONDITIONS PARTICULIÈRES" in text for text in texts.values())
    assert any("Madame, Monsieur," in text for text in texts.values())
    assert any(text.count("|") > 20 for text in texts.values()), "one contract uses a table layout"


@pytest.mark.integration
def test_contract_expected_fields_cover_every_version(dataset_root):
    expected = json.loads((dataset_root / "expected" / "contract_fields.json").read_text(encoding="utf-8"))
    assert len(expected) == 13
    assert set(expected) == {path.stem for path in (dataset_root / "contracts").glob("*.txt")}
    sample = expected["ctr-001-v1"]
    assert sample["customer_name"] == "DURAND INDUSTRIES SAS"
    assert sample["monthly_subscription"] == "5000.00"
    assert sample["extra_hour_rate"] == "110.00"
    assert sample["included_hours_per_month"] == "60.00"
    assert sample["covered_accounts_or_resources"] == 40
    assert sample["ambiguous_clause"] is False
    assert len(sample["services_included"]) >= 6
    assert len(sample["sla_commitments"]) == 3


@pytest.mark.integration
def test_one_contract_has_an_ambiguous_clause(dataset_root):
    expected = json.loads((dataset_root / "expected" / "contract_fields.json").read_text(encoding="utf-8"))
    ambiguous = [key for key, row in expected.items() if row["ambiguous_clause"]]
    assert ambiguous == ["ctr-007-v1"]
    assert any("raisonnable" in item for item in expected["ctr-007-v1"]["exclusions"])
