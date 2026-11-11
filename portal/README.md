# Marge — validation portal (static, no build step)

Three screens on top of the portal API (spec 16, EF-VAL-01):

| Screen | Route used | Requirement |
|---|---|---|
| Matches | `GET /v1/matches`, `POST /v1/matches/{id}/decision` | EF-REF-01 |
| Contracts | `GET /v1/contracts`, `GET /v1/contracts/{id}`, `PUT .../fields`, `POST .../validate` | EF-CTR-02, EF-CTR-03 |
| Classifications | `GET /v1/classifications?status=pending`, `POST /v1/classifications/{id}/decision` | EF-CLS-03 |

Each extracted contract field is displayed next to the passage of the contract
it was read from, with a **validate** and a **correct** button. Each pending
classification shows its cited clause and offers **validate / correct /
discard**. Every decision asks for a reason: it is written to the audit log
with its author and date (EF-VAL-02).

## Run it

```bash
# 1. API (dev auth mode: X-Actor-Id / X-Actor-Role headers, EF-ADM-03)
PYTHONPATH=src uvicorn marge.api.app:create_app --factory --port 8000

# 2. Portal: any static file server, no build step
python3 -m http.server 8080 --directory portal
```

Then open <http://localhost:8080>. The **API** field in the header points at the
running API (`http://localhost:8000` by default).

## Demo identities (EF-ADM-03)

The header carries an actor id and a role. Switching the role reproduces the
row-level filtering of EF-TDB-06 live:

| Actor id | Role | Sees |
|---|---|---|
| `exec-01` | `EXECUTIVE` | every client, hourly costs |
| `ops-01` | `OPERATIONS_DIRECTOR` | every client, hourly costs |
| `am-01` | `ACCOUNT_MANAGER` | only its own clients, **no hourly cost** (ENF-CONF-03) |
| `controller-01` | `CONTROLLER` | every client, hourly costs, may validate |
| `admin-01` | `ADMINISTRATOR` | every client, references |

The banner at the top of the page is permanent: the portal only ever shows
synthetic demo data.

## No number is computed here

The portal renders what the API returns. Every figure comes from `marge.calc`
on the server (ENF-IA-01), and nothing AI-produced counts before a human
decision (ENF-IA-02). Ticket and contract text is inserted with `textContent`,
never `innerHTML`, so it stays data and never becomes an instruction (ENF-IA-03).
