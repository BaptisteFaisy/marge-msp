"""The twelve clients of the fake MSP, assembled from their two halves.

The declarations live in :mod:`generator.client_set_a` (c-001..c-005) and
:mod:`generator.client_set_b` (c-006..c-012); this module is the single place
where the whole roster is exposed, plus the derived lookups the generator and
the harnesses use.

Seeded situations of spec 19.1, in one glance:

* two loss-making clients — ``c-004`` (always) and ``c-009`` (abnormal volume);
* three clients with repeated out-of-scope work — ``c-002``, ``c-006``, ``c-008``;
* one profitable client renewing in 60 days with a falling margin — ``c-001``;
* one contract with an ambiguous exclusion — ``c-007``;
* one contract never validated (margin INCOMPLETE, R4) — ``c-010``;
* one v2 amendment effective 2026-08-01 (EF-CTR-04) — ``c-011``;
* one month with poor data coverage (ESTIMATE, spec 12.4) — ``c-012``.
"""

from __future__ import annotations

from .client_set_a import CLIENTS as CLIENTS_A
from .client_set_b import CLIENTS as CLIENTS_B
from .profiles import ClientProfile, ContractSpec

CLIENTS: tuple[ClientProfile, ...] = CLIENTS_A + CLIENTS_B

CLIENTS_BY_ID: dict[str, ClientProfile] = {profile.client_id: profile for profile in CLIENTS}

CONTRACTS: tuple[ContractSpec, ...] = tuple(spec for profile in CLIENTS for spec in profile.contracts)

CONTRACTS_BY_KEY: dict[str, ContractSpec] = {spec.key: spec for spec in CONTRACTS}

AMBIGUOUS_CONTRACT_KEYS: tuple[str, ...] = tuple(spec.key for spec in CONTRACTS if spec.ambiguous_clause)

UNVALIDATED_CONTRACT_KEYS: tuple[str, ...] = tuple(
    spec.key for spec in CONTRACTS if spec.status != "VALIDATED"
)

AMENDED_CONTRACT_IDS: tuple[str, ...] = tuple(
    profile.contract.contract_id for profile in CLIENTS if profile.amendment is not None
)

LEGACY_ALIAS = ("itsm", "MARTIN", "MARTIN (ancien code client)")
"""A legacy ITSM code that two clients could claim: the matcher cannot be sure.

It is the one alias the R2 measure is allowed to get wrong, and the reason the
proposal stays PENDING (EF-REF-01: a human decides).
"""

LEGACY_ALIAS_TRUTH = "c-012"
"""What the MSP's own records say the legacy code ``MARTIN`` belongs to."""
