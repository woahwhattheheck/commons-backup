(() => {
  "use strict";

  const SELECTED_KEY = "hive-study:selected-document:v1";
  const PENDING_KEY = "hive-study:pending-review:v1";

  class ApiError extends Error {
    constructor(message, status = 0) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }

  class StudyApi {
    async request(method, path, body) {
      let response;
      try {
        response = await fetch(path, {
          method,
          headers: body === undefined ? undefined : { "Content-Type": "application/json" },
          body: body === undefined ? undefined : JSON.stringify(body),
          cache: "no-store"
        });
      } catch (error) {
        throw new ApiError("The workspace server could not be reached. Your in-flight answer is still saved in this browser.", 0);
      }
      const type = response.headers.get("content-type") || "";
      let payload = null;
      if (type.includes("application/json")) {
        try { payload = await response.json(); } catch (_) { payload = null; }
      }
      if (!response.ok) {
        throw new ApiError(payload && payload.message ? payload.message : `The workspace returned HTTP ${response.status}.`, response.status);
      }
      return payload;
    }
    capabilities() { return this.request("GET", "/api/capabilities"); }
    documents() { return this.request("GET", "/api/documents"); }
    document(id) { return this.request("GET", `/api/documents/${encodeURIComponent(id)}`); }
    cards(id, dueOnly) { return this.request("GET", `/api/documents/${encodeURIComponent(id)}/cards${dueOnly ? "?due=1" : ""}`); }
    importDocument(payload) { return this.request("POST", "/api/import", payload); }
    editCard(id, payload) { return this.request("POST", `/api/cards/${encodeURIComponent(id)}`, payload); }
    review(payload) { return this.request("POST", "/api/review", payload); }
    deleteDocument(id) { return this.request("DELETE", `/api/documents/${encodeURIComponent(id)}`); }
  }

  const api = new StudyApi();
  const state = {
    capabilities: null,
    documents: [],
    selectedId: safeStorageGet(SELECTED_KEY),
    document: null,
    cards: [],
    cardIndex: 0,
    dueOnly: true,
    pending: safeJsonStorageGet(PENDING_KEY),
    feedback: null,
    recoveryMode: false
  };

  const el = {};
  function byId(id) { return document.getElementById(id); }
  function bindElements() {
    [
      "capability-badge", "import-form", "import-title", "import-file", "file-label", "file-help", "import-submit",
      "refresh-library", "document-list", "empty-library", "global-status", "welcome", "study-view", "document-kind",
      "document-title", "document-meta", "original-link", "export-link", "delete-document", "pending-banner", "retry-pending",
      "show-due", "show-all", "queue-summary", "no-cards", "no-cards-copy", "card-stage", "card-kind", "source-link",
      "card-prompt", "tutor-editor", "edit-card-form", "edit-prompt", "edit-answer", "edit-aliases", "edit-explanation",
      "review-form", "review-answer", "check-answer", "feedback", "feedback-title", "feedback-schedule", "feedback-message",
      "feedback-answer", "feedback-quote", "feedback-explanation", "feedback-source", "next-card"
    ].forEach(id => { el[id] = byId(id); });
  }

  function safeStorageGet(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }
  function safeStorageSet(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* private-mode storage can fail */ }
  }
  function safeStorageRemove(key) {
    try { localStorage.removeItem(key); } catch (_) { /* best effort */ }
  }
  function safeJsonStorageGet(key) {
    const raw = safeStorageGet(key);
    if (!raw) return null;
    try {
      const value = JSON.parse(raw);
      return value && typeof value === "object" ? value : null;
    } catch (_) {
      safeStorageRemove(key);
      return null;
    }
  }

  function setStatus(message = "", kind = "") {
    el["global-status"].hidden = !message;
    el["global-status"].textContent = message;
    el["global-status"].className = `status${kind ? ` ${kind}` : ""}`;
  }

  function setBusy(button, busy, busyLabel) {
    if (!button) return;
    if (busy) {
      button.dataset.label = button.textContent;
      button.textContent = busyLabel || "Working…";
      button.disabled = true;
    } else {
      if (button.dataset.label) button.textContent = button.dataset.label;
      button.disabled = false;
    }
  }

  function humanBytes(bytes) {
    if (!Number.isFinite(bytes)) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KiB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
  }

  function scheduleLabel(result) {
    if (!result) return "";
    if (!result.correct) return "Retry in about 10 min";
    const days = Number(result.interval_days || 0);
    if (days === 1) return "Next review in 1 day";
    return `Next review in ${Number.isInteger(days) ? days : days.toFixed(1)} days`;
  }

  function freshRequestId() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (globalThis.crypto && typeof globalThis.crypto.getRandomValues === "function") {
      globalThis.crypto.getRandomValues(bytes);
      return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`;
  }

  function bytesToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    const chunk = 0x8000;
    let binary = "";
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + chunk, bytes.length)));
    }
    return btoa(binary);
  }

  function savePending(value) {
    state.pending = value;
    if (value) safeStorageSet(PENDING_KEY, JSON.stringify(value));
    else safeStorageRemove(PENDING_KEY);
    renderPending();
  }

  function pendingPayload(pending) {
    return {
      card_id: pending.card_id,
      answer: pending.answer,
      request_id: pending.request_id,
      revision: pending.revision
    };
  }

  function renderPending() {
    const sameDocument = state.pending && state.document && state.pending.document_id === state.document.id;
    el["pending-banner"].hidden = !sameDocument;
    if (sameDocument && state.pending.answer && !el["review-answer"].value) {
      const card = currentCard();
      if (card && card.id === state.pending.card_id) el["review-answer"].value = state.pending.answer;
    }
  }

  function currentCard() { return state.cards[state.cardIndex] || null; }

  async function refreshCapabilities() {
    try {
      state.capabilities = await api.capabilities();
      const pdf = state.capabilities.pdf ? "PDF ready" : "Text only";
      el["capability-badge"].textContent = pdf;
      el["file-help"].textContent = state.capabilities.pdf
        ? `Up to ${humanBytes(state.capabilities.max_upload)}. Text PDFs are extracted locally; scans need a transcription.`
        : `Up to ${humanBytes(state.capabilities.max_upload)}. PDF conversion is unavailable here; use UTF-8 text or Markdown.`;
    } catch (error) {
      el["capability-badge"].textContent = "Server offline";
      setStatus(error.message, "error");
    }
  }

  async function refreshLibrary({ preserveStatus = false } = {}) {
    if (!preserveStatus) setStatus();
    try {
      const payload = await api.documents();
      state.documents = Array.isArray(payload.documents) ? payload.documents : [];
      if (state.selectedId && !state.documents.some(doc => doc.id === state.selectedId)) state.selectedId = null;
      if (!state.selectedId && state.documents.length) state.selectedId = state.documents[0].id;
      if (state.selectedId) safeStorageSet(SELECTED_KEY, state.selectedId); else safeStorageRemove(SELECTED_KEY);
      renderLibrary();
      if (state.selectedId) await loadDocument(state.selectedId, { preserveStatus: true });
      else showWelcome();
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  function renderLibrary() {
    el["document-list"].replaceChildren();
    el["empty-library"].hidden = state.documents.length > 0;
    state.documents.forEach(doc => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `document-item${doc.id === state.selectedId ? " active" : ""}`;
      button.setAttribute("role", "listitem");
      const title = document.createElement("strong");
      title.textContent = doc.title;
      const filename = document.createElement("small");
      filename.textContent = doc.filename;
      const stats = document.createElement("div");
      stats.className = "document-stats";
      [ `${doc.cards} cards`, `${doc.due} due`, `${doc.attempts} attempts` ].forEach(text => {
        const badge = document.createElement("span"); badge.textContent = text; stats.appendChild(badge);
      });
      button.append(title, filename, stats);
      button.addEventListener("click", () => selectDocument(doc.id));
      el["document-list"].appendChild(button);
    });
  }

  function showWelcome() {
    state.document = null;
    state.cards = [];
    state.feedback = null;
    el.welcome.hidden = false;
    el["study-view"].hidden = true;
    renderPending();
  }

  async function selectDocument(id) {
    if (state.pending && state.pending.document_id !== id) {
      setStatus("Retry the saved in-flight answer before switching sources. This preserves its request ID.", "error");
      return;
    }
    state.selectedId = id;
    safeStorageSet(SELECTED_KEY, id);
    renderLibrary();
    await loadDocument(id);
  }

  async function loadDocument(id, { preserveStatus = false } = {}) {
    if (!preserveStatus) setStatus();
    try {
      const [document, cards] = await Promise.all([api.document(id), api.cards(id, state.dueOnly)]);
      state.document = document;
      state.cards = Array.isArray(cards.cards) ? cards.cards : [];
      state.recoveryMode = false;
      state.cardIndex = Math.min(state.cardIndex, Math.max(0, state.cards.length - 1));
      if (state.pending && state.pending.document_id === id) {
        const pendingIndex = state.cards.findIndex(card => card.id === state.pending.card_id);
        if (pendingIndex >= 0) state.cardIndex = pendingIndex;
        else {
          const all = await api.cards(id, false);
          state.cards = Array.isArray(all.cards) ? all.cards : [];
          state.recoveryMode = true;
          state.cardIndex = Math.max(0, state.cards.findIndex(card => card.id === state.pending.card_id));
        }
      }
      state.feedback = null;
      renderDocument();
      renderCard();
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  function renderDocument() {
    el.welcome.hidden = true;
    el["study-view"].hidden = false;
    el["document-kind"].textContent = state.document.kind === "pdf" ? "Text PDF" : "Notes / text";
    el["document-title"].textContent = state.document.title;
    const summary = state.documents.find(doc => doc.id === state.document.id);
    el["document-meta"].textContent = summary ? `${summary.cards} cards · ${summary.due} due · ${summary.attempts} attempts` : state.document.filename;
    el["original-link"].href = `/original/${encodeURIComponent(state.document.id)}`;
    el["export-link"].href = `/api/documents/${encodeURIComponent(state.document.id)}/export`;
    renderPending();
  }

  function renderCard() {
    const card = currentCard();
    el["queue-summary"].textContent = state.cards.length
      ? `${state.recoveryMode ? "Saved-answer recovery" : state.dueOnly ? "Due now" : "All cards"}: ${state.cardIndex + 1} of ${state.cards.length}`
      : (state.dueOnly ? "No cards are due right now." : "This source has no generated practice cards.");
    el["no-cards"].hidden = !!card;
    el["card-stage"].hidden = !card;
    if (!card) {
      el["no-cards-copy"].textContent = state.dueOnly
        ? "Nothing is due right now. Inspect all cards or return when the next review becomes due."
        : "The source is still saved. Notes written as “term: definition” produce explicit definition cards.";
      renderPending();
      return;
    }
    el["card-kind"].textContent = card.kind === "definition" ? "Definition" : "Cloze";
    el["source-link"].href = card.source_url;
    el["card-prompt"].textContent = card.prompt;
    el["edit-prompt"].value = card.prompt;
    el["edit-answer"].value = card.answer;
    el["edit-aliases"].value = (card.aliases || []).join("\n");
    el["edit-explanation"].value = card.explanation;
    if (!(state.pending && state.pending.card_id === card.id)) el["review-answer"].value = "";
    el.feedback.hidden = true;
    el.feedback.classList.remove("incorrect");
    el["review-form"].hidden = false;
    renderPending();
  }

  async function changeFilter(dueOnly) {
    if (state.pending) {
      setStatus("Retry the saved in-flight answer before changing the queue. This preserves its exact request ID.", "error");
      return;
    }
    state.dueOnly = dueOnly;
    el["show-due"].classList.toggle("active", dueOnly);
    el["show-all"].classList.toggle("active", !dueOnly);
    el["show-due"].setAttribute("aria-pressed", String(dueOnly));
    el["show-all"].setAttribute("aria-pressed", String(!dueOnly));
    state.cardIndex = 0;
    await loadDocument(state.selectedId);
  }

  async function importSource(event) {
    event.preventDefault();
    const file = el["import-file"].files && el["import-file"].files[0];
    if (!file) return;
    const max = state.capabilities && state.capabilities.max_upload;
    if (max && file.size > max) {
      setStatus(`That file is ${humanBytes(file.size)}; the server limit is ${humanBytes(max)}. Split the chapter first.`, "error");
      return;
    }
    setBusy(el["import-submit"], true, "Importing…");
    setStatus();
    try {
      const data = bytesToBase64(await file.arrayBuffer());
      const result = await api.importDocument({ filename: file.name, title: el["import-title"].value.trim(), data });
      state.selectedId = result.id;
      safeStorageSet(SELECTED_KEY, result.id);
      el["import-form"].reset();
      el["file-label"].textContent = "Choose .txt, .md, or text-PDF";
      setStatus(result.duplicate ? "That exact source was already here; existing keys and progress were preserved." : (result.notice || `Imported ${result.cards} practice cards.`), "success");
      await refreshLibrary({ preserveStatus: true });
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      setBusy(el["import-submit"], false);
    }
  }

  async function editCurrentCard(event) {
    event.preventDefault();
    const card = currentCard();
    if (!card) return;
    const aliases = el["edit-aliases"].value.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
    const button = el["edit-card-form"].querySelector("button[type=submit]");
    setBusy(button, true, "Saving…");
    setStatus();
    try {
      const updated = await api.editCard(card.id, {
        prompt: el["edit-prompt"].value,
        answer: el["edit-answer"].value,
        aliases,
        explanation: el["edit-explanation"].value,
        revision: card.revision
      });
      state.cards[state.cardIndex] = updated;
      el["tutor-editor"].open = false;
      setStatus("Tutor key saved. This card was rescheduled for review now.", "success");
      await refreshLibrary({ preserveStatus: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) await loadDocument(state.selectedId, { preserveStatus: true });
      setStatus(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function submitReview(event) {
    if (event) event.preventDefault();
    const card = currentCard();
    if (!card) return;
    const answer = el["review-answer"].value;
    let pending = state.pending;
    if (pending) {
      if (pending.document_id !== state.document.id || pending.card_id !== card.id || pending.answer !== answer || pending.revision !== card.revision) {
        setStatus("A different answer is already saved for retry. Recover it before creating a new review request.", "error");
        return;
      }
    } else {
      pending = { document_id: state.document.id, card_id: card.id, answer, request_id: freshRequestId(), revision: card.revision };
      savePending(pending); // Persist before any network write.
    }
    setBusy(el["check-answer"], true, "Checking…");
    setBusy(el["retry-pending"], true, "Retrying…");
    setStatus();
    try {
      const result = await api.review(pendingPayload(pending));
      savePending(null);
      state.feedback = result;
      renderFeedback(result);
    } catch (error) {
      const transient = !(error instanceof ApiError) || error.status === 0 || error.status >= 500;
      if (!transient) savePending(null); // A definitive 4xx response means the operation did not need retry recovery.
      if (error instanceof ApiError && error.status === 409) await loadDocument(state.selectedId, { preserveStatus: true });
      setStatus(error.message, "error");
      renderPending();
    } finally {
      setBusy(el["check-answer"], false);
      setBusy(el["retry-pending"], false);
    }
  }

  function renderFeedback(result) {
    el.feedback.hidden = false;
    el.feedback.classList.toggle("incorrect", !result.correct);
    el["feedback-title"].textContent = result.correct ? "Matches the key" : "Check the source";
    el["feedback-schedule"].textContent = scheduleLabel(result);
    el["feedback-message"].textContent = result.feedback;
    el["feedback-answer"].textContent = result.answer;
    el["feedback-quote"].textContent = result.quote;
    el["feedback-explanation"].textContent = result.explanation;
    el["feedback-source"].href = result.source_url;
    el["review-form"].hidden = true;
    el.feedback.focus();
  }

  async function nextCard() {
    state.feedback = null;
    state.cardIndex = 0;
    await refreshLibrary({ preserveStatus: true });
    if (!el["card-stage"].hidden) el["review-answer"].focus();
  }

  async function deleteDocument() {
    if (!state.document) return;
    if (state.pending && state.pending.document_id === state.document.id) {
      setStatus("Retry the saved in-flight answer before deleting this source.", "error");
      return;
    }
    if (!confirm(`Delete “${state.document.title}” and its cards/reviews from this active workspace? Exported copies and disk sanitization are outside this action.`)) return;
    const id = state.document.id;
    setBusy(el["delete-document"], true, "Deleting…");
    try {
      await api.deleteDocument(id);
      if (state.selectedId === id) state.selectedId = null;
      safeStorageRemove(SELECTED_KEY);
      setStatus("Source, cards, and active review rows deleted from this workspace.", "success");
      await refreshLibrary({ preserveStatus: true });
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      setBusy(el["delete-document"], false);
    }
  }

  function attachEvents() {
    el["import-form"].addEventListener("submit", importSource);
    el["import-file"].addEventListener("change", () => {
      const file = el["import-file"].files && el["import-file"].files[0];
      el["file-label"].textContent = file ? `${file.name} · ${humanBytes(file.size)}` : "Choose .txt, .md, or text-PDF";
    });
    el["refresh-library"].addEventListener("click", () => refreshLibrary());
    el["show-due"].addEventListener("click", () => changeFilter(true));
    el["show-all"].addEventListener("click", () => changeFilter(false));
    el["review-form"].addEventListener("submit", submitReview);
    el["edit-card-form"].addEventListener("submit", editCurrentCard);
    el["retry-pending"].addEventListener("click", () => submitReview());
    el["next-card"].addEventListener("click", nextCard);
    el["delete-document"].addEventListener("click", deleteDocument);
  }

  async function start() {
    bindElements();
    attachEvents();
    await Promise.all([refreshCapabilities(), refreshLibrary()]);
  }

  globalThis.HiveStudy = { ApiError, StudyApi, bytesToBase64, scheduleLabel, pendingPayload, freshRequestId };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
