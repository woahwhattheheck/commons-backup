/* UIOWA-128: exact, receipt-bound navigation. No scoring, persistence or network. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.UIowaReviewNavigation = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const SCHEMA = "uiowa-rfq18649-review-navigation/v1";
  const KINDS = new Set(["source", "finding", "recommendation", "review-comment"]);
  const FIELDS = ["review", "receipt", "kind", "origin", "id", "revision"];
  const RECEIPT = /^[0-9a-f]{64}$/;
  const MAX_RECORDS = 2000;
  function object(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
  function required(value, field, limit = 512) {
    if (typeof value !== "string" || !value.trim() || value.length > limit || /[\x00-\x1f\x7f]/.test(value)) {
      throw new Error(`${field}: expected nonempty text, at most ${limit} characters, without control characters.`);
    }
    try { encodeURIComponent(value); } catch (_) { throw new Error(`${field}: malformed Unicode.`); }
    return value; // Deliberately do not trim, case-fold or Unicode-normalize identifiers.
  }
  function identity(record) {
    if (!object(record) || !KINDS.has(record.kind)) throw new Error("kind: expected source, finding, recommendation or review-comment.");
    return { kind: record.kind, origin: required(record.origin, "origin"), id: required(record.id, "id"),
      revision: required(record.revision, "revision", 128) };
  }
  function key(record) { const r = identity(record); return JSON.stringify([r.kind, r.origin, r.id, r.revision]); }
  function validateReceipt(receipt) {
    if (typeof receipt !== "string" || !RECEIPT.test(receipt)) throw new Error("receipt: expected an exact lowercase SHA-256 report receipt.");
    return receipt;
  }
  function routeFor(receipt, record) {
    const r = identity(record);
    return "#" + new URLSearchParams({review: "v1", receipt: validateReceipt(receipt), ...r}).toString();
  }
  function parseRoute(hash) {
    if (!hash || hash === "#") return null;
    const raw = hash.startsWith("#") ? hash.slice(1) : hash;
    if (!raw.startsWith("review=") && !raw.includes("&review=")) return null;
    if (raw.length > 8192) throw new Error("Navigation link exceeds 8192 characters.");
    try { decodeURIComponent(raw.replace(/\+/g, " ")); } catch (_) { throw new Error("Navigation link has invalid percent encoding or Unicode."); }
    const params = new URLSearchParams(raw);
    for (const name of params.keys()) if (!FIELDS.includes(name)) throw new Error(`Unknown navigation field: ${name}.`);
    for (const name of FIELDS) if (params.getAll(name).length !== 1) throw new Error(`Navigation field ${name} must occur exactly once.`);
    if (params.get("review") !== "v1") throw new Error("Unsupported navigation link version.");
    const r = identity(Object.fromEntries(params));
    return {receipt: validateReceipt(params.get("receipt")), ...r};
  }
  function sourceRecords(report) {
    const sources = new Map();
    if (!report) return [];
    const receipt = validateReceipt(report.receipt_sha256);
    for (const cell of report.assessment_matrix || []) {
      for (const id of cell.source_ids || []) {
        required(id, "source id");
        if (!sources.has(id)) sources.set(id, {kind: "source", origin: "compiler-report", id, revision: receipt,
          title: id, text: "Source identifier referenced by the installed report; the report does not contain the source document.",
          synthetic: report.synthetic_demo === true, cell_keys: [], references: []});
        const cells = sources.get(id).cell_keys;
        const cellKey = `${cell.group}|${cell.dimension}`;
        if (!cells.includes(cellKey)) cells.push(cellKey);
      }
    }
    return [...sources.values()];
  }
  function validatePacket(packet, report) {
    if (!object(packet) || packet.schema !== SCHEMA) throw new Error(`Expected ${SCHEMA}.`);
    validateReceipt(packet.report_receipt_sha256);
    if (!report) throw new Error("Import the matching compiler report or synthetic UI demo before importing review records.");
    if (packet.report_receipt_sha256 !== report.receipt_sha256) throw new Error("RECEIPT_MISMATCH: review records belong to a different report; import the matching report first.");
    if (!Array.isArray(packet.records) || packet.records.length > MAX_RECORDS) throw new Error(`records: expected an array of at most ${MAX_RECORDS} records.`);
    const cells = new Set((report.assessment_matrix || []).map(c => `${c.group}|${c.dimension}`));
    const normalized = JSON.parse(JSON.stringify(packet, (_key, value) => {
      try {
        encodeURIComponent(_key);
        if (typeof value === "string") encodeURIComponent(value);
      } catch (_) { throw new Error("Review JSON contains malformed Unicode in a string or key."); }
      if (typeof value === "number" && (!Number.isFinite(value) || Object.is(value, -0) || (Number.isInteger(value) && !Number.isSafeInteger(value)))) {
        throw new Error("Review JSON contains a number that cannot be preserved safely; encode it as text.");
      }
      return value;
    })); // Own a JSON-semantic snapshot; never mutate caller evidence.
    normalized.records.forEach((r, index) => {
      identity(r);
      if (r.origin === "compiler-report") throw new Error(`Record ${index}: compiler-report is reserved for actual installed source memberships.`);
      if (typeof r.title !== "string" || typeof r.text !== "string") throw new Error(`Record ${index}: title and text must be strings.`);
      if (r.title.length > 2000 || r.text.length > 50000) throw new Error(`Record ${index}: title or text exceeds the documented size limit.`);
      if (typeof r.synthetic !== "boolean") throw new Error(`Record ${index}: synthetic must be an explicit boolean.`);
      if (!Array.isArray(r.references) || r.references.length > MAX_RECORDS) throw new Error(`Record ${index}: references must be a bounded array.`);
      r.references.forEach(identity);
      if (!Array.isArray(r.cell_keys) || r.cell_keys.some(c => typeof c !== "string" || !cells.has(c))) {
        throw new Error(`Record ${index}: cell_keys must name actual installed group|dimension cells.`);
      }
    });
    return normalized;
  }
  function captureReviewState(report, packet, hash) {
    if (typeof hash !== "string") throw new Error("Review locator must be text.");
    // One owned packet snapshot accompanies the existing parked workspace. It
    // uses the current intake/record bounds and is never a second history cache.
    return Object.freeze({
      report_receipt_sha256: report ? validateReceipt(report.receipt_sha256) : null,
      packet: packet === null ? null : validatePacket(packet, report),
      hash
    });
  }
  function restoreReviewState(snapshot, report) {
    if (!object(snapshot) || snapshot.report_receipt_sha256 !== (report ? report.receipt_sha256 : null)) {
      throw new Error("Parked review records do not match the restored report.");
    }
    return captureReviewState(report, snapshot.packet, snapshot.hash);
  }
  function catalog(report, packet) {
    const records = sourceRecords(report);
    // Refuse to mix a stale manifest even when a caller bypasses validatePacket.
    if (packet && report && packet.report_receipt_sha256 === report.receipt_sha256) records.push(...packet.records);
    const byKey = new Map();
    records.forEach(record => { const k = key(record); if (!byKey.has(k)) byKey.set(k, []); byKey.get(k).push(record); });
    return {records, byKey};
  }
  function resolve(route, report, packet) {
    if (!route) return {status: "NO_ROUTE", message: "Choose a review record or open a saved review link."};
    identity(route); validateReceipt(route.receipt);
    if (!report) return {status: "WAITING_FOR_REPORT", message: `Import report ${route.receipt} (or load its matching synthetic demo). The link is retained; no evidence is stored in it.`};
    if (route.receipt !== report.receipt_sha256) return {status: "REPORT_MISMATCH", message: `Link expects report ${route.receipt}; installed report is ${report.receipt_sha256}. Import the matching report; no substitute was selected.`};
    if (route.origin !== "compiler-report" && !packet) return {status: "WAITING_FOR_RECORDS", message: `Import the review-navigation JSON for report ${route.receipt} to locate ${route.kind} ${route.id}.`};
    const entries = catalog(report, packet).byKey.get(key(route)) || [];
    if (entries.length > 1) return {status: "AMBIGUOUS_RECORD", message: `${entries.length} records share the exact kind, origin, ID and revision. Repair the imported packet; no first-match selection was made.`};
    if (!entries.length) {
      const candidates = catalog(report, packet).records.filter(r => r.kind === route.kind && r.id === route.id).map(identity);
      return {status: "MISSING_RECORD", message: `No exact ${route.kind} ${route.id} at origin ${route.origin}, revision ${route.revision}. Check its ID/version or import the correct packet.`, candidates};
    }
    return {status: "FOUND", message: "Exact record located. Navigation is not evidence validation or approval.", record: entries[0]};
  }
  function relatedCells(record, report, packet) {
    const result = new Set(), seen = new Set(), pending = [identity(record)];
    const index = catalog(report, packet).byKey;
    while (pending.length) {
      const ref = pending.pop(), k = key(ref);
      if (seen.has(k)) continue;
      seen.add(k);
      const hits = index.get(k) || [];
      if (hits.length !== 1) continue; // Missing or ambiguous links do not become implicit joins.
      const r = hits[0];
      (r.cell_keys || []).forEach(c => result.add(c));
      (r.references || []).forEach(ref => pending.push(ref));
    }
    return [...result].sort();
  }
  function escapeHTML(value) { return String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  function anchorFor(receipt, record) { return "record-" + encodeURIComponent(JSON.stringify([validateReceipt(receipt), key(record)])); }
  function guideHTML(report, packet) {
    if (!report) throw new Error("No report installed.");
    const receipt = validateReceipt(report.receipt_sha256), {records, byKey} = catalog(report, packet);
    const link = r => "#" + encodeURIComponent(anchorFor(receipt, r));
    const section = (r, i) => {
      const unique = byKey.get(key(r)).length === 1;
      const refs = (r.references || []).map(ref => {
        const hits = byKey.get(key(ref)) || [];
        return hits.length === 1 ? `<li><a href="${link(ref)}">${escapeHTML(ref.kind + " · " + ref.id)}</a></li>` :
          `<li>${escapeHTML(ref.kind + " · " + ref.id)} — ${hits.length ? "AMBIGUOUS_RECORD" : "MISSING_RECORD"}; ${escapeHTML(key(ref))}</li>`;
      }).join("");
      const anchor = unique ? anchorFor(receipt, r) : "ambiguous-" + i;
      return `<section id="${escapeHTML(anchor)}"><h2>${escapeHTML(r.kind + " · " + r.id)}</h2>` +
        `<p>${unique ? "EXACT ID" : "AMBIGUOUS_RECORD"} · ${r.synthetic ? "SYNTHETIC EXAMPLE — NOT UNIVERSITY FINDINGS" : "IMPORTED RECORD — NOT INDEPENDENTLY VERIFIED"}</p>` +
        `<h3>${escapeHTML(r.title)}</h3><p>${escapeHTML(r.text)}</p><p>Origin: ${escapeHTML(r.origin)} · revision: ${escapeHTML(r.revision)}</p>` +
        `<p>Related cells: ${escapeHTML(relatedCells(r, report, packet).join(", ") || "none resolved")}</p><ul>${refs}</ul>` +
        `<details><summary>Original record, including extension fields</summary><pre>${escapeHTML(JSON.stringify(r, null, 2))}</pre></details><p><a href="#review-index">Back to review index</a></p></section>`;
    };
    const index = records.map((r, i) => `<li><a href="${byKey.get(key(r)).length === 1 ? link(r) : "#ambiguous-" + i}">${escapeHTML(r.kind + " · " + r.id)}</a></li>`).join("");
    return "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" +
      "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">" +
      "<title>RFQ 18649 linked review guide — draft</title><style>body{font:1rem/1.6 system-ui,sans-serif;max-width:70rem;margin:auto;padding:1rem}section{border-top:1px solid;padding-top:1rem;margin-top:2rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}a:focus-visible{outline:3px solid}p,li{overflow-wrap:anywhere}@media print{section{break-inside:auto}h2,h3{break-after:avoid}details{display:block}}</style></head><body>" +
      `<h1>Linked review guide — DRAFT / NON-AUTHORITATIVE</h1><p>Report receipt: ${receipt}</p>` +
      "<p>Read-only snapshots and exact links. This guide does not contain source documents unless they were explicitly supplied as record text. It makes no assessment, acceptance, payment or approval decision. No scripts, telemetry or external links.</p>" +
      `<nav id="review-index" aria-label="Review records"><h2>Review index</h2><ul>${index}</ul></nav>${records.map(section).join("\n")}</body></html>\n`;
  }
  function syntheticPacket() {
    const receipt = "d".repeat(64), origin = "uiowa-128-synthetic-review", revision = "example-v1";
    const source = {kind: "source", origin: "compiler-report", id: "synthetic-ess-software_development", revision: receipt};
    const finding = {kind: "finding", origin, id: "FND-SYN-128", revision};
    const recommendation = {kind: "recommendation", origin, id: "REC-SYN-128", revision};
    const comment = {kind: "review-comment", origin, id: "COMMENT-SYN-128/é + #1", revision};
    return {schema: SCHEMA, report_receipt_sha256: receipt, synthetic: true, records: [
      {...finding, title: "Locate the referenced development evidence", text: "SYNTHETIC rehearsal question, not a finding: which source belongs to the ESS development cell? The UI-only source identifier is not source-document evidence.", synthetic: true, cell_keys: [], references: [source], extensions: {assessment_status: "NOT_ASSESSED", source_fixture: "app.js::syntheticReport"}},
      {...recommendation, title: "Request the source document before drawing a conclusion", text: "SYNTHETIC suggested next review action, not a University recommendation or a maturity rating.", synthetic: true, cell_keys: [], references: [finding], extensions: {effort: null, basis: "UNESTIMATED"}},
      {...comment, title: "Reviewer asks where the proposed next step came from", text: "SYNTHETIC reviewer comment: follow recommendation → finding question → original source ID → ESS cell, then retain the exact link for the next reviewer.", synthetic: true, cell_keys: [], references: [recommendation], extensions: {reviewer_role: "Fictional peer reviewer", disposition: "OPEN"}}
    ], extensions: {purpose: "Navigation rehearsal only; no scoring, credentials, University evidence or real reviewer identity."}};
  }
  function attach(adapter) {
    const document = adapter.document || globalThis.document, window = document.defaultView;
    let report = null, packet = null, importGeneration = 0;
    const make = (tag, content, attrs = {}) => { const e = document.createElement(tag); if (content !== undefined) e.textContent = content; for (const [k,v] of Object.entries(attrs)) e.setAttribute(k,v); return e; };
    const panel = make("section", undefined, {class: "panel", "aria-labelledby": "review-heading", id: "review-navigation"});
    panel.append(make("h2", "5. Linked review records", {id: "review-heading"}), make("p", "Open an exact source, finding, recommendation or review-comment link. Review JSON stays in this browser tab. Evidence imports clear review records; a temporary sample parks them until you leave. Links contain IDs and revisions, not evidence text."));
    const input = make("input", undefined, {id: "reviewFile", type: "file", accept: "application/json,.json"});
    const label = make("label", "Review-navigation JSON"); label.append(input);
    const demo = make("button", "Load synthetic linked review queue", {id: "reviewDemoBtn", type: "button"});
    const exportBtn = make("button", "Export linked HTML review guide", {id: "reviewGuideBtn", type: "button"});
    const exportPacket = make("button", "Export review-navigation JSON", {id: "reviewPacketBtn", type: "button"});
    const actions = make("div", undefined, {class: "actions"}); actions.append(demo, exportBtn, exportPacket);
    const error = make("p", "", {id: "reviewError", role: "alert", class: "error"});
    const status = make("p", "", {id: "reviewStatus", role: "status", "aria-live": "polite"});
    const queue = make("ul", undefined, {id: "reviewQueue", "aria-label": "Linked review queue"});
    const sources = make("details", undefined, {id: "reviewSources"});
    const sourceSummary = make("summary", "Report source references");
    const sourceQueue = make("ul", undefined, {id: "reviewSourceQueue", "aria-label": "Installed report source references"});
    sources.append(sourceSummary, sourceQueue);
    const detail = make("div", undefined, {id: "reviewDetail", tabindex: "-1", "aria-label": "Located review record"});
    const selectedLink = make("input", undefined, {id: "reviewCurrentLink", type: "text", readonly: "", "aria-label": "Exact current workbench link"});
    const linkLabel = make("label", "Exact link for this record (select to copy)"); linkLabel.append(selectedLink);
    panel.append(label, actions, error, status, queue, sources, linkLabel, detail);
    document.querySelector("main").append(panel);
    function download(content, type, name) {
      const url = window.URL.createObjectURL(new window.Blob([content], {type})), a = make("a", "", {href: url, download: name});
      document.body.append(a); a.click(); a.remove(); window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    }
    function chooseCell(cellKey) {
      adapter.selectCell(cellKey);
    }
    function follow(eventFocus = false) {
      detail.replaceChildren(); selectedLink.value = "";
      let result;
      try { result = resolve(parseRoute(window.location.hash), report, packet); }
      catch (e) { result = {status: "INVALID_LINK", message: e.message}; }
      status.dataset.state = result.status; status.textContent = result.status + ": " + result.message;
      if (result.status !== "FOUND") {
        if (result.status !== "NO_ROUTE") adapter.clearSelection?.();
        if (result.candidates?.length) detail.append(make("pre", JSON.stringify({available_versions_not_substituted: result.candidates}, null, 2)));
        return;
      }
      const r = result.record, cells = relatedCells(r, report, packet);
      const base = /^https?:$/.test(window.location.protocol) ? window.location.origin + window.location.pathname : "";
      selectedLink.value = base + routeFor(report.receipt_sha256, r);
      detail.append(make("h3", r.kind + " · " + r.id), make("p", r.synthetic ? "SYNTHETIC EXAMPLE — NOT UNIVERSITY FINDINGS" : "IMPORTED RECORD — NOT INDEPENDENTLY VERIFIED"), make("h4", r.title), make("p", r.text));
      const refs = make("ul", undefined, {"aria-label": "Exact record references"});
      for (const ref of r.references || []) { const li = make("li"); li.append(make("a", ref.kind + " · " + ref.id, {href: routeFor(report.receipt_sha256, ref)})); refs.append(li); }
      detail.append(refs);
      for (const cellKey of cells) { const b = make("button", "Open cell " + cellKey, {type: "button"}); b.addEventListener("click", () => { chooseCell(cellKey); document.getElementById("detail").focus(); }); detail.append(b); }
      const raw = make("details"); raw.append(make("summary", "Original record and extension fields"), make("pre", JSON.stringify(r, null, 2))); detail.append(raw);
      if (cells.length === 1) chooseCell(cells[0]);
      if (eventFocus) { detail.focus(); detail.scrollIntoView({block: "nearest"}); }
    }
    function render() {
      queue.replaceChildren(); sourceQueue.replaceChildren();
      exportBtn.disabled = !report; exportPacket.disabled = !packet;
      for (const r of catalog(report, packet).records) {
        const li = make("li"); li.append(make("a", r.kind + " · " + r.id, {href: routeFor(report.receipt_sha256, r)}));
        (r.origin === "compiler-report" ? sourceQueue : queue).append(li);
      }
      sourceSummary.textContent = `Report source references (${sourceQueue.childElementCount})`;
      if (!queue.childElementCount) queue.append(make("li", "No review records imported. Load a matching review packet; source references remain available below."));
      follow(false);
    }
    function importPacket(value) {
      packet = null; error.textContent = "";
      try { packet = validatePacket(value, report); }
      catch (e) { error.textContent = e.message; render(); throw e; }
      render();
    }
    function setReport(value) {
      importGeneration += 1; report = value; packet = null; input.value = ""; error.textContent = ""; render();
    }
    function captureState() { return captureReviewState(report, packet, window.location.hash); }
    function restoreState(snapshot) {
      const restored = restoreReviewState(snapshot, report);
      // Replace only this entry's fragment: leaving a sample does not add a
      // history entry or let a pending sample-file read reinstall its packet.
      if (window.location.hash !== restored.hash) {
        window.history.replaceState(window.history.state, "", window.location.href.split("#", 1)[0] + restored.hash);
      }
      importGeneration += 1; packet = restored.packet; input.value = ""; error.textContent = ""; render();
    }
    function clearSampleState() { restoreState(captureReviewState(report, null, "")); }
    input.addEventListener("change", async () => {
      const generation = ++importGeneration;
      packet = null; error.textContent = ""; render();
      try {
        const file = input.files?.[0]; if (!file) return;
        if (file.size > 1024 * 1024) throw new Error("Review-navigation file exceeds 1 MiB.");
        const bytes = await file.arrayBuffer();
        if (generation !== importGeneration) return; // A report replacement or later import superseded this read.
        let raw;
        try { raw = new TextDecoder("utf-8", {fatal: true}).decode(bytes); }
        catch (_) { throw new Error("Review-navigation file must contain valid UTF-8."); }
        importPacket(JSON.parse(raw));
      } catch (e) { if (generation === importGeneration) { error.textContent = e.message; render(); } }
    });
    demo.addEventListener("click", () => { importGeneration += 1; try { importPacket(syntheticPacket()); } catch (_) {} });
    exportBtn.addEventListener("click", () => { if (report) download(guideHTML(report, packet), "text/html", "uiowa-linked-review-guide.html"); });
    exportPacket.addEventListener("click", () => { if (packet) download(JSON.stringify(packet, null, 2) + "\n", "application/json", "uiowa-review-navigation.json"); });
    const onHash = () => follow(true); window.addEventListener("hashchange", onHash);
    render();
    return {setReport, importPacket, captureState, restoreState, clearSampleState,
      dispose: () => {window.removeEventListener("hashchange", onHash); panel.remove();}};
  }
  return Object.freeze({SCHEMA, identity, key, routeFor, parseRoute, sourceRecords, validatePacket, captureReviewState, restoreReviewState, catalog, resolve, relatedCells, anchorFor, guideHTML, syntheticPacket, attach});
});
