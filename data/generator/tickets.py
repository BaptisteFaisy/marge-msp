"""Intervention generation: ~4 000 tickets over six months (spec 19.1).

Distribution notes:

* categories follow a realistic MSP mix (supervision first, development last);
* durations are quarter hours, normalised so each client-month lands on the
  hours declared in its profile (those hours are what drive the margin);
* ``c-009`` carries an abnormal ticket volume, which is why it loses money;
* ``c-002``, ``c-006`` and ``c-008`` repeat out-of-scope work every month;
* ``c-007`` sends ambiguous "maintenance évolutive" work (its contract has an
  ambiguous exclusion, so those interventions must be labelled UNCERTAIN);
* at least twenty interventions have no ``customer_ref`` (UNASSIGNED bucket);
* ``c-012`` has one month where part of the tickets were typed without a
  customer reference (poor coverage, spec 12.4);
* 150 interventions are labelled for the classification harness (R5/R6).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .common import MONTHS, SEED, business_days, hours, month_of
from .profiles import ClientProfile

COLUMNS = (
    "intervention_id",
    "ticket_id",
    "customer_ref",
    "occurred_on",
    "category",
    "ticket_type",
    "level",
    "engineer_ref",
    "hours_spent",
    "description",
    "aws_account_id",
    "managed_resource_id",
)

TICKET_TYPES = ("INCIDENT", "DEMANDE", "CHANGEMENT", "PROBLEME")

UNASSIGNED_COUNT = 24
"""Interventions with an empty ``customer_ref`` (EF-REF-04, spec 12.4)."""

POOR_COVERAGE_TICKETS = 22
"""Tickets typed without a customer reference on the poor-coverage month."""

LABEL_QUOTAS = (
    ("clearly_included", 60),
    ("trap_included", 25),
    ("out_of_scope", 45),
    ("ambiguous", 20),
)
"""150 labelled interventions in total (spec 13.3)."""


@dataclass(frozen=True, slots=True)
class Category:
    """A work category, its scope semantics and its usual duration."""

    name: str
    scope: str
    weight: Decimal
    hours: Decimal
    levels: tuple[str, ...]
    descriptions: tuple[str, ...]


IN_SCOPE = "in"
OUT_OF_SCOPE = "out"
AMBIGUOUS = "ambiguous"

IN_SCOPE_CATEGORIES: tuple[Category, ...] = (
    Category(
        "Supervision infrastructure",
        IN_SCOPE,
        Decimal("0.26"),
        Decimal("0.75"),
        ("N1", "N2"),
        (
            "Contrôle des alertes de supervision",
            "Vérification des tableaux de bord de supervision",
            "Ajustement des seuils d'alerte",
            "Revue des journaux de supervision",
        ),
    ),
    Category(
        "Sauvegarde",
        IN_SCOPE,
        Decimal("0.16"),
        Decimal("1.00"),
        ("N1", "N2"),
        (
            "Contrôle du job de sauvegarde nocturne",
            "Vérification de l'intégrité des sauvegardes",
            "Relance d'une sauvegarde en échec",
        ),
    ),
    Category(
        "Patch management",
        IN_SCOPE,
        Decimal("0.12"),
        Decimal("0.60"),
        ("N1",),
        (
            "Application des correctifs mensuels",
            "Mise à jour système des serveurs",
            "Redémarrage planifié après mise à jour système",
        ),
    ),
    Category(
        "Incident infrastructure",
        IN_SCOPE,
        Decimal("0.18"),
        Decimal("1.60"),
        ("N2", "N3"),
        (
            "Incident sur l'application métier : service relancé",
            "Redémarrage du service applicatif de facturation",
            "Saturation mémoire sur le serveur applicatif",
            "Incident réseau sur le site principal",
        ),
    ),
    Category(
        "Gestion des accès",
        IN_SCOPE,
        Decimal("0.09"),
        Decimal("0.50"),
        ("N1",),
        (
            "Création et suppression de comptes utilisateurs",
            "Réinitialisation d'un accès",
            "Revue trimestrielle des accès",
        ),
    ),
    Category(
        "Optimisation des coûts AWS",
        IN_SCOPE,
        Decimal("0.05"),
        Decimal("1.20"),
        ("N3", "ARCHITECT"),
        (
            "Analyse des coûts AWS et ajustement des instances",
            "Suppression des volumes orphelins",
        ),
    ),
    Category(
        "Restauration de données",
        IN_SCOPE,
        Decimal("0.04"),
        Decimal("2.00"),
        ("N2", "N3"),
        (
            "Restauration d'un fichier demandé par l'utilisateur",
            "Test de restauration sur environnement de secours",
        ),
    ),
    Category(
        "Support utilisateurs N1",
        IN_SCOPE,
        Decimal("0.10"),
        Decimal("0.40"),
        ("N1",),
        (
            "Support téléphonique de premier niveau",
            "Assistance à la connexion au poste de travail",
        ),
    ),
)

OUT_OF_SCOPE_CATEGORIES: tuple[Category, ...] = (
    Category(
        "Développement applicatif",
        OUT_OF_SCOPE,
        Decimal("0.34"),
        Decimal("3.00"),
        ("N3", "ARCHITECT"),
        (
            "Développement d'un nouvel écran de gestion",
            "Développement d'un script métier pour la facturation",
        ),
    ),
    Category(
        "Correctif requête SQL",
        OUT_OF_SCOPE,
        Decimal("0.20"),
        Decimal("2.00"),
        ("N3",),
        (
            "Correctif d'une requête SQL applicative lente",
            "Réécriture d'une requête SQL du module de stock",
        ),
    ),
    Category(
        "Formation utilisateurs",
        OUT_OF_SCOPE,
        Decimal("0.16"),
        Decimal("3.50"),
        ("N2",),
        (
            "Formation des utilisateurs au nouvel outil",
            "Session de formation des équipes du Client",
        ),
    ),
    Category(
        "Achat de matériel",
        OUT_OF_SCOPE,
        Decimal("0.10"),
        Decimal("0.50"),
        ("N1",),
        (
            "Achat de matériel : recherche de fournisseur",
            "Achat de matériel : installation d'un poste neuf",
        ),
    ),
    Category(
        "Projet de migration applicative",
        OUT_OF_SCOPE,
        Decimal("0.10"),
        Decimal("4.00"),
        ("ARCHITECT",),
        (
            "Projet de migration applicative vers le nouveau socle",
            "Cadrage du projet de migration applicative",
        ),
    ),
    Category(
        "Intégration API applicative",
        OUT_OF_SCOPE,
        Decimal("0.10"),
        Decimal("2.50"),
        ("N3",),
        (
            "Intégration API applicative avec l'outil de facturation",
            "Intégration API applicative du portail client",
        ),
    ),
)

AMBIGUOUS_CATEGORY = Category(
    "Maintenance évolutive",
    AMBIGUOUS,
    Decimal("1.00"),
    Decimal("2.00"),
    ("N3", "N2"),
    (
        "Maintenance évolutive du module de facturation",
        "Évolution mineure du module de gestion des contrats",
        "Maintenance évolutive : ajustement d'un formulaire",
    ),
)

ENGINEERS = tuple(f"eng-{index:02d}" for index in range(1, 31))
"""Opaque person identifiers: the loader drops them (ENF-CONF-01)."""


@dataclass(slots=True)
class TicketDataset:
    """Generated interventions plus the labelled subset and the counts."""

    rows: list[dict] = field(default_factory=list)
    labels: list[dict] = field(default_factory=list)
    unassigned: int = 0

    @property
    def total_hours(self) -> Decimal:
        return hours(sum((Decimal(row["hours_spent"]) for row in self.rows), Decimal("0")))


def _pick_category(rng: random.Random, categories: tuple[Category, ...]) -> Category:
    draw = Decimal(str(round(rng.random(), 6)))
    cumulative = Decimal("0")
    for category in categories:
        cumulative += category.weight
        if draw <= cumulative:
            return category
    return categories[-1]


def _durations(categories: list[Category], target: Decimal, rng: random.Random) -> list[Decimal]:
    """Quarter-hour durations that add up exactly to ``target``."""
    raw = [float(category.hours) * rng.uniform(0.45, 1.9) for category in categories]
    total = sum(raw) or 1.0
    scaled = [
        max(Decimal("0.25"), hours(target * Decimal(str(value)) / Decimal(str(total)))) for value in raw
    ]
    scaled = [value.quantize(Decimal("0.25")) for value in scaled]
    residual = target - sum(scaled, Decimal("0"))
    if residual != 0 and scaled:
        biggest = max(range(len(scaled)), key=lambda index: scaled[index])
        scaled[biggest] = hours(scaled[biggest] + residual)
    return scaled


def _client_month_rows(profile: ClientProfile, month: str, month_index: int, client_index: int) -> list[dict]:
    rng = random.Random(SEED + client_index * 101 + month_index)
    target_hours = profile.monthly_hours[month_index]
    volume = profile.monthly_volume + rng.randint(-3, 3)
    volume = max(6, volume)
    ambiguous_share = profile.ambiguous_share
    out_share = profile.out_of_scope_share

    categories: list[Category] = []
    for _ in range(volume):
        draw = Decimal(str(round(rng.random(), 6)))
        if ambiguous_share > 0 and draw < ambiguous_share:
            categories.append(AMBIGUOUS_CATEGORY)
        elif draw < ambiguous_share + out_share:
            categories.append(_pick_category(rng, OUT_OF_SCOPE_CATEGORIES))
        else:
            categories.append(_pick_category(rng, IN_SCOPE_CATEGORIES))

    durations = _durations(categories, target_hours, rng)
    days = business_days(month)
    rows: list[dict] = []
    for index, (category, duration) in enumerate(zip(categories, durations, strict=True)):
        day = days[(index * len(days)) // max(1, volume)]
        rows.append(
            {
                "customer_ref": profile.itsm_alias,
                "occurred_on": day.isoformat(),
                "category": category.name,
                "ticket_type": TICKET_TYPES[rng.randrange(len(TICKET_TYPES))],
                "level": category.levels[rng.randrange(len(category.levels))],
                "engineer_ref": ENGINEERS[rng.randrange(len(ENGINEERS))],
                "hours_spent": f"{duration:.2f}",
                "description": category.descriptions[rng.randrange(len(category.descriptions))],
                "aws_account_id": profile.billing_alias,
                "managed_resource_id": f"{profile.client_id}-res-{rng.randint(1, 40):03d}",
                "_scope": category.scope,
                "_client": profile.client_id,
            }
        )
    return rows


def _unassigned_rows() -> list[dict]:
    """Tickets with no customer reference: they must stay visible (EF-REF-04)."""
    random.Random(SEED + 7717)
    rows: list[dict] = []
    for index in range(UNASSIGNED_COUNT):
        month = MONTHS[index % len(MONTHS)]
        days = business_days(month)
        category = IN_SCOPE_CATEGORIES[index % len(IN_SCOPE_CATEGORIES)]
        rows.append(
            {
                "customer_ref": "",
                "occurred_on": days[(index * 3) % len(days)].isoformat(),
                "category": category.name,
                "ticket_type": "DEMANDE",
                "level": category.levels[0],
                "engineer_ref": ENGINEERS[(index * 7) % len(ENGINEERS)],
                "hours_spent": f"{Decimal('0.50') + Decimal(index % 4) * Decimal('0.25'):.2f}",
                "description": "Ticket saisi sans référence client (file d'attente générale)",
                "aws_account_id": "",
                "managed_resource_id": "",
                "_scope": IN_SCOPE,
                "_client": "",
            }
        )
    return rows


def _poor_coverage_rows(profile: ClientProfile, month: str) -> list[dict]:
    """Tickets of one client typed without a customer reference (spec 12.4).

    The client name is still in the description, so the loader can say the
    hours belong to that client without being able to attach them to a
    contract line: coverage drops below the floor and the month is ESTIMATE.
    """
    random.Random(SEED + 4242)
    days = business_days(month)
    rows: list[dict] = []
    for index in range(POOR_COVERAGE_TICKETS):
        category = IN_SCOPE_CATEGORIES[index % len(IN_SCOPE_CATEGORIES)]
        rows.append(
            {
                "customer_ref": "",
                "occurred_on": days[(index * 2) % len(days)].isoformat(),
                "category": category.name,
                "ticket_type": "INCIDENT",
                "level": category.levels[0],
                "engineer_ref": ENGINEERS[(index * 5) % len(ENGINEERS)],
                "hours_spent": "0.75",
                "description": f"{profile.name} — {category.descriptions[0]} "
                "(ticket saisi sans référence client)",
                "aws_account_id": "",
                "managed_resource_id": "",
                "_scope": IN_SCOPE,
                "_client": "",
                "_queue_client": profile.client_id,
            }
        )
    return rows


def _evenly_spaced(candidates: list[dict], quota: int) -> list[dict]:
    """Deterministic sample spread over the whole candidate list."""
    if len(candidates) <= quota:
        return list(candidates)
    step = len(candidates) / quota
    return [candidates[int(index * step)] for index in range(quota)]


def _label_for(key: str, row: dict) -> dict:
    """The expected class of one labelled intervention (spec 13.3)."""
    expected = {
        "out_of_scope": ("OUT_OF_SCOPE", False),
        "ambiguous": ("UNCERTAIN", False),
    }.get(key, ("IN_SCOPE", True))
    return {
        "intervention_id": row["intervention_id"],
        "expected_class": expected[0],
        "clearly_included": expected[1],
    }


def _select_labels(rows: list[dict]) -> list[dict]:
    """Pick the 150 labelled interventions (R5/R6, spec 13.3).

    A quota whose candidate pool is too small is topped up from the remaining
    unlabelled rows, so the labelled set always reaches its size.
    """
    traps = [row for row in rows if row["_scope"] == IN_SCOPE and "applicati" in row["description"].lower()]
    trap_ids = {row["_row_id"] for row in traps}
    groups = {
        "clearly_included": [
            row for row in rows if row["_scope"] == IN_SCOPE and row["_row_id"] not in trap_ids
        ],
        "trap_included": traps,
        "out_of_scope": [row for row in rows if row["_scope"] == OUT_OF_SCOPE],
        "ambiguous": [row for row in rows if row["_scope"] == AMBIGUOUS],
    }
    target = sum(quota for _key, quota in LABEL_QUOTAS)
    chosen: dict[str, list[dict]] = {}
    taken: set[str] = set()
    for key, quota in LABEL_QUOTAS:
        picked = _evenly_spaced(groups[key], quota)
        chosen[key] = picked
        taken.update(row["_row_id"] for row in picked)
    shortfall = target - sum(len(picked) for picked in chosen.values())
    if shortfall > 0:
        reserve = [row for row in rows if row["_row_id"] not in taken and row["_scope"] == IN_SCOPE]
        chosen["clearly_included"].extend(_evenly_spaced(reserve, shortfall))
    labels = [_label_for(key, row) for key, picked in chosen.items() for row in picked]
    return sorted(labels, key=lambda item: item["intervention_id"])


def generate(profiles: tuple[ClientProfile, ...]) -> TicketDataset:
    """Build every intervention of the six months and the labelled subset."""
    rows: list[dict] = []
    for client_index, profile in enumerate(profiles):
        for month_index, month in enumerate(MONTHS):
            rows.extend(_client_month_rows(profile, month, month_index, client_index))
            if profile.poor_coverage_month == month:
                rows.extend(_poor_coverage_rows(profile, month))
    rows.extend(_unassigned_rows())

    rows.sort(key=lambda row: (row["occurred_on"], row["customer_ref"], row["category"]))
    dataset = TicketDataset()
    for index, row in enumerate(rows, start=1):
        row["intervention_id"] = f"wl-{index:06d}"
        row["ticket_id"] = f"t-{100000 + index:06d}"
        row["_row_id"] = f"wl-{index:06d}"
    dataset.rows = rows
    dataset.labels = _select_labels(rows)
    dataset.unassigned = sum(1 for row in rows if not row["customer_ref"])
    return dataset


def csv_rows(dataset: TicketDataset) -> list[tuple]:
    """Rows in the canonical column order of ``interventions.csv``."""
    return [tuple(row[column] for column in COLUMNS) for row in dataset.rows]


def month_counts(dataset: TicketDataset) -> dict[str, int]:
    """Interventions per month, for the manifest."""
    counts: dict[str, int] = dict.fromkeys(MONTHS, 0)
    for row in dataset.rows:
        counts[month_of(date.fromisoformat(row["occurred_on"]))] += 1
    return counts
