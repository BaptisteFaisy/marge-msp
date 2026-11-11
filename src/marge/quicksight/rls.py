"""Row-level security rules of the Quick Sight datasets (EF-TDB-06, ENF-CONF-03).

Two rules are defined:

* ``RLS-ACCOUNT-MANAGER-SCOPE`` — an account manager only sees the rows of the
  clients they own. The identity is taken from a Quick session parameter
  holding the ``account_manager_id`` of the signed-in user.
* ``RLS-HOURLY-COST-RESTRICTED`` — the hourly costs and the contractual rates
  are protected: only the controller and the direction read them.

The rules are declared as data so that the same file feeds the dashboards, the
agent instructions, the asset bundle and the deployment plan.
"""

from __future__ import annotations

from .models import RlsRule

__all__ = ["RLS_RULES", "RLS_RULE_IDS", "ROLE_CONTROLLER", "ROLE_EXECUTIVE", "rls_by_id"]

ROLE_EXECUTIVE = "EXECUTIVE"
ROLE_OPERATIONS_DIRECTOR = "OPERATIONS_DIRECTOR"
ROLE_ACCOUNT_MANAGER = "ACCOUNT_MANAGER"
ROLE_CONTROLLER = "CONTROLLER"
ROLE_ADMINISTRATOR = "ADMINISTRATOR"

_ALL_ROLES = (
    ROLE_EXECUTIVE,
    ROLE_OPERATIONS_DIRECTOR,
    ROLE_ACCOUNT_MANAGER,
    ROLE_CONTROLLER,
    ROLE_ADMINISTRATOR,
)

_SESSION_PARAMETER = "marge_account_manager_id"
"""Name of the Quick session parameter carrying the identity of the user."""

RLS_RULES: tuple[RlsRule, ...] = (
    RlsRule(
        rule_id="RLS-ACCOUNT-MANAGER-SCOPE",
        identity_parameter=_SESSION_PARAMETER,
        identity_source="Quick session parameter set at sign-in from the portal (Cognito group claim)",
        role_values=(
            (ROLE_EXECUTIVE, ("ALL",)),
            (ROLE_OPERATIONS_DIRECTOR, ("ALL",)),
            (ROLE_CONTROLLER, ("ALL",)),
            (ROLE_ADMINISTRATOR, ("ALL",)),
            (ROLE_ACCOUNT_MANAGER, ("SELF",)),
        ),
        protected_datasets=(
            "marge_client_mois",
            "effort_client_mois_categorie",
            "heures_non_facturees",
            "contrats_actifs",
            "interventions_a_valider",
        ),
        protected_fields=(),
        description=(
            "Rows are kept when the account_manager_id column equals the session parameter. "
            "Roles listed with ALL see every row."
        ),
        requirement="EF-TDB-06, ENF-CONF-03",
    ),
    RlsRule(
        rule_id="RLS-HOURLY-COST-RESTRICTED",
        identity_parameter=_SESSION_PARAMETER,
        identity_source="Quick session parameter set at sign-in from the portal (Cognito group claim)",
        role_values=(
            (ROLE_EXECUTIVE, ("ALL",)),
            (ROLE_CONTROLLER, ("ALL",)),
            (ROLE_ADMINISTRATOR, ("ALL",)),
            (ROLE_OPERATIONS_DIRECTOR, ("NONE",)),
            (ROLE_ACCOUNT_MANAGER, ("NONE",)),
        ),
        protected_datasets=(),
        protected_fields=(
            "effort_client_mois_categorie.hourly_cost",
            "heures_non_facturees.contract_hour_rate",
            "contrats_actifs.extra_hour_rate",
        ),
        description=(
            "The hourly costs and the contractual hourly rates are readable by the controller and "
            "the direction only. The other roles see the field masked. The cost of the labour is "
            "kept: only the rate that produces it is hidden (ENF-CONF-03, spec 17)."
        ),
        requirement="ENF-CONF-03, spec 6",
    ),
)

RLS_RULE_IDS: tuple[str, ...] = tuple(rule.rule_id for rule in RLS_RULES)


def rls_by_id(rule_id: str) -> RlsRule:
    """Return the rule ``rule_id`` or raise ``KeyError``."""
    for rule in RLS_RULES:
        if rule.rule_id == rule_id:
            return rule
    raise KeyError(f"no RLS rule named {rule_id!r}")
