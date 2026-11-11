"""``marge demo`` — the whole journey, offline, in one command (spec 8, 19).

Steps: generate the fictional MSP, load the three sources, propose the client
matches, read and validate the contracts, classify the work, compute the
margins, print the review and exercise the MCP tools.

The human validations are simulated on purpose (``--auto-validate``): the real
path is the validation portal, this is the demo path described in
docs/TEST-INSTRUCTIONS.md.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from ..domain import ContractStatus, DecisionStatus, Month, SourceKind


def _approve_matches(store) -> int:
    """Demo shortcut: the controller approves every proposal."""
    from ..domain import AuditEntry

    approved = 0
    for match in store.list_matches(pending_only=True):
        match.status = DecisionStatus.APPROVED
        match.decided_by = "controller-01"
        match.reason = "demo: approved without review"
        approved += 1
    store.save_matches(store.list_matches())
    store.append(AuditEntry.now("matches", "all", "approve", "controller-01", "demo shortcut"))
    return approved


def _read_contracts(store, files, resolver) -> int:
    """Extract every contract text and validate it (demo shortcut)."""
    from ..contracts import extract_fields, validate_contract
    from ..domain import Contract, ContractFields

    directory = files.root / "contracts"
    if not directory.exists():
        return 0
    validated = 0
    for text_path in sorted(directory.glob("*.txt")):
        stem = text_path.stem
        contract_id, _, version = stem.partition("-v")
        fields = extract_fields(text_path.read_bytes(), stem)
        client_id = resolver.resolve(SourceKind.CONTRACT, contract_id) or ""
        contract = Contract(
            contract_id=contract_id,
            client_id=client_id,
            version=int(version or 1),
            fields=fields if fields else ContractFields(),
            status=ContractStatus.EXTRACTED,
            document_key=f"contracts/{stem}.pdf",
            effective_from=fields.start_date,
        )
        try:
            store.save_contract(validate_contract(contract, "controller-01", "demo validation"))
            validated += 1
        except ValueError:
            store.save_contract(contract)
    return validated


def demo(args: argparse.Namespace) -> int:
    """Run the full offline demo and print the key figures."""
    from ..ingest import SourceFiles, load_month, load_reference_data
    from ..match import MappingResolver
    from ..pipeline import run_monthly, run_nightly
    from ..store import open_store

    root = Path(args.data)
    if not (root / "clients.json").exists():
        from data.generator.build import build_dataset

        print(f"no dataset in {root}: generating one…")
        build_dataset(root, seed=args.seed)

    db = args.db or str(Path(tempfile.mkdtemp()) / "marge-demo.sqlite3")
    store = open_store(db)
    files = SourceFiles.of(root)

    counts = load_reference_data(store, files)
    print(f"reference: {counts}")

    aliases = _aliases(files)
    resolver = MappingResolver(aliases, store.list_matches())
    if args.auto_validate:
        approved = _approve_matches(store)
        resolver = MappingResolver(aliases, store.list_matches())
        print(f"matches approved (demo): {approved}")
        contracts = _read_contracts(store, files, resolver)
        print(f"contracts validated (demo): {contracts}")

    month = Month.parse(args.month) if args.month else Month.parse(_latest_month(root))
    for report in load_month(store, files, month):
        print(f"load {report.source}: {report.rows} row(s), {report.unattributed_hours} h unattributed")

    nightly = run_nightly(store, store.load(), month=month, classifier=_classifier(store))
    queued = nightly.queued_for_validation
    print(f"nightly {nightly.month}: {nightly.classified} classified, {queued} to validate")
    _print_margins(store, month)

    if args.review:
        report = run_monthly(store, store.load(), month)
        print()
        print(report.review_text)

    _mcp_self_test(store)
    print(f"\ndatabase: {db}")
    print(f"portal:   python3 -m marge.cli serve --db {db}")
    return 0


def _aliases(files) -> list:
    from ..ingest.loaders import load_aliases

    return load_aliases(files.aliases)


def _classifier(store):
    from ..classify import LocalRuleModel
    from ..classify.memory import DecisionMemory
    from ..classify.service import classify

    memory = DecisionMemory(store)
    model = LocalRuleModel()

    def run(intervention, contract):
        return classify(intervention, contract, model, store.load(), memory=memory)

    return run


def _latest_month(root: Path) -> str:
    import json

    manifest = root / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text(encoding="utf-8")).get("last_month", "2026-10")
    return "2026-10"


def _print_margins(store, month: Month) -> None:
    rows = sorted(store.list_margin_months(month=month), key=lambda r: r.margin_rate)
    print(f"\n{'client':<10}{'revenue':>12}{'costs':>12}{'margin':>12}{'rate':>8}  state")
    for row in rows:
        rate = f"{(row.margin_rate * 100).quantize(__import__('decimal').Decimal('0.1'))}%"
        print(
            f"{row.client_id:<10}{row.revenue.total:>12}{row.costs.total:>12}"
            f"{row.margin:>12}{rate:>8}  {row.state.value}"
        )


def _mcp_self_test(store) -> None:
    from ..domain import ActorRole
    from ..mcp import McpContext, handle_request

    ctx = McpContext(store=store, role=ActorRole.CONTROLLER)
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, ctx)
    tools = [tool["name"] for tool in response["result"]["tools"]]
    print(f"\nMCP tools available: {', '.join(tools)}")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", default="data/generated", help="dataset directory")
    parser.add_argument("--db", default="", help="sqlite file (default: temporary)")
    parser.add_argument("--month", default="", help="YYYY-MM (default: latest in the manifest)")
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--review", action="store_true", help="also print the monthly review")
    parser.add_argument(
        "--auto-validate",
        action="store_true",
        help="simulate the human validations (demo only, the real path is the portal)",
    )


demo.configure = configure  # type: ignore[attr-defined]

COMMANDS = {"demo": demo}
