"use strict";

// Draft notes are a separate projection. They never alter the compiler report.
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.WorkbenchHandoff = api;
})(typeof window !== "undefined" ? window : null, function () {
  const SCHEMA = "uiowa-rfq18649-analyst-handoff-draft/v1";
  const MAX_NOTE_LENGTH = 4000;
  const DISPOSITIONS = new Set([
    "UNREVIEWED", "NEEDS_EVIDENCE", "DISCUSS_WITH_PRIME", "TECHNICAL_DRAFT_NOTE"
  ]);
  const AUTHORITY_KEYS = [
    "buyer_approved", "prime_approved", "current_evidence_review_authority",
    "submission_authorized", "signature_authorized", "invoice_or_payment_authorized",
    "recognized_revenue"
  ];
  const DRAFT_KEYS = [
    "schema", "status", "report_receipt_sha256", "report_mode", "aggregate_state",
    "synthetic_demo", "cell_notes", "authority"
  ];
  const NOTE_KEYS = ["group", "dimension", "compiler_status", "disposition", "analyst_note"];

  function object(value, label) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`${label} must be an object.`);
    }
    return value;
  }

  function exactKeys(value, expected, label) {
    object(value, label);
    const actual = Object.keys(value).sort();
    if (actual.length !== expected.length || actual.some((key, i) => key !== expected.slice().sort()[i])) {
      throw new Error(`${label} has unexpected or missing fields.`);
    }
  }

  function keyFor(cell) {
    if (typeof cell.group !== "string" || typeof cell.dimension !== "string" ||
        !cell.group || !cell.dimension || cell.group.includes("|") || cell.dimension.includes("|")) {
      throw new Error("Assessment cell identity is invalid.");
    }
    return `${cell.group}|${cell.dimension}`;
  }

  function reportCells(report) {
    object(report, "Compiler report");
    if (report.mode !== "UNTRUSTED_INSPECTION" ||
        report.trust?.current_evidence_review_authority !== false ||
        report.trust?.authority_root_supplied_out_of_band !== false ||
        report.aggregate_state !== "HOLD_TRUSTED_AUTHORITY_REQUIRED") {
      throw new Error("Draft handoffs require a non-authorizing untrusted inspection report.");
    }
    if (typeof report.receipt_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(report.receipt_sha256)) {
      throw new Error("Compiler report receipt is invalid.");
    }
    if (report.synthetic_demo !== undefined && typeof report.synthetic_demo !== "boolean") {
      throw new Error("Compiler report synthetic marker must be boolean.");
    }
    if (!Array.isArray(report.assessment_matrix) || report.assessment_matrix.length !== 12) {
      throw new Error("Compiler report must contain exactly 12 assessment cells.");
    }
    const cells = report.assessment_matrix;
    // The existing synthetic UI uses the long software label; real compiler v2 uses software.
    const software = report.synthetic_demo === true ? "software_development" : "software";
    const expected = new Set(["ESS", "RIS", "IAM"].flatMap(group =>
      [software, "security", "deployment", "ai_readiness"].map(dimension => `${group}|${dimension}`)));
    for (const cell of cells) {
      object(cell, "Assessment cell");
      if (!expected.delete(keyFor(cell))) throw new Error("Compiler report has duplicate or unexpected assessment cells.");
      if (typeof cell.status !== "string" ||
          !(cell.status === "UNTRUSTED_EVIDENCE_CONSISTENT" || cell.status.startsWith("HOLD_"))) {
        throw new Error("Compiler report cell is not an untrusted inspection state.");
      }
    }
    return cells;
  }

  function checkedNote(value) {
    if (typeof value !== "string" || value.length > MAX_NOTE_LENGTH) {
      throw new Error(`Analyst notes must be strings of at most ${MAX_NOTE_LENGTH} characters.`);
    }
    return value;
  }

  function checkedDisposition(value) {
    if (!DISPOSITIONS.has(value)) throw new Error("Unknown analyst disposition.");
    return value;
  }

  function buildDraft(report, notes = new Map(), dispositions = new Map()) {
    const cells = reportCells(report);
    const keys = new Set(cells.map(keyFor));
    for (const [label, values] of [["Notes", notes], ["Dispositions", dispositions]]) {
      if (!(values instanceof Map)) throw new Error(`${label} must be a Map.`);
      for (const key of values.keys()) {
        if (!keys.has(key)) throw new Error(`${label} contain an unknown assessment cell.`);
      }
    }
    const draft = {
      schema: SCHEMA,
      status: "DRAFT_NON_AUTHORITATIVE",
      report_receipt_sha256: report.receipt_sha256,
      report_mode: report.mode,
      aggregate_state: report.aggregate_state,
      synthetic_demo: report.synthetic_demo === true,
      cell_notes: cells.map(cell => ({
        group: cell.group,
        dimension: cell.dimension,
        compiler_status: cell.status,
        disposition: checkedDisposition(dispositions.has(keyFor(cell)) ? dispositions.get(keyFor(cell)) : "UNREVIEWED"),
        analyst_note: checkedNote(notes.has(keyFor(cell)) ? notes.get(keyFor(cell)) : "")
      })),
      authority: Object.fromEntries(AUTHORITY_KEYS.map(key => [key, false]))
    };
    return draft;
  }

  function validateDraft(draft, report) {
    const cells = reportCells(report);
    exactKeys(draft, DRAFT_KEYS, "Draft handoff");
    if (draft.schema !== SCHEMA || draft.status !== "DRAFT_NON_AUTHORITATIVE") {
      throw new Error("Unsupported draft handoff schema or status.");
    }
    if (draft.report_receipt_sha256 !== report.receipt_sha256 ||
        draft.report_mode !== report.mode || draft.aggregate_state !== report.aggregate_state ||
        draft.synthetic_demo !== (report.synthetic_demo === true)) {
      throw new Error("Draft handoff does not match this report receipt, mode, state, or synthetic marker.");
    }
    exactKeys(draft.authority, AUTHORITY_KEYS, "Draft authority");
    if (AUTHORITY_KEYS.some(key => draft.authority[key] !== false)) {
      throw new Error("Every draft handoff authority flag must be false.");
    }
    if (!Array.isArray(draft.cell_notes) || draft.cell_notes.length !== cells.length) {
      throw new Error("Draft handoff must contain exactly 12 cell notes.");
    }
    const byKey = new Map();
    const expected = new Map(cells.map(cell => [keyFor(cell), cell]));
    for (const row of draft.cell_notes) {
      exactKeys(row, NOTE_KEYS, "Cell note");
      const key = keyFor(row);
      const cell = expected.get(key);
      if (!cell || byKey.has(key)) throw new Error("Draft handoff has duplicate or unknown assessment cells.");
      if (row.compiler_status !== cell.status) throw new Error("Draft cell status differs from the compiler report.");
      byKey.set(key, {
        group: cell.group,
        dimension: cell.dimension,
        compiler_status: cell.status,
        disposition: checkedDisposition(row.disposition),
        analyst_note: checkedNote(row.analyst_note)
      });
    }
    return cells.map(cell => byKey.get(keyFor(cell)));
  }

  function escapeMarkdown(value) {
    return String(value == null ? "Not supplied" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\\/g, "\\\\").replace(/([`*_{}\[\]()#+.!|~\-])/g, "\\$1")
      .replace(/\r\n?/g, "\n");
  }

  function inline(value) { return escapeMarkdown(value).replace(/\n/g, " "); }

  function renderMarkdown(report, draft) {
    const rows = validateDraft(draft, report);
    const cells = report.assessment_matrix;
    const statusCounts = new Map();
    const dispositionCounts = new Map();
    cells.forEach(cell => statusCounts.set(cell.status, (statusCounts.get(cell.status) || 0) + 1));
    rows.forEach(row => dispositionCounts.set(row.disposition, (dispositionCounts.get(row.disposition) || 0) + 1));
    const counts = values => [...values.entries()].sort(([a], [b]) => a.localeCompare(b))
      .map(([name, count]) => `${inline(name)}: ${count}`).join("; ");
    const lines = [
      "# University of Iowa RFQ 18649 — draft analyst handoff", "",
      "**DRAFT — NON-AUTHORITATIVE**", "",
      `- Report receipt: ${inline(report.receipt_sha256)}`,
      `- Report mode: ${inline(report.mode)}`,
      `- Aggregate state: ${inline(report.aggregate_state)}`,
      `- Evidence generation: ${inline(report.evidence_authority?.generation || report.candidate?.authority_generation)}`,
      `- Evaluation time recorded in report: ${inline(report.evaluated_at)}`,
      `- Evidence authority root recorded in report: ${inline(report.authority_root_sha256)}`,
      `- Synthetic UI demonstration: ${draft.synthetic_demo ? "YES — not compiler output" : "no"}`,
      `- Compiler states: ${counts(statusCounts)}`,
      `- Analyst dispositions: ${counts(dispositionCounts)}`, "",
      "## Assessment overview", "",
      "| Group | Dimension | Compiler state | Analyst disposition | Sources |",
      "|---|---|---|---|---:|"
    ];
    cells.forEach((cell, i) => lines.push(
      `| ${inline(cell.group)} | ${inline(cell.dimension)} | ${inline(cell.status)} | ${inline(rows[i].disposition)} | ${Array.isArray(cell.source_ids) ? cell.source_ids.length : 0} |`
    ));
    lines.push("", "## Evidence and analyst notes", "");
    const sourceReceipts = new Map((Array.isArray(report.source_receipts) ? report.source_receipts : [])
      .map(source => [source.source_id, source]));
    cells.forEach((cell, i) => {
      const sourceIds = Array.isArray(cell.source_ids) ? cell.source_ids : [];
      const recordDigests = Array.isArray(cell.source_record_sha256s) ? cell.source_record_sha256s : [];
      const reasons = Array.isArray(cell.reason_codes) ? cell.reason_codes : [];
      lines.push(`### ${inline(cell.group)} / ${inline(cell.dimension)}`, "",
        `- Compiler state: ${inline(cell.status)}`,
        `- Analyst disposition: ${inline(rows[i].disposition)}`,
        `- Compiler reasons: ${reasons.length ? reasons.map(inline).join("; ") : "None recorded"}`);
      if (!sourceIds.length) lines.push("- Source references: none recorded for this cell.");
      sourceIds.forEach((id, sourceIndex) => {
        const receipt = sourceReceipts.get(id);
        lines.push(`- Source ID: ${inline(id)}`,
          `  - Source record SHA-256: ${inline(recordDigests[sourceIndex])}`,
          `  - Source content SHA-256: ${inline(receipt?.source_content_sha256)}`);
      });
      lines.push("", "Analyst note (draft, not evidence):", "");
      const note = rows[i].analyst_note;
      if (note) lines.push(...note.split(/\r\n?|\n/).map(line => `> ${escapeMarkdown(line)}`));
      else lines.push("No analyst note recorded.");
      lines.push("");
    });
    lines.push("## Open follow-ups", "");
    let followups = 0;
    cells.forEach((cell, i) => {
      const row = rows[i];
      const actions = [];
      if (cell.status === "HOLD_MISSING_EVIDENCE") actions.push("Obtain source evidence for this cell.");
      else if (cell.status === "HOLD_STALE_EVIDENCE") actions.push("Refresh the stale source evidence identified in the compiler reasons.");
      else if (cell.status === "HOLD_CONFLICT") actions.push("Reconcile the conflicting source evidence.");
      else if (cell.status.startsWith("HOLD_")) actions.push("Resolve the compiler HOLD reasons shown above.");
      if (row.disposition === "UNREVIEWED") actions.push("Complete analyst review.");
      else if (row.disposition === "NEEDS_EVIDENCE") actions.push("Resolve the analyst's evidence request.");
      else if (row.disposition === "DISCUSS_WITH_PRIME") actions.push("Review the analyst note with the prospective prime through the existing coordination process.");
      else if (row.disposition === "TECHNICAL_DRAFT_NOTE") actions.push("Review the draft technical note before using it in a finding.");
      if (actions.length) {
        followups += 1;
        lines.push(`- ${inline(cell.group)} / ${inline(cell.dimension)}: ${actions.join(" ")}`);
      }
    });
    if (!followups) lines.push("No cell-specific follow-ups were recorded; the report remains untrusted.");
    lines.push("", "## Limitations and authority", "",
      "- This export preserves the report's recorded evaluation time; it does not perform currentness verification.",
      "- Receipt matching binds draft notes to a report. It does not authenticate the analyst, evidence provenance, or authority root.",
      "- Source IDs and digests are traceability references. Original source contents and the full compiler report are not included in this Markdown file.",
      "- Analyst notes, dispositions, and follow-ups are draft production inputs; they do not change compiler states or establish technical conclusions.",
      "- Every buyer, prime, current-evidence, submission, signature, invoice/payment, and recognized-revenue authority flag is false.",
      "- Final professional judgment, recommendations, and University-facing activity remain with the prospective prime.");
    if (draft.synthetic_demo) lines.push("- This is a synthetic UI demonstration, not a compiled assessment or evidence of customer work.");
    lines.push("");
    return lines.join("\n");
  }

  return Object.freeze({ buildDraft, validateDraft, renderMarkdown });
});
