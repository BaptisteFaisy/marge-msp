# VIDEO-SCRIPT.md — Shooting script for the 3-minute submission video

**Hackathon:** AWS MSP AI (per-client MSP profitability).
**Deliverable:** one 3-minute video, English voice-over, published on YouTube as a **public** link, submitted on Devpost.
**Timing source:** `docs/SPEC.fr.md` §19.2 — 7 shots, 180 seconds.
**Script source of truth:** the commands below come from the real CLI (`PYTHONPATH=src:. python3 -m marge.cli --help` → `assets, demo, eval, generate, mcp, monthly, nightly, serve, smoke, version, weekly`).
**Measured numbers** in this document come from a real offline run of `marge.cli demo --auto-validate --review` on this branch (seeded dataset: 12 clients, 49 aliases, 13 contracts). Anything that depends on the deployed AWS environment is written as `[to measure on the live demo]` — **never invent a number on camera**.

---

## 1. Preamble — before the shoot

### 1.1 Prepare (checklist)

| # | What to prepare | Exact command / action | Done |
|---|---|---|---|
| P1 | Demo dataset (fictional MSP: 12 clients, 6 months, 12 contracts) | `PYTHONPATH=src:. python3 -m marge.cli generate --out data/demo --seed <fixed-value>` (pin the seed so the figures are reproducible on set) | ☐ |
| P2 | Demo database + key figures (source of every on-screen number) | `PYTHONPATH=src:. python3 -m marge.cli demo --auto-validate --review` → prints the DB path and the `serve` command | ☐ |
| P3 | Portal running, logged in with the demo account manager | `PYTHONPATH=src:. python3 -m marge.cli serve --db <db-path> --port 8000 --auth-mode dev` (use `--auth-mode cognito` on the deployed stack) | ☐ |
| P4 | QuickSight dashboard opened (Quick console) **and** the embedded portal page open side by side | `PYTHONPATH=src:. python3 -m marge.cli assets` (write bundle) then `PYTHONPATH=src:. python3 -m marge.cli assets --check` | ☐ |
| P5 | Nightly pipeline already run, so the queues are filled | `PYTHONPATH=src:. python3 -m marge.cli nightly --db <db-path> --month 2026-10` | ☐ |
| P6 | Weekly out-of-scope queue ready (unbilled hours waiting for a decision) | `PYTHONPATH=src:. python3 -m marge.cli weekly --db <db-path>` | ☐ |
| P7 | Monthly review text generated before filming (no live generation on camera) | `PYTHONPATH=src:. python3 -m marge.cli monthly --db <db-path> --month 2026-10 --to manager@demo.msp` | ☐ |
| P8 | Chat agent connected to the MCP server, one tool call rehearsed | `PYTHONPATH=src:. python3 -m marge.cli mcp --db <db-path> --actor manager@demo.msp --role account_manager` — check `mcp --self-test` first | ☐ |
| P9 | Ticketing tool open, empty queue, ready to receive the renegotiation task | manual step in the demo ticketing app | ☐ |
| P10 | Inbox open with the review email (demo mailbox) | manual step, demo mailbox only | ☐ |
| P11 | Screen: 1920×1080, browser zoom 125 %, notifications off, terminal cleared, no notification banners | manual | ☐ |
| P12 | Two demo accounts ready (account manager + admin), both pre-logged in in separate browser profiles | manual | ☐ |
| P13 | Rehearsal run of all 7 shots end to end, once, without recording | manual | ☐ |

> Filming rule: never type a long command live. Commands are pre-typed in a scratch terminal and pasted, or shown in a prepared pane.

### 1.2 Hide (mandatory masking, checked frame by frame before publishing)

- **E-mail addresses** — only demo aliases (`manager@demo.msp`, `finance@demo.msp`) may appear. Real mailboxes, personal names and customer domains are blurred.
- **Tokens and secrets** — no API key, session cookie, `Authorization` header, `.env`, CLI profile or DB connection string may be visible. Blur the browser DevTools network panel while the calls are shown, or crop it.
- **AWS account IDs** — the 12-digit account number must never be readable (console header, ARN, S3 bucket name, CloudTrail event, QuickSight user). Blur it, or use a dedicated throwaway demo account.
- Also mask: QuickSight account identifiers, internal ticket IDs that could identify a real customer, browser bookmarks, and the OS taskbar if it shows personal items.

---

## 2. Shot-by-shot (the 7 shots of `docs/SPEC.fr.md` §19.2)

