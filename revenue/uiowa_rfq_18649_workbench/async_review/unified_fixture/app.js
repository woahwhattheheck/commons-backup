"use strict";

const state = {
  report: null, cells: [], selectedKey: null, notes: new Map(), dispositions: new Map(),
  generation: 0, editRevision: 0, draftLoadSequence: 0
};
const el = Object.fromEntries([
  "candidateFile","authorityFile","inspectBtn","demoBtn","resetBtn","error","summary","search",
  "statusFilter","matrix","detail","disposition","note","exportBtn","exportStatus",
  "sampleBadge","importPanel","matrixCount","cellSummary","sourceList","reportMeta",
  "matrixStatus","backToCellBtn",
  "handoffFile","importDraftBtn","markdownBtn"
].map(id => [id, document.getElementById(id)]));

function keyFor(cell) { return `${cell.group}|${cell.dimension}`; }
function text(value) { return value == null ? "—" : String(value); }
function setError(message="") { el.error.textContent = message; }

const groupLabels = { ESS: "Enterprise Student Systems", RIS: "Research Information Systems", IAM: "Identity & Access Management" };
const areaLabels = { software: "Software development", software_development: "Software development", security: "Security", deployment: "Deployment", ai_readiness: "AI readiness" };
const evidenceStates = {
  UNTRUSTED_EVIDENCE_CONSISTENT: { label: "Evidence consistent", tone: "consistent", next: "Review the supporting records in context, then capture the observation or follow-up that belongs in the assessment." },
  HOLD_MISSING_EVIDENCE: { label: "Evidence needed", tone: "needed", next: "Identify the specific artifact or example needed to understand this practice. An empty evidence set leaves the assessment open." },
  HOLD_CONFLICT: { label: "Sources disagree", tone: "conflict", next: "Compare the sources' definitions, dates, and scope. Record what would resolve the disagreement before selecting a conclusion." },
  HOLD_STALE_EVIDENCE: { label: "Update source", tone: "stale", next: "Request a recent example of this practice. Keep the older record as context and check what has changed." }
};
function evidenceState(cell) { return evidenceStates[cell.status] || { label: "Review evidence", tone: "needed", next: "Review the source record and its technical details." }; }
function appendText(parent, tag, value, className="") {
  const node = document.createElement(tag); node.textContent = value;
  if (className) node.className = className;
  parent.append(node); return node;
}
function statusBadge(cell, className="status") {
  const badge = document.createElement("span"); badge.className = className;
  badge.dataset.tone = evidenceState(cell).tone;
  const dot = document.createElement("span"); dot.className = "status-dot"; dot.setAttribute("aria-hidden", "true");
  badge.append(dot, document.createTextNode(evidenceState(cell).label)); return badge;
}

function returnToSelectedCell() {
  const target = [...el.matrix.querySelectorAll(".cell")].find(button => button.dataset.key === state.selectedKey);
  if (target) target.focus();
  else if (state.report) {
    el.search.focus();
    el.matrixStatus.textContent = "The selected area is outside the current filters. Change the filters to return to it; its notes are retained.";
  }
}

function syntheticReport() {
  const groups = ["ESS", "RIS", "IAM"];
  const dimensions = ["software_development", "security", "deployment", "ai_readiness"];
  const cells = [];
  for (const group of groups) for (const dimension of dimensions) {
    cells.push({
      group, dimension,
      status: dimension === "security" ? "HOLD_MISSING_EVIDENCE" : "UNTRUSTED_EVIDENCE_CONSISTENT",
      maturity: null,
      confidence_bp: null,
      source_ids: [`synthetic-${group.toLowerCase()}-${dimension}`],
      source_record_sha256s: ["0".repeat(64)],
      reason_codes: [dimension === "security" ? "NO_ROOTED_SOURCE_RECORD" : "TRUSTED_AUTHORITY_ROOT_REQUIRED"]
    });
  }
  return {
    schema: "SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT",
    synthetic_demo: true,
    mode: "UNTRUSTED_INSPECTION",
    receipt_sha256: "d".repeat(64),
    aggregate_state: "HOLD_TRUSTED_AUTHORITY_REQUIRED",
    trust: { authority_root_supplied_out_of_band: false, current_evidence_review_authority: false },
    commercial_terms: { status: "PROPOSED_NOT_ACCEPTED" },
    assessment_matrix: cells,
    status_counts: { HOLD_MISSING_EVIDENCE: 3, UNTRUSTED_EVIDENCE_CONSISTENT: 9 }
  };
}

