"""ENF-PERF-01: the full nightly recalculation fits 30 minutes for 200 clients.

The default dataset ships 12 clients; the specification targets 200. Instead of
touching the generator, the test *replicates* the 12 shipped profiles into 200
distinct clients (fresh identifiers, same shape and volumes) and hands them to
the regular ``data.generator.build.generate`` — every artefact (tickets,
contracts, billing, references) comes from the generator's own functions.

The store is then filled through the exact demo path (reference data, approved
matches, validated contracts, one loaded month) and ``run_nightly`` is timed
with ``time.monotonic``. A second, smaller run (50 clients) proves the cost
grows linearly: the time per client must not more than double from 50 to 200.

Both tests are ``slow``: the CI runs ``-m "not slow"`` and stays fast.
Run them with::

    PYTHONPATH=src:. pytest tests/perf -q -m slow -s
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # make `data.generator` importable, as the demo does
    sys.path.insert(0, str(ROOT))

from data.generator import build  # noqa: E402
from data.generator.profile_data import CLIENTS  # noqa: E402
from data.generator.profiles import ClientProfile, ContractSpec  # noqa: E402

from marge.commands.demo import _approve_matches, _classifier, _read_contracts  # noqa: E402
from marge.domain import Month  # noqa: E402
from marge.ingest import SourceFiles, load_month, load_reference_data  # noqa: E402
from marge.ingest.loaders import load_aliases  # noqa: E402
from marge.match import MappingResolver  # noqa: E402
from marge.pipeline import NightlyReport, run_nightly  # noqa: E402
from marge.store import SqliteStore, open_store  # noqa: E402

TARGET_MONTH = "2026-10"
"""The latest of the six generated months: the one a nightly run recomputes."""

SMALL_CLIENTS = 50
LARGE_CLIENTS = 200
BUDGET_SECONDS = 1800.0
"""ENF-PERF-01: 30 minutes for the full nightly recalculation."""

MAX_PER_CLIENT_GROWTH = 2.0
"""Per-client time may not more than double from 50 to 200 clients.

