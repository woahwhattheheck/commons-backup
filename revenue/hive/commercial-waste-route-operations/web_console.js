"use strict";
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="console-key"]').content;
let state = null, busy = false, pending = null, loadedDate = null, selectedInvoice = null;
let stateGeneration = 0, routeGeneration = 0, invoiceGeneration = 0;
const retryKeys = new Map();

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function say(message, error = false) {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
}
function failure(error) { say(error.message || String(error), true); }
function amount(value, currency = "") { return `${value ?? "unknown"} ${currency} minor units`.replace(/ +/g, " "); }
function button(label, action, secondary = false) {
  const b = node("button", label, secondary ? "secondary" : "");
  b.type = "button";
  b.addEventListener("click", () => Promise.resolve().then(action).catch(failure));
  return b;
}
function empty(target, message) { target.replaceChildren(node("p", message, "empty")); }
function table(target, headers, records) {
  if (!records.length) { empty(target, "No retained records in this view."); return; }
  const t = node("table"), head = node("tr"), thead = node("thead"), body = node("tbody");
  for (const label of headers) head.append(node("th", label));
  thead.append(head); t.append(thead, body);
  for (const record of records) {
    const tr = node("tr");
    for (const value of record) {
      const td = node("td");
      if (value instanceof Node) td.append(value); else td.textContent = String(value ?? "—");
      tr.append(td);
    }
    body.append(tr);
  }
  target.replaceChildren(t);
}
async function request(path, options = {}) {
  const response = await fetch(path, {...options, headers: {"X-Console-Key": token, ...(options.headers || {})}, cache: "no-store"});
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const error = await response.json(); message = `${error.error}: ${error.message}`; } catch (_) {}
    throw new Error(message);
  }
  return response;
}
async function json(path, options) { return (await request(path, options)).json(); }
function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob), a = node("a");
  a.href = url; a.download = name; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
