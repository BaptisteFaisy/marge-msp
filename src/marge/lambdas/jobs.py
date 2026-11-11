"""Scheduled job handlers: nightly, weekly, monthly (spec 8.2, 8.3, 8.4).

Invoked by the Step Functions state machine of the ``MargeOrchestration``
stack. They only wire the pipeline to the deployed store: every figure comes
from ``marge.calc`` through ``marge.pipeline``.
"""

from __future__ import annotations

import os
from typing import Any

from .handlers import _classifier, _store


def _month_or_latest(event: dict[str, Any]):
    from ..domain import Month
    from ..pipeline.assemble import months_present

    if event.get("month"):
        return Month.parse(event["month"])
    present = months_present(_store())
    return present[-1] if present else None


def nightly_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Classify the new work, recompute the margins, refresh the tables."""
    from ..pipeline import run_nightly

    store = _store()
    month = _month_or_latest(event)
    report = run_nightly(store, store.load(), month=month, classifier=_classifier())
    return {
        "month": str(report.month),
        "classified": report.classified,
        "queued_for_validation": report.queued_for_validation,
        "clients_recalculated": report.clients_recalculated,
        "coverage_percent": str(report.coverage_percent),
        "duration_seconds": str(report.duration_seconds),
        "warnings": report.warnings,
    }


def publish_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Write the five analytical tables into the curated bucket (Annex A)."""
    from ..domain import Month
    from ..publish import S3Writer, publish

    bucket = event.get("bucket") or os.environ["MARGE_CURATED_BUCKET"]
    months = [Month.parse(event["month"])] if event.get("month") else None
    report = publish(
        _store(),
        S3Writer(bucket),
        months=months,
        prefix=event.get("prefix", "analytical"),
        database=event.get("database", "marge"),
        bucket=bucket,
    )
    return {"bucket": bucket, "rows": report.rows, "files": report.files}


def weekly_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Build the per-account-manager validation queues (spec 8.3)."""
    from ..pipeline import run_weekly

    report = run_weekly(_store(), _store().load())
    return {
        "generated_on": report.generated_on,
        "pending_total": report.pending_total,
        "hours_total": str(report.hours_total),
        "value_total": str(report.value_total),
        "queues": [
            {
                "account_manager_id": queue.account_manager_id,
                "items": len(queue.intervention_ids),
                "hours": str(queue.hours),
            }
            for queue in report.queues
        ],
    }


def monthly_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Produce the monthly review and store it (Annex E, EF-REV-01)."""
    from ..domain import Month
    from ..pipeline import run_monthly
    from ..review import LocalSink
    from ..review import publish as publish_review

    month = _month_or_latest(event) or Month.parse(os.environ.get("MARGE_MONTH", "2026-10"))
    recipients = tuple(event.get("recipients") or [])
    report = run_monthly(_store(), _store().load(), month, recipients=recipients)
    sink = LocalSink()
    delivery = publish_review(month, report.review_text, recipients, sink=sink)
    return {
        "month": str(month),
        "stored_at": delivery["stored_at"],
        "figures": report.figures,
        "characters": len(report.review_text),
    }
