"use strict";

const $ = (id) => document.getElementById(id);
const SIDES = ["source", "target"];
const MAX_FILE_BYTES = 4000000;
const PAGE_SIZE = 50;
const CSV_PLAN_SCHEMA = "saas-migration-csv-intake/v1";
const GENERAL_PLAN_SCHEMA = "saas-migration-workbench-plan/v1";
const token = document.querySelector('meta[name="workbench-token"]').content;
const loaded = {source: null, target: null};
const loadSequence = {source: 0, target: 0};
let generation = 0, planSequence = 0, busy = false, page = 0;
let pendingPlan = null, rows = [], downloadUrls = [];
let aliases = new Map();
const downloadIds = ["download-manifest", "download-report", "download-markdown", "download-html", "download-plan", "download-intake", "download-bundle"];

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function status(message, error = false) {
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
}
function mode() { return $("intake-mode").value; }
function delimiter(side) { return $(`${side}-delimiter`).value === "tab" ? "\t" : $(`${side}-delimiter`).value; }
function discardResults() {
  generation += 1;
  downloadUrls.forEach((url) => URL.revokeObjectURL(url));
  downloadUrls = [];
  downloadIds.forEach((id) => { $(id).removeAttribute("href"); $(id).removeAttribute("download"); });
  rows = []; aliases = new Map(); page = 0;
  $("results").hidden = true;
  ["row-body", "metrics", "provenance"].forEach((id) => $(id).replaceChildren());
  ["result-state", "report-meta"].forEach((id) => { $(id).textContent = ""; });
}
function changed() {
  const hadResult = !$("results").hidden;
  discardResults();
  if (hadResult) status("Inputs changed. Compare again for the new inputs.");
}
function ready() { return SIDES.every((side) => loaded[side] !== null); }
function updateControls() {
  $("compare").disabled = busy || !ready();
  $("save-plan").disabled = busy || !ready();
  $("compare").textContent = busy ? "Working…" : "Compare exports";
  const csvPlan = mode() === "csv-plan";
  for (const side of SIDES) {
    $(`${side}-format`).disabled = csvPlan;
    $(`${side}-delimiter-wrap`).hidden = !csvPlan;
    if (csvPlan) $(`${side}-format`).value = "csv";
  }
  $("mode-description").textContent = csvPlan
    ? "Batch-compatible CSV plans compare selected columns through key_*/field_* aliases. Comma, semicolon and tab are explicit; original headers and excluded columns stay visible."
    : "General CSV/JSON retains original field names and all supplied fields in the private manifest. CSV uses commas. JSON types and 64-bit integers stay exact.";
  for (const kind of ["key", "field"]) {
    const children = Array.from($(`${kind}-map`).children);
    $(`add-${kind}`).disabled = !ready() || children.length >= (kind === "key" ? 4 : 32);
    children.forEach((row) => {
      row.querySelector("button").disabled = children.length <= 1;
      row.querySelectorAll("select").forEach((select) => { select.disabled = !ready(); });
    });
  }
}
async function api(path, payload) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, {
      method: "POST", headers: {"Content-Type": "application/json", "X-Intake-Token": token},
      body: JSON.stringify(payload), signal: controller.signal, cache: "no-store",
    });
    let result;
    try { result = await response.json(); }
    catch (_) { throw new Error(`Server returned an unreadable response (HTTP ${response.status}).`); }
    if (!response.ok) throw new Error(result.error || `Request failed (HTTP ${response.status}).`);
    return result;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Request timed out. Check the local server and retry explicitly.");
    throw error;
  } finally { clearTimeout(timer); }
}
function mappingSelect(caption, options, placeholder) {
  const label = element("label", caption);
  const select = document.createElement("select");
  select.required = true;
  if (placeholder) { const first = element("option", placeholder); first.value = ""; select.append(first); }
  for (const value of options) { const option = element("option", value); option.value = value; select.append(option); }
  label.append(select);
  return label;
}
function addMapping(kind, mapping = null) {
  const container = $(`${kind}-map`);
  if (container.children.length >= (kind === "key" ? 4 : 32)) return false;
  const row = element("div", undefined, "mapping-row");
  row.append(mappingSelect("Source field", loaded.source?.columns || [], "Choose source field"),
    mappingSelect("Target field", loaded.target?.columns || [], "Choose target field"),
    mappingSelect("Type", kind === "key" ? ["string", "integer"] : ["string", "integer", "boolean"]));
  let matched = true;
  if (mapping) {
    row.querySelectorAll("select").forEach((select, index) => {
      select.value = mapping[["source", "target", "type"][index]];
      if (!select.value) matched = false;
    });
  }
  const remove = element("button", "Remove");
  remove.type = "button";
  remove.setAttribute("aria-label", `Remove ${kind} mapping`);
  remove.addEventListener("click", () => { row.remove(); changed(); updateControls(); });
  row.append(remove); container.append(row); updateControls();
  return matched;
}
function resetMappings() {
  const saved = ready() ? pendingPlan : null;
  let matched = true;
  for (const kind of ["key", "field"]) {
    $(`${kind}-map`).replaceChildren();
    for (const mapping of saved?.[`${kind}_map`] || [null]) {
      if (!addMapping(kind, mapping)) matched = false;
    }
  }
  if (saved) pendingPlan = null;
  return matched;
}
async function loadExport(side, newFile) {
  const sequence = ++loadSequence[side];
  changed(); loaded[side] = null;
  $(`${side}-columns`).replaceChildren();
  if (newFile) { $(`${side}-captured`).value = ""; $(`${side}-complete`).checked = false; }
  resetMappings(); updateControls();
  const file = $(`${side}-file`).files[0];
  if (!file) {
    $(`${side}-preview`).textContent = "No export loaded.";
    status("Load both exports to begin."); return;
  }
  if (newFile && mode() === "general" && /\.(csv|json)$/i.test(file.name)) {
    $(`${side}-format`).value = file.name.toLowerCase().endsWith(".json") ? "json" : "csv";
  }
  const format = $(`${side}-format`).value;
  const selectedMode = mode(), selectedDelimiter = delimiter(side);
  $(`${side}-preview`).textContent = "Reading field names and record count…";
  try {
    if (file.size > MAX_FILE_BYTES) throw new Error(`Export exceeds ${MAX_FILE_BYTES.toLocaleString()} bytes; it was not truncated.`);
    // No JSON record is parsed in JavaScript. Fatal UTF-8 decoding retains BOM
    // and line endings, allowing Python to hash the exact original file bytes.
    const text = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(await file.arrayBuffer());
    if (sequence !== loadSequence[side]) return;
    const preview = await api("/api/inspect", {mode: selectedMode, format, text, delimiter: selectedDelimiter});
    if (sequence !== loadSequence[side]) return;
    loaded[side] = {format, text, columns: preview.columns};
    $(`${side}-preview`).textContent = `${preview.record_count} records · ${preview.columns.length} fields · ${preview.byte_count.toLocaleString()} bytes · SHA-256 ${preview.original_file_sha256}`;
    $(`${side}-columns`).replaceChildren(...preview.columns.map((name) => element("span", name, "field-chip")));
    const mapped = resetMappings();
    if (!mapped) status("The imported plan names columns missing from these exports. Missing choices remain blank; repair the mappings before comparing.", true);
    else status(ready() ? "Exports loaded. Confirm snapshot facts and choose or review the explicit mappings." : "Load the other export to continue.");
  } catch (error) {
    if (sequence !== loadSequence[side]) return;
    $(`${side}-preview`).textContent = "Export could not be loaded.";
    status(`${side}: ${error.message}`, true);
  } finally { if (sequence === loadSequence[side]) updateControls(); }
}
function readMappings(kind) {
  return Array.from($(`${kind}-map`).children).map((row) => {
    const values = Array.from(row.querySelectorAll("select"), (select) => select.value);
    return {source: values[0], target: values[1], type: values[2]};
  });
}
function currentPlan() {
  const csvPlan = mode() === "csv-plan";
  const plan = {schema: csvPlan ? CSV_PLAN_SCHEMA : GENERAL_PLAN_SCHEMA,
    cutover_at_utc: $("cutover").value, max_snapshot_age_seconds: Number($("max-age").value),
    key_map: readMappings("key"), field_map: readMappings("field")};
  if (!Number.isSafeInteger(plan.max_snapshot_age_seconds)) throw new Error("Maximum age must be a whole number of seconds.");
  for (const side of SIDES) {
    plan[`${side}_snapshot`] = {snapshot_id: $(`${side}-id`).value, schema_revision: $(`${side}-revision`).value,
      captured_at_utc: $(`${side}-captured`).value, complete: $(`${side}-complete`).checked,
      ...(csvPlan ? {delimiter: delimiter(side)} : {format: loaded[side].format})};
  }
  return plan;
}
function intakeRequest() {
  return {mode: mode(), plan: currentPlan(), source_text: loaded.source.text, target_text: loaded.target.text};
}
function download(id, filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  downloadUrls.push(url); $(id).href = url; $(id).download = filename;
}
function mappingCaption(field) {
  const original = aliases.get(field.source_field);
  return original ? `${original.source} → ${original.target} (${field.source_field})` : `${field.source_field} → ${field.target_field}`;
}
function renderRows() {
  const classification = $("classification-filter").value, needle = $("key-filter").value.toLowerCase();
  const filtered = rows.filter((row) => (!classification || row.classification === classification) &&
    `${row.key_commitment} ${row.classification} ${row.mismatch_fields.map(mappingCaption).join(" ")} ${row.reason_codes.join(" ")}`.toLowerCase().includes(needle));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  page = Math.min(page, pages - 1);
  const body = $("row-body"); body.replaceChildren();
  for (const row of filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)) {
    const tr = document.createElement("tr"), state = element("td"), key = element("td"), detail = element("td");
    state.append(element("span", row.classification, `tag ${row.classification === "PARITY" ? "parity" : "attention"}`));
    key.append(element("code", row.key_commitment));
    detail.append(element("p", row.reason_codes.length ? row.reason_codes.join(", ") : "Mapped fields match."));
    for (const mismatch of row.mismatch_fields) {
      const disclosure = document.createElement("details");
      disclosure.append(element("summary", mappingCaption(mismatch)), element("p", "Source value digest"),
        element("code", mismatch.source_value_sha256), element("p", "Target value digest"), element("code", mismatch.target_value_sha256));
      detail.append(disclosure);
    }
    tr.append(state, key, detail); body.append(tr);
  }
  if (!filtered.length) { const tr = element("tr"), cell = element("td", "No result rows match this filter."); cell.colSpan = 3; tr.append(cell); body.append(tr); }
  $("page-info").textContent = `${filtered.length} matching / ${rows.length} total keys · page ${page + 1} of ${pages}`;
  $("prev-page").disabled = page === 0; $("next-page").disabled = page + 1 >= pages;
}
function renderReport(result) {
  // Parse only bounded plan/provenance and digest-only report metadata, never
  // source records or manifest values. Downloads use exact server strings.
  const report = JSON.parse(result.report_json), intake = JSON.parse(result.intake_json);
  const counts = report.summary.counts; rows = report.rows;
  aliases = new Map(intake.columns.filter((column) => column.alias).map((column) => [column.alias, column]));
  $("result-state").textContent = report.summary.diagnostic_state;
  $("report-meta").textContent = `Mode ${result.mode} · cutover ${report.cutover_at_utc} · source ${report.source_snapshot.record_count} records · target ${report.target_snapshot.record_count} records`;
  const metrics = [["Union keys", report.summary.union_key_count], ["Parity", counts.PARITY],
    ["Missing / unexpected / changed", counts.MISSING_TARGET + counts.UNEXPECTED_TARGET + counts.FIELD_MISMATCH],
    ["Stale / duplicate / invalid", counts.STALE_EVIDENCE + counts.DUPLICATE_KEY + counts.INVALID_EVIDENCE]];
  $("metrics").replaceChildren(...metrics.map(([label, value]) => { const card = element("div", undefined, "metric"); card.append(element("strong", value), element("span", label)); return card; }));
  download("download-manifest", "parity-input.json", result.manifest_json, "application/json;charset=utf-8");
  download("download-report", "parity-report.json", result.report_json, "application/json;charset=utf-8");
  download("download-markdown", "parity-report.md", result.report_markdown, "text/markdown;charset=utf-8");
  download("download-html", "parity-report.html", result.report_html, "text/html;charset=utf-8");
  download("download-plan", result.mode === "csv-plan" ? "intake-plan.json" : "workbench-plan.json", result.plan_json, "application/json;charset=utf-8");
  download("download-intake", "column-map.json", result.intake_json, "application/json;charset=utf-8");
  const binary = atob(result.bundle_base64);
  download("download-bundle", "migration-parity-private.zip", Uint8Array.from(binary, (character) => character.charCodeAt(0)), "application/zip");
  $("provenance").textContent = JSON.stringify(intake, null, 2);
  $("private-notice").textContent = result.mode === "csv-plan"
    ? "PRIVATE: input JSON and replay ZIP contain the selected raw CSV values. Original CSV files are not inside the ZIP; retain them separately."
    : "PRIVATE: input JSON and replay ZIP contain all supplied field values, including unmapped fields. Original CSV/JSON files are not inside the ZIP; retain them separately.";
  const all = element("option", "All classifications"); all.value = "";
  $("classification-filter").replaceChildren(all, ...Object.entries(counts).map(([name, count]) => { const option = element("option", `${name} (${count})`); option.value = name; return option; }));
  $("key-filter").value = ""; page = 0; renderRows(); $("results").hidden = false; $("report-title").focus();
}

