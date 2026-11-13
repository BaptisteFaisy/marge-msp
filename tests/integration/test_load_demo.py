"""``marge load-demo``: the deployed load, replayed offline on SQLite.

The command that fills the demonstration environment is exercised here on the
generated dataset: it must leave the three human gates open (client matching,
contract clauses, out-of-scope work) and compute every margin with the code.
"""

from __future__ import annotations

from pathlib import Path

from marge.commands.demo import run_pipeline
from marge.domain import Month
from marge.ingest import SourceFiles
from marge.store import SqliteStore


def test_load_demo_leaves_the_three_gates_open(tmp_path: Path, dataset_root: Path) -> None:
    files = SourceFiles.of(dataset_root)
    store = SqliteStore(tmp_path / "marge.sqlite3")
    try:
        counts = run_pipeline(
            store,
            files,
            [Month.parse("2026-10")],
            approve_matches=False,
            read_contracts=True,
            keep_unvalidated={"ctr-010"},
        )
        assert counts["clients"] == 12
        assert counts["matches"] == 49
        assert counts["contracts_extracted"] == 13
        assert counts["contracts_validated"] == 12

        # Gate 1 — the client matches wait for the controller.
        assert all(match.status.value == "PENDING" for match in store.list_matches())

        # Gate 2 — one contract waits for the controller (R4).
        unvalidated = [c for c in store.list_contracts() if c.status.value != "VALIDATED"]
        assert [c.contract_id for c in unvalidated] == ["ctr-010"]

        # Gate 3 — the out-of-scope work waits for the account manager.
        queued = [c for c in store.list_classifications(status="PENDING") if c.needs_human_validation]
        assert queued

        # The margins are computed by the code, not by a model.
        rows = {r.client_id: r for r in store.list_margin_months(month=Month.parse("2026-10"))}
        assert len(rows) == 12
        assert rows["c-010"].state.value == "INCOMPLETE"
        assert rows["c-004"].margin < 0
        assert rows["c-009"].margin < 0
    finally:
        store.close()


def test_load_demo_is_replayable(tmp_path: Path, dataset_root: Path) -> None:
    """Running it twice leaves the same rows: every write is on a natural key."""
    files = SourceFiles.of(dataset_root)
    store = SqliteStore(tmp_path / "marge.sqlite3")
    try:
        first = run_pipeline(
            store, files, [Month.parse("2026-10")], read_contracts=True, keep_unvalidated={"ctr-010"}
        )
        second = run_pipeline(
            store, files, [Month.parse("2026-10")], read_contracts=True, keep_unvalidated={"ctr-010"}
        )
        assert first["contracts_extracted"] == second["contracts_extracted"]
        assert len(store.list_clients()) == 12
        assert len(store.list_matches()) == 49
        assert len(store.list_margin_months(month=Month.parse("2026-10"))) == 12
    finally:
        store.close()