function installReport(report) {
  if (!report || !Array.isArray(report.assessment_matrix) || report.assessment_matrix.length !== 12) {
    throw new Error("Expected a 12-cell compiler report.");
  }
  if (report.mode !== "UNTRUSTED_INSPECTION") throw new Error("Workbench accepts untrusted inspection reports only.");
  if (report.trust?.current_evidence_review_authority !== false) throw new Error("Report unexpectedly carries current review authority.");
  WorkbenchHandoff.buildDraft(report);
  state.generation++;
  state.editRevision = 0;
  state.draftLoadSequence++;
  state.report = report;
  state.cells = report.assessment_matrix.slice();
  state.selectedKey = null;
  state.notes = new Map();
  state.dispositions = new Map();
  el.search.value = "";
  el.note.value = "";
  el.disposition.value = "UNREVIEWED";
  el.note.disabled = true;
  el.disposition.disabled = true;
  el.search.disabled = false;
  el.statusFilter.disabled = false;
  el.exportBtn.disabled = false;
  el.importDraftBtn.disabled = false;
  el.markdownBtn.disabled = false;
  el.inspectBtn.disabled = false;
  el.exportStatus.textContent = "";
  renderSummary();
  rebuildStatuses();
  renderMatrix();
  el.detail.textContent = "Select a cell.";
  el.importPanel.open = false;
  if (state.cells.length) selectCell(keyFor(state.cells[0]), false);
}

function renderSummary() {
  el.summary.replaceChildren();
  for (const [code, presentation] of Object.entries(evidenceStates)) {
    const item = document.createElement("div");
    appendText(item, "dt", presentation.label);
    appendText(item, "dd", String(state.cells.filter(cell => cell.status === code).length));
    el.summary.append(item);
  }
  const sources = state.report.evidence_authority?.sources || [];
  const syntheticEvidence = sources.length > 0 && sources.every(source => String(source.source_ref || "").startsWith("synthetic://"));
  el.sampleBadge.hidden = false;
  el.sampleBadge.textContent = state.report.synthetic_demo === true ? "Synthetic sample · UI demonstration" : syntheticEvidence ? "Synthetic evidence · compiler run" : "Imported evidence package";
  el.reportMeta.textContent = JSON.stringify({
    mode: state.report.mode, aggregate_state: state.report.aggregate_state,
    receipt_sha256: state.report.receipt_sha256, trust: state.report.trust,
    commercial_terms: state.report.commercial_terms,
    synthetic_ui_demo: state.report.synthetic_demo === true,
    synthetic_source_records: syntheticEvidence
  }, null, 2);
}

function rebuildStatuses() {
  const current = el.statusFilter.value;
  const statuses = [...new Set(state.cells.map(c => c.status))].sort();
  el.statusFilter.replaceChildren(new Option("All evidence states", ""), ...statuses.map(s => new Option(evidenceState({status:s}).label, s)));
  if (statuses.includes(current)) el.statusFilter.value = current;
}

function visibleCells() {
  const q = el.search.value.trim().toLowerCase();
  const status = el.statusFilter.value;
  return state.cells.filter(cell => {
    if (status && cell.status !== status) return false;
    if (!q) return true;
    const hay = [cell.group, groupLabels[cell.group], cell.dimension, areaLabels[cell.dimension], cell.status, evidenceState(cell).label, ...(cell.reason_codes || []), ...(cell.source_ids || [])].join(" ").toLowerCase();
    return hay.includes(q);
  });
}