| Shot | Time / duration | What we see (exact commands on screen) | Voice-over (verbatim) | On-screen text |
|---|---|---|---|---|
| **1** | 0:00 → 0:20 (**20 s**) | Fast cuts: ticket board, billing spreadsheet, a stack of contracts. Then a terminal: `PYTHONPATH=src:. python3 -m marge.cli version` | A managed service provider runs on three tools: ticketing, billing spreadsheets, and contracts nobody re-reads. Invoices go out, but no one can answer the question that matters: what margin do we make on each client? Some clients are served at a loss, and hours are given away without anyone knowing. | **3 tools. No per-client margin.** |
| **2** | 0:20 → 0:50 (**30 s**) | Portal, contract page. Contract uploaded → clauses extracted → **each clause next to the source text**, one click "Validate". Then the matching queue: 49 alias proposals, one click "Approve all". Terminal in a corner: `PYTHONPATH=src:. python3 -m marge.cli serve --db <db-path> --auth-mode dev` | This is Marge. Drop a contract in: Bedrock Data Automation reads it and extracts every clause. The portal shows each extracted clause right next to the source text, so a human checks the machine. One click validates the reading. Client names in contracts rarely match the ticketing tool, so Marge proposes matches — forty-nine aliases resolved here — and the account manager approves them in one click. Every step stays auditable. | **Contract → clauses → human validation**<br>**Bedrock Data Automation** |
| **3** | 0:50 → 1:25 (**35 s**) | QuickSight dashboard embedded in the portal: margin ranking of the 12 clients, the two red rows first. Click a client → cost breakdown by month and by cost driver (labor, tooling, licenses). Prepped by `PYTHONPATH=src:. python3 -m marge.cli nightly --db <db-path> --month 2026-10` | Every night, a scheduled pipeline loads tickets, billing and invoices, then recomputes all margins — an EventBridge rule, no human in the loop. The dashboard ranks the twelve clients. Two are in the red: Marchand Distribution at minus thirty-two percent, Blanchard Chimie at minus thirty-one. Click one client: the breakdown shows exactly where the cost comes from — labor, tooling, licenses — month after month. Five clients now sit below the twenty percent threshold. For the first time, per-client profitability fits on one screen. | **5 clients below the 20 % threshold**<br>**2 in the red** |
| **4** | 1:25 → 1:55 (**30 s**) | Unbilled-hours page: one ticket classified "out of scope", the **cited contract clause** under it, a link back to the contract page, one click "Validate". Footer with the monthly total. Queue prepared by `PYTHONPATH=src:. python3 -m marge.cli weekly --db <db-path>` | Where does the money leak? Unbilled hours. A technician closes a ticket; a Bedrock model classifies it as out of scope and quotes the exact contract clause that excludes it. The account manager reads the citation and validates the decision in one click. This month: sixty-one hours, six thousand five hundred fifty euros of work delivered for free. Every citation links back to the contract page. | **61 h unbilled = €6 555** |
| **5** | 1:55 → 2:30 (**35 s**) | Chat agent. Question: "Why did Girard BTP lose ten margin points?" → answer with the drivers. Then a price-hike simulation (+8 %) → margin recomputed. Then the agent creates the task; **cut to the ticketing tool where the task appears, assigned, with the figures**. MCP server running in a side pane: `PYTHONPATH=src:. python3 -m marge.cli mcp --db <db-path> --actor manager@demo.msp --role account_manager`; tool names visible: `get_margin_breakdown`, `draft_extra_billing_proposal`, `create_renegotiation_task` | The chat agent sits on top of all of it through an MCP server, exposed to the model as real tools. Ask: why did Girard BTP lose ten margin points? The agent answers from the data: labor cost rose, revenue stayed flat. Then simulate a price increase of eight percent — the agent recomputes the margin live. One decision, and the agent calls create renegotiation task: the task appears in the ticketing tool, assigned, with the figures attached — the loop closes where the work happens. | **Ask the data. Create the task.**<br>**MCP: create_renegotiation_task** |
| **6** | 2:30 → 2:45 (**15 s**) | Email client, demo inbox: the monthly review email from the account manager, sections scrolling: global margin, root causes, unbilled hours, renewals, three decisions. Text generated by `PYTHONPATH=src:. python3 -m marge.cli monthly --db <db-path> --month 2026-10` | On the first of each month, the review lands in every account manager's inbox: margin, root causes, unbilled hours, renewals, three decisions to take. The meeting no longer starts with spreadsheet digging — it starts from a finished document. | **The monthly review, on its own.** |
| **7** | 2:45 → 3:00 (**15 s**) | Architecture diagram (from `docs/`), the three measured numbers, then the repository URL and the install command `git clone` + `make demo` | The whole stack runs on AWS: S3, Glue, Athena, QuickSight, Bedrock, EventBridge, deployed by one SAM template. Another MSP installs it in a day, points it at its own tools, and finds its own lost margin. | **One SAM template. Another MSP, one day.** |

---

## 3. Proving that a real AWS AI service is called

