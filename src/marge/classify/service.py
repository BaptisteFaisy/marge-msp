"""The classification step itself (spec 13.2, EF-CLS-01..05).

Three rules carry the whole design:

1. prudence: a doubtful case is ``UNCERTAIN``, never ``OUT_OF_SCOPE``;
2. the 15 minute floor: short out-of-scope work is counted but not queued;
3. memory: a human decision on a category is reused for that contract.
"""

from __future__ import annotations

from ..domain import (
    Classification,
    Contract,
    DecisionStatus,
    Intervention,
    Settings,
    WorkClass,
)
from .memory import DecisionMemory
from .output import InvalidModelOutput, parse_model_output
from .prompt import OUTPUT_SCHEMA, build_prompt


class ClassifierModel:
    """Anything that can turn a prompt into an Annex C JSON answer."""

    def complete(self, prompt: str, schema: dict) -> str:  # pragma: no cover - interface
        raise NotImplementedError


def _needs_validation(work_class: WorkClass, hours, settings: Settings) -> bool:
    """EF-CLS-03: out-of-scope above the floor, and every uncertain case.

    The 15 minute floor only spares the account manager from a flood of tiny
    out-of-scope items (spec 13.2); a doubtful case is always worth a look.
    """
    if work_class == WorkClass.UNCERTAIN:
        return True
    if work_class == WorkClass.OUT_OF_SCOPE:
        return hours >= settings.min_hours_for_validation
    return False


def _uncertain(intervention: Intervention, contract: Contract, reason: str) -> Classification:
    return Classification(
        intervention_id=intervention.intervention_id,
        client_id=contract.client_id,
        contract_version=contract.version,
        work_class=WorkClass.UNCERTAIN,
        confidence=0,
        cited_clause="",
        reason=reason,
        billable_hours=intervention.hours_spent,
        needs_human_validation=True,
        status=DecisionStatus.PENDING,
    )


def classify(
    intervention: Intervention,
    contract: Contract,
    model: ClassifierModel | None,
    settings: Settings,
    memory: DecisionMemory | None = None,
) -> Classification:
    """Classify one intervention against one contract."""
    if model is None:
        return _uncertain(intervention, contract, "no classifier available")

    prompt = build_prompt(intervention, contract)
    try:
        raw = model.complete(prompt, OUTPUT_SCHEMA)
        classification = parse_model_output(raw, intervention, contract.version)
    except (InvalidModelOutput, ValueError, RuntimeError) as exc:
        return _uncertain(intervention, contract, f"unusable model output: {exc}")

    classification.client_id = contract.client_id
    classification.model_id = getattr(model, "model_id", "")

    if classification.confidence < settings.classification_confidence_threshold:
        classification.work_class = WorkClass.UNCERTAIN
        classification.reason = (
            f"confidence {classification.confidence} below "
            f"{settings.classification_confidence_threshold}: {classification.reason}"
        )

    if memory is not None:
        reused = memory.apply(classification, contract.contract_id, intervention.category)
        if reused is not None:
            return reused

    classification.needs_human_validation = _needs_validation(
        classification.work_class, intervention.hours_spent, settings
    )
    classification.status = DecisionStatus.PENDING
    return classification


def classify_batch(
    interventions,
    contract_for,
    model: ClassifierModel | None,
    settings: Settings,
    memory: DecisionMemory | None = None,
) -> list[Classification]:
    """Classify a batch; ``contract_for`` maps an intervention to its contract."""
    results: list[Classification] = []
    for intervention in interventions:
        contract = contract_for(intervention)
        if contract is None:
            continue
        results.append(classify(intervention, contract, model, settings, memory))
    return results
