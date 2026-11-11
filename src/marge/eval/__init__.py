"""Accuracy harnesses of the Marge demo (spec 13.3).

Four measures, one shape:

* :func:`clause_accuracy` — Annex B fields read right on the twelve contracts (R3);
* :func:`classification_agreement` — agreement with the 150 labels, and the
  hard R6 rule (never "out of scope" on clearly included work);
* :func:`match_accuracy` — client identity matching (R2);
* :func:`agent_accuracy` — right answers on the 20 reference questions (R11).

``run_all`` executes the four of them on a generated dataset and returns a
report that is both printable and serialisable, so the demo, the tests and the
CLI all read the same numbers.
"""

from __future__ import annotations

from .agent_accuracy import Answer, agent_accuracy
from .classification_agreement import Label, classification_agreement
from .clause_accuracy import clause_accuracy
from .fields import ANNEX_B_FIELDS, normalise_text
from .match_accuracy import match_accuracy
from .score import Score, format_report, score_of

__all__ = [
    "ANNEX_B_FIELDS",
    "Answer",
    "Label",
    "Score",
    "agent_accuracy",
    "classification_agreement",
    "clause_accuracy",
    "format_report",
    "match_accuracy",
    "normalise_text",
    "score_of",
]
