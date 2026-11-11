"""The 20 reference questions of the agent (R11), written to ``data/generated/``.

The catalogue itself lives in :mod:`marge.eval.question_set`, next to the
harness that scores it, so the expected answers and the measured answers come
from one implementation. This module is the generator side: it runs the analyst
on the freshly generated dataset and writes
``questions/reference_questions.json``.
"""

from __future__ import annotations

from marge.eval.analyst import Analyst
from marge.eval.question_set import QUESTIONS, build_reference

from .common import write_json


def build(dataset, report) -> list[dict]:
    """Write the reference questions and return them."""
    rows = build_reference(Analyst(report))
    write_json(dataset.root / "questions" / "reference_questions.json", rows)
    return rows


def count() -> int:
    """How many questions the catalogue holds (must be 20, R11)."""
    return len(QUESTIONS)
