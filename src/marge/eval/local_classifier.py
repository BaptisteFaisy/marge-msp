"""Deterministic local classifier (offline stand-in for Bedrock, spec 13.2).

It reads the contract scope text and the intervention text, and applies the
prudence rule: when the two texts disagree, or when the contract hedges, the
answer is UNCERTAIN — never OUT_OF_SCOPE (R6). The real pipeline calls Bedrock;
the CI workers have no credentials, so the harness runs this reader instead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from ..domain import (
    Classification,
    Contract,
    DecisionStatus,
    Intervention,
    Settings,
    WorkClass,
)
from .fields import normalise_text

OUT_KEYWORDS: tuple[str, ...] = (
    "developpement",
    "requete sql",
    "modification du code",
    "code du client",
    "formation",
    "achat de materiel",
    "migration applicative",
    "integration api",
    "audit de securite",
)
"""Vocabulary of the exclusion lists (spec 13.1 keeps them whole)."""

IN_KEYWORDS: tuple[str, ...] = (
    "supervision",
    "sauvegarde",
    "restauration",
    "patch",
    "mise a jour",
    "incident",
    "acces",
    "couts aws",
    "support",
    "redemarrage",
)

VAGUE_MARKERS: tuple[str, ...] = (
    "raisonnable",
    "substantielle",
    "notable",
    "significative",
    "selon l'ampleur",
    "au cas par cas",
)

STOPWORDS = frozenset(
    {
        "les",
        "des",
        "de",
        "du",
        "la",
        "le",
        "un",
        "une",
        "et",
        "dans",
        "dont",
        "pour",
        "sur",
        "au",
        "aux",
        "d",
        "l",
        "cadre",
        "intervention",
        "client",
    }
)


def _tokens(text: str) -> set[str]:
    """Significant words, plural stripped, stopwords removed."""
    words: set[str] = set()
    for word in normalise_text(text).replace("-", " ").split():
        word = word.strip(".,;:()«»\"'")
        if len(word) < 4 or word in STOPWORDS:
            continue
        words.add(word[:-1] if word.endswith("s") else word)
    return words


def _hits(text: str, keywords: Sequence[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def _vague_clause(contract: Contract) -> str | None:
    for exclusion in contract.fields.exclusions:
        if any(marker in normalise_text(exclusion) for marker in VAGUE_MARKERS):
            return exclusion
    return None


def _cited_clause(contract: Contract, keywords: Sequence[str], section: str) -> str:
    for item in (*contract.fields.exclusions, *contract.fields.services_included):
        if _hits(normalise_text(item), keywords):
            return f"{section} : « {item} »"
    return ""


def classify(
    intervention: Intervention,
    contract: Contract | None,
    settings: Settings | None = None,
) -> Classification:
    """Classify one intervention against the scope of its client's contract."""
    settings = settings or Settings()
    text = normalise_text(f"{intervention.category} {intervention.description}")
    out_hits = _hits(text, OUT_KEYWORDS)
    in_hits = _hits(text, IN_KEYWORDS)
    vague = _vague_clause(contract) if contract is not None else None
    vague_tokens = _tokens(vague) if vague else set()

    work_class, confidence, cited, reason = WorkClass.UNCERTAIN, Decimal("0.40"), "", ""
    if vague and vague_tokens & _tokens(text):
        work_class, confidence = WorkClass.UNCERTAIN, Decimal("0.45")
        cited = f"Exclusions ambiguës : « {vague} »"
        reason = "la clause d'exclusion ne permet pas de trancher (règle de prudence)"
    elif out_hits and not in_hits:
        work_class, confidence = WorkClass.OUT_OF_SCOPE, Decimal("0.88")
        cited = _cited_clause(contract, OUT_KEYWORDS, "Exclusions") if contract else ""
        reason = f"hors périmètre : {out_hits[0]}"
    elif in_hits and not out_hits:
        work_class, confidence = WorkClass.INCLUDED, Decimal("0.93")
        cited = _cited_clause(contract, IN_KEYWORDS, "Services inclus") if contract else ""
        reason = f"dans le périmètre : {in_hits[0]}"
    elif in_hits and out_hits:
        work_class, confidence = WorkClass.UNCERTAIN, Decimal("0.50")
        reason = "le texte mélange périmètre inclus et exclusion (règle de prudence)"
    else:
        reason = "aucun élément de périmètre reconnu (règle de prudence)"

    return Classification(
        intervention_id=intervention.intervention_id,
        client_id=intervention.client_id or "",
        contract_version=contract.version if contract else 0,
        work_class=work_class,
        confidence=confidence,
        cited_clause=cited,
        reason=reason,
        billable_hours=intervention.hours_spent,
        needs_human_validation=settings.needs_validation(
            intervention.hours_spent, work_class == WorkClass.OUT_OF_SCOPE
        ),
        model_id="local-rules-v1",
        status=DecisionStatus.PENDING,
    )


def classify_all(
    interventions: Sequence[Intervention],
    contracts: Mapping[str, Contract],
    settings: Settings | None = None,
) -> list[Classification]:
    """Classify a batch, using each intervention's client contract."""
    return [
        classify(intervention, contracts.get(intervention.client_id or ""), settings)
        for intervention in interventions
    ]