function renderMatrix() {
  const active = document.activeElement;
  const focusedKey = el.matrix.contains(active) ? active.dataset.key : null;
  el.matrix.replaceChildren();
  let previousGroup = null;
  for (const cell of visibleCells()) {
    if (cell.group !== previousGroup) {
      const heading = document.createElement("div"); heading.className = "matrix-group";
      appendText(heading, "strong", cell.group); appendText(heading, "span", groupLabels[cell.group] || cell.group);
      el.matrix.append(heading); previousGroup = cell.group;
    }
    const key = keyFor(cell);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cell";
    button.dataset.key = key;
    button.dataset.tone = evidenceState(cell).tone;
    button.setAttribute("aria-controls", "detailPanel");
    button.setAttribute("aria-label", `${cell.group}: ${areaLabels[cell.dimension] || cell.dimension}, ${evidenceState(cell).label}. Open evidence and notes.`);
    button.setAttribute("aria-current", state.selectedKey === key ? "true" : "false");
    appendText(button, "span", areaLabels[cell.dimension] || cell.dimension, "area");
    button.append(statusBadge(cell));
    const count = (cell.source_ids || []).length;
    appendText(button, "span", `${count} source${count === 1 ? "" : "s"}`, "source-count");
    button.addEventListener("click", () => selectCell(key));
    el.matrix.append(button);
  }
  const renderedCount = el.matrix.querySelectorAll(".cell").length;
  el.matrix.dataset.renderedCells = String(renderedCount);
  el.matrixCount.textContent = `${renderedCount} of ${state.cells.length} areas`;
  el.matrixStatus.textContent = renderedCount ? `${renderedCount} of ${state.cells.length} assessment areas shown.` : "No cells match. Clear or change the filters.";
  if (state.selectedKey && !visibleCells().some(cell => keyFor(cell) === state.selectedKey)) el.matrixStatus.textContent += " Selected evidence and notes remain available outside the current filters.";
  if (focusedKey) {
    const replacement = [...el.matrix.querySelectorAll(".cell")].find(button => button.dataset.key === focusedKey);
    (replacement || el.search).focus();
  }
}

function selectCell(key, focusDetail = true) {
  const cell = state.cells.find(c => keyFor(c) === key);
  if (!cell) return;
  state.selectedKey = key;
  renderMatrix();
  el.detail.textContent = JSON.stringify(cell, null, 2);
  el.cellSummary.replaceChildren();
  const selectedHeading = appendText(el.cellSummary, "h3", `${cell.group} / ${areaLabels[cell.dimension] || cell.dimension}`);
  selectedHeading.id = "selectedCellHeading"; selectedHeading.tabIndex = -1;
  el.backToCellBtn.disabled = false;
  appendText(el.cellSummary, "p", groupLabels[cell.group] || cell.group, "team-context");
  el.cellSummary.append(statusBadge(cell, "evidence-status"));
  const next = document.createElement("p"); next.className = "next-step";
  appendText(next, "strong", "Useful next step"); next.append(document.createTextNode(evidenceState(cell).next)); el.cellSummary.append(next);
  el.sourceList.replaceChildren();
  const records = state.report.evidence_authority?.sources || [];
  for (const sourceId of cell.source_ids || []) {
    const source = records.find(row => row.source_id === sourceId);
    const card = document.createElement("div"); card.className = "source-card";
    appendText(card, "span", sourceId, "source-id");
    if (source) {
      appendText(card, "p", source.claim || "Source record available for review.");
      appendText(card, "small", [source.evidence_kind, source.observed_at?.slice(0, 10)].filter(Boolean).join(" · "));
      const record = document.createElement("details");
      appendText(record, "summary", "View source record"); appendText(record, "pre", JSON.stringify(source, null, 2)); card.append(record);
    } else appendText(card, "p", state.report.synthetic_demo === true ? "Illustrative source identifier for this UI sample. Import the sample evidence files to inspect the actual compiler output." : "This source identifier is retained in the report; its full record is not included in this view.");
    el.sourceList.append(card);
  }
  el.note.disabled = false;
  el.disposition.disabled = false;
  el.note.value = state.notes.get(key) || "";
  el.disposition.value = state.dispositions.get(key) || "UNREVIEWED";
  if (focusDetail) selectedHeading.focus();
}

