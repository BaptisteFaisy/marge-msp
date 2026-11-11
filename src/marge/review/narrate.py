"""Narrating the review without ever computing a figure (spec 14.4, ENF-IA-01).

The scheduled flow (Quick Flows) writes the commentary around the figures.
This module is the same step outside Quick: the prompt embeds the numbers, the
model may only rephrase them, and the result is checked — if a figure of the
answer is not in the input, the deterministic text is returned instead.
"""

from __future__ import annotations

import re

from ..domain import Settings
from .aggregates import ReviewInputs
from .template import render_review

NARRATION_INSTRUCTION = (
    "You are the analyst of an MSP. Rewrite the monthly profitability review "
    "below in three short paragraphs, in French, for the executive committee.\n"
    "HARD RULES:\n"
    "- Use ONLY the figures present in the review text. Never compute, round or "
    "invent a number.\n"
    "- Keep the client names and the amounts exactly as written.\n"
    "- Mention the data coverage when it is below 100 %.\n"
)

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[str]:
    return {match.replace(",", ".") for match in NUMBER_RE.findall(text)}


def _allowed(inputs: ReviewInputs, settings: Settings) -> set[str]:
    """Every figure the model is allowed to write: those of the deterministic text."""
    return _numbers(render_review(inputs, settings))


def unknown_figures(answer: str, allowed: set[str]) -> list[str]:
    """Figures present in the answer but absent from the input (should be none)."""
    return sorted(_numbers(answer) - allowed)


def narrate_review(
    inputs: ReviewInputs,
    settings: Settings,
    model=None,
) -> str:
    """Return the narrated review, or the deterministic text when narration fails."""
    baseline = render_review(inputs, settings)
    if model is None:
        return baseline
    prompt = f"{NARRATION_INSTRUCTION}\n---\n{baseline}\n---"
    try:
        answer = model.complete(prompt, {"type": "string"})
    except (RuntimeError, ValueError):
        return baseline
    if not isinstance(answer, str) or len(answer.strip()) < 40:
        return baseline
    if unknown_figures(answer, _allowed(inputs, settings)):
        return baseline
    return answer.strip()


def review_with_figures(inputs: ReviewInputs, settings: Settings, model=None) -> dict:
    """Both texts plus the figures, so the caller can compare with the dashboards."""
    return {
        "deterministic": render_review(inputs, settings),
        "narrated": narrate_review(inputs, settings, model),
        "figures": {
            "total_margin": str(inputs.total_margin),
            "total_margin_rate": str(inputs.total_margin_rate),
            "coverage_percent": str(inputs.coverage_percent),
            "unbilled_hours": str(inputs.unbilled_hours),
            "unbilled_value": str(inputs.unbilled_value),
        },
    }