async function download(params, name) {
  const response = await request(`/api/download?${new URLSearchParams(params)}`);
  saveBlob(await response.blob(), name);
}
function showResult(value) {
  $("result").textContent = JSON.stringify(value, null, 2);
  $("last-result").open = true;
  if (value.op_key) $("operation-key").value = value.op_key;
}
function showPending(value) {
  pending = value;
  $("retry-box").hidden = !value;
  $("retry-key").textContent = value ? value.op_key : "";
}
async function perform(action, args, exactRequest = null) {
  if (busy) return;
  const fingerprint = JSON.stringify({action, args});
  if (!retryKeys.has(fingerprint)) retryKeys.set(fingerprint, `web:${crypto.randomUUID()}`);
  const body = exactRequest || {action, args, op_key: retryKeys.get(fingerprint)};
  if (pending && !exactRequest) {
    throw new Error("Resolve the pending operation first: retry its exact request or look up its key in Activity.");
  }
  busy = true;
  const controls = Array.from(document.querySelectorAll("button"), b => [b, b.disabled]);
  controls.forEach(([b]) => b.disabled = true);
  showPending(body);
  say(`Saving ${action}. Operation key: ${body.op_key}`);
  let saved = false;
  try {
    const result = await json("/api/command", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    saved = true;
    showPending(null); showResult(result);
    say(`Saved ${action}. Operation key: ${result.op_key}. Nothing was sent or charged.`);
    if (action === "route") $("route-date").value = body.args.date;
    await refresh();
    if (action === "invoice") await openInvoice(result.result.invoice_id);
    else if ($("route-date").value && (action === "route" || loadedDate)) await loadRoute($("route-date").value);
  } catch (error) {
    if (saved) say(`Change was saved, but refreshing its view failed: ${error.message}. Use Refresh workspace; do not create a replacement operation.`, true);
    else {
      showResult({op_key: body.op_key, error: error.message, request: body});
      say(`${error.message} The original request and key are retained below for exact retry or lookup.`, true);
    }
  } finally {
    busy = false;
    controls.forEach(([b, disabled]) => { if (b.isConnected) b.disabled = disabled; });
    $("print-invoice").disabled = !selectedInvoice;
    $("manifest-fields").disabled = Boolean(state?.initialized);
  }
}
function customerCurrency(id) { return state?.customers.find(c => c.id === id)?.currency || ""; }
function makeInput(label, type = "text", value = "") {
  const wrapper = node("label", label), input = node("input");
  input.type = type; input.value = value; wrapper.append(input);
  return {wrapper, input};
}
function stopCard(stop, serviceDate) {
  const card = node("article", null, "stop");
  card.append(node("span", stop.status, `tag${stop.status === "EXCEPTION_OPEN" ? " alert" : ""}`),
    node("h3", `${stop.customer_name} · ${stop.site_name}`),
    node("p", `${serviceDate} · ${stop.container_label} · ${stop.service_code}`),
    node("p", stop.stop_id, "muted small"),
    node("p", `Scheduled: ${amount(stop.price_minor, customerCurrency(stop.customer_id))}`),
    node("p", `Recorded charge: ${amount(stop.charge_minor, customerCurrency(stop.customer_id))}`));
  if (stop.exception_code) card.append(node("p", `Exception: ${stop.exception_code}`));
  if (stop.resolution) card.append(node("p", `Resolution: ${stop.resolution}${stop.makeup_service_date ? ` · ${stop.makeup_service_date}` : ""}`));
  if (stop.invoice_id) card.append(node("p", `Retained draft: ${stop.invoice_id}`, "muted"));
  if (!state?.business_date || serviceDate > state.business_date) {
    card.append(node("p", "Planning only: this service date has not arrived.", "muted"));
    return card;
  }
  if (stop.status === "PENDING") {
    card.append(button("Record serviced", async () => {
      if (confirm(`Record actual completed service for ${stop.stop_id}?`)) await perform("record", {stop_id: stop.stop_id, outcome: "SERVICED"});
    }));
    const form = node("form"), reason = makeInput("Skipped-service exception code", "text", "BLOCKED_ACCESS");
    reason.input.required = true; reason.input.maxLength = 240;
    const submit = node("button", "Record skipped service", "secondary"); submit.type = "submit";
    form.append(reason.wrapper, submit);
    form.addEventListener("submit", event => { event.preventDefault(); perform("record", {stop_id: stop.stop_id, outcome: "SKIPPED", exception_code: reason.input.value}).catch(failure); });
    card.append(form);
  } else if (stop.status === "EXCEPTION_OPEN") {
    const form = node("form"), label = node("label", "Resolution"), select = node("select");
    for (const [value, title] of [["NO_SERVICE_NO_CHARGE", "No service — no charge"], ["MAKEUP_COMPLETED_BILLABLE", "Actual completed makeup — billable"]]) {
      const option = node("option", title); option.value = value; select.append(option);
    }
    label.append(select);
    const date = makeInput("Actual makeup service date", "date");
    date.input.min = serviceDate; date.input.max = state.business_date; date.wrapper.hidden = true;
    select.addEventListener("change", () => {
      const needed = select.value === "MAKEUP_COMPLETED_BILLABLE";
      date.wrapper.hidden = !needed; date.input.required = needed;
    });
    const submit = node("button", "Resolve retained exception"); submit.type = "submit";
    form.append(label, date.wrapper, submit);
    form.addEventListener("submit", event => {
      event.preventDefault();
      const args = {stop_id: stop.stop_id, resolution: select.value};
      if (select.value === "MAKEUP_COMPLETED_BILLABLE") args.makeup_service_date = date.input.value;
      if (confirm(`Retain this resolution for ${stop.stop_id}? This does not dispatch a vehicle or charge a customer.`)) perform("resolve", args).catch(failure);
    });
    card.append(form);
  }
  return card;
}
async function refresh() {
  const generation = ++stateGeneration;
  const result = await json("/api/state");
  if (generation !== stateGeneration) return;
  state = result;
  $("business-clock").textContent = result.initialized ? `Business date: ${result.business_date} · Retained timezone: ${result.business_timezone}` : "New workspace — import a manifest to begin";
  $("manifest-fields").disabled = result.initialized;
  $("manifest-panel").open = !result.initialized;
  $("setup-state").textContent = result.initialized ? "The retained manifest is initialized. Catalog and timezone cannot be replaced through this console." : "Choose the correct database and initialize it once. The fictional sample is for a separate demonstration database only.";
  for (const id of ["route-date", "period-start", "period-end"]) if (!$(id).value && result.business_date) $(id).value = result.business_date;
  $("period-end").max = result.business_date || "";
  $("period-start").max = result.business_date || "";
  $("metrics").replaceChildren(...[[result.counts.customers, "Customers"], [result.counts.plans, "Recurring plans"], [result.exception_count, "Open exceptions"], [result.counts.invoice_drafts, "Retained drafts"]].map(([n, text]) => {
    const box = node("div", null, "metric"); box.append(node("strong", n), node("span", text)); return box;
  }));
  $("customers").replaceChildren(...result.customers.map(c => { const option = node("option"); option.value = c.id; option.label = `${c.name} · ${c.currency}`; return option; }));
  $("route-history-label").textContent = `Saved route history — showing ${result.routes.length} of ${result.counts.routes} (any other date can be loaded above)`;
  table($("route-history"), ["Date", "Stops", "Pending", "Exceptions", "Open"], result.routes.map(r => [r.service_date, r.stop_count, r.pending, r.exceptions, button("Open route", () => { $("route-date").value = r.service_date; return loadRoute(r.service_date); }, true)]));
  $("exception-count").textContent = `Showing ${result.exceptions.length} of ${result.exception_count} unresolved stops, oldest first. Other stops remain accessible through their route date.`;
  if (result.exceptions.length) $("exception-list").replaceChildren(...result.exceptions.map(s => stopCard(s, s.service_date))); else empty($("exception-list"), "No open exceptions are retained.");
  $("invoice-count").textContent = `Showing ${result.invoices.length} of ${result.counts.invoice_drafts} retained drafts, newest first. Older IDs can be opened below.`;
  table($("invoice-list"), ["Customer", "Period", "Draft total", "Retained ID", "Actions"], result.invoices.map(i => {
    const actions = node("div"); actions.append(button("View", () => openInvoice(i.id), true), button("JSON", () => download({kind: "invoice", id: i.id}, "waste-invoice-DRAFT.json"), true));
    return [i.customer_name, `${i.period_start} – ${i.period_end}`, amount(i.total_minor, i.currency), i.id, actions];
  }));
  const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  table($("plan-list"), ["Customer / site", "Container", "Day", "Service", "Price", "Plan ID"], result.plans.map(p => [`${p.customer_name} / ${p.site_name}`, `${p.container_label} (${p.container_type})`, weekdays[p.weekday], p.service_code, amount(p.price_minor, p.currency), p.id]));
  $("event-count").textContent = `Showing ${result.events.length} of ${result.counts.events} events, newest first. Complete history is available as a download.`;
  table($("event-list"), ["Event", "Action", "Entity", "Operation key"], result.events.map(e => [e.id, e.event_type, e.entity_id, button(e.op_key, () => lookupOperation(e.op_key), true)]));
}
async function loadRoute(date) {
  const generation = ++routeGeneration;
  const result = await json(`/api/route?${new URLSearchParams({date})}`);
  if (generation !== routeGeneration || $("route-date").value !== date) return;
  loadedDate = date;
  $("route-summary").textContent = `${result.route_id} · ${result.stop_count} stops · dates and charges are enforced by the existing desk`;
  $("route-downloads").hidden = false;
  $("stops").replaceChildren(...result.stops.map(s => stopCard(s, date)));
}
async function openInvoice(id) {
  const generation = ++invoiceGeneration;
  const result = await json(`/api/invoice?${new URLSearchParams({id})}`);
  if (generation !== invoiceGeneration) return;
  selectedInvoice = id; $("invoice-id").value = id; $("print-invoice").disabled = false;
  const preview = $("invoice-preview"), lines = node("div", null, "table-wrap");
  lines.tabIndex = 0; lines.setAttribute("role", "region"); lines.setAttribute("aria-label", "Invoice draft line items");
  preview.hidden = false;
  preview.replaceChildren(node("p", "INVOICE DRAFT — NOT SENT / NOT PAID", "draft-heading"), node("h3", result.customer_name), node("p", result.invoice_id, "small"), node("p", `Service period: ${result.period_start} – ${result.period_end}`), node("p", `Retained business date: ${result.business_date}`), node("p", `Draft total: ${amount(result.total_minor, result.currency)}`), lines);
  table(lines, ["Date", "Site / container", "Service / resolution", "Charge (minor units)", "Stop"], result.lines.map(l => [l.service_date, `${l.site_id} / ${l.container_id}`, `${l.service_code} · ${l.resolution || l.status}${l.makeup_service_date ? ` · makeup ${l.makeup_service_date}` : ""}`, l.charge_minor, l.stop_id]));
  preview.append(node("p", `Retained digest: ${result.receipt_digest}`, "small"), node("p", "Prepared from recorded operations. This is not a sent invoice, payment confirmation, or evidence that real-world service occurred.", "muted"), button("Download exact retained draft JSON", () => download({kind: "invoice", id}, "waste-invoice-DRAFT.json"), true));
}
async function lookupOperation(key) {
  const result = await json(`/api/operation?${new URLSearchParams({key})}`);
  showResult(result);
  if (pending?.op_key === key) {
    showPending(null);
    say(result.found ? "The operation is retained. Its saved result is shown in Activity; refreshing the workspace." : "No saved operation exists for that key. The pending request is cleared; correct the inputs or try again.");
    await refresh();
    if (loadedDate && $("route-date").value) await loadRoute($("route-date").value);
  } else say(result.found ? "Saved operation found. See Activity for the exact result." : "No saved operation exists for that key.");
}
function on(id, type, action) { $(id).addEventListener(type, event => { event.preventDefault(); Promise.resolve().then(() => action(event)).catch(failure); }); }
on("refresh", "click", async () => { await refresh(); if (loadedDate) await loadRoute($("route-date").value); say("Workspace refreshed from the retained database."); });
on("route-form", "submit", () => loadRoute($("route-date").value));
on("generate-route", "click", () => { if ($("route-form").reportValidity()) return perform("route", {date: $("route-date").value}); });
$("route-date").addEventListener("change", () => { routeGeneration++; loadedDate = null; $("route-downloads").hidden = true; $("stops").replaceChildren(); $("route-summary").textContent = "Date changed. Load its retained route or generate a plan."; });
for (const b of document.querySelectorAll("[data-route-format]")) b.addEventListener("click", () => { if (loadedDate) download({kind: "route", date: loadedDate, format: b.dataset.routeFormat}, `waste-route-${loadedDate}.${b.dataset.routeFormat === "markdown" ? "md" : b.dataset.routeFormat}`).catch(failure); });
on("manifest-file", "change", async () => {
  const file = $("manifest-file").files[0]; if (!file) return;
  if (file.size > 1024 * 1024) throw new Error("Manifest file exceeds the console's 1 MiB upload limit.");
  $("manifest").value = new TextDecoder("utf-8", {fatal: true}).decode(await file.arrayBuffer());
  say("Original UTF-8 manifest loaded into the editor. It has not been imported.");
});
on("load-sample", "click", async () => { $("manifest").value = await (await request("/api/sample")).text(); say("Fictional sample loaded into the editor only. Use a separate demonstration database."); });
let csvManifestText = null;
on("csv-file", "change", async () => {
  const file = $("csv-file").files && $("csv-file").files[0];
  if (!file) return;
  if (file.size > 1024 * 1024) throw new Error("CSV file exceeds the 1 MiB intake limit. The paste box and reviewed manifest were left unchanged.");
  const bytes = await file.arrayBuffer();
  let text;
  try {
    text = new TextDecoder("utf-8", {fatal: true}).decode(bytes);
  } catch (_) {
    throw new Error("CSV must be UTF-8. The paste box and reviewed manifest were left unchanged.");
  }
  $("csv-text").value = text;
  say("CSV loaded into the paste box only. Preview before initializing.");
});
on("csv-preview", "click", async () => {
  $("csv-preview-out").textContent = "Previewing…";
  let result;
  try {
    result = await json("/api/csv-preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({csv_text: $("csv-text").value, timezone_policy: $("csv-timezone").value})});
  } catch (error) {
    $("csv-preview-out").textContent = error.message || String(error);
    throw error;
  }
  if (typeof result.manifest_text !== "string") {
    const message = "Preview did not return manifest text.";
    $("csv-preview-out").textContent = message;
    throw new Error(message);
  }
  csvManifestText = result.manifest_text;
  $("manifest").value = result.manifest_text;
  $("csv-download").disabled = false;
  const counts = result.counts || {};
  $("csv-preview-out").textContent = `No structural errors. ${counts.customers} customers, ${counts.sites} sites, ${counts.containers} containers, ${counts.plans} plans. Timezone ${result.business_timezone}. Manifest text is in the editor. Initialize is still a separate step.`;
  say("CSV preview is read-only. Review the manifest, then initialize if this is a new database.");
});
on("csv-download", "click", () => {
  if (!csvManifestText) throw new Error("Preview a valid CSV before downloading its manifest.");
  saveBlob(new Blob([csvManifestText], {type: "application/json"}), "waste-manifest.json");
});
on("manifest-form", "submit", () => { if (confirm("Initialize this database permanently from this manifest and business timezone?")) return perform("import", {manifest_text: $("manifest").value}); });
on("invoice-form", "submit", () => {
  if (confirm("Create an immutable invoice DRAFT and permanently associate its settled stops? Nothing will be sent or charged.")) return perform("invoice", {customer_id: $("invoice-customer").value, period_start: $("period-start").value, period_end: $("period-end").value});
});
on("invoice-lookup", "submit", () => openInvoice($("invoice-id").value));
on("print-invoice", "click", () => { if (selectedInvoice) window.print(); });
on("download-events", "click", () => download({kind: "events"}, "waste-events.json"));
on("operation-lookup", "submit", () => lookupOperation($("operation-key").value));
on("retry", "click", () => { if (pending) return perform(pending.action, pending.args, pending); });
on("save-retry", "click", () => { if (pending) saveBlob(new Blob([JSON.stringify(pending, null, 2)], {type: "application/json"}), "waste-operation-recovery.json"); });
refresh().then(() => say("Workspace opened. Changes require an explicit operator action; invoice output stays draft-only.")).catch(failure);