function resetWorkbench() {
  state.generation++;
  state.editRevision = 0;
  state.draftLoadSequence++;
  state.report = null; state.cells = []; state.selectedKey = null;
  state.notes = new Map(); state.dispositions = new Map();
  el.summary.replaceChildren(); el.matrix.replaceChildren();
  el.matrix.dataset.renderedCells = "0";
  el.matrixStatus.textContent = "No report loaded. Import evidence or load the synthetic UI demo.";
  el.backToCellBtn.disabled = true;
  el.detail.textContent = "Select a cell.";
  el.search.value = ""; el.search.disabled = true;
  el.statusFilter.replaceChildren(new Option("All statuses", "")); el.statusFilter.disabled = true;
  el.note.value = ""; el.note.disabled = true;
  el.disposition.value = "UNREVIEWED"; el.disposition.disabled = true;
  el.exportBtn.disabled = true; el.exportStatus.textContent = "";
  el.cellSummary.replaceChildren();
  const emptyHeading = appendText(el.cellSummary, "h3", "No cell selected");
  emptyHeading.id = "selectedCellHeading"; emptyHeading.tabIndex = -1;
  appendText(el.cellSummary, "p", "Choose an area to explore its sources and next step.", "empty-state");
  el.sourceList.replaceChildren(); el.sampleBadge.hidden = true;
  el.reportMeta.textContent = "Load a package to view its report metadata.";
  el.matrixCount.textContent = "Select an area";
  el.importPanel.open = true;
  el.importDraftBtn.disabled = true;
  el.markdownBtn.disabled = true;
  el.inspectBtn.disabled = false;
  setError("");
}

