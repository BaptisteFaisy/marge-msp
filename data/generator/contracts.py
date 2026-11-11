"""Contract rendering: styles, Annex B values, PDF and ``.txt`` outputs.

One :class:`~generator.profiles.ContractSpec` feeds all outputs, so a value is
never written twice. The twelve contracts use visibly different layouts
(spec 19.1): variable clause numbering, variable section order, one
table-shaped contract, one letter, one with general/specific conditions, one
with a deliberately ambiguous exclusion.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from . import contract_prose as prose
from .common import french_hours, french_money, write_text
from .pdf import generate_pdf
from .profiles import MSP_BRAND, ContractSpec

ORDER_A = (
    prose.PARTIES,
    prose.OBJECT,
    prose.DURATION,
    prose.RESOURCES,
    prose.PRICE,
    prose.INCLUDED,
    prose.EXCLUDED,
    prose.SERVICE_HOURS,
    prose.SLA,
    prose.PENALTIES,
    prose.INDEXATION,
    prose.TERMINATION,
)
ORDER_B = (
    prose.PARTIES,
    prose.OBJECT,
    prose.INCLUDED,
    prose.EXCLUDED,
    prose.SERVICE_HOURS,
    prose.SLA,
    prose.PENALTIES,
    prose.PRICE,
    prose.DURATION,
    prose.RESOURCES,
    prose.INDEXATION,
    prose.TERMINATION,
)
ORDER_C = (
    prose.PARTIES,
    prose.PRICE,
    prose.INCLUDED,
    prose.EXCLUDED,
    prose.DURATION,
    prose.TERMINATION,
    prose.SERVICE_HOURS,
    prose.SLA,
    prose.PENALTIES,
    prose.RESOURCES,
    prose.INDEXATION,
    prose.OBJECT,
)
ORDER_D = (
    prose.OBJECT,
    prose.PARTIES,
    prose.DURATION,
    prose.PRICE,
    prose.RESOURCES,
    prose.INCLUDED,
    prose.EXCLUDED,
    prose.SLA,
    prose.SERVICE_HOURS,
    prose.PENALTIES,
    prose.INDEXATION,
    prose.TERMINATION,
)

GENERAL = "CONDITIONS GÉNÉRALES"
SPECIFIC = "CONDITIONS PARTICULIÈRES"
GENERAL_PART = (GENERAL, (prose.PARTIES, prose.OBJECT, prose.DURATION, prose.TERMINATION))
SPECIFIC_PART = (
    SPECIFIC,
    (prose.PRICE, prose.INCLUDED, prose.EXCLUDED, prose.SERVICE_HOURS, prose.SLA, prose.PENALTIES),
)

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV")


@dataclass(frozen=True, slots=True)
class Style:
    """How one contract is laid out on the page."""

    key: str
    heading: str
    parts: tuple[tuple[str, tuple[str, ...]], ...]
    recap_at_top: bool = False
    recap_as_table: bool = False
    table_body: bool = False
    letter: bool = False
    annex: bool = False
    phrasing: int = 0


STYLES: dict[str, Style] = {
    "articles": Style("articles", "Article {n} — {title}", (("", ORDER_A),), phrasing=0),
    "decimal": Style("decimal", "{n}. {title}", (("", ORDER_B),), phrasing=1),
    "roman": Style("roman", "{roman}. — {title}", (("", ORDER_A),), phrasing=2),
    "table": Style("table", "Article {n} — {title}", (("", ORDER_A),), table_body=True, phrasing=1),
    "letter": Style("letter", "{title}", (("", ORDER_C),), letter=True, phrasing=2),
    "clauses": Style("clauses", "CLAUSE {n} — {title}", (("", ORDER_B),), phrasing=0),
    "sections": Style("sections", "TITRE {n} — {title}", (("", ORDER_A),), phrasing=1),
    "reversed": Style("reversed", "Article {n} — {title}", (("", ORDER_D),), phrasing=2),
    "annexes": Style("annexes", "Article {n} — {title}", (("", ORDER_A),), annex=True, phrasing=0),
    "summary_table": Style(
        "summary_table",
        "Article {n} — {title}",
        (("", ORDER_C),),
        recap_at_top=True,
        recap_as_table=True,
        phrasing=1,
    ),
    "general_specific": Style(
        "general_specific",
        "Article {n} — {title}",
        (GENERAL_PART, SPECIFIC_PART),
        phrasing=2,
    ),
    "paragraphs": Style("paragraphs", "§ {n}. {title}", (("", ORDER_B),), phrasing=0),
}


def _roman(index: int) -> str:
    return ROMAN[index - 1] if index <= len(ROMAN) else str(index)


def scalar_fields(spec: ContractSpec) -> tuple[tuple[str, str], ...]:
    """The Annex B scalar fields, as ``(label, French value)`` pairs."""
    quota = (
        "illimité" if spec.included_hours_per_month is None else french_hours(spec.included_hours_per_month)
    )
    return (
        ("Client", spec.customer_name),
        ("Date d'effet", spec.start_date.isoformat()),
        ("Date de fin", spec.end_date.isoformat()),
        ("Reconduction", spec.renewal_terms),
        ("Préavis de résiliation", spec.termination_notice),
        ("Abonnement mensuel", f"{french_money(spec.monthly_subscription, spec.currency)} HT"),
        ("Heures incluses par mois", quota),
        ("Tarif horaire hors forfait", french_money(spec.extra_hour_rate, spec.currency)),
        ("Plages de service", spec.service_hours),
        ("Pénalités", spec.penalties),
        ("Clause d'indexation", spec.indexation_clause),
        ("Comptes et ressources couverts", str(spec.covered_accounts_or_resources)),
    )


def list_fields(spec: ContractSpec) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The Annex B list fields, kept whole (spec 13.1)."""
    return (
        ("Services inclus", spec.services_included),
        ("Exclusions", spec.exclusions),
        (
            "Engagements de niveau de service",
            tuple(f"{item.subject} — {item.target}" for item in spec.sla_commitments),
        ),
    )


