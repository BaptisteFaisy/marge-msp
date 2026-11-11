"""Contract clause accuracy (spec 13.3, R3): > 90 % of fields read right.

The measure compares the fields extracted from the twelve generated contracts
with the hand-written ground truth of ``expected/contract_fields.json``. The
"source passage" requirement (EF-CTR-02) is a product feature; this harness
scores the values and lists the missed fields per contract version.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..domain import Contract
from .fields import ANNEX_B_FIELDS, mismatched_fields
from .score import Score, score_of

TARGET = Decimal("0.90")


def contract_key(contract: Contract) -> str:
    """``ctr-004-v1`` — the key used by ``contract_fields.json``."""
    return f"{contract.contract_id}-v{contract.version}"


def clause_accuracy(extracted: Sequence[Contract], expected: Sequence[dict]) -> Score:
    """Share of Annex B fields whose extracted value equals the expected one."""
    truth = {
        f"{item['contract_id']}-v{item['version']}": item
        for item in expected
        if item.get("contract_id") and item.get("version")
    }
    detail: list[str] = []
    correct = 0
    total = 0
    for contract in extracted:
        key = contract_key(contract)
        reference = truth.get(key)
        total += len(ANNEX_B_FIELDS)
        if reference is None:
            detail.append(f"{key}: no expected values")
            continue
        missed = mismatched_fields(contract.fields, reference)
        correct += len(ANNEX_B_FIELDS) - len(missed)
        if missed:
            detail.append(f"{key}: wrong {', '.join(missed)}")
    missing = sorted(set(truth) - {contract_key(contract) for contract in extracted})
    if missing:
        detail.append(f"not extracted: {', '.join(missing)}")
    detail.insert(0, f"{len(extracted)} version(s) scored, {len(ANNEX_B_FIELDS)} fields each")
    return score_of(correct, total, TARGET, detail)
