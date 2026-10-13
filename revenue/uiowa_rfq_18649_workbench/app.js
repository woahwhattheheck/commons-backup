"use strict";

const state = {
  report: null, cells: [], selectedKey: null, notes: new Map(), dispositions: new Map(),
  generation: 0, editRevision: 0, draftLoadSequence: 0, savedDrafts: new Map()
};
const el = Object.fromEntries([
  "candidateFile","authorityFile","inspectBtn","demoBtn","resetBtn","error","summary","search",
  "statusFilter","matrix","detail","disposition","note","exportBtn","exportStatus",
  "sampleBadge","importPanel","matrixCount","cellSummary","sourceList","reportMeta",
  "matrixStatus","backToCellBtn",
  "handoffFile","importDraftBtn","markdownBtn",
  "savedDraftSelect","restoreTabDraftBtn","downloadTabDraftBtn","savedDraftStatus"
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
  HOLD_STALE_EVIDENCE: { label: "Update source", tone: "stale", next: "Request a recent example of this practice. Keep the older record as context and check what has changed." },
  NOT_ASSESSED: { label: "Not assessed", tone: "unassessed", next: "Determine what assessment work is still needed; no outcome is established." },
  NOT_APPLICABLE: { label: "Not applicable", tone: "inapplicable", next: "Retain the stated applicability decision and its basis; this is not a zero or a pass." },
  UNKNOWN: { label: "Unknown", tone: "unknown", next: "Resolve the missing context before assigning an assessment outcome." }
};
function evidenceState(cell) {
  return typeof cell.status === "string" && Object.prototype.hasOwnProperty.call(evidenceStates, cell.status)
    ? evidenceStates[cell.status]
    : { label: "Unrecognized status", tone: "unknown", next: "Review the original status code and source record; no outcome is inferred." };
}

// Presentation recovered from UIOWA-126 (#16265). This never creates a compiler
// state or score: the original report and exported handoff remain unchanged.
const CELL_PRESENTATION = Object.freeze({
  UNTRUSTED_EVIDENCE_CONSISTENT: ["consistent", "[=]", "Supplied records agree; no current review authority."],
  HOLD_MISSING_EVIDENCE: ["missing", "[?]", "No supporting record in this cell; not a poor-performance finding."],
  HOLD_CONFLICT: ["conflict", "[!]", "Differing records remain unresolved; do not average them into a score."],
  HOLD_STALE_EVIDENCE: ["stale", "[~]", "Evidence exceeds its configured age window; not a finding about current practice."],
  NOT_ASSESSED: ["unassessed", "[-]", "No assessment outcome is established for this cell."],
  NOT_APPLICABLE: ["inapplicable", "[/]", "Declared outside the applicable assessment; not a zero or a pass."],
  UNKNOWN: ["unknown", "[?]", "The supplied status does not establish an outcome."]
});
function cellPresentation(cell) {
  const row = typeof cell.status === "string" && Object.prototype.hasOwnProperty.call(CELL_PRESENTATION, cell.status)
    ? CELL_PRESENTATION[cell.status]
    : ["unrecognized", "[?]", "Read the original code and evidence; no outcome is inferred."];
  return { kind: row[0], marker: row[1], explanation: row[2] };
}
function valuePresentation(cell, field) {
  if (!Object.prototype.hasOwnProperty.call(cell, field)) return "Not supplied (field absent)";
  const value = cell[field];
  if (value === null) {
    return cell.status === "UNTRUSTED_EVIDENCE_CONSISTENT"
      ? "Not reported in untrusted inspection (null)"
      : "Not determined (null)";
  }
  if (typeof value !== "number" || !Number.isFinite(value)) return "Non-numeric or invalid value; inspect original record";
  return `Supplied value: ${Object.is(value, -0) ? "-0" : String(value)} (display only)`;
}
function appendText(parent, tag, value, className="") {
  const node = document.createElement(tag); node.textContent = value;
  if (className) node.className = className;
  parent.append(node); return node;
}
function appendCellValues(parent, cell) {
  appendText(parent, "span", `Source status: ${text(cell.status)}`, "source-status");
  appendText(parent, "span", cellPresentation(cell).explanation, "state-explanation");
  appendText(parent, "span", `Maturity: ${valuePresentation(cell, "maturity")}`, "value-state");
  appendText(parent, "span", `Confidence (basis points): ${valuePresentation(cell, "confidence_bp")}`, "value-state");
}
function statusBadge(cell, className="status") {
  const badge = document.createElement("span"); badge.className = className;
  badge.dataset.tone = evidenceState(cell).tone;
  const dot = document.createElement("span"); dot.className = "status-dot"; dot.setAttribute("aria-hidden", "true");
  badge.append(dot, document.createTextNode(`${cellPresentation(cell).marker} ${evidenceState(cell).label}`)); return badge;
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

// Snapshots are immutable serialized handoffs, not retained report objects.
// New receipts enter the tab cache only after meaningful work. Once present,
// explicitly emptied drafts replace their prior contents so deleted notes stay deleted.
function rememberDraft(report, notes, dispositions) {
  const draft = WorkbenchHandoff.buildDraft(report, notes, dispositions);
  const contents = JSON.stringify(draft, null, 2) + "\n";
  HandoffImport.parseDraft(contents, report);
  const notesCount = draft.cell_notes.filter(row => row.analyst_note !== "").length;
  const dispositionCount = draft.cell_notes.filter(row => row.disposition !== "UNREVIEWED").length;
  if (notesCount || dispositionCount || state.savedDrafts.has(report.receipt_sha256)) {
    state.savedDrafts.set(report.receipt_sha256, Object.freeze({ text: contents, notesCount, dispositionCount }));
  }
  renderSavedDrafts();
}

function rememberActiveDraft() {
  if (state.report) rememberDraft(state.report, state.notes, state.dispositions);
}

function preservationError(err) {
  setError(`Your current work is still here, but could not be saved in this tab. ${err instanceof Error ? err.message : String(err)}`);
}

function rememberEditedDraft() {
  try { rememberActiveDraft(); setError(""); }
  catch (err) { preservationError(err); }
}

function renderSavedDrafts(preferredReceipt = "") {
  const previous = preferredReceipt || el.savedDraftSelect.value;
  const receipts = [...state.savedDrafts.keys()];
  el.savedDraftSelect.replaceChildren(...(receipts.length ? receipts.map(receipt => {
    const saved = state.savedDrafts.get(receipt);
    return new Option(`${receipt.slice(0, 12)}… · ${saved.notesCount} notes · ${saved.dispositionCount} dispositions`, receipt);
  }) : [new Option("No drafts saved yet", "")]));
  el.savedDraftSelect.value = state.savedDrafts.has(previous) ? previous : (receipts[0] || "");
  el.savedDraftSelect.disabled = !receipts.length;
  const selected = el.savedDraftSelect.value;
  const saved = state.savedDrafts.get(selected);
  const matches = !!saved && state.report?.receipt_sha256 === selected;
  el.downloadTabDraftBtn.disabled = !saved;
  el.restoreTabDraftBtn.disabled = !matches;
  el.savedDraftStatus.textContent = saved
    ? `${receipts.length} draft${receipts.length === 1 ? "" : "s"} saved in this tab. Selected report receipt: ${selected}. ${saved.notesCount} notes; ${saved.dispositionCount} reviewed dispositions. ${matches ? "Matches the active report." : "Inspect the matching evidence files before restoring this draft."}`
    : "Notes and dispositions are saved here as you work. Nothing is saved outside this tab.";
}

function restoreTabDraft() {
  if (!state.report) return;
  try {
    rememberActiveDraft();
    const saved = state.savedDrafts.get(el.savedDraftSelect.value);
    if (!saved) throw new Error("Select a draft saved in this tab.");
    const restored = HandoffImport.parseDraft(saved.text, state.report);
    state.notes = restored.notes;
    state.dispositions = restored.dispositions;
    state.editRevision++;
    state.draftLoadSequence++;
    el.importDraftBtn.disabled = false;
    selectCell(state.selectedKey || keyFor(state.cells[0]));
    setError("");
    el.exportStatus.textContent = "Draft restored from this tab for the matching report. No approval authority is created.";
  } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
}

function downloadTabDraft() {
  try {
    const receipt = el.savedDraftSelect.value;
    const saved = state.savedDrafts.get(receipt);
    if (!saved) throw new Error("Select a draft saved in this tab.");
    downloadText(saved.text, "json", "application/json", receipt);
    setError("");
    el.savedDraftStatus.textContent = `Saved draft downloaded for report receipt ${receipt}. Inspect its matching evidence files to restore it.`;
  } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
}

function installReport(report) {
  if (!report || !Array.isArray(report.assessment_matrix) || report.assessment_matrix.length !== 12) {
    throw new Error("Expected a 12-cell compiler report.");
  }
  if (report.mode !== "UNTRUSTED_INSPECTION") throw new Error("Workbench accepts untrusted inspection reports only.");
  if (report.trust?.current_evidence_review_authority !== false) throw new Error("Report unexpectedly carries current review authority.");
  WorkbenchHandoff.buildDraft(report);
  rememberActiveDraft();
  const saved = state.savedDrafts.get(report.receipt_sha256);
  const restored = saved ? HandoffImport.parseDraft(saved.text, report) : null;
  state.generation++;
  state.editRevision = 0;
  state.draftLoadSequence++;
  state.report = report;
  state.cells = report.assessment_matrix.slice();
  state.selectedKey = null;
  state.notes = restored ? restored.notes : new Map();
  state.dispositions = restored ? restored.dispositions : new Map();
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
  renderSavedDrafts(report.receipt_sha256);
  if (restored) el.exportStatus.textContent = "Draft restored from this tab for the same report receipt. No approval authority is created.";
}

function renderSummary() {
  el.summary.replaceChildren();
  const codes = [...new Set([
    "UNTRUSTED_EVIDENCE_CONSISTENT", "HOLD_MISSING_EVIDENCE", "HOLD_CONFLICT", "HOLD_STALE_EVIDENCE",
    ...state.cells.map(cell => cell.status)
  ])];
  for (const code of codes) {
    const item = document.createElement("div");
    appendText(item, "dt", evidenceState({ status: code }).label);
    appendText(item, "dd", String(state.cells.filter(cell => cell.status === code).length));
    if (!Object.prototype.hasOwnProperty.call(evidenceStates, code)) appendText(item, "small", text(code), "source-status");
    el.summary.append(item);
  }
  const guide = document.createElement("div"); guide.className = "reading-guide";
  appendText(guide, "dt", "Reading the evidence");
  appendText(guide, "dd", "Zero is a supplied numeric value, not missing data. Missing evidence, not assessed, not applicable, stale and conflicting records remain distinct. Null is not a score or a finding. Labels and border patterns work without color.");
  el.summary.append(guide);
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
  el.statusFilter.replaceChildren(new Option("All evidence states", ""), ...statuses.map(s => new Option(`${evidenceState({status:s}).label} · ${text(s)}`, s)));
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
    button.dataset.evidenceState = cellPresentation(cell).kind;
    button.setAttribute("aria-controls", "detailPanel");
    button.setAttribute("aria-label", `${cell.group}: ${areaLabels[cell.dimension] || cell.dimension}, ${evidenceState(cell).label}. Maturity: ${valuePresentation(cell, "maturity")}. Confidence in basis points: ${valuePresentation(cell, "confidence_bp")}. Open evidence and notes.`);
    button.setAttribute("aria-current", state.selectedKey === key ? "true" : "false");
    appendText(button, "span", areaLabels[cell.dimension] || cell.dimension, "area");
    button.append(statusBadge(cell));
    appendCellValues(button, cell);
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
  const values = document.createElement("div"); values.className = "cell-values";
  appendCellValues(values, cell); el.cellSummary.append(values);
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
  try { rememberActiveDraft(); }
  catch (err) { preservationError(err); return false; }
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
  renderSavedDrafts();
  setError("");
  return true;
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
  if (!resetWorkbench()) return;
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
    rememberDraft(report, restored.notes, restored.dispositions);
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
function downloadText(contents, extension, contentType, receipt = state.report?.receipt_sha256) {
  if (typeof receipt !== "string" || !/^[a-f0-9]{64}$/.test(receipt)) throw new Error("A report receipt is required for this download.");
  const blob = new Blob([contents], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `uiowa-rfq18649-draft-handoff-${receipt.slice(0, 12)}.${extension}`;
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
  try {
    setError(""); installReport(syntheticReport());
    if (restoreInvokerFocus) document.getElementById("summary-heading").focus();
  } catch (err) { preservationError(err); }
});
el.resetBtn.addEventListener("click", resetWorkbench);
el.search.addEventListener("input", renderMatrix);
el.statusFilter.addEventListener("change", renderMatrix);
el.note.addEventListener("input", () => {
  if (state.selectedKey) { state.notes.set(state.selectedKey, el.note.value); state.editRevision++; rememberEditedDraft(); }
});
el.disposition.addEventListener("change", () => {
  if (state.selectedKey) { state.dispositions.set(state.selectedKey, el.disposition.value); state.editRevision++; rememberEditedDraft(); }
});
el.exportBtn.addEventListener("click", exportDraft);
el.backToCellBtn.addEventListener("click", returnToSelectedCell);
el.markdownBtn.addEventListener("click", exportMarkdown);
el.importDraftBtn.addEventListener("click", importDraft);
el.savedDraftSelect.addEventListener("change", () => renderSavedDrafts());
el.restoreTabDraftBtn.addEventListener("click", restoreTabDraft);
el.downloadTabDraftBtn.addEventListener("click", downloadTabDraft);

resetWorkbench();
if (new URLSearchParams(location.search).get("demo") === "1") installReport(syntheticReport());
