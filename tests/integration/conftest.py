"""Shared fixtures of the integration tests (offline, deterministic).

The generated dataset is produced once per session into a temporary directory:
``data/generated/`` is gitignored, so the tests always start from the generator
— exactly what the demo does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

from generator.build import generate  # noqa: E402


@pytest.fixture(scope="session")
def dataset_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate the whole fake MSP once and return its directory."""
    out = tmp_path_factory.mktemp("generated")
    generate(out)
    return out


@pytest.fixture(scope="session")
def dataset(dataset_root: Path):
    """The dataset loaded through the canonical interchange formats."""
    from marge.eval.dataset import load

    return load(dataset_root)


@pytest.fixture(scope="session")
def report(dataset):
    """Every client-month margin of the generated dataset."""
    from marge.eval.report import build_report

    return build_report(dataset)
