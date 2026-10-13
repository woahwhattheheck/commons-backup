"use strict";

// UIOWA-125, recovered from Orthoclase's #16275 onto the current draft-cache UI.
// Loaded after app.js. This adapter owns only the explicit sample interaction;
// it does not replace the renderer, parser, report format or async counters.
(() => {
  let parked = null;
  const originalClearLabel = el.resetBtn.textContent;
  const panel = document.createElement("section");
  panel.className = "import-panel";
  panel.setAttribute("aria-label", "Temporary synthetic demonstration");
  panel.hidden = true;
  const content = document.createElement("div"); content.className = "import-content";
  const actions = document.createElement("div"); actions.className = "actions";
  const restart = document.createElement("button");
  restart.id = "demoResetBtn"; restart.type = "button";
  restart.className = "secondary"; restart.textContent = "Reset sample only";
  const leave = document.createElement("button");
  leave.id = "demoExitBtn"; leave.type = "button";
  leave.className = "secondary"; leave.textContent = "Leave sample and restore review";
  const message = document.createElement("p");
  message.id = "demoStatus"; message.className = "field-note";
  message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite");
  actions.append(restart, leave); content.append(actions, message); panel.append(content);
  el.importPanel.insertAdjacentElement("afterend", panel);

  function updateControls() {
    panel.hidden = parked === null;
    el.demoBtn.textContent = parked ? "Restart temporary sample" : "Start temporary synthetic sample";
    el.resetBtn.textContent = parked ? "Leave sample and restore review" : originalClearLabel;
    if (parked) {
      el.inspectBtn.disabled = true;
      message.textContent = "Synthetic sample only — not compiler output. Reset clears this sample's notes, dispositions, selection, filters, linked review records and temporary draft cache. Downloaded files are untouched. " +
        (parked.report ? "Your prior report and drafts are parked in this tab; leave to restore them." : "Your existing tab drafts are parked; leave to return to the empty workbench.") +
        " Closing or reloading still requires downloaded JSON to retain important work.";
    }
  }

  function captureWorkspace() {
    // Complete the existing save before replacing any active state. A malformed
    // note leaves the user's work in place and the sample does not start.
    rememberActiveDraft();
    return {
      report: state.report ? structuredClone(state.report) : null,
      notes: new Map(state.notes), dispositions: new Map(state.dispositions),
      savedDrafts: new Map(state.savedDrafts), selectedKey: state.selectedKey,
      search: el.search.value, status: el.statusFilter.value,
      savedReceipt: el.savedDraftSelect.value,
      exported: el.exportStatus.textContent, error: el.error.textContent,
      intakeOpen: el.importPanel.open,
      savedPanelOpen: document.getElementById("savedDraftPanel")?.open,
      review: globalThis.UIowaWorkbenchReview?.captureState() || null
    };
  }

  function cleanSample() {
    // Never let installReport recover an edited demo from its constant receipt.
    // The real draft cache lives only in parked while the sample is active.
    state.report = null;
    state.notes = new Map(); state.dispositions = new Map();
    state.savedDrafts = new Map();
    el.statusFilter.value = "";
    installReport(syntheticReport());
    globalThis.UIowaWorkbenchReview?.clearSampleState();
    setError("");
    updateControls();
    document.getElementById("summary-heading").focus();
  }

  function startSample() {
    try {
      if (!parked) parked = captureWorkspace();
      cleanSample();
    } catch (err) {
      preservationError(err);
      updateControls();
    }
  }

  function leaveSample() {
    if (!parked) return;
    const prior = parked;
    try {
      // Validate the retained snapshot before touching the active sample.
      if (prior.report) WorkbenchHandoff.buildDraft(prior.report, prior.notes, prior.dispositions);
      state.report = null;
      state.notes = new Map(); state.dispositions = new Map();
      state.savedDrafts = new Map(prior.savedDrafts);
      if (prior.report) {
        // installReport advances generation/draftLoadSequence; never restore old
        // counters, even if the sample and parked report share a receipt.
        installReport(prior.report);
        state.notes = new Map(prior.notes);
        state.dispositions = new Map(prior.dispositions);
        state.editRevision++;
        el.search.value = prior.search;
        el.statusFilter.value = prior.status;
        if (prior.selectedKey) selectCell(prior.selectedKey, false);
        else renderMatrix();
      } else {
        resetWorkbench();
      }
      renderSavedDrafts(prior.savedReceipt);
      el.importPanel.open = prior.intakeOpen;
      const savedPanel = document.getElementById("savedDraftPanel");
      if (savedPanel && typeof prior.savedPanelOpen === "boolean") savedPanel.open = prior.savedPanelOpen;
      el.exportStatus.textContent = prior.exported;
      setError(prior.error);
      if (prior.review) globalThis.UIowaWorkbenchReview?.restoreState(prior.review);
      parked = null;
      updateControls();
      // The sample panel is now hidden and the original intake may be collapsed.
      // Restore focus to a visible heading, not the hidden demo/leave buttons.
      document.getElementById(prior.report ? "selectedCellHeading" : "summary-heading").focus();
    } catch (err) {
      // Keep the parked snapshot reachable through Leave rather than discarding it.
      preservationError(err);
      updateControls();
    }
  }

  function ownClick(event, action) {
    event.preventDefault();
    event.stopImmediatePropagation();
    action();
  }

  // Capture the existing UI entry points instead of replacing app.js functions.
  // The normal Clear/Inspect behavior remains untouched outside sample mode.
  el.demoBtn.addEventListener("click", event => ownClick(event, startSample), true);
  el.resetBtn.addEventListener("click", event => {
    if (parked) ownClick(event, leaveSample);
  }, true);
  el.inspectBtn.addEventListener("click", event => {
    if (parked) ownClick(event, () => setError("Leave the synthetic sample to restore your review before inspecting replacement evidence."));
  }, true);
  restart.addEventListener("click", () => { if (parked) startSample(); });
  leave.addEventListener("click", leaveSample);
  updateControls();

  // app.js already loaded its built-in demo for this URL. There was no user
  // review before page startup, so do not park that initial demo as real work.
  if (new URLSearchParams(location.search).get("demo") === "1" && state.report?.synthetic_demo === true) {
    parked = {
      report: null, notes: new Map(), dispositions: new Map(), savedDrafts: new Map(),
      selectedKey: null, search: "", status: "", savedReceipt: "",
      exported: "", error: "", intakeOpen: true, savedPanelOpen: false,
      review: {report_receipt_sha256: null, packet: null, hash: location.hash}
    };
    try { cleanSample(); }
    catch (err) { preservationError(err); updateControls(); }
  }
})();
