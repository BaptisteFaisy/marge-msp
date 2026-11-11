"""``marge model-compare``: offline by default, discoverable, exportable (idea 26)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from marge.cli import build_parser, discover_commands
from marge.commands import model_compare as command


@pytest.fixture(scope="module")
def dataset_root(tmp_path_factory) -> Path:
    import sys

    data = Path(__file__).resolve().parents[3] / "data"
    if str(data) not in sys.path:
        sys.path.insert(0, str(data))
    from generator.build import generate

    out = tmp_path_factory.mktemp("model-compare")
    generate(out)
    return out


def _args(**overrides) -> argparse.Namespace:
    values = {
        "data": "data/generated",
        "models": "local,scripted",
        "model_id": "eu.amazon.nova-lite-v1:0",
        "limit": 0,
        "bedrock": False,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_the_command_is_discovered() -> None:
    assert "model-compare" in discover_commands()


def test_the_command_exposes_a_configure_hook() -> None:
    assert callable(command.model_compare.configure)
    assert set(command.COMMANDS) == {"model-compare"}
    assert command.COMMANDS["model-compare"] is command.model_compare


def test_the_parser_accepts_every_flag() -> None:
    args = build_parser().parse_args(
        ["model-compare", "--data", "/tmp/x", "--models", "local", "--limit", "3", "--json"]
    )
    assert args.data == "/tmp/x"
    assert args.models == "local"
    assert args.limit == 3
    assert args.json is True


def test_the_offline_pair_is_the_default() -> None:
    models = command._build_models(_args(), cases=[])
    assert [getattr(model, "model_id", "") for model in models] == [
        "local-rule-model",
        "replayed-reference",
    ]


def test_an_unknown_model_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown model"):
        command._build_models(_args(models="local,gpt-magic"), cases=[])


def test_bedrock_needs_the_flag() -> None:
    with pytest.raises(ValueError, match="--bedrock"):
        command._build_models(_args(models="local,bedrock"), cases=[])


def test_the_flag_replaces_the_replayed_reference(monkeypatch) -> None:
    """``--bedrock`` swaps the offline reference for the real model."""
    calls: list[str] = []

    def fake_bedrock(model_id: str):
        calls.append(model_id)
        return argparse.Namespace(model_id=model_id)

    monkeypatch.setattr(command, "_bedrock_model", fake_bedrock)
    models = command._build_models(_args(bedrock=True, model_id="eu.test"), cases=[])
    assert calls == ["eu.test"]
    assert [model.model_id for model in models] == ["local-rule-model", "eu.test"]


def test_an_empty_model_list_is_refused() -> None:
    with pytest.raises(ValueError, match="no model"):
        command._build_models(_args(models=" , "), cases=[])


def test_the_command_prints_the_comparison_table(dataset_root, capsys) -> None:
    assert command.model_compare(_args(data=str(dataset_root), limit=6)) == 0
    out = capsys.readouterr().out
    assert "local-rule-model" in out
    assert "replayed-reference" in out
    assert "R6 false-out" in out
    assert "6 labelled intervention(s)" in out


def test_the_command_exports_valid_json(dataset_root, capsys) -> None:
    assert command.model_compare(_args(data=str(dataset_root), limit=4, json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [row["modelId"] for row in payload["models"]] == [
        "local-rule-model",
        "replayed-reference",
    ]
    assert payload["models"][0]["calls"] == 4


def test_the_command_fails_without_a_labelled_dataset(tmp_path, capsys) -> None:
    assert command.model_compare(_args(data=str(tmp_path))) == 1
    assert "no labelled intervention" in capsys.readouterr().out


def test_the_command_reports_a_bad_model_name(dataset_root, capsys) -> None:
    assert command.model_compare(_args(data=str(dataset_root), models="nope")) == 1
    assert "MODEL COMPARE FAILED" in capsys.readouterr().out