The three AI moments must be *shown as calls*, not asserted by the voice-over.

| Shot | AWS AI service called | What proves it on screen | Capture plan |
|---|---|---|---|
| 2 | **Amazon Bedrock Data Automation** — reads the contract, extracts the clauses | The extraction result in the portal **plus** the service metadata (model / job id + timestamp) in a side pane or DevTools response | Film a 5 s insert of the response headers/metadata; mask the AWS account id in any ARN |
| 4 | **Amazon Bedrock model** — classifies a ticket as out of scope and quotes the clause | The classification answer containing the **cited clause**, with the model id and the request id visible in the log line | Keep the server log line (model + request id) legible for 2 s in the edit |
| 5 | **MCP server** — `create_renegotiation_task` | The MCP tool-call line in the server pane, then the task materialising in the ticketing tool | Film both; the cut is the proof |

**Offline fallback plan (if AWS is unavailable on the day).**
Run the same three moments with the local fallback: the **local extractor** for the contract clauses and the **local rules model** for ticket classification, with the local MCP server (`marge.cli mcp --self-test` proves the tool layer offline). Everything else in the script is unchanged.
**Mandatory:** state in the YouTube description which segments were recorded with the offline fallback (e.g. "Segments 2 and 4 were recorded with the local fallback; no AWS AI service was called in this take."). Never present the fallback as a live AWS call, and never claim an AWS call that did not happen.

---

## 4. The three impact numbers

| # | Impact | Value | Command that displays it | Shown in |
|---|---|---|---|---|
| I1 | **Time to prepare the monthly review** | `[to measure on the live demo]` — record the wall-clock time of the review generation and the manual baseline it replaces, on the deployed stack | `time PYTHONPATH=src:. python3 -m marge.cli monthly --db <db-path> --month 2026-10` (plus the manual baseline, measured once on the demo account) | Shot 6 |
| I2 | **Value of the unbilled hours detected** | **61.00 h = €6 555.00** for 2026-10 (offline seeded demo, this branch) — re-measure and replace on the deployed stack: `[to measure on the live demo]` | `PYTHONPATH=src:. python3 -m marge.cli demo --auto-validate --review` → section "Heures non facturées" (also `marge.cli weekly --db <db-path>`) | Shot 4 |
| I3 | **Clients below the threshold identified** | **5 clients below the 20 % threshold, 2 of them in the red** — Marchand Distribution −31.7 %, Blanchard Chimie −30.8 % (offline seeded demo) — `[to measure on the live demo]` | `PYTHONPATH=src:. python3 -m marge.cli demo --auto-validate --review` → section "Clients sous le seuil de 20.0 %" (also the QuickSight ranking) | Shot 3 |

**Rules:** these three values come from a real, reproducible offline run of the seeded demo — no other figure may be stated on camera. Any figure that depends on the deployed environment is spoken as `[to measure on the live demo]` until it has been measured on the deployment, and then the measured value replaces the placeholder in this file before shooting. No invented numbers, ever.

---

## 5. Full voice-over, end to end

Read at a calm pace of **150 words per minute** (2.5 words/second). One paragraph per shot, in shot order.

<!-- VO-START -->

A managed service provider runs on three tools: ticketing, billing spreadsheets, and contracts nobody re-reads. Invoices go out, but no one can answer the question that matters: what margin do we make on each client? Some clients are served at a loss, and hours are given away without anyone knowing.

This is Marge. Drop a contract in: Bedrock Data Automation reads it and extracts every clause. The portal shows each extracted clause right next to the source text, so a human checks the machine. One click validates the reading. Client names in contracts rarely match the ticketing tool, so Marge proposes matches — forty-nine aliases resolved here — and the account manager approves them in one click. Every step stays auditable.

Every night, a scheduled pipeline loads tickets, billing and invoices, then recomputes all margins — an EventBridge rule, no human in the loop. The dashboard ranks the twelve clients. Two are in the red: Marchand Distribution at minus thirty-two percent, Blanchard Chimie at minus thirty-one. Click one client: the breakdown shows exactly where the cost comes from — labor, tooling, licenses — month after month. Five clients now sit below the twenty percent threshold. For the first time, per-client profitability fits on one screen.

Where does the money leak? Unbilled hours. A technician closes a ticket; a Bedrock model classifies it as out of scope and quotes the exact contract clause that excludes it. The account manager reads the citation and validates the decision in one click. This month: sixty-one hours, six thousand five hundred fifty euros of work delivered for free. Every citation links back to the contract page.

The chat agent sits on top of all of it through an MCP server, exposed to the model as real tools. Ask: why did Girard BTP lose ten margin points? The agent answers from the data: labor cost rose, revenue stayed flat. Then simulate a price increase of eight percent — the agent recomputes the margin live. One decision, and the agent calls create renegotiation task: the task appears in the ticketing tool, assigned, with the figures attached — the loop closes where the work happens.

