"""Tracing every model call without touching the classification logic.

``logged_classifier`` decorates the ``(intervention, contract) -> Classification``
callable that ``marge.pipeline.nightly.classify_pending`` already takes, so the
log is written where the context is known: which intervention, which contract,
which client, which outcome. The classification code itself stays untouched —
one implementation of the rules, one place that measures them.

Token usage is read from the model when it reports it (``last_usage``), and
estimated from the text otherwise, always flagged as estimated.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from ..domain import Classification, Contract, Intervention, LlmCall
from ..store.base import Store
from .pricing import estimate_cost, estimate_tokens

Classifier = Callable[[Intervention, Contract], Classification]
InjectionScanner = Callable[[str], tuple[bool, tuple[str, ...]]]


def _usage_of(model: Any, prompt: str, answer: str) -> tuple[int, int, bool]:
    """Reported usage when available, estimated otherwise."""
    usage = getattr(model, "last_usage", None)
    if isinstance(usage, dict) and usage:
        input_tokens = int(usage.get("inputTokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("outputTokens") or usage.get("output_tokens") or 0)
        if input_tokens or output_tokens:
            return input_tokens, output_tokens, False
    return estimate_tokens(prompt), estimate_tokens(answer), True


def logged_classifier(
    classifier: Classifier,
    store: Store,
    *,
    purpose: str = "classify",
    model: Any = None,
    injection_scanner: InjectionScanner | None = None,
) -> Classifier:
    """Wrap a classifier so every call is recorded in the store."""

    def run(intervention: Intervention, contract: Contract) -> Classification:
        model_id = getattr(model, "model_id", "") or "unknown"
        started = time.monotonic()
        error = ""
        result: Classification | None = None
        try:
            result = classifier(intervention, contract)
            return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
            raise
        finally:
            _record(
                store=store,
                purpose=purpose,
                model_id=model_id,
                intervention=intervention,
                contract=contract,
                result=result,
                error=error,
                latency_ms=int((time.monotonic() - started) * 1000),
                model=model,
                injection_scanner=injection_scanner,
            )

    return run


def _record(
    *,
    store: Store,
    purpose: str,
    model_id: str,
    intervention: Intervention,
    contract: Contract,
    result: Classification | None,
    error: str,
    latency_ms: int,
    model: Any,
    injection_scanner: InjectionScanner | None,
) -> None:
    """Write one ``LlmCall``; a logging failure never breaks the run."""
    detected, patterns = _scan(intervention, injection_scanner)
    call = LlmCall(
        purpose=purpose,
        model_id=model_id,
        entity_kind="intervention",
        entity_id=intervention.intervention_id,
        client_id=contract.client_id or (intervention.client_id or ""),
        contract_id=contract.contract_id,
        outcome=result.work_class.value if result is not None else "",
        success=not error,
        error=error,
        latency_ms=latency_ms,
        injection_detected=detected,
        injection_patterns=patterns,
    )
    _fill_tokens(call, model, intervention, result)
    try:
        store.append_llm_call(call)
    except Exception as exc:
        print(f"llm log write failed: {type(exc).__name__}: {exc}")


def _fill_tokens(call: LlmCall, model: Any, intervention: Intervention, result: Any) -> None:
    prompt_size = len(intervention.description) + len(intervention.category)
    answer_size = len(result.reason) + len(result.cited_clause) if result is not None else 0
    usage = getattr(model, "last_usage", None)
    if isinstance(usage, dict) and usage:
        call.input_tokens = int(usage.get("inputTokens") or usage.get("input_tokens") or 0)
        call.output_tokens = int(usage.get("outputTokens") or usage.get("output_tokens") or 0)
        call.tokens_estimated = False
    else:
        call.input_tokens = estimate_tokens(" " * prompt_size)
        call.output_tokens = estimate_tokens(" " * answer_size)
        call.tokens_estimated = True
    call.cost_usd = estimate_cost(call.model_id, call.input_tokens, call.output_tokens)


def _scan(intervention: Intervention, scanner: InjectionScanner | None) -> tuple[bool, tuple[str, ...]]:
    if scanner is None:
        return (False, ())
    try:
        detected, patterns = scanner(intervention.description)
    except Exception:
        return (False, ())
    return (bool(detected), tuple(patterns))


def summarise(calls: list[LlmCall]) -> dict[str, Any]:
    """Aggregate a set of calls: counts, latency, tokens and estimated cost."""
    successful = [c for c in calls if c.success]
    latencies = sorted(c.latency_ms for c in successful)
    return {
        "calls": len(calls),
        "failures": len(calls) - len(successful),
        "injections_detected": sum(1 for c in calls if c.injection_detected),
        "tokens_estimated_share": _share(calls),
        "input_tokens": sum(c.input_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "cost_usd": str(sum((c.cost_usd for c in calls), Decimal("0"))),
        "latency_ms_median": latencies[len(latencies) // 2] if latencies else 0,
        "latency_ms_max": latencies[-1] if latencies else 0,
        "by_outcome": _by_outcome(calls),
        "by_model": _by_model(calls),
    }


def _share(calls: list[LlmCall]) -> str:
    if not calls:
        return "0"
    estimated = sum(1 for c in calls if c.tokens_estimated)
    return str((Decimal(estimated) / Decimal(len(calls))).quantize(Decimal("0.01")))


def _by_outcome(calls: list[LlmCall]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in calls:
        key = call.outcome or ("error" if not call.success else "none")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _by_model(calls: list[LlmCall]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for call in calls:
        entry = grouped.setdefault(call.model_id, {"calls": 0, "cost_usd": Decimal("0")})
        entry["calls"] += 1
        entry["cost_usd"] += call.cost_usd
    return {key: {"calls": v["calls"], "cost_usd": str(v["cost_usd"])} for key, v in grouped.items()}
