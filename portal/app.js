/* Marge validation portal — vanilla JS, no build step (spec 16, EF-VAL-01).
 *
 * All figures come from the API (marge.calc on the server); the model never
 * computes a number (ENF-IA-01). Ticket and contract text is rendered with
 * textContent, never innerHTML: untrusted text stays data (ENF-IA-03).
 */
"use strict";

const $ = (id) => document.getElementById(id);

function defaultApiBase() {
  /* Local: the API runs next to the portal on localhost. Deployed: CloudFront
   * proxies /v1/* to API Gateway, so the base is the empty string (same
   * origin) and no CORS header is needed. */
  const here = window.location.origin || "";
  if (here.startsWith("http://localhost") || here.startsWith("http://127.")) return here;
  return "";
}

function apiBase() {
  return $("api-base").value.trim().replace(/\/+$/, "");
}

function authHeaders() {
  /* Cognito mode: the API reads the identity from the verified token.
   * Dev mode: the identity comes from the two headers below. */
  const token = typeof bearerToken === "function" ? bearerToken() : "";
  if (token) return { Authorization: "Bearer " + token };
  return {
    "X-Actor-Id": $("actor-id").value || "anonymous",
    "X-Actor-Role": $("actor-role").value,
  };
}

function setStatus(text) {
  $("status").textContent = text;
}

async function api(path, options = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, authHeaders(), options.headers || {});
  const response = await fetch(apiBase() + path, Object.assign({}, options, { headers }));
  if (!response.ok) {
    let detail = response.status + " " + response.statusText;
    try {
      const body = await response.json();
      if (body && body.detail) detail = body.detail;
    } catch (err) { /* keep the status line */ }
    throw new Error(detail);
  }
  return response.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function askReason(action, subject) {
  const reason = window.prompt("Reason for " + action + " of " + subject + " (audited):");
  return reason && reason.trim() ? reason.trim() : null;
}

async function decide(path, payload, label) {
  try {
    await api(path, { method: "POST", body: JSON.stringify(payload) });
    setStatus(label + " recorded.");
    await refresh();
  } catch (err) {
    setStatus("Error: " + err.message);
  }
}

/* ---------------------------------------------------------------- matches */

async function renderMatches() {
  const host = $("matches-list");
  host.textContent = "";
  let rows;
  try {
    rows = await api("/v1/matches");
  } catch (err) {
    host.appendChild(el("p", "error", "Cannot load matches: " + err.message));
    return;
  }
  if (!rows.length) {
    host.appendChild(el("p", "empty", "No match proposals."));
    return;
  }
  const table = el("table");
  const head = table.createTHead().insertRow();
  ["Match", "Client", "Source", "Source id", "Confidence", "Status", "Actions"].forEach((h) =>
    head.appendChild(el("th", null, h)));
  const body = table.createTBody();
  rows.forEach((m) => {
    const tr = body.insertRow();
    [m.match_id, m.client_id, m.source, m.source_id, m.confidence, m.status].forEach((v) =>
      tr.appendChild(el("td", null, String(v))));
    const actions = tr.insertCell();
    if (m.status === "PENDING") {
      actions.appendChild(matchButton(m.match_id, "APPROVED", "Validate", "btn-ok"));
      actions.appendChild(matchButton(m.match_id, "REJECTED", "Reject", "btn-ko"));
    } else {
      actions.appendChild(el("span", "muted", m.decided_by || ""));
    }
  });
  host.appendChild(table);
}

function matchButton(matchId, decision, label, cssClass) {
  const button = el("button", cssClass, label);
  button.addEventListener("click", async () => {
    const reason = askReason(decision.toLowerCase(), "match " + matchId);
    if (!reason) return;
    await decide("/v1/matches/" + encodeURIComponent(matchId) + "/decision",
      { decision, reason }, "Match decision");
  });
  return button;
}

/* -------------------------------------------------------------- contracts */

async function renderContracts() {
  const host = $("contracts-list");
  host.textContent = "";
  let rows;
  try {
    rows = await api("/v1/contracts");
  } catch (err) {
    host.appendChild(el("p", "error", "Cannot load contracts: " + err.message));
    return;
  }
  if (!rows.length) {
    host.appendChild(el("p", "empty", "No contracts visible for this role."));
    return;
  }
  const list = el("ul", "contract-picker");
  rows.forEach((c) => {
    const item = el("li");
    const button = el("button", "link", c.contract_id + " v" + c.version + " — " + c.status);
    button.addEventListener("click", () => openContract(c.contract_id, c.version));
    item.appendChild(button);
    list.appendChild(item);
  });
  host.appendChild(list);
}

async function openContract(contractId, version) {
  const host = $("contract-detail");
  host.textContent = "";
  let contract;
  try {
    contract = await api("/v1/contracts/" + encodeURIComponent(contractId) + "?version=" + version);
  } catch (err) {
    host.appendChild(el("p", "error", "Cannot load contract: " + err.message));
    return;
  }
  host.appendChild(el("h3", null, contract.contract_id + " v" + contract.version +
    " (" + contract.status + ")"));
  host.appendChild(fieldsTable(contract));
  host.appendChild(contractActions(contract));
}

const FIELD_ORDER = [
  "customer_name", "start_date", "end_date", "renewal_terms", "termination_notice",
  "monthly_subscription", "currency", "included_hours_per_month", "extra_hour_rate",
  "service_hours", "penalties",
];

