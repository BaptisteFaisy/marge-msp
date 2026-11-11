"""Injection attempt detection and counting in untrusted text (ENF-IA-03).

The classification prompt already *defends*: it fences the ticket text and
neutralises any early fence close (:mod:`marge.classify.prompt`), and the
parser refuses an answer that tries to change the task
(:func:`marge.classify.output.parse_model_output`). What was missing is the
*measure* (idea 19): how many attempts reached the classifier, which patterns
they used, and what the text looked like.

This module is that measure. It scans an untrusted text — a ticket, a contract
passage, or a model answer — against a table of French and English attack
patterns and returns an :class:`InjectionReport`.

Design rules:

* the pattern table is **data**, not code: teach the guard a new attack by
  appending a ``(name, regex)`` pair to :data:`PATTERNS`;
* detection is **deterministic**: plain regular expressions on accent-folded
  lower-case text, no model, no randomness, so a test reproduces it exactly;
* accent folding is reused from :mod:`marge.match.normalise` instead of being
  rewritten here (one implementation per logic);
* :data:`ANSWER_PATTERNS` is the subset that means "this answer tries to
  hijack the task"; it is the single source of truth of the check the output
  parser performs, so the parser and the counter never disagree.

A detection is deliberately cheap to be wrong about: the guard of
:mod:`marge.classify.service` never turns an ``OUT_OF_SCOPE`` into anything
else and only ever lowers an ``IN_SCOPE`` to ``UNCERTAIN``, so a false positive
costs one human review, never a wrong figure (ENF-IA-01, ENF-IA-02).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ..match.normalise import strip_accents

MAX_SAMPLES = 3
SAMPLE_WINDOW = 90

HIJACK_VERBS = r"ignore|ignorez|ignorer|disregard|forget|oublie|oubliez|oublier"
ANSWER_TARGETS = r"instructions?|consignes?|directives?|regles?|rules|prompt"
CLASS_NAMES = r"in_scope|out_of_scope|uncertain|inclus|in scope"
FORCE_VERBS = r"reponds|repondez|repondre|answer|reply|dis|dites|say|return\w*|classe\w*|marque\w*"
FIGURE_VERBS = r"invente\w*|fabrique\w*|imagine\w*|indique|donne|calcule\w*|make up|invent\w*"
FIGURE_NOUNS = r"montant|chiffre|prix|facture\w*|somme|amount|figure|price|invoice|cout"
SCOPE_NOUNS = r"exclusions?|perimetre|scope"
CLASS_ASSIGN = r"\"?(?:class|classe)\"?\s*[:=]\s*\"?(?:in_scope|out_of_scope|uncertain)"
NEAR = r".{0,40}?"
CLOSE = r".{0,25}?"

_PATTERN_TABLE: tuple[tuple[str, str], ...] = (
    ("override-instructions", rf"\b(?:{HIJACK_VERBS}|nouvelles?|nouveaux?)\b{NEAR}\b(?:{ANSWER_TARGETS})\b"),
    ("previous-context", rf"\b(?:{HIJACK_VERBS})\b{CLOSE}\b(?:previous|above|prior|precedent\w*)\b"),
    ("role-hijack", r"\b(?:tu es|vous etes|t es|you are)\s+(?:maintenant|desormais|a present|now)\b"),
    ("role-impersonation", r"(?:^|[\s\"'>({/\\])(?:system|assistant|developer|admin|root)\s*:"),
    ("new-objective", r"\b(?:nouvel|nouvelle|new)\s+(?:objectif\w*|mission|but|goal|objective|tache)\b"),
    ("forced-class", rf"\b(?:{FORCE_VERBS}|consider\w*)\b{NEAR}\b(?:{CLASS_NAMES})\b"),
    ("exclusion-bypass", rf"\b(?:{HIJACK_VERBS}|sans|skip|bypass)\b{NEAR}\b(?:{SCOPE_NOUNS})\b"),
    ("invented-figure", rf"\b(?:{FIGURE_VERBS})\b{NEAR}\b(?:{FIGURE_NOUNS})\b"),
    ("fence-close", r"<\s*/\s*(?:ticket_data|contract_scope|system|instructions?)\s*>"),
    ("fence-open", r"<\s*(?:ticket_data|contract_scope)\s*>"),
    ("payload-override", rf"\{{[^{{}}]{{0,120}}?{CLASS_ASSIGN}"),
    ("repetition-flood", r"\b(?:repete\w*|repeat)\b.{0,40}?\b(?:ce texte|le texte|this text|sans fin)\b"),
)

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(regex, re.IGNORECASE)) for name, regex in _PATTERN_TABLE
)
"""Every known attack pattern, matched against normalised text."""

ANSWER_PATTERN_NAMES: frozenset[str] = frozenset(
    {
        "override-instructions",
        "previous-context",
        "role-hijack",
        "role-impersonation",
        "new-objective",
        "forced-class",
        "exclusion-bypass",
    }
)
"""The subset that means "this model answer tries to change the task"."""

ANSWER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, regex) for name, regex in PATTERNS if name in ANSWER_PATTERN_NAMES
)


@dataclass(frozen=True, slots=True)
class InjectionReport:
    """The counter of idea 19: how many attempts, which patterns, which samples."""

    count: int = 0
    patterns_found: tuple[str, ...] = ()
    samples: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return self.count > 0

    def marker(self) -> str:
        """One-line trace written into ``Classification.reason`` (ENF-IA-03)."""
        if not self.detected:
            return ""
        return f"injection-guard: {self.count} attempt(s) [{', '.join(self.patterns_found)}]"

    def as_dict(self) -> dict:
        return {
            "count": self.count,
            "patternsFound": list(self.patterns_found),
            "samples": list(self.samples),
        }


def normalise(text: str) -> str:
    """Accent-folded, lower-cased, whitespace-collapsed text to match against."""
    return " ".join(strip_accents(text or "").lower().split())


def _sample(text: str, start: int, end: int) -> str:
    """A short deterministic excerpt around one match."""
    left = max(0, start - SAMPLE_WINDOW // 3)
    right = min(len(text), end + SAMPLE_WINDOW)
    excerpt = " ".join(text[left:right].split())
    return excerpt[:SAMPLE_WINDOW]


def scan(text: str, patterns: Sequence[tuple[str, re.Pattern[str]]] = PATTERNS) -> InjectionReport:
    """Count every injection attempt of ``text`` (idea 19).

    Deterministic and side-effect free: the same text always yields the same
    report, which is what makes the adversarial set of idea 20 testable.
    """
    haystack = normalise(text)
    if not haystack:
        return InjectionReport()
    count = 0
    names: list[str] = []
    samples: list[str] = []
    for name, regex in patterns:
        for match in regex.finditer(haystack):
            count += 1
            if name not in names:
                names.append(name)
            if len(samples) < MAX_SAMPLES:
                samples.append(f"{name}: {_sample(haystack, match.start(), match.end())}")
    return InjectionReport(count=count, patterns_found=tuple(names), samples=tuple(samples))


def scan_answer(text: str) -> InjectionReport:
    """Scan a model answer with the hijack subset only.

    An answer quoting a contract clause that contains a figure is legitimate
    (the parser must not reject it), so the money-shaped patterns of
    :data:`PATTERNS` are deliberately *not* part of this check.
    """
    return scan(text, ANSWER_PATTERNS)


def scan_intervention(intervention) -> InjectionReport:
    """Scan the untrusted fields of one intervention (never the contract)."""
    return scan(
        "\n".join(
            (
                str(getattr(intervention, "category", "") or ""),
                str(getattr(intervention, "ticket_type", "") or ""),
                str(getattr(intervention, "description", "") or ""),
            )
        )
    )


def scan_texts(*texts: str) -> InjectionReport:
    """Scan several untrusted passages at once (a contract, a ticket, both)."""
    return scan("\n".join(text for text in texts if text))


def pattern_names() -> tuple[str, ...]:
    """Names of every known attack pattern, in table order."""
    return tuple(name for name, _regex in PATTERNS)
