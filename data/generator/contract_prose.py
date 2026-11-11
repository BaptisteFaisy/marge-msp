"""French prose of the contract sections (Annex B fields, in context).

Every section returns plain paragraphs; lists are rendered as ``-`` bullets.
Three phrasing variants exist so the twelve contracts do not read the same.
"""

from __future__ import annotations

from .common import french_date, french_hours, french_money
from .profiles import MSP_ADDRESS, MSP_LEGAL_NAME, ContractSpec

PARTIES = "parties"
OBJECT = "object"
DURATION = "duration"
RESOURCES = "resources"
PRICE = "price"
INCLUDED = "included"
EXCLUDED = "excluded"
SERVICE_HOURS = "service_hours"
SLA = "sla"
PENALTIES = "penalties"
INDEXATION = "indexation"
TERMINATION = "termination"

TITLES = {
    PARTIES: "Parties au contrat",
    OBJECT: "Objet du contrat",
    DURATION: "Durée et reconduction",
    RESOURCES: "Comptes et ressources couverts",
    PRICE: "Conditions financières",
    INCLUDED: "Services inclus",
    EXCLUDED: "Exclusions",
    SERVICE_HOURS: "Plages de service",
    SLA: "Engagements de niveau de service",
    PENALTIES: "Pénalités",
    INDEXATION: "Indexation",
    TERMINATION: "Résiliation",
}


def _bullets(items: tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]


def parties(spec: ContractSpec) -> list[str]:
    return [
        "Entre les soussignés :",
        f"{MSP_LEGAL_NAME}, dont le siège social est situé {MSP_ADDRESS}, "
        "immatriculée au registre du commerce et des sociétés de Nantes, "
        "ci-après « le Prestataire »,",
        f"et {spec.customer_name}, ci-après « le Client »,",
        "il a été convenu ce qui suit.",
    ]


def object_(spec: ContractSpec) -> list[str]:
    paragraphs = [
        "Le Prestataire assure pour le compte du Client les services managés "
        "décrits au présent contrat, dans les conditions de niveau de service "
        "et de périmètre définies ci-après."
    ]
    if spec.version > 1:
        paragraphs.insert(
            0,
            f"Le présent avenant n°{spec.version - 1} modifie le contrat "
            f"{spec.contract_id} à compter du {french_date(spec.effective_from)}. "
            f"Motif : {spec.amendment_reason}.",
        )
    return paragraphs


def duration(spec: ContractSpec, phrasing: int = 0) -> list[str]:
    start, end = french_date(spec.start_date), french_date(spec.end_date)
    notice = spec.termination_notice
    variants = (
        f"Le contrat prend effet le {start} et se termine le {end}. "
        f"Il est renouvelable selon les modalités suivantes : {spec.renewal_terms.lower()}. "
        f"Le préavis de résiliation est de {notice}.",
        f"Durée : du {start} au {end} inclus. {spec.renewal_terms}. "
        f"Toute résiliation est notifiée avec un préavis de {notice}.",
        f"Le présent contrat est conclu pour la période du {start} au {end}. "
        f"À son terme, {spec.renewal_terms.lower()}. "
        f"Chaque partie peut y mettre fin avec un préavis de {notice}.",
    )
    return [variants[phrasing % len(variants)]]


def resources(spec: ContractSpec) -> list[str]:
    return [
        f"Le périmètre couvre {spec.covered_accounts_or_resources} comptes ou ressources "
        "gérés, dont la liste est tenue à jour par le Prestataire et communiquée au Client "
        "à chaque revue trimestrielle."
    ]


def price(spec: ContractSpec, phrasing: int = 0) -> list[str]:
    amount = french_money(spec.monthly_subscription, spec.currency)
    rate = french_money(spec.extra_hour_rate, spec.currency)
    quota = (
        "un volume d'heures non limité"
        if spec.included_hours_per_month is None
        else french_hours(spec.included_hours_per_month)
    )
    variants = (
        f"En contrepartie, le Client verse un abonnement mensuel de {amount} hors taxes, "
        f"couvrant {quota} par mois. Les heures réalisées au-delà de ce forfait sont "
        f"facturées au tarif horaire hors forfait de {rate}.",
        f"Le prix de l'abonnement mensuel est fixé à {amount} hors taxes. Il comprend "
        f"{quota} par mois. Toute heure supplémentaire est facturée {rate}.",
        f"Conditions financières : abonnement mensuel de {amount} hors taxes pour {quota} "
        f"incluses chaque mois ; au-delà, le tarif horaire hors forfait s'établit à {rate}.",
    )
    return [variants[phrasing % len(variants)]]


def included(spec: ContractSpec) -> list[str]:
    return ["Le Prestataire réalise les services suivants :", *_bullets(spec.services_included)]


def excluded(spec: ContractSpec) -> list[str]:
    return ["Ne sont pas compris dans le périmètre du contrat :", *_bullets(spec.exclusions)]


def service_hours(spec: ContractSpec) -> list[str]:
    return [f"Les services sont rendus selon les plages suivantes : {spec.service_hours}."]


def sla(spec: ContractSpec) -> list[str]:
    items = tuple(f"{item.subject} : {item.target}" for item in spec.sla_commitments)
    return ["Le Prestataire s'engage sur les niveaux de service suivants :", *_bullets(items)]


def penalties(spec: ContractSpec) -> list[str]:
    return [f"Pénalités : {spec.penalties}"]


def indexation(spec: ContractSpec) -> list[str]:
    return [f"Clause d'indexation : {spec.indexation_clause}"]


def termination(spec: ContractSpec) -> list[str]:
    return [
        f"Le contrat peut être résilié par l'une ou l'autre partie avec un préavis de "
        f"{spec.termination_notice}, notifié par lettre recommandée avec accusé de réception. "
        f"{spec.renewal_terms}. En cas de manquement grave, la résiliation intervient de plein "
        "droit trente jours après mise en demeure restée sans effet."
    ]


BUILDERS = {
    PARTIES: parties,
    OBJECT: object_,
    RESOURCES: resources,
    INCLUDED: included,
    EXCLUDED: excluded,
    SERVICE_HOURS: service_hours,
    SLA: sla,
    PENALTIES: penalties,
    INDEXATION: indexation,
    TERMINATION: termination,
}


def build_section(key: str, spec: ContractSpec, phrasing: int) -> list[str]:
    """Paragraphs of one section, phrasing-aware for price and duration."""
    if key == PRICE:
        return price(spec, phrasing)
    if key == DURATION:
        return duration(spec, phrasing)
    return BUILDERS[key](spec)