def contract_fields(spec: ContractSpec) -> dict:
    """Ground truth of ``expected/contract_fields.json`` for one version."""
    quota = spec.included_hours_per_month
    return {
        "client_id": spec.client_id,
        "contract_id": spec.contract_id,
        "version": spec.version,
        "status": spec.status,
        "effective_from": spec.effective_from.isoformat(),
        "customer_name": spec.customer_name,
        "start_date": spec.start_date.isoformat(),
        "end_date": spec.end_date.isoformat(),
        "renewal_terms": spec.renewal_terms,
        "termination_notice": spec.termination_notice,
        "monthly_subscription": f"{Decimal(spec.monthly_subscription):.2f}",
        "currency": spec.currency,
        "included_hours_per_month": None if quota is None else f"{Decimal(quota):.2f}",
        "extra_hour_rate": f"{Decimal(spec.extra_hour_rate):.2f}",
        "services_included": list(spec.services_included),
        "exclusions": list(spec.exclusions),
        "service_hours": spec.service_hours,
        "sla_commitments": [
            {"subject": item.subject, "target": item.target} for item in spec.sla_commitments
        ],
        "penalties": spec.penalties,
        "indexation_clause": spec.indexation_clause,
        "covered_accounts_or_resources": spec.covered_accounts_or_resources,
        "ambiguous_clause": spec.ambiguous_clause,
    }


def _title_block(spec: ContractSpec) -> list[str]:
    kind = "AVENANT AU CONTRAT DE SERVICES MANAGÉS" if spec.version > 1 else "CONTRAT DE SERVICES MANAGÉS"
    lines = [kind, f"n° {spec.contract_id} — version {spec.version}"]
    if spec.status != "VALIDATED":
        lines.append("Document non validé par le contrôleur de gestion.")
    lines.extend([f"{MSP_BRAND} — {spec.customer_name}", ""])
    return lines


def _table_rows(spec: ContractSpec) -> list[str]:
    """Rows of the contractual table: scalars, then the scope lists."""
    rows = [f"| {label} | {value} |" for label, value in scalar_fields(spec)]
    for label, items in list_fields(spec):
        rows.append(f"| {label} | {items[0]} |")
        rows.extend(f"| | {item} |" for item in items[1:])
    return rows


def _prose_recap(spec: ContractSpec) -> list[str]:
    lines = ["Récapitulatif des conditions", ""]
    lines.extend(f"{label} : {value}" for label, value in scalar_fields(spec))
    for label, items in list_fields(spec):
        lines.append(f"{label} :")
        lines.extend(f"- {item}" for item in items)
    return [*lines, ""]


def _annex_lines(spec: ContractSpec) -> list[str]:
    return [
        "",
        "ANNEXE 1 — COMPTES ET RESSOURCES COUVERTS",
        "",
        f"La présente annexe recense les {spec.covered_accounts_or_resources} comptes et "
        "ressources gérés entrant dans le périmètre du contrat.",
        "- Comptes AWS de production et de préproduction du Client",
        "- Équipements réseau et pare-feu du siège",
        "- Serveurs et bases de données supervisés",
        "- Postes de travail couverts par le support de premier niveau",
    ]


def _numbered_body(spec: ContractSpec, style: Style) -> list[str]:
    lines: list[str] = []
    number = 0
    for part_title, order in style.parts:
        if part_title:
            lines.extend(["", part_title, ""])
        for key in order:
            number += 1
            heading = style.heading.format(n=number, roman=_roman(number), title=prose.TITLES[key])
            lines.extend([heading, ""])
            lines.extend(prose.build_section(key, spec, style.phrasing))
            lines.append("")
    return lines


def render_contract(spec: ContractSpec) -> str:
    """The full French text of one contract version (also used for the PDF)."""
    style = STYLES[spec.style]
    lines: list[str] = _title_block(spec)
    if style.letter:
        lines.extend(["Madame, Monsieur,", ""])
    if style.recap_at_top and style.recap_as_table:
        lines.extend(["FICHE CONTRACTUELLE", "", "| Champ | Valeur |"])
        lines.extend(_table_rows(spec))
        lines.append("")
    if style.table_body:
        lines.extend(["TABLEAU DES CONDITIONS CONTRACTUELLES", "", "| Champ | Valeur |"])
        lines.extend(_table_rows(spec))
        lines.append("")
    lines.extend(_numbered_body(spec, style))
    if style.annex:
        lines.extend(_annex_lines(spec))
    if style.letter:
        lines.extend(
            [
                "",
                "Nous vous prions d'agréer, Madame, Monsieur, l'expression de nos salutations distinguées.",
                "",
                f"Pour {MSP_BRAND}, le Directeur des opérations",
            ]
        )
    if not style.recap_at_top and not style.table_body:
        lines.extend(_prose_recap(spec))
    return "\n".join(lines).rstrip("\n") + "\n"


def write_contract_documents(spec: ContractSpec, out_dir: Path) -> tuple[Path, Path]:
    """Write ``<id>-v<n>.pdf`` and ``<id>-v<n>.txt``; return both paths."""
    text = render_contract(spec)
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / f"{spec.key}.txt"
    pdf_path = out_dir / f"{spec.key}.pdf"
    write_text(text_path, text)
    pdf_path.write_bytes(generate_pdf(text))
    return pdf_path, text_path
