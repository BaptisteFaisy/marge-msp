"""Generator orchestrator: writes every file of ``data/generated/`` (spec 19.1).

Run it with::

    PYTHONPATH=src python3 data/generator/build.py

It produces the whole fake MSP: clients, aliases, contracts (PDF + text +
expected values), six months of interventions, the labelled subset, AWS costs,
FX, invoices, rates, tooling, penalties, the 20 reference questions and a
manifest with the seed and the counts. Deterministic: fixed seed, no wall-clock
value, byte-identical output on every run.

``data/generated/`` is gitignored: the dataset is a build artefact, the
generator is the source.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python3 data/generator/build.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "generator"

from marge.eval.analyst import Analyst
from marge.eval.dataset import load
from marge.eval.question_set import QUESTIONS, build_reference
from marge.eval.report import build_report

from . import billing, contracts, references, tickets
from .common import (
    GENERATED_AT,
    MONTHS,
    SEED,
    TODAY,
    write_csv,
    write_json,
    write_jsonl,
)
from .profile_data import CLIENTS, CONTRACTS

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = ROOT / "data" / "generated"


def _checksums(out: Path) -> dict[str, str]:
    """SHA-256 of every generated file, so a drift is visible in the diff."""
    digests: dict[str, str] = {}
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            digests[path.relative_to(out).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def _write_contracts(out: Path) -> None:
    expected: dict[str, dict] = {}
    for spec in CONTRACTS:
        contracts.write_contract_documents(spec, out / "contracts")
        expected[spec.key] = contracts.contract_fields(spec)
    write_json(out / "expected" / "contract_fields.json", expected)


def _write_tickets(out: Path, dataset: tickets.TicketDataset) -> None:
    write_csv(out / "interventions.csv", tickets.COLUMNS, tickets.csv_rows(dataset))
    write_jsonl(out / "labels" / "interventions.jsonl", dataset.labels)


def _write_billing(out: Path, export: billing.BillingExport) -> None:
    write_csv(out / "aws_costs.csv", billing.COLUMNS, export.cost_rows)
    write_csv(out / "fx.csv", billing.FX_COLUMNS, export.fx_rows)


def _write_references(out: Path, tables: references.ReferenceTables) -> None:
    write_json(out / "clients.json", tables.clients)
    write_json(out / "aliases.json", tables.aliases)
    write_csv(out / "rates.csv", references.RATE_COLUMNS, tables.rates)
    write_csv(out / "tooling.csv", references.TOOLING_COLUMNS, tables.tooling)
    write_csv(out / "invoices.csv", references.INVOICE_COLUMNS, tables.invoices)
    write_csv(out / "penalties.csv", references.PENALTY_COLUMNS, tables.penalties)


def _manifest(out: Path, dataset: tickets.TicketDataset) -> dict:
    return {
        "seed": SEED,
        "today": TODAY.isoformat(),
        "clients": len(CLIENTS),
        "months": len(MONTHS),
        "first_month": MONTHS[0],
        "last_month": MONTHS[-1],
        "interventions": len(dataset.rows),
        "interventions_by_month": tickets.month_counts(dataset),
        "unassigned_interventions": dataset.unassigned,
        "total_hours": str(dataset.total_hours),
        "contracts": len({spec.contract_id for spec in CONTRACTS}),
        "contract_versions": len(CONTRACTS),
        "labelled_interventions": len(dataset.labels),
        "reference_questions": len(QUESTIONS),
        "generated_at": GENERATED_AT,
        "files": _checksums(out),
    }


def generate(out: Path = DEFAULT_OUT) -> dict:
    """Write the whole dataset under ``out`` and return its manifest."""
    out.mkdir(parents=True, exist_ok=True)
    _write_contracts(out)
    dataset = tickets.generate(CLIENTS)
    _write_tickets(out, dataset)
    _write_billing(out, billing.build(CLIENTS))
    _write_references(out, references.build(CLIENTS))

    loaded = load(out)
    report = build_report(loaded)
    write_json(out / "questions" / "reference_questions.json", build_reference(Analyst(report)))

    manifest = _manifest(out, dataset)
    write_json(out / "manifest.json", manifest)
    return manifest


def main() -> int:
    manifest = generate()
    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
