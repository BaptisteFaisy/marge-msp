/* Marge margin screen — the margin of every client, month by month (EF-CAL-01,
 * EF-TDB-01), and the client sheet decomposed down to its source lines
 * (ENF-TRA-01). Vanilla JS, no build step.
 *
 * Everything is rendered from the API: the portal never computes a figure
 * (ENF-IA-01), and it renders with textContent so a ticket or contract string
 * stays data, never an instruction (ENF-IA-03).
 */
"use strict";

async function renderMargins() {
  const host = $("margins-list");
  const detail = $("margin-detail");
  host.textContent = "";
  detail.textContent = "";
  let rows;
  try {
    rows = await api("/v1/margins");
  } catch (err) {
    host.appendChild(el("p", "error", "Cannot load margins: " + err.message));
    return;
  }
  if (!rows.length) {
    host.appendChild(el("p", "empty", "No margin computed yet. Run `marge demo` first."));
    return;
  }
  const months = [];
  rows.forEach((row) => {
    if (!months.includes(row.month)) months.push(row.month);
  });
  const select = el("select");
  months.forEach((month) => {
    const option = el("option", null, month);
    option.value = month;
    select.appendChild(option);
  });
  const picker = el("div", "picker");
  picker.appendChild(el("label", null, "Month"));
  picker.appendChild(select);
  host.appendChild(picker);
  const redraw = () => {
    detail.textContent = "";
    renderMarginTable(rows.filter((row) => row.month === select.value), host);
  };
  select.addEventListener("change", redraw);
  redraw();
}

function renderMarginTable(rows, host) {
  const table = el("table");
  const head = table.createTHead().insertRow();
  ["Client", "Revenue", "Costs", "Margin", "Margin rate", "Coverage", "State", "Decomposition"].forEach(
    (title) => head.appendChild(el("th", null, title))
  );
  const body = table.createTBody();
  rows.forEach((row) => {
    const tr = body.insertRow();
    const label = row.client_name ? row.client_name + " (" + row.client_id + ")" : row.client_id;
    [
      label,
      row.revenue_total,
      row.cost_total,
      row.margin,
      row.margin_rate_percent + " %",
      row.coverage_percent + " %",
      row.state,
    ].forEach((value) => tr.appendChild(el("td", null, String(value))));
    const actions = tr.insertCell();
    const why = el("button", "link", "Why?");
    why.addEventListener("click", () => openMarginWhy(row.client_id, row.month));
    actions.appendChild(why);
    if (Number(row.margin) < 0) tr.classList.add("loss");
  });
  host.appendChild(table);
}

async function openMarginWhy(clientId, month) {
  const host = $("margin-detail");
  host.textContent = "";
  let why;
  try {
    why = await api("/v1/margins/" + encodeURIComponent(clientId) + "/" + encodeURIComponent(month) + "/why");
  } catch (err) {
    host.appendChild(el("p", "error", "Cannot load the decomposition: " + err.message));
    return;
  }
  host.appendChild(el("h3", null, why.client_id + " — " + month + " (" + why.state + ")"));
  host.appendChild(marginKpis(why));
  host.appendChild(postsTable(why.posts || []));
  if (why.hours) host.appendChild(hoursTable(why.hours));
  host.appendChild(linesTable(why.lines || []));
}

function marginKpis(why) {
  const table = el("table", "fields");
  const body = table.createTBody();
  const rows = [
    ["Revenue", why.revenue_total],
    ["Costs", why.cost_total],
    ["Margin", why.margin],
    ["Margin rate", why.margin_rate_percent + " %"],
    ["Coverage", why.coverage_percent + " %"],
    ["Calculation version", String(why.calc_version)],
  ];
  if (why.incomplete_reason) rows.push(["Incomplete because", why.incomplete_reason]);
  rows.forEach(([name, value]) => {
    const tr = body.insertRow();
    tr.appendChild(el("td", null, name));
    tr.appendChild(el("td", null, value === null || value === undefined ? "" : String(value)));
  });
  return table;
}

function postsTable(posts) {
  const table = el("table");
  const head = table.createTHead().insertRow();
  ["Post", "Amount"].forEach((title) => head.appendChild(el("th", null, title)));
  const body = table.createTBody();
  posts.forEach((post) => {
    const tr = body.insertRow();
    tr.appendChild(el("td", null, post.post));
    tr.appendChild(el("td", null, post.amount));
  });
  return table;
}

function hoursTable(hours) {
  const table = el("table", "fields");
  const body = table.createTBody();
  const rows = [
    ["Included quota (h)", hours.included_quota],
    ["Consumed (h)", hours.consumed_hours],
    ["Out of scope, validated (h)", hours.out_of_scope_validated_hours],
    ["Over quota (h)", hours.over_quota_hours],
    ["Billed extra hours (h)", hours.billed_extra_hours],
    ["Unbilled (h)", hours.unbilled_hours],
    ["Unbilled value", hours.unbilled_value],
  ];
  rows.forEach(([name, value]) => {
    const tr = body.insertRow();
    tr.appendChild(el("td", null, name));
    tr.appendChild(el("td", null, String(value)));
  });
  return table;
}

function linesTable(lines) {
  const table = el("table");
  const head = table.createTHead().insertRow();
  ["Post", "Source line", "Amount", "Source"].forEach((title) => head.appendChild(el("th", null, title)));
  const body = table.createTBody();
  lines.forEach((line) => {
    const tr = body.insertRow();
    const source = (line.source_kind || "") + (line.source_id ? " · " + line.source_id : "");
    [line.post, line.label, line.amount, source].forEach((value) =>
      tr.appendChild(el("td", null, value === null || value === undefined ? "" : String(value)))
    );
  });
  return table;
}