A quadratic blow-up would multiply it by ~4 and fail; ~1.x is linear growth
within measurement noise.
"""


def _replica_contract(spec: ContractSpec, client_id: str, index: int) -> ContractSpec:
    """Re-key one contract spec for replica ``index`` of a client."""
    return replace(
        spec,
        contract_id=f"{spec.contract_id}-r{index:02d}",
        client_id=client_id,
        customer_name=f"{spec.customer_name} R{index}",
    )


def _replica(profile: ClientProfile, index: int) -> ClientProfile:
    """A copy of ``profile`` with fresh identifiers: a new client, same shape.

    Every field used as a key somewhere downstream (client id, the three source
    aliases, the contract ids and customer names) gets a unique ``-r<index>``
    suffix, so the matcher, the resolver and the store see ``index``-many
    distinct clients with the volumes of the original profile.
    """
    client_id = f"{profile.client_id}-r{index:02d}"
    amendment = profile.amendment
    return replace(
        profile,
        client_id=client_id,
        name=f"{profile.name} R{index}",
        itsm_alias=f"{profile.itsm_alias}-R{index:02d}",
        billing_alias=f"{profile.billing_alias}-r{index:02d}",
        invoice_alias=f"{profile.invoice_alias}-r{index:02d}",
        contract=_replica_contract(profile.contract, client_id, index),
        amendment=_replica_contract(amendment, client_id, index) if amendment else None,
    )


def _scaled_profiles(count: int) -> tuple[ClientProfile, ...]:
    """The 12 generated profiles, replicated round-robin to ``count`` clients."""
    profiles: list[ClientProfile] = []
    position = 0
    while len(profiles) < count:
        base = CLIENTS[position % len(CLIENTS)]
        index = position // len(CLIENTS)
        profiles.append(base if index == 0 else _replica(base, index))
        position += 1
    return tuple(profiles)


def _generate_dataset(destination: Path, count: int) -> None:
    """Write the whole fake MSP for ``count`` clients with the regular generator.

    ``build.generate`` reads its client list from module constants; the test
    swaps them for the scaled ones and restores them afterwards — the generator
    code itself is never modified and never duplicated.
    """
    profiles = _scaled_profiles(count)
    clients, contracts = build.CLIENTS, build.CONTRACTS
    try:
        build.CLIENTS = profiles
        build.CONTRACTS = tuple(spec for profile in profiles for spec in profile.contracts)
        build.generate(destination)
    finally:
        build.CLIENTS, build.CONTRACTS = clients, contracts


def _load_dataset(store: SqliteStore, destination: Path, month: Month) -> None:
    """Fill the store from the dataset, following the demo path exactly."""
    files = SourceFiles.of(destination)
    load_reference_data(store, files)
    _approve_matches(store)
    resolver = MappingResolver(load_aliases(files.aliases), store.list_matches())
    _read_contracts(store, files, resolver)
    load_month(store, files, month)


@dataclass(frozen=True, slots=True)
class NightlyRun:
    """One measured nightly run over a scaled dataset."""

    client_count: int
    month_rows: int
    duration_seconds: float
    report: NightlyReport

    @property
    def throughput(self) -> float:
        """Interventions of the month processed per wall-clock second."""
        return self.month_rows / self.duration_seconds

    @property
    def seconds_per_client(self) -> float:
        return self.duration_seconds / self.client_count


def _measure_nightly(factory: pytest.TempPathFactory, count: int) -> NightlyRun:
    """Generate a ``count``-client dataset, load it, and time one nightly run."""
    base = factory.mktemp(f"perf-{count}")
    dataset = base / "dataset"
    _generate_dataset(dataset, count)

    store = open_store(base / "perf.sqlite3")
    month = Month.parse(TARGET_MONTH)
    _load_dataset(store, dataset, month)

    started = time.monotonic()
    report = run_nightly(store, store.load(), month=month, classifier=_classifier(store))
    duration = time.monotonic() - started

    rows = len(store.list_interventions(month=month))
    store.close()
    run = NightlyRun(count, rows, duration, report)
    print(
        f"[perf] {count} clients, {TARGET_MONTH}: nightly {run.duration_seconds:.1f} s "
        f"({run.month_rows} interventions, {run.throughput:.1f}/s, "
        f"{run.report.classified} classified, coverage {run.report.coverage_percent} %)"
    )
    return run


@pytest.fixture(scope="module")
def small_run(tmp_path_factory: pytest.TempPathFactory) -> NightlyRun:
    """The 50-client nightly run: the baseline of the growth check."""
    return _measure_nightly(tmp_path_factory, SMALL_CLIENTS)


@pytest.fixture(scope="module")
def large_run(tmp_path_factory: pytest.TempPathFactory) -> NightlyRun:
    """The 200-client nightly run: the ENF-PERF-01 target."""
    return _measure_nightly(tmp_path_factory, LARGE_CLIENTS)


@pytest.mark.slow
def test_nightly_200_clients_fits_the_30_minute_budget(large_run: NightlyRun) -> None:
    """ENF-PERF-01: a full nightly recalculation of 200 clients under 30 min."""
    assert large_run.report.clients_recalculated == LARGE_CLIENTS
    assert large_run.report.margins_written == LARGE_CLIENTS
    assert large_run.report.classified > 0  # the run really classified the month
    print(
        f"[ENF-PERF-01] {LARGE_CLIENTS} clients: {large_run.duration_seconds:.1f} s "
        f"= {large_run.duration_seconds / 60:.1f} min "
        f"(budget {BUDGET_SECONDS / 60:.0f} min), "
        f"throughput {large_run.throughput:.1f} interventions/s"
    )
    assert large_run.duration_seconds < BUDGET_SECONDS


@pytest.mark.slow
def test_growth_stays_linear_from_50_to_200_clients(small_run: NightlyRun, large_run: NightlyRun) -> None:
    """The per-client cost must not more than double between 50 and 200 clients."""
    assert small_run.report.clients_recalculated == SMALL_CLIENTS
    assert small_run.report.classified > 0
    ratio = large_run.seconds_per_client / small_run.seconds_per_client
    print(
        f"[growth] 50 clients: {small_run.duration_seconds:.1f} s "
        f"({small_run.seconds_per_client:.3f} s/client); "
        f"200 clients: {large_run.duration_seconds:.1f} s "
        f"({large_run.seconds_per_client:.3f} s/client); "
        f"per-client ratio {ratio:.2f} (limit {MAX_PER_CLIENT_GROWTH})"
    )
    assert ratio <= MAX_PER_CLIENT_GROWTH