// Validate the shape, but never use the parsed value as transport data. JSON.parse
// collapses duplicate keys and rounds large integers; the parent strict parser
// must receive the original document, not a browser-normalized substitute.
function validateJsonObjectText(raw, label) {
  if (typeof raw !== "string") throw new Error(`${label} must be JSON source text.`);
  let value;
  try { value = JSON.parse(raw); } catch { throw new Error(`${label} is not valid JSON.`); }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must be a JSON object.`);
  return raw;
}

async function readUtf8File(file, label) {
  if (file.size > 1024 * 1024) throw new Error(`${label} file exceeds 1 MiB browser intake limit.`);
  const bytes = await file.arrayBuffer();
  if (bytes.byteLength > 1024 * 1024) throw new Error(`${label} file exceeds 1 MiB browser intake limit.`);
  let raw;
  try {
    // Blob.text() replaces invalid UTF-8. Fatal decoding rejects it instead.
    // ignoreBOM=true preserves a BOM so JSON validation rejects, not strips, it.
    raw = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch { throw new Error(`${label} must be valid UTF-8.`); }
  return raw;
}

async function readJsonFile(input, label) {
  const file = input.files?.[0];
  if (!file) throw new Error(`${label} file is required.`);
  return validateJsonObjectText(await readUtf8File(file, label), label);
}

function buildInspectionBody(candidate, authority) {
  // Each fragment must be one complete object before insertion. This prevents
  // trailing data from changing the envelope while retaining duplicate members
  // for server-side rejection. Do not stringify the parsed fragment objects.
  const body = `{"candidate":${validateJsonObjectText(candidate, "Candidate")},"authority":${validateJsonObjectText(authority, "Authority")}}`;
  if (new TextEncoder().encode(body).byteLength > 2 * 1024 * 1024) {
    throw new Error("Combined evidence files and request envelope exceed the 2 MiB server intake limit.");
  }
  return body;
}

async function inspectFiles() {
  const restoreInvokerFocus = document.activeElement === el.inspectBtn;
  // A replacement attempt invalidates the prior generation immediately. If file
  // parsing, transport, or compiler inspection fails, stale notes/export authority
  // must not remain actionable under the guise of the attempted new import.
  resetWorkbench();
  const generation = state.generation;
  el.inspectBtn.disabled = true;
  try {
    const [candidate, authority] = await Promise.all([
      readJsonFile(el.candidateFile, "Candidate"), readJsonFile(el.authorityFile, "Authority")
    ]);
    if (generation !== state.generation) return;
    const response = await fetch("/api/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: buildInspectionBody(candidate, authority),
      credentials: "same-origin",
      cache: "no-store"
    });
    const payload = await response.json().catch(() => ({}));
    if (generation !== state.generation) return;
    if (!response.ok) throw new Error(payload.error || `Inspection failed (${response.status}).`);
    installReport(payload.report);
    if (restoreInvokerFocus && document.activeElement === document.body) {
      document.getElementById("summary-heading").focus();
    }
  } catch (err) {
    if (generation === state.generation) setError(err instanceof Error ? err.message : String(err));
  } finally {
    if (generation === state.generation) {
      el.inspectBtn.disabled = false;
      if (restoreInvokerFocus && document.activeElement === document.body) {
        (state.report ? document.getElementById("summary-heading") : el.inspectBtn).focus();
      }
    }
  }
}

async function importDraft() {
  if (!state.report) return;
  const report = state.report;
  const generation = state.generation;
  const editRevision = state.editRevision;
  const sequence = ++state.draftLoadSequence;
  el.importDraftBtn.disabled = true;
  setError("");
  try {
    const file = el.handoffFile.files?.[0];
    if (!file) throw new Error("Choose a saved draft handoff JSON file.");
    const contents = await readUtf8File(file, "Saved draft");
    if (generation !== state.generation || sequence !== state.draftLoadSequence) return;
    if (editRevision !== state.editRevision) {
      throw new Error("Notes changed while the draft was loading. Restore again if you want to replace them.");
    }
    const restored = HandoffImport.parseDraft(contents, report);
    // Validation completes before either map is replaced. Failed imports preserve
    // the active report and every note, disposition, selection and filter.
    state.notes = restored.notes;
    state.dispositions = restored.dispositions;
    state.editRevision++;
    const key = state.selectedKey || keyFor(state.cells.find(cell =>
      state.notes.get(keyFor(cell)) || state.dispositions.get(keyFor(cell)) !== "UNREVIEWED"
    ) || state.cells[0]);
    selectCell(key);
    el.exportStatus.textContent = "Saved draft restored for this report. All 12 cell notes and dispositions replaced; no approval authority is created.";
  } catch (err) {
    if (generation === state.generation && sequence === state.draftLoadSequence) {
      setError(err instanceof Error ? err.message : String(err));
    }
  } finally {
    if (generation === state.generation && sequence === state.draftLoadSequence) {
      el.importDraftBtn.disabled = !state.report;
    }
  }
}

// Export projection from Trellis's handoff continuity work (PR #16130).
function downloadText(contents, extension, contentType) {
  const blob = new Blob([contents], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `uiowa-rfq18649-draft-handoff-${state.report.receipt_sha256.slice(0, 12)}.${extension}`;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function exportDraft() {
  if (!state.report) return;
  try {
    const handoff = WorkbenchHandoff.buildDraft(state.report, state.notes, state.dispositions);
    downloadText(JSON.stringify(handoff, null, 2) + "\n", "json", "application/json");
    setError("");
    el.exportStatus.textContent = "Draft handoff exported. It carries no approval or payment authority.";
  } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
}

function exportMarkdown() {
  if (!state.report) return;
  try {
    const handoff = WorkbenchHandoff.buildDraft(state.report, state.notes, state.dispositions);
    downloadText(WorkbenchHandoff.renderMarkdown(state.report, handoff), "md", "text/markdown;charset=utf-8");
    setError("");
    el.exportStatus.textContent = "Readable draft exported with evidence references and open follow-ups.";
  } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
}

el.inspectBtn.addEventListener("click", inspectFiles);
el.demoBtn.addEventListener("click", () => {
  const restoreInvokerFocus = document.activeElement === el.demoBtn;
  setError(""); installReport(syntheticReport());
  if (restoreInvokerFocus) document.getElementById("summary-heading").focus();
});
el.resetBtn.addEventListener("click", resetWorkbench);
el.search.addEventListener("input", renderMatrix);
el.statusFilter.addEventListener("change", renderMatrix);
el.note.addEventListener("input", () => {
  if (state.selectedKey) { state.notes.set(state.selectedKey, el.note.value); state.editRevision++; }
});
el.disposition.addEventListener("change", () => {
  if (state.selectedKey) { state.dispositions.set(state.selectedKey, el.disposition.value); state.editRevision++; }
});
el.exportBtn.addEventListener("click", exportDraft);
el.backToCellBtn.addEventListener("click", returnToSelectedCell);
el.markdownBtn.addEventListener("click", exportMarkdown);
el.importDraftBtn.addEventListener("click", importDraft);

resetWorkbench();
if (new URLSearchParams(location.search).get("demo") === "1") installReport(syntheticReport());
