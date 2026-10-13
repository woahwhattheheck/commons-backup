"use strict";

// Portable working-note transport only. Original draft strings stay opaque until
// HandoffImport validates the selected entry against the active evidence report.
(() => {
  const HEADER = "TJLABS_DRAFT_BUNDLE_V1";
  const MAX_BYTES = 16 * 1024 * 1024;
  const MAX_ENTRIES = 256;
  const encoder = new TextEncoder();
  let drafts = new Map();
  let loadSequence = 0;

  const panel = document.createElement("details"); panel.className = "import-panel";
  appendText(panel, "summary", "Back up or restore several report drafts");
  const content = document.createElement("div"); content.className = "import-content";
  panel.append(content);
  const backupRow = document.createElement("div"); backupRow.className = "actions";
  const backup = button(backupRow, "Download tab draft bundle");
  content.append(backupRow);
  appendText(content, "p", "A bundle keeps the original note handoffs, not evidence files or the separate reviewer queue. It is not encrypted. Leave a temporary sample before backing up the parked review's drafts. Nothing is uploaded or saved outside the tab until you download it.", "field-note");
  const fileLabel = appendText(content, "label", "Saved draft bundle (.tjdrafts)");
  const fileInput = document.createElement("input");
  fileInput.type = "file"; fileInput.accept = ".tjdrafts,text/plain";
  fileLabel.append(fileInput);
  const loadRow = document.createElement("div"); loadRow.className = "actions";
  const load = button(loadRow, "Read bundle without changing notes"); load.disabled = true;
  const forget = button(loadRow, "Forget loaded bundle"); forget.disabled = true;
  content.append(loadRow);
  const entryLabel = appendText(content, "label", "Draft in loaded bundle");
  const select = document.createElement("select"); select.disabled = true;
  select.append(new Option("No bundle loaded", "")); entryLabel.append(select);
  const context = appendText(content, "p", "", "field-note");
  context.style.overflowWrap = "anywhere";
  const preview = document.createElement("details");
  appendText(preview, "summary", "Inspect original draft text");
  const original = appendText(preview, "pre", "No draft selected.");
  original.tabIndex = 0; original.setAttribute("aria-label", "Original draft JSON text");
  content.append(preview);
  const restoreRow = document.createElement("div"); restoreRow.className = "actions";
  const download = button(restoreRow, "Download selected draft JSON"); download.disabled = true;
  const restore = button(restoreRow, "Replace active notes with selected draft"); restore.disabled = true;
  content.append(restoreRow);
  appendText(content, "p", "Restoring replaces all 12 notes and dispositions for the matching report. Download the current draft first when both versions should be kept. The original strict handoff validator must accept the entire draft before any replacement.", "field-note");
  const status = appendText(content, "p", "", "field-note");
  status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  document.getElementById("savedDraftPanel").insertAdjacentElement("afterend", panel);

  function button(parent, title) {
    const node = appendText(parent, "button", title, "secondary");
    node.type = "button"; return node;
  }

  function message(error) {
    status.textContent = error instanceof Error ? error.message : String(error);
  }

  function render() {
    backup.disabled = state.savedDrafts.size === 0;
    backup.textContent = `Download ${state.savedDrafts.size} tab draft${state.savedDrafts.size === 1 ? "" : "s"} in one bundle`;
    const receipt = select.value;
    const selected = drafts.has(receipt);
    download.disabled = !selected;
    forget.disabled = drafts.size === 0;
    restore.disabled = !selected || state.report?.receipt_sha256 !== receipt;
    context.textContent = selected
      ? `${drafts.size} entries loaded. Selected receipt: ${receipt}. ${state.report?.receipt_sha256 === receipt ? "Receipt matches the active report; full validation happens on Restore." : "Inspect the matching evidence files before restoring this draft."}`
      : "Reading a bundle only loads a separate preview. Your current report, notes and tab drafts stay unchanged.";
    original.textContent = selected ? drafts.get(receipt) : "No draft selected.";
  }

  function renderEntries() {
    const prior = select.value;
    const receipts = [...drafts.keys()];
    select.replaceChildren(...(receipts.length
      ? receipts.map(receipt => new Option(receipt, receipt))
      : [new Option("No bundle loaded", "")]));
    select.disabled = !receipts.length;
    select.value = drafts.has(prior) ? prior
      : drafts.has(state.report?.receipt_sha256) ? state.report.receipt_sha256
      : receipts[0] || "";
    render();
  }

  function downloadTextFile(text, filename, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const link = document.createElement("a");
    link.href = url; link.download = filename;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function checkEntry(receipt, text, lineNumber) {
    if (typeof receipt !== "string" || !/^[a-f0-9]{64}$/.test(receipt) || typeof text !== "string") {
      throw new Error(`Bundle line ${lineNumber}: expected a receipt and original draft-text string.`);
    }
    if (encoder.encode(text).byteLength > HandoffImport.MAX_DRAFT_BYTES) {
      throw new Error(`Bundle line ${lineNumber}: a draft exceeds the existing 1 MiB intake limit.`);
    }
  }

  function readBundle(text) {
    const lines = text.split("\n");
    if (lines.at(-1) === "") lines.pop();
    if (lines[0]?.replace(/\r$/, "") !== HEADER) throw new Error("This is not a supported TJLabs draft bundle. Load individual JSON drafts with the existing Saved draft handoff control.");
    if (lines.length < 2 || lines.length > MAX_ENTRIES + 1) throw new Error(`A bundle must contain between 1 and ${MAX_ENTRIES} draft entries.`);
    const incoming = new Map();
    for (let index = 1; index < lines.length; index++) {
      let entry;
      try { entry = JSON.parse(lines[index]); }
      catch { throw new Error(`Bundle line ${index + 1}: invalid JSON entry.`); }
      // Only a two-string array is accepted. There are no object keys to collapse
      // or amounts to round; the original nested draft remains an exact string.
      if (!Array.isArray(entry) || entry.length !== 2) throw new Error(`Bundle line ${index + 1}: expected exactly [receipt, draftText].`);
      checkEntry(entry[0], entry[1], index + 1);
      if (incoming.has(entry[0])) throw new Error(`Bundle line ${index + 1}: duplicate report receipt; no entry was overwritten.`);
      incoming.set(entry[0], entry[1]);
    }
    return incoming;
  }

  async function loadBundle() {
    const sequence = ++loadSequence;
    const file = fileInput.files?.[0];
    load.disabled = true;
    try {
      if (!file) throw new Error("Choose a .tjdrafts bundle first.");
      if (file.size > MAX_BYTES) throw new Error("Bundle exceeds the 16 MiB intake limit.");
      const bytes = await file.arrayBuffer();
      if (sequence !== loadSequence) return;
      if (bytes.byteLength > MAX_BYTES) throw new Error("Bundle exceeds the 16 MiB intake limit.");
      let text;
      try { text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes); }
      catch { throw new Error("Bundle must be valid UTF-8."); }
      const incoming = readBundle(text);
      drafts = incoming;
      renderEntries();
      status.textContent = `${drafts.size} draft entries loaded for inspection. Contents are not yet validated against evidence. No active notes or saved drafts were changed.`;
    } catch (error) {
      if (sequence === loadSequence) message(error);
    } finally {
      if (sequence === loadSequence) load.disabled = !fileInput.files?.[0];
    }
  }

  function saveBundle() {
    try {
      rememberActiveDraft();
      const entries = [...state.savedDrafts];
      if (!entries.length) throw new Error("There are no tab drafts to back up yet.");
      if (entries.length > MAX_ENTRIES) throw new Error(`The bundle limit is ${MAX_ENTRIES} drafts; use the existing individual draft downloads for this tab.`);
      const lines = [HEADER];
      for (const [receipt, saved] of entries) {
        checkEntry(receipt, saved.text, lines.length + 1);
        lines.push(JSON.stringify([receipt, saved.text]));
      }
      const text = lines.join("\n") + "\n";
      if (encoder.encode(text).byteLength > MAX_BYTES) throw new Error("Bundle exceeds 16 MiB. Use individual draft downloads; no draft was removed.");
      downloadTextFile(text, "uiowa-working-drafts.tjdrafts", "text/plain;charset=utf-8");
      status.textContent = `Download requested for ${entries.length} tab drafts. Retain the downloaded file before closing this tab. Evidence packages and reviewer queues are not included.`;
    } catch (error) { message(error); }
  }

  function restoreSelected() {
    try {
      const receipt = select.value;
      if (!drafts.has(receipt) || state.report?.receipt_sha256 !== receipt) throw new Error("Inspect the exact matching evidence report before restoring this draft.");
      const restored = HandoffImport.parseDraft(drafts.get(receipt), state.report);
      rememberDraft(state.report, restored.notes, restored.dispositions);
      state.notes = restored.notes;
      state.dispositions = restored.dispositions;
      state.editRevision++;
      state.draftLoadSequence++;
      el.importDraftBtn.disabled = false;
      selectCell(state.selectedKey || keyFor(state.cells[0]));
      status.textContent = "All 12 working notes and dispositions were restored to the matching report. The loaded bundle remains available for other reports; no evidence or approval authority was changed.";
    } catch (error) { message(error); }
  }

  backup.addEventListener("click", saveBundle);
  load.addEventListener("click", loadBundle);
  fileInput.addEventListener("change", () => { loadSequence++; load.disabled = !fileInput.files?.[0]; });
  select.addEventListener("change", render);
  restore.addEventListener("click", restoreSelected);
  download.addEventListener("click", () => {
    const receipt = select.value;
    if (!drafts.has(receipt)) return;
    downloadTextFile(drafts.get(receipt), `uiowa-draft-${receipt.slice(0, 12)}.json`, "application/json");
    status.textContent = "Original draft JSON download requested. This does not validate it or change the active review.";
  });
  forget.addEventListener("click", () => {
    loadSequence++; drafts = new Map(); fileInput.value = ""; load.disabled = true;
    renderEntries(); status.textContent = "Loaded bundle forgotten. Active notes, tab drafts and downloaded files are unchanged.";
  });
  // Observe existing UI updates instead of wrapping report installation or the
  // separate sample/reviewer-navigation lifecycle.
  const observer = new MutationObserver(render);
  observer.observe(el.savedDraftSelect, { childList: true });
  observer.observe(el.reportMeta, { childList: true, characterData: true, subtree: true });
  renderEntries();
})();
