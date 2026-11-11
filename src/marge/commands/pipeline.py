"""``marge nightly``, ``weekly`` and ``monthly`` — the scheduled runs (spec 8)."""

from __future__ import annotations

import argparse

from marge.domain import Month


def _store(path: str):
    from marge.api.deps import build_local_store

    return build_local_store(path)


def _classifier(store, settings):
    """Wire the real classifier (Bedrock) or fall back to the local rules."""
    from marge.classify.memory import DecisionMemory
    from marge.classify.service import classify

    memory = DecisionMemory(store)

    def run(intervention, contract):
        model = _model()
        return classify(intervention, contract, model, settings, memory=memory)

    return run


def _model():
    """Return the Bedrock model when available, else the deterministic local one."""
    from marge.classify.bedrock import BedrockClassifierModel

    try:
        return BedrockClassifierModel()
    except RuntimeError:
        from marge.classify.local_model import LocalRuleModel

        return LocalRuleModel()


def nightly(args: argparse.Namespace) -> int:
    """Classify the new work, recompute the margins, refresh the analytics tables."""
    from marge.pipeline import run_nightly

    store = _store(args.db)
    settings = store.load()
    month = Month.parse(args.month) if args.month else None
    report = run_nightly(store, settings, month=month, classifier=_classifier(store, settings))
    print(f"month            : {report.month}")
    print(f"classified       : {report.classified} (reused decisions: {report.reused_decisions})")
    print(f"queued for human : {report.queued_for_validation}")
    print(f"clients computed : {report.clients_recalculated}")
    print(f"coverage         : {report.coverage_percent}%")
    print(f"duration         : {report.duration_seconds}s")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    return 0


def weekly(args: argparse.Namespace) -> int:
    """Send each account manager the out-of-scope work waiting for a decision."""
    from marge.pipeline import run_weekly

    store = _store(args.db)
    report = run_weekly(store, store.load())
    print(f"generated on : {report.generated_on}")
    print(f"pending      : {report.pending_total} ({report.hours_total} h, {report.value_total})")
    for queue in report.queues:
        print(f"  {queue.account_manager_id}: {len(queue.intervention_ids)} item(s), {queue.hours} h")
    return 0


def monthly(args: argparse.Namespace) -> int:
    """Produce the monthly review text (Annex E) for one month."""
    from marge.pipeline import run_monthly

    store = _store(args.db)
    report = run_monthly(store, store.load(), Month.parse(args.month), recipients=tuple(args.to))
    print(report.review_text)
    return 0


def _add_db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default="marge.sqlite3")


def configure_nightly(parser: argparse.ArgumentParser) -> None:
    _add_db(parser)
    parser.add_argument("--month", default="", help="YYYY-MM (default: latest month with data)")


def configure_monthly(parser: argparse.ArgumentParser) -> None:
    _add_db(parser)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--to", action="append", default=[], help="recipient (repeatable)")


nightly.configure = configure_nightly  # type: ignore[attr-defined]
monthly.configure = configure_monthly  # type: ignore[attr-defined]
weekly.configure = _add_db  # type: ignore[attr-defined]

COMMANDS = {"nightly": nightly, "weekly": weekly, "monthly": monthly}
