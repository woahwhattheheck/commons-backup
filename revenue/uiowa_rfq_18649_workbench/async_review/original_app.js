"use strict";

const state = { report: null, cells: [], selectedKey: null, notes: new Map(), dispositions: new Map() };
const el = Object.fromEntries([
  "candidateFile","authorityFile","inspectBtn","demoBtn","resetBtn","error","summary","search",
  "statusFilter","matrix","detail","disposition","note","exportBtn","exportStatus"
].map(id => [id, document.getElementById(id)]));

function keyFor(cell) { return `${cell.group}|${cell.dimension}`; }
function text(value) { return value == null ? "—" : String(value); }
function setError(message="") { el.error.textContent = message; }

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
  el.exportStatus.textContent = "";
  renderSummary();
  rebuildStatuses();
  renderMatrix();
  el.detail.textContent = "Select a cell.";
}

function renderSummary() {
  const rows = [
    ["Mode", state.report.mode],
    ["Aggregate", state.report.aggregate_state],
    ["Receipt", state.report.receipt_sha256],
    ["Commercial", state.report.commercial_terms?.status || "UNKNOWN"],
    ["Current authority", "false"],
    ["Synthetic demo", state.report.synthetic_demo === true ? "YES — UI ONLY" : "no"]
  ];
  el.summary.replaceChildren();
  for (const [k,v] of rows) {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = text(v);
    el.summary.append(dt, dd);
  }
}

function rebuildStatuses() {
  const current = el.statusFilter.value;
  const statuses = [...new Set(state.cells.map(c => c.status))].sort();
  el.statusFilter.replaceChildren(new Option("All statuses", ""), ...statuses.map(s => new Option(s, s)));
  if (statuses.includes(current)) el.statusFilter.value = current;
}

function visibleCells() {
  const q = el.search.value.trim().toLowerCase();
  const status = el.statusFilter.value;
  return state.cells.filter(cell => {
    if (status && cell.status !== status) return false;
    if (!q) return true;
    const hay = [cell.group, cell.dimension, cell.status, ...(cell.reason_codes || []), ...(cell.source_ids || [])].join(" ").toLowerCase();
    return hay.includes(q);
  });
}

function renderMatrix() {
  el.matrix.replaceChildren();
  for (const cell of visibleCells()) {
    const key = keyFor(cell);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cell";
    button.dataset.key = key;
    button.setAttribute("aria-current", state.selectedKey === key ? "true" : "false");
    const group = document.createElement("strong"); group.textContent = cell.group;
    const dimension = document.createElement("span"); dimension.textContent = cell.dimension;
    const status = document.createElement("span"); status.className = "status"; status.textContent = cell.status;
    button.append(group, dimension, status);
    button.addEventListener("click", () => selectCell(key));
    el.matrix.append(button);
  }
  el.matrix.dataset.renderedCells = String(el.matrix.childElementCount);
}

function selectCell(key) {
  const cell = state.cells.find(c => keyFor(c) === key);
  if (!cell) return;
  state.selectedKey = key;
  renderMatrix();
  el.detail.textContent = JSON.stringify({
    group: cell.group,
    dimension: cell.dimension,
    status: cell.status,
    maturity: cell.maturity,
    confidence_bp: cell.confidence_bp,
    source_ids: cell.source_ids || [],
    reason_codes: cell.reason_codes || []
  }, null, 2);
  el.note.disabled = false;
  el.disposition.disabled = false;
  el.note.value = state.notes.get(key) || "";
  el.disposition.value = state.dispositions.get(key) || "UNREVIEWED";
}

function resetWorkbench() {
  state.report = null; state.cells = []; state.selectedKey = null;
  state.notes = new Map(); state.dispositions = new Map();
  el.summary.replaceChildren(); el.matrix.replaceChildren();
  el.matrix.dataset.renderedCells = "0";
  el.detail.textContent = "Select a cell.";
  el.search.value = ""; el.search.disabled = true;
  el.statusFilter.replaceChildren(new Option("All statuses", "")); el.statusFilter.disabled = true;
  el.note.value = ""; el.note.disabled = true;
  el.disposition.value = "UNREVIEWED"; el.disposition.disabled = true;
  el.exportBtn.disabled = true; el.exportStatus.textContent = "";
  setError("");
}

async function readJsonFile(input, label) {
  const file = input.files?.[0];
  if (!file) throw new Error(`${label} file is required.`);
  if (file.size > 1024 * 1024) throw new Error(`${label} file exceeds 1 MiB browser intake limit.`);
  let value;
  try { value = JSON.parse(await file.text()); } catch { throw new Error(`${label} is not valid JSON.`); }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must be a JSON object.`);
  return value;
}

async function inspectFiles() {
  // A replacement attempt invalidates the prior generation immediately. If file
  // parsing, transport, or compiler inspection fails, stale notes/export authority
  // must not remain actionable under the guise of the attempted new import.
  resetWorkbench();
  el.inspectBtn.disabled = true;
  try {
    const [candidate, authority] = await Promise.all([
      readJsonFile(el.candidateFile, "Candidate"), readJsonFile(el.authorityFile, "Authority")
    ]);
    const response = await fetch("/api/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidate, authority }),
      credentials: "same-origin",
      cache: "no-store"
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Inspection failed (${response.status}).`);
    installReport(payload.report);
  } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  finally { el.inspectBtn.disabled = false; }
}

function exportDraft() {
  if (!state.report) return;
  const cellNotes = state.cells.map(cell => {
    const key = keyFor(cell);
    return {
      group: cell.group,
      dimension: cell.dimension,
      compiler_status: cell.status,
      disposition: state.dispositions.get(key) || "UNREVIEWED",
      analyst_note: state.notes.get(key) || ""
    };
  });
  const handoff = {
    schema: "uiowa-rfq18649-analyst-handoff-draft/v1",
    status: "DRAFT_NON_AUTHORITATIVE",
    report_receipt_sha256: state.report.receipt_sha256,
    report_mode: state.report.mode,
    aggregate_state: state.report.aggregate_state,
    synthetic_demo: state.report.synthetic_demo === true,
    cell_notes: cellNotes,
    authority: {
      buyer_approved: false,
      prime_approved: false,
      current_evidence_review_authority: false,
      submission_authorized: false,
      signature_authorized: false,
      invoice_or_payment_authorized: false,
      recognized_revenue: false
    }
  };
  const blob = new Blob([JSON.stringify(handoff, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `uiowa-rfq18649-draft-handoff-${state.report.receipt_sha256.slice(0, 12)}.json`;
  document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  el.exportStatus.textContent = "Draft handoff exported. It carries no approval or payment authority.";
}

el.inspectBtn.addEventListener("click", inspectFiles);
el.demoBtn.addEventListener("click", () => { setError(""); installReport(syntheticReport()); });
el.resetBtn.addEventListener("click", resetWorkbench);
el.search.addEventListener("input", renderMatrix);
el.statusFilter.addEventListener("change", renderMatrix);
el.note.addEventListener("input", () => { if (state.selectedKey) state.notes.set(state.selectedKey, el.note.value); });
el.disposition.addEventListener("change", () => { if (state.selectedKey) state.dispositions.set(state.selectedKey, el.disposition.value); });
el.exportBtn.addEventListener("click", exportDraft);

resetWorkbench();
if (new URLSearchParams(location.search).get("demo") === "1") installReport(syntheticReport());
