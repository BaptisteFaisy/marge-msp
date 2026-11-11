"""Comparing models on the labelled set (idea 26)."""

from __future__ import annotations

import itertools
import json
from decimal import Decimal
from pathlib import Path

import pytest
from tests.fakes.fake_model import FailingModel, ScriptedModel

from generator.build import generate
from marge.classify.bedrock import LocalRuleModel
from marge.eval.model_comparison import (
    ReplayedModel,
    build_cases,
    compare_models,
    prompt_key,
    record_reference,
    render_table,
    to_json,
)


@pytest.fixture(scope="module")
def dataset_root(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("comparison")
    generate(out)
    return out


@pytest.fixture(scope="module")
def cases(dataset_root) -> list:
    return build_cases(dataset_root)


def test_build_cases_returns_the_labelled_interventions(cases):
    assert len(cases) > 100
    assert all(case.label.intervention_id == case.intervention.intervention_id for case in cases)
    assert [case.intervention.intervention_id for case in cases] == sorted(
        case.intervention.intervention_id for case in cases
    )


def test_build_cases_respects_the_limit(dataset_root):
    assert len(build_cases(dataset_root, limit=5)) == 5


def test_every_case_prompt_fences_the_ticket(cases):
    for case in cases[:5]:
        assert "<ticket_data>" in case.prompt
        assert "<contract_scope>" in case.prompt


def test_prompt_key_is_stable_and_discriminating():
    assert prompt_key("same prompt") == prompt_key("same prompt")
    assert prompt_key("same prompt") != prompt_key("another prompt")
    assert len(prompt_key("x")) == 16


def test_the_replayed_model_answers_from_the_recording(cases):
    recorded = record_reference(cases)
    model = ReplayedModel("replayed-reference", recorded)
    assert len(model) == len(cases)
    answer = model.complete(cases[0].prompt, {})
    assert json.loads(answer)["class"] in {"IN_SCOPE", "OUT_OF_SCOPE", "UNCERTAIN"}


def test_the_replayed_model_falls_back_to_its_default():
    model = ReplayedModel("empty", {}, default="{}")
    assert model.complete("unknown prompt", {}) == "{}"


def test_record_reference_covers_every_case(cases):
    assert len(record_reference(cases)) == len({prompt_key(case.prompt) for case in cases})


def test_compare_models_measures_every_indicator(cases):
    models = [LocalRuleModel(), ReplayedModel("replayed-reference", record_reference(cases))]
    stats = compare_models(models, cases)
    assert [item.model_id for item in stats] == ["local-rule-model", "replayed-reference"]
    for item in stats:
        assert item.calls == len(cases)
        assert item.failures == 0
        assert item.false_out_of_scope == 0
        assert item.agreement.target == Decimal("0.90")
        assert Decimal("0") <= item.abstention_rate <= Decimal("1")
        assert item.mean_latency_ms >= Decimal("0")


def test_the_replayed_reference_is_at_least_as_good_as_the_keyword_model(cases):
    stats = compare_models(
        [LocalRuleModel(), ReplayedModel("replayed-reference", record_reference(cases))], cases
    )
    assert stats[0].agreement.passed is True or stats[1].agreement.passed is True
    assert stats[1].agreement.value >= stats[0].agreement.value


def test_the_model_id_falls_back_to_the_class_name(cases):
    stats = compare_models([ScriptedModel(default='{"class": "UNCERTAIN", "confidence": 0.5}')], cases)
    assert stats[0].model_id == "ScriptedModel"


def test_latency_is_measured_with_the_injected_clock(cases):
    ticks = iter(itertools.count(0.0, 0.002))
    stats = compare_models([LocalRuleModel()], cases[:3], clock=lambda: next(ticks))
    assert stats[0].mean_latency_ms == Decimal("2.00")
    assert stats[0].calls == 3


def test_a_model_that_raises_is_counted_not_crashing(cases):
    stats = compare_models([FailingModel()], cases[:4])
    assert stats[0].failures == 4
    assert stats[0].calls == 4
    assert stats[0].agreement.value == Decimal("0")
    assert stats[0].mean_latency_ms == Decimal("0")


def test_a_model_that_returns_garbage_counts_a_failure(cases):
    stats = compare_models([ScriptedModel(default="not json at all")], cases[:4])
    assert stats[0].failures == 4
    assert stats[0].agreement.value == Decimal("0")


def test_render_table_lists_every_model(cases):
    stats = compare_models([LocalRuleModel()], cases[:5])
    table = render_table(stats)
    assert "local-rule-model" in table
    assert "agreement" in table
    assert "R6 false-out" in table
    assert "latency ms" in table


def test_to_json_is_valid_json(cases):
    payload = json.loads(to_json(compare_models([LocalRuleModel()], cases[:5])))
    assert payload["targets"] == {"agreement": "0.90", "false_out_of_scope": 0}
    row = payload["models"][0]
    assert set(row) == {
        "modelId",
        "agreement",
        "falseOutOfScope",
        "abstentionRate",
        "meanLatencyMs",
        "calls",
        "failures",
    }
    assert row["calls"] == 5


def test_stats_are_serialisable(cases):
    stats = compare_models([LocalRuleModel()], cases[:2])[0]
    assert stats.as_dict()["modelId"] == "local-rule-model"
    assert stats.agreement.passed in (True, False)
