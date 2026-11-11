"""Shared constructors of the twelve generated clients (spec 19.1).

``_spec`` fills the recurring contract clauses and ``_client`` the recurring
demo knobs, so a client declaration only carries what is specific to it. The
twelve declarations themselves are split over :mod:`generator.client_set_a` and
:mod:`generator.client_set_b` to keep every file small.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .profiles import (
    CATALOGUE_EXCLUDED,
    CATALOGUE_INCLUDED,
    INDEXATION_STANDARD,
    PENALTY_STANDARD,
    SLA_STANDARD_247,
    ClientProfile,
    ContractSpec,
)

D = date


def spec(**kwargs) -> ContractSpec:
    """Build a contract version, filling the standard clauses by default."""
    defaults = {
        "currency": "EUR",
        "status": "VALIDATED",
        "ambiguous_clause": False,
        "penalties": PENALTY_STANDARD,
        "indexation_clause": INDEXATION_STANDARD,
        "sla_commitments": SLA_STANDARD_247,
        "services_included": CATALOGUE_INCLUDED,
        "exclusions": CATALOGUE_EXCLUDED,
    }
    defaults.update(kwargs)
    return ContractSpec(**defaults)


def client(**kwargs) -> ClientProfile:
    """Build a client, filling the recurring demo knobs by default."""
    defaults = {
        "amendment": None,
        "ambiguous_share": Decimal("0"),
        "poor_coverage_month": None,
        "penalties": (),
        "extra_hours": (),
        "projects": (),
        "aws_markup": Decimal("0.12"),
    }
    defaults.update(kwargs)
    return ClientProfile(**defaults)
