# Marge — documentation index

Everything needed to understand, run, deploy and judge Marge. Start with the specification if you want the requirements; start with the HLD if you want the design.

## For judges and evaluators

| Document | What it gives you |
|---|---|
| [SUBMISSION.md](SUBMISSION.md) | The submission text: problem, solution, what the AI does and never does, the four judging criteria, the three impact numbers, test instructions, assumed limitations |
| [TEST-INSTRUCTIONS.md](TEST-INSTRUCTIONS.md) | Step-by-step demo (offline and hosted), demo credentials by role (EF-ADM-03), and the R1..R15 acceptance checklist (spec ch.23) |
| [HLD.md](HLD.md) | High-level design: context, goals, requirements, architecture (2 Mermaid diagrams), components, data and calculation models, the three AI steps, security, observability, performance, reproducibility, risks, roadmap |

## Design and engineering

| Document | What it gives you |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detailed architecture: exact AWS services per layer, nightly/weekly/monthly data flows, security controls, costs (Quick pricing, production estimate, hackathon budget), 3-minute video plan |
| [DECISIONS.md](DECISIONS.md) | Seven short ADRs: code computes and never a model; AI proposes and humans validate; levels not people; unassigned hours are never spread; one `Store` Protocol, two backends; CI ≤ 5 min offline; effective-dated immutable rates |
| [acceptance/MATRIX.md](acceptance/MATRIX.md) | Traceability: every `EF-*`, `ENF-*` and `R1..R15` → implementing file + proving test (its section 9 lists the remaining gaps) |
| [CONTRACT.md](CONTRACT.md) | Module ownership and the public API each package must expose — the agreement between the parallel builders |
| [DATA-FORMATS.md](DATA-FORMATS.md) | Canonical interchange formats between the data generator, the connectors and the evaluation harnesses |

## Operations

| Document | What it gives you |
|---|---|
| [RUNBOOK.md](RUNBOOK.md) | Deployment order, environment variables, secret handling, the manual Quick elements that no API can create (agent, scheduled flow, contract space) with exact labels, asset-bundle updates, troubleshooting (load failure, low resolution rate, mass uncertainty, blocked Mergify queue), rollback |

## Requirements (frozen)

| Document | What it gives you |
|---|---|
| [SPEC.fr.md](SPEC.fr.md) | The authoritative French cahier des charges: 25 chapters and annexes A–F (requirements `EF-*` / `ENF-*`, calculation model ch.12, costs ch.18, demo plan ch.19, submission checklist ch.20, risks ch.22, acceptance ch.23). Frozen — the English documents above are derived from it. |

## Reading order

1. [SUBMISSION.md](SUBMISSION.md) — what Marge is, in one page.
2. [HLD.md](HLD.md) — how it is built.
3. [TEST-INSTRUCTIONS.md](TEST-INSTRUCTIONS.md) — prove it yourself.
4. [ARCHITECTURE.md](ARCHITECTURE.md) → [RUNBOOK.md](RUNBOOK.md) — deploy and operate it.
5. [acceptance/MATRIX.md](acceptance/MATRIX.md) — check requirement by requirement.

## Conventions

- All submission and engineering documents are in English; only [SPEC.fr.md](SPEC.fr.md) is in French (internal working document, frozen).
- Requirement ids (`EF-SRC-01`, `ENF-IA-01`, `R8`…) always refer to [SPEC.fr.md](SPEC.fr.md).
- Every figure quoted in these documents comes from the specification, not from an estimate: 4 620 € / 3 725 € / 895 € = 19.4 % and 9 h × 110 € = 990 € (Annex D), Quick at 20 $ / 40 $ per user per month, 250 $ infrastructure, 8 / 18 agent hours, 0.38 $ per GB of SPICE, 30-day trial, ≈ 330 $ hackathon budget (ch.18).