$("intake").addEventListener("input", changed);
$("intake").addEventListener("change", changed);
$("intake").addEventListener("submit", async (event) => {
  event.preventDefault(); if (busy || !ready()) return;
  discardResults(); const submitted = generation; busy = true; updateControls();
  status("Comparing the supplied exports…");
  try {
    const result = await api("/api/compare", intakeRequest());
    if (submitted !== generation) { status("Inputs changed during comparison. Compare again for the current inputs."); return; }
    renderReport(result); status("Comparison complete. Report-only and private replay downloads are separated below.");
  } catch (error) { if (submitted === generation) status(error.message, true); }
  finally { busy = false; updateControls(); }
});
for (const side of SIDES) {
  $(`${side}-file`).addEventListener("change", () => loadExport(side, true));
  for (const suffix of ["format", "delimiter"]) $(`${side}-${suffix}`).addEventListener("change", () => loadExport(side, false));
}
$("intake-mode").addEventListener("change", () => {
  pendingPlan = null; planSequence += 1; changed(); updateControls();
  for (const side of SIDES) loadExport(side, false);
});
$("plan-file").addEventListener("change", async (event) => {
  event.stopPropagation(); changed();
  const file = $("plan-file").files[0]; if (!file) return;
  $("plan-file").value = ""; // Allow an explicit reload of the same saved plan.
  const sequence = ++planSequence, submitted = generation;
  try {
    if (file.size > 100000) throw new Error("Plan exceeds 100,000 bytes.");
    const text = new TextDecoder("utf-8", {fatal: true}).decode(await file.arrayBuffer());
    const response = await api("/api/plan", {plan_text: text});
    if (sequence !== planSequence || submitted !== generation) { status("Inputs changed while the plan loaded. Import it again explicitly."); return; }
    // The server rejected unknown schemas and unsafe numeric metadata first.
    const plan = JSON.parse(response.plan_json);
    $("intake-mode").value = response.mode; pendingPlan = plan;
    $("cutover").value = plan.cutover_at_utc; $("max-age").value = plan.max_snapshot_age_seconds;
    for (const side of SIDES) {
      const snapshot = plan[`${side}_snapshot`];
      $(`${side}-id`).value = snapshot.snapshot_id; $(`${side}-revision`).value = snapshot.schema_revision;
      $(`${side}-captured`).value = snapshot.captured_at_utc; $(`${side}-complete`).checked = snapshot.complete;
      $(`${side}-format`).value = response.mode === "csv-plan" ? "csv" : snapshot.format;
      if (response.mode === "csv-plan") $(`${side}-delimiter`).value = snapshot.delimiter === "\t" ? "tab" : snapshot.delimiter;
      loadSequence[side] += 1; loaded[side] = null;
    }
    changed(); updateControls(); resetMappings();
    await Promise.all(SIDES.map((side) => loadExport(side, false)));
    if (sequence === planSequence) $("plan-notice").textContent = `Loaded ${plan.schema}. Review the retained mappings and reconfirm snapshot facts. Selecting a different file clears its capture time and completeness.`;
  } catch (error) { if (sequence === planSequence) status(error.message, true); }
});
$("save-plan").addEventListener("click", async () => {
  if (busy || !ready() || !$("intake").reportValidity()) return;
  const submitted = generation; busy = true; updateControls();
  try {
    const result = await api("/api/plan", {plan_text: JSON.stringify(currentPlan())});
    if (submitted !== generation) { status("Inputs changed. Save the current plan again."); return; }
    const url = URL.createObjectURL(new Blob([result.plan_json], {type: "application/json;charset=utf-8"}));
    downloadUrls.push(url);
    const link = element("a"); link.href = url; link.download = result.mode === "csv-plan" ? "intake-plan.json" : "workbench-plan.json";
    document.body.append(link); link.click(); link.remove();
    status("Plan downloaded. Its format identifies the adapter; reconfirm snapshot facts before reusing it.");
  } catch (error) { if (submitted === generation) status(error.message, true); }
  finally { busy = false; updateControls(); }
});
for (const kind of ["key", "field"]) $(`add-${kind}`).addEventListener("click", () => { changed(); addMapping(kind); });
$("use-now").addEventListener("click", () => { changed(); $("cutover").value = new Date().toISOString().replace(/\.\d{3}Z$/, "Z"); });
$("classification-filter").addEventListener("change", () => { page = 0; renderRows(); });
$("key-filter").addEventListener("input", () => { page = 0; renderRows(); });
$("prev-page").addEventListener("click", () => { page = Math.max(0, page - 1); renderRows(); });
$("next-page").addEventListener("click", () => { page += 1; renderRows(); });
$("clear-session").addEventListener("click", () => {
  discardResults(); planSequence += 1; pendingPlan = null; $("intake").reset();
  $("plan-notice").textContent = "Plans save explicit mappings and metadata, never the source files. Formats are not silently translated.";
  for (const side of SIDES) { loadSequence[side] += 1; loaded[side] = null; $(`${side}-preview`).textContent = "No export loaded."; $(`${side}-columns`).replaceChildren(); }
  resetMappings(); updateControls(); status("Session cleared. Files already downloaded are not deleted.");
});
window.addEventListener("beforeunload", () => downloadUrls.forEach((url) => URL.revokeObjectURL(url)));
resetMappings(); updateControls();
