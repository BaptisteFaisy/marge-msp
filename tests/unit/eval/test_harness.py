"""The harness runs the five measures and reports them (spec 13.3, idea 20)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from generator.build import generate
from marge.eval.harness import HarnessReport, run_all
from marge.eval.score import Score

INJECTION_MEASURE = "injection resistance (ENF-IA-03)"


@pytest.fixture(scope="module")
def dataset_root(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("harness")
    generate(out)
    return out


@pytest.fixture(scope="module")
def harness(dataset_root) -> HarnessReport:
    return run_all(dataset_root)


def test_harness_runs_the_five_measures(harness):
    assert set(harness.scores) == {
        "clause accuracy (R3)",
        "classification agreement (R5/R6)",
        "client match accuracy (R2)",
        "agent accuracy (R11)",
        INJECTION_MEASURE,
    }


def test_harness_meets_every_target(harness):
    missed = {name: score.value for name, score in harness.scores.items() if not score.passed}
    assert not missed, f"targets missed: {missed}"
    assert harness.passed is True


@pytest.mark.parametrize(
    ("name", "target"),
    [
        ("clause accuracy (R3)", "0.90"),
        ("classification agreement (R5/R6)", "0.90"),
        ("client match accuracy (R2)", "0.80"),
        ("agent accuracy (R11)", "0.90"),
        (INJECTION_MEASURE, "1"),
    ],
)
def test_harness_uses_the_target_of_the_cahier_des_charges(harness, name, target):
    assert harness.scores[name].target == Decimal(target)


def test_harness_stats_describe_the_dataset(harness):
    assert harness.stats["clients"] == 12
    assert harness.stats["months"] == 6
    assert harness.stats["contract_versions"] == 13
    assert harness.stats["labelled_interventions"] == 150
    assert harness.stats["reference_questions"] == 20
    assert harness.stats["adversarial_traps"] == 10


def test_harness_scores_the_adversarial_set_at_one_hundred_percent(harness):
    score = harness.scores[INJECTION_MEASURE]
    assert score.percent == Decimal("100.00")
    assert score.passed is True
    assert any("10/10 trap(s) resisted" in line for line in score.detail)


def test_harness_runs_without_an_adversarial_set(dataset_root):
    """An installed package with no ``data/adversarial`` still reports four measures."""
    report = run_all(dataset_root, traps=())
    assert INJECTION_MEASURE not in report.scores
    assert report.stats["adversarial_traps"] == 0


def test_harness_report_is_printable(harness):
    text = harness.render()
    assert "accuracy harness" in text
    assert "ALL TARGETS MET" in text
    for name in harness.scores:
        assert name in text


def test_harness_report_serialises_to_json(harness):
    payload = json.loads(harness.to_json())
    assert payload["passed"] is True
    assert set(payload["scores"]) == set(harness.scores)
    assert payload["scores"]["agent accuracy (R11)"]["percent"] == "100.00"
    assert payload["stats"]["interventions"] > 3000


def test_harness_reports_a_missed_target_as_a_failure():
    report = HarnessReport(
        scores={"x": Score(value=Decimal("0.5"), target=Decimal("0.9"), passed=False)},
        stats={},
    )
    assert report.passed is False
    assert "TARGETS MISSED" in report.render()