function fieldsTable(contract) {
  const table = el("table", "fields");
  const head = table.createTHead().insertRow();
  ["Field", "Extracted value", "Source passage (EF-CTR-02)", "Actions"].forEach((h) =>
    head.appendChild(el("th", null, h)));
  const body = table.createTBody();
  const spans = contract.fields.spans || {};
  const names = FIELD_ORDER.concat(Object.keys(contract.fields).filter(
    (k) => !FIELD_ORDER.includes(k) && k !== "spans" && k !== "services_included" && k !== "exclusions"));
  names.forEach((name) => {
    const tr = body.insertRow();
    tr.appendChild(el("td", null, name));
    const value = contract.fields[name];
    tr.appendChild(el("td", null, value === null || value === undefined ? "" : String(value)));
    const span = spans[name];
    tr.appendChild(el("td", "quote", span && span.quote ? "« " + span.quote + " »" : "—"));
    const actions = tr.insertCell();
    const correct = el("button", "btn-edit", "Correct");
    correct.addEventListener("click", () => correctField(contract, name, value));
    actions.appendChild(correct);
  });
  ["services_included", "exclusions"].forEach((name) => {
    const tr = body.insertRow();
    tr.appendChild(el("td", null, name));
    const cell = tr.insertCell();
    (contract.fields[name] || []).forEach((line) => cell.appendChild(el("div", null, "• " + line)));
    tr.appendChild(el("td", "quote", "—"));
    tr.insertCell();
  });
  return table;
}

async function correctField(contract, name, current) {
  const raw = window.prompt("New value for " + name + ":", current === null ? "" : String(current));
  if (raw === null) return;
  const reason = askReason("correction", contract.contract_id + " field " + name);
  if (!reason) return;
  try {
    await api("/v1/contracts/" + encodeURIComponent(contract.contract_id) + "/fields", {
      method: "PUT",
      body: JSON.stringify({ reason, fields: { [name]: raw } }),
    });
    setStatus("Field " + name + " corrected.");
    await openContract(contract.contract_id, contract.version);
  } catch (err) {
    setStatus("Error: " + err.message);
  }
}

function contractActions(contract) {
  const box = el("div", "actions");
  const validate = el("button", "btn-ok", "Validate contract");
  validate.addEventListener("click", async () => {
    const reason = askReason("validation", contract.contract_id);
    if (!reason) return;
    try {
      await api("/v1/contracts/" + encodeURIComponent(contract.contract_id) + "/validate", {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setStatus("Contract validated.");
      await refresh();
      await openContract(contract.contract_id, contract.version);
    } catch (err) {
      setStatus("Error: " + err.message);
    }
  });
  const correct = el("button", "btn-edit", "Correct");
  correct.addEventListener("click", () => {
    const name = window.prompt("Field name to correct:", "monthly_subscription");
    if (name) correctField(contract, name, contract.fields[name]);
  });
  box.appendChild(validate);
  box.appendChild(correct);
  return box;
}

/* --------------------------------------------------------- classifications */

async function renderClassifications() {
  const host = $("classifications-list");
  host.textContent = "";
  let rows;
  try {
    rows = await api("/v1/classifications?status=pending");
  } catch (err) {
    host.appendChild(el("p", "error", "Cannot load classifications: " + err.message));
    return;
  }
  if (!rows.length) {
    host.appendChild(el("p", "empty", "Nothing waiting for a decision."));
    return;
  }
  const table = el("table");
  const head = table.createTHead().insertRow();
  ["Intervention", "Client", "Class", "Confidence", "Cited clause", "Hours", "Actions"]
    .forEach((h) => head.appendChild(el("th", null, h)));
  const body = table.createTBody();
  rows.forEach((c) => {
    const tr = body.insertRow();
    [c.intervention_id, c.client_id, c.work_class, c.confidence, c.cited_clause || "—", c.billable_hours]
      .forEach((v) => tr.appendChild(el("td", null, String(v))));
    const actions = tr.insertCell();
    actions.appendChild(classButton(c, "APPROVED", "Validate", "btn-ok"));
    actions.appendChild(classButton(c, "CORRECTED", "Correct", "btn-edit"));
    actions.appendChild(classButton(c, "REJECTED", "Discard", "btn-ko"));
  });
  host.appendChild(table);
}

function classButton(cls, decision, label, cssClass) {
  const button = el("button", cssClass, label);
  button.addEventListener("click", async () => {
    const reason = askReason(decision.toLowerCase(), "intervention " + cls.intervention_id);
    if (!reason) return;
    const payload = { decision, reason };
    if (decision === "CORRECTED") {
      const raw = window.prompt("New class (IN_SCOPE / OUT_OF_SCOPE / UNCERTAIN):", cls.work_class);
      if (!raw) return;
      payload.corrected_value = { work_class: raw };
    }
    await decide("/v1/classifications/" + encodeURIComponent(cls.intervention_id) + "/decision",
      payload, "Classification decision");
  });
  return button;
}

/* ------------------------------------------------------------- navigation */

async function refresh() {
  const active = document.querySelector(".tab.active");
  if (!active) return;
  if (active.dataset.screen === "matches") await renderMatches();
  if (active.dataset.screen === "contracts") { await renderContracts(); }
  if (active.dataset.screen === "classifications") await renderClassifications();
}

function showScreen(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.screen === name));
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === "screen-" + name));
  refresh();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => showScreen(tab.dataset.screen));
});
$("actor-role").addEventListener("change", refresh);
$("actor-id").addEventListener("change", refresh);

/* The API base defaults to the origin that serves the page, unless the URL
 * carries ?api=… (useful when the portal is opened from a local file). */
const urlApi = new URLSearchParams(window.location.search).get("api");
$("api-base").value = urlApi !== null ? urlApi : defaultApiBase();

initAuth()
  .catch(() => setStatus("auth config unavailable: dev mode"))
  .then(() => showScreen("matches"));
