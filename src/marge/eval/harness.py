"""The five accuracy measures of spec 13.3, run end to end on generated data.

``run_all`` loads a generated dataset, replays the pipeline with the offline
doubles (rule-based extractor, rule-based classifier, rule-based matcher) and
scores the indicators of the cahier des charges, plus the adversarial set of
idea 20:

===========================  ==========================================  =======
Measure                      Requirement                                 Target
===========================  ==========================================  =======
``clause_accuracy``          EF-CTR-01, R3 — Annex B fields read right   > 90 %
``classification_agreement`` EF-CLS-01, R5 + hard rule R6                > 90 %
``match_accuracy``           EF-REF-01, R2                                > 80 %
``agent_accuracy``           EF-AGT-01, R11 — 20 questions               > 90 %
``injection_resistance``     ENF-IA-03, idea 20 — 10 trap tickets          100 %
===========================  ==========================================  =======

The report is printable (``render``) and serialisable (``as_dict``), so the
demo, the tests and the CLI read the same numbers.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..classify.bedrock import LocalRuleModel
from .adversarial import TRAPS_PATH, Trap, injection_resistance, load_traps, run_traps
from .agent_accuracy import agent_accuracy
from .analyst import Analyst
from .classification_agreement import Label, classification_agreement
from .clause_accuracy import clause_accuracy
from .dataset import Dataset, load
from .local_classifier import classify
from .local_extractor import extract_contract
from .local_matcher import propose_matches
from .match_accuracy import match_accuracy
from .question_set import answer_all
from .report import MarginReport, build_report
from .score import Score, format_report

MATCH_SOURCES = ("itsm", "billing", "contract")
"""The three sources of R2 (the invoice feed is optional, EF-SRC-04)."""


@dataclass(slots=True)
class HarnessReport:
    """The four scores plus the dataset figures they were measured on."""

    scores: dict[str, Score] = field(default_factory=dict)
    stats: dict[str, object] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(score.passed for score in self.scores.values())

    def render(self) -> str:
        """Human-readable report, one block per measure."""
        blocks = [format_report("Marge — accuracy harness (spec 13.3)", self.scores)]
        blocks.append("Dataset")
        blocks.append("=" * len("Dataset"))
        blocks.extend(f"  {key}: {value}" for key, value in self.stats.items())
        verdict = "ALL TARGETS MET" if self.passed else "TARGETS MISSED"
        blocks.append(f"\n{verdict}")
        return "\n".join(blocks)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "scores": {name: score.as_dict() for name, score in self.scores.items()},
            "stats": self.stats,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2)


def _extracted_contracts(dataset: Dataset) -> list:
    """Re-read every ``.txt`` contract with the local extractor (R3)."""
    contracts = []
    for expected in dataset.expected_fields:
        key = f"{expected['contract_id']}-v{expected['version']}"
        path = dataset.root / "contracts" / f"{key}.txt"
        status = dataset.contracts[0].status.__class__(expected["status"])
        contract = extract_contract(path, expected["client_id"], status)
        contracts.append(contract)
    return contracts


def _predicted_classes(dataset: Dataset, report: MarginReport) -> list:
    """Classify the labelled interventions with the rule-based classifier (R5)."""
    labelled = {row["intervention_id"] for row in dataset.labels}
    predicted = []
    for item in dataset.interventions:
        if item.intervention_id not in labelled:
            continue
        contract = report.contracts_in_force.get(
            (item.client_id, f"{item.occurred_on.year:04d}-{item.occurred_on.month:02d}")
        )
        predicted.append(classify(item, contract))
    return predicted


def _match_inputs(dataset: Dataset) -> tuple[list[dict], list[tuple[str, str]]]:
    """Aliases without their answer, and the truth the matcher must find."""
    aliases = json.loads((dataset.root / "aliases.json").read_text(encoding="utf-8"))
    wanted = [row for row in aliases if row["source"] in MATCH_SOURCES]
    blind = [
        {"source": row["source"], "source_id": row["source_id"], "name_variant": row["name_variant"]}
        for row in wanted
    ]
    truth = [(row["client_id"], row["source_id"]) for row in wanted]
    return blind, truth


def _trap_set(traps: Sequence[Trap] | None) -> tuple[Trap, ...]:
    """The adversarial set to score: the caller's, else the one of the repo."""
    if traps is not None:
        return tuple(traps)
    return load_traps() if TRAPS_PATH.exists() else ()


def run_all(root: Path, traps: Sequence[Trap] | None = None) -> HarnessReport:
    """Run the measures of spec 13.3, plus idea 20, on the dataset under ``root``."""
    dataset = load(root)
    report = build_report(dataset)

    clauses = clause_accuracy(_extracted_contracts(dataset), dataset.expected_fields)
    labels = [Label.from_dict(row) for row in dataset.labels]
    agreement = classification_agreement(_predicted_classes(dataset, report), labels)
    blind, truth = _match_inputs(dataset)
    clients = [(client.client_id, client.name) for client in dataset.clients]
    matches = propose_matches(blind, clients)
    identity = match_accuracy(matches, truth)
    questions = agent_accuracy(answer_all(Analyst(report)), dataset.questions)

    trap_set = _trap_set(traps)
    scores = {
        "clause accuracy (R3)": clauses,
        "classification agreement (R5/R6)": agreement,
        "client match accuracy (R2)": identity,
        "agent accuracy (R11)": questions,
    }
    if trap_set:
        # The traps go through the real classification pipeline, guard included:
        # what is measured is the defence that ships, not a stand-in.
        scores["injection resistance (ENF-IA-03)"] = injection_resistance(
            run_traps(trap_set, LocalRuleModel()), trap_set
        )
    stats = {
        "clients": len(dataset.clients),
        "months": len(report.months),
        "interventions": len(dataset.interventions),
        "contract_versions": len(dataset.expected_fields),
        "labelled_interventions": len(dataset.labels),
        "reference_questions": len(dataset.questions),
        "proposed_matches": len(matches),
        "adversarial_traps": len(trap_set),
    }
    return HarnessReport(scores=scores, stats=stats)


def render_file(root: Path) -> str:
    """Printable report of ``root`` — what the demo shows and the CLI prints."""
    return run_all(root).render()
