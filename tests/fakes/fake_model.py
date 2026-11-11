"""Deterministic model doubles (no network, no credentials).

``ScriptedModel`` replays canned completions; ``KeywordClassifierModel``
returns an Annex C payload driven by keywords in the prompt, which is enough to
test the classification pipeline, the prudence rule and the decision memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

OUT_OF_SCOPE_KEYWORDS = (
    "developpement",
    "développement",
    "code",
    "requete sql",
    "requête sql",
    "application",
    "formation",
    "achat materiel",
    "achat matériel",
)

INCLUDED_KEYWORDS = (
    "supervision",
    "monitoring",
    "sauvegarde",
    "backup",
    "patch",
    "mise a jour systeme",
    "mise à jour système",
    "incident",
    "redemarrage",
    "redémarrage",
)


@dataclass(slots=True)
class ScriptedModel:
    """Returns the queued completions, in order, then the ``default``."""

    responses: list[str] = field(default_factory=list)
    default: str = "{}"
    calls: list[str] = field(default_factory=list)

    def complete(self, prompt: str, schema: dict) -> str:
        self.calls.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        return self.default


class KeywordClassifierModel:
    """Annex C classification driven by the text of the intervention."""

    def __init__(self, out_of_scope_confidence: float = 0.88, uncertain_confidence: float = 0.42) -> None:
        self.out_of_scope_confidence = out_of_scope_confidence
        self.uncertain_confidence = uncertain_confidence
        self.calls: list[str] = []

    @staticmethod
    def _ticket(prompt: str) -> str:
        """Only the fenced ticket block: the contract scope is not the ticket."""
        return prompt.split("<ticket_data>")[-1].split("</ticket_data>")[0].lower()

    def complete(self, prompt: str, schema: dict) -> str:
        self.calls.append(prompt)
        lowered = self._ticket(prompt)
        work_class, confidence = "IN_SCOPE", 0.93
        if any(word in lowered for word in OUT_OF_SCOPE_KEYWORDS):
            work_class, confidence = "OUT_OF_SCOPE", self.out_of_scope_confidence
        elif not any(word in lowered for word in INCLUDED_KEYWORDS):
            work_class, confidence = "UNCERTAIN", self.uncertain_confidence
        return json.dumps(
            {
                "class": work_class,
                "confidence": confidence,
                "citedClause": "Article 3.2 — Exclusions",
                "reason": "keyword-based test double",
            }
        )


@dataclass(slots=True)
class FailingModel:
    """Always raises: used to test the retry / uncertain fallback paths."""

    error: Exception = field(default_factory=lambda: RuntimeError("model unavailable"))

    def complete(self, prompt: str, schema: dict) -> str:
        raise self.error