On the first of each month, the review lands in every account manager's inbox: margin, root causes, unbilled hours, renewals, three decisions to take. The meeting no longer starts with spreadsheet digging — it starts from a finished document.

The whole stack runs on AWS: S3, Glue, Athena, QuickSight, Bedrock, EventBridge, deployed by one SAM template. Another MSP installs it in a day, points it at its own tools, and finds its own lost margin.

<!-- VO-END -->

**Measured word count and duration:**

```bash
# Voice-over word count, extracted between the markers (first occurrence of each):
s=$(grep -n 'VO-START' docs/VIDEO-SCRIPT.md | head -1 | cut -d: -f1)
e=$(grep -n 'VO-END'   docs/VIDEO-SCRIPT.md | head -1 | cut -d: -f1)
sed -n "$((s+1)),$((e-1))p" docs/VIDEO-SCRIPT.md | wc -w
# → 432

# 432 words / 150 wpm = 2.88 min = 172.8 s  -> inside the 180 s budget, ~7 s of breathing room
```

Per-shot check at 150 wpm (words → seconds): 50 → 20.0 | 71 → 28.4 | 84 → 33.6 | 66 → 26.4 | 86 → 34.4 | 39 → 15.6 | 36 → 14.4.

---

## 6. Compliance checklist before publication

- [ ] **Duration**: final cut ≤ 3:00 (target 2:55–3:00). Check the exported file, not the timeline.
- [ ] **Language**: voice-over in English, on-screen text in English, no French subtitles burned in.
- [ ] **No third-party brand**: only AWS and this project are named. No other logo, product name, customer name, or competitor on screen. Blur unrelated tabs and the taskbar.
- [ ] **No third-party music**: royalty-free only, or silent. No copyrighted track, no song from a TV show, no "AI-generated music from a commercial generator" without a licence.
- [ ] **No secrets visible**: frame-by-frame check of e-mails, tokens, API keys, cookies, `.env`, AWS account IDs, ARNs, bucket names.
- [ ] **Demo data only**: every client, contract, amount and ticket on screen comes from the seeded fictional dataset.
- [ ] **Numbers spoken match the screen**: the three impact numbers of §4 are read as measured; deployment-dependent ones are replaced by their measured value before shooting.
- [ ] **Video is PUBLIC** on YouTube (unlisted/private links are not accepted by the submission page), link pasted in the Devpost submission.
- [ ] **Repository link shared** with `testing@devpost.com` and `aws-msp@amazon.com` (public repo `BaptisteFaisy/marge-msp`, branch `main`).
- [ ] **Demo credentials published**: demo accounts and the exact start commands in the video description (`marge.cli generate`, `marge.cli demo --auto-validate --review`, `marge.cli serve --db … --auth-mode dev`).
- [ ] **Offline fallback disclosed** in the YouTube description if any segment was recorded without AWS (§3).
- [ ] **Description complete**: what the product does, the three impact numbers, the repo link, the demo credentials, the fallback note if any.

---

## 7. What can be filmed today (no AWS) vs what needs the deployment

| Filmable today, without AWS | Requires the deployed AWS environment |
|---|---|
| `marge.cli generate` — dataset, contracts, invoices | `serve --auth-mode cognito` — real sign-in, real accounts |
| `marge.cli demo --auto-validate --review` — every figure of §4 (offline, seeded) | Bedrock Data Automation — real contract ingestion in shot 2 |
| `marge.cli serve --db <db> --auth-mode dev` — the whole portal UI | Bedrock model — real ticket classification in shot 4 |
| `marge.cli nightly` — margin recomputation (local scheduler) | EventBridge — the real nightly trigger shown in shot 3 |
| `marge.cli weekly` — out-of-scope queue | QuickSight embedded dashboard + the Quick console (shot 3) |
| `marge.cli monthly` — review text, pasted into a demo mailbox | SES — real delivery of the review email (shot 6) |
| `marge.cli mcp --self-test` + a local agent on the MCP server (shot 5, tool call + task creation) | S3 / Glue / Athena lake + the deployed MCP server behind the agent |
| `marge.cli smoke`, `marge.cli eval`, `marge.cli assets --check` | CloudTrail / console inserts proving the AWS calls (§3) |
| The 7 shots in their offline-fallback variant (§3) | CloudFormation/SAM deploy of the whole stack (shot 7) |
| The architecture diagram, the closing shot, the compliance pass | The measured values of §4 on real data (I1 in particular) |

**Shooting rule:** if the deployment is not ready, film the offline variant of the whole script and disclose it (§3). Do not fake an AWS console: a mock console is worse than the honest fallback.
