/* Read one atomic Python projection through the raw CDN. No event reducer or polling. */
(() => {
  "use strict";
  const helpers = window.CommonsCommand;
  const panel = document.getElementById("canonical-swarm");
  if (!helpers || !panel) return;
  const REPO = "woahwhattheheck/commons", BRANCH = "state/claims";
  const PATH = "holdings/swarm-status.json", MAX_BYTES = 4 * 1024 * 1024;
  const CACHE_KEY = "commons-swarm-status-snapshot-v2", CACHE_MS = 60000, PAGE = 50;
  const root = document.getElementById("canonical-swarm-body");
  const stamp = document.getElementById("canonical-swarm-stamp");
  const node = (tag, text, cls) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = String(text);
    if (cls) item.className = cls;
    if (tag === "pre") { item.style.whiteSpace = "pre-wrap"; item.style.overflowWrap = "anywhere"; }
    return item;
  };
  const known = value => value !== undefined && value !== null && value !== "" && value !== "UNKNOWN";
  const readable = value => !known(value) ? "UNKNOWN" : typeof value === "object" ? JSON.stringify(value) : String(value);
  const compact = (value, limit = 600) => readable(value).slice(0, limit);
  const date = value => Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString() : "UNKNOWN";
  const badge = (text, cls = "UNKNOWN") => node("span", text, "pill " + cls);
  const liveClass = state => state === "SHIPPED" ? "LIVE" : state === "ACTIVE" ? "QUIET" : state === "BLOCKED" ? "STALE" : "UNKNOWN";
  const actions = node("div", undefined, "actions");
  const refresh = node("button", "Refresh canonical tasks"); refresh.type = "button";
  const search = node("input"); search.type = "search"; search.placeholder = "Task key, worker or blocker";
  search.setAttribute("aria-label", "Search loaded canonical tasks");
  const filter = node("select"); filter.setAttribute("aria-label", "Canonical task lifecycle");
  [["working", "Open, active and blocked"], ["all", "All tasks"], ["recoverable", "Recoverable at projection"],
    ...["OPEN", "ACTIVE", "SHIPPED", "BLOCKED", "SUPERSEDED", "ABANDONED"].map(s => [s, s])]
    .forEach(([value, label]) => { const option = node("option", label); option.value = value; filter.append(option); });
  actions.append(refresh, search, filter);
  const note = node("p", "Open this panel to read the shared task snapshot.", "small muted"); note.setAttribute("role", "status");
  const counts = node("div", undefined, "counts");
  const rows = node("ul", undefined, "rows");
  const pages = node("div", undefined, "actions"), previous = node("button", "Previous"), next = node("button", "Next");
  previous.type = next.type = "button";
  const pageNote = node("span", "", "small muted"); pages.append(previous, next, pageNote);
  const details = node("details"), detailBody = node("div"); detailBody.style.overflowWrap = "anywhere";
  details.append(node("summary", "Source, collisions and capability pools"), detailBody);
  root.append(actions, note, counts, rows, pages, details);
  let snapshot = null, observation = null, failure = "", inFlight = null, retryAt = 0, offset = 0, repaint;
  const queryTask = new URLSearchParams(location.search).get("swarm_task");
  let exactTask = queryTask || "";
  if (queryTask) { search.value = queryTask; filter.value = "all"; }

  function cache() {
    try { return JSON.parse(localStorage.getItem(CACHE_KEY) || "null"); } catch (_) { return null; }
  }
  function save(value) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(value)); } catch (_) {
      // A large snapshot may exceed storage quota; keep cooldowns cheap.
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({checked_at: value.checked_at, retry_at: value.retry_at})); } catch (_) {}
    }
  }
  function validSnapshot(body) {
    return body?.schema === "commons-swarm-status/v1" && body.authority === BRANCH && Array.isArray(body.tasks) && body.tasks.length <= 5000;
  }
  function ageLabel(when) {
    const seconds = (Date.now() - Date.parse(when)) / 1000;
    if (!Number.isFinite(seconds) || seconds < -300) return "unknown age";
    if (seconds < 90) return Math.max(0, Math.floor(seconds)) + "s ago";
    return seconds < 7200 ? Math.floor(seconds / 60) + "m ago" : Math.floor(seconds / 3600) + "h ago";
  }
  function permalink(key) {
    const url = new URL(location.href); url.searchParams.set("swarm_task", key); url.hash = "canonical-swarm"; return url.href;
  }
  function taskURL(task) {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(task.repo || "")) return null;
    for (const [kind, number] of [["pull", task.pr], ["issues", task.issue]]) {
      if (Number.isSafeInteger(Number(number)) && Number(number) > 0) return "https://github.com/" + task.repo + "/" + kind + "/" + number;
    }
    return null;
  }
  function render() {
    clearTimeout(repaint);
    if (panel.open && !document.hidden) repaint = setTimeout(render, 60000); // Ages only; no provider requests.
    refresh.disabled = !!inFlight || Date.now() < retryAt;
    rows.replaceChildren(); counts.replaceChildren(); detailBody.replaceChildren();
    const retry = Date.now() < retryAt ? " Retry after " + date(new Date(retryAt).toISOString()) + "." : "";
    if (!snapshot) {
      stamp.textContent = inFlight ? "Reading" : failure ? "UNREAD" : "Open to load";
      stamp.className = "pill UNKNOWN";
      note.textContent = failure ? "Task read failed: " + failure + ". Unread does not mean empty." + retry : "Read canonical tasks on request. No background provider polling.";
      previous.disabled = next.disabled = true; pageNote.textContent = "";
      return;
    }
    const summary = snapshot.summary || {}, tasks = snapshot.tasks;
    const query = search.value.trim().toLowerCase(), selected = filter.value;
    const queryExact = query ? tasks.find(task => String(task.task_key).toLowerCase() === query)?.task_key : null;
    const matches = tasks.filter(task => (!exactTask || task.task_key === exactTask) && (!queryExact || task.task_key === queryExact) &&
      (selected === "all" || selected === "working" && ["OPEN", "ACTIVE", "BLOCKED"].includes(task.state) ||
        selected === "recoverable" && task.recoverable === true || task.state === selected) &&
      [task.task_key, task.title, task.worker, task.blocker, task.next_action].map(readable).join(" ").toLowerCase().includes(query));
    if (offset >= matches.length) offset = Math.max(0, Math.floor((matches.length - 1) / PAGE) * PAGE);
    const visible = matches.slice(offset, offset + PAGE);
    const stale = Date.now() - Date.parse(snapshot.projected_at) >= 3600000;
    stamp.textContent = "Projected " + ageLabel(snapshot.projected_at);
    stamp.className = "pill " + (failure || stale ? "STALE" : "QUIET");
    note.textContent = (failure ? "Refresh failed: " + failure + ". Previous observed snapshot retained." + retry + " " : "") +
      "Projected " + date(snapshot.projected_at) + " · " + tasks.length + " loaded / " + readable(snapshot.total) + " canonical tasks. " +
      "Counts and lifecycle are as projected; current lease ages appear on each active task." +
      (snapshot.truncated ? " Task list is truncated; filters cover loaded rows only. Use swarmctl status --task for an exact lookup." : "") +
      (snapshot.metadata_truncated ? " Some source and summary detail is omitted from this bounded snapshot." : "");
    for (const [state, count] of Object.entries(summary.counts || {})) counts.append(badge(state + " " + count, liveClass(state)));
    counts.append(badge(readable(summary.recoverable_count) + " recoverable", "STALE"),
      badge(readable(summary.stale_seat_count) + " stale seats", "STALE"),
      badge(readable(summary.collision_count) + " collisions"), badge(readable(summary.idle_seat_count) + " idle seats", "QUIET"));
    if (!visible.length) rows.append(node("li", "No matching tasks in the loaded snapshot. See source coverage below.", "muted"));
    for (const task of visible) {
      const item = node("li"), head = node("div", undefined, "row-head");
      const link = node("a", compact(task.task_key, 300), "mono"); link.href = permalink(task.task_key);
      link.style.overflowWrap = "anywhere"; link.style.maxWidth = "100%";
      head.append(link, badge(readable(task.state), liveClass(task.state)), node("span", compact(task.worker, 100), "who"));
      if (task.recoverable === true) head.append(badge("recoverable at projection", "STALE"));
      item.append(head);
      const url = taskURL(task);
      if (known(task.title)) { const title = node(url ? "a" : "div", compact(task.title)); if (url) title.href = url; item.append(title); }
      else if (url) { const source = node("a", "Issue / PR"); source.href = url; item.append(source); }
      if (task.state === "ACTIVE") {
        const heartbeat = task.lease?.heartbeat || task.heartbeat;
        const live = helpers.liveFromHeartbeat(heartbeat);
        item.append(node("div", "Lease heartbeat " + date(heartbeat) + " · now " + live.liveness + " · " + ageLabel(heartbeat), "small muted"));
      }
      for (const [field, label] of [["blocker", "Blocker"], ["next_action", "Next"], ["reconciliation_needed", "Reconcile"], ["superseded_by", "Superseded by"]]) {
        if (known(task[field])) item.append(node("div", label + ": " + compact(task[field]), field === "blocker" ? "note bad" : "small"));
      }
      const evidence = ["head_sha", "merge_sha", "landed_sha"].filter(key => known(task[key])).map(key => key.replace("_sha", "") + " " + String(task[key]).slice(0, 12));
      if (evidence.length) item.append(node("div", evidence.join(" · "), "small mono"));
      rows.append(item);
    }
    previous.disabled = offset === 0; next.disabled = offset + PAGE >= matches.length;
    pageNote.textContent = (matches.length ? offset + 1 : 0) + "–" + (offset + visible.length) + " of " + matches.length + " matching";
    detailBody.append(node("p", "Authority " + readable(snapshot.authority) + " · branch snapshot observed " + date(observation?.checked_at) + " · commit pin UNKNOWN", "small mono"));
    const source = node("a", "Open current branch snapshot"); source.href = "https://raw.githubusercontent.com/" + REPO + "/" + BRANCH + "/" + PATH;
    detailBody.append(source, node("p", "Source ledger SHA-256 " + readable(snapshot.source_ledger_sha256), "small mono"),
      node("p", "The CDN may retain an older branch snapshot. This digest identifies its source ledger; the link follows the branch and can change.", "small muted"),
      node("p", "Consumed feed cursor " + readable(snapshot.feed_cursor), "small mono"));
    if (snapshot.metadata_truncated) detailBody.append(node("p", "Omitted detail: " + compact(snapshot.omitted_metadata), "small muted"));
    const pools = summary.idle_capabilities || {};
    detailBody.append(node("h3", "Idle capability pools at projection", "small muted"));
    const poolRows = Object.entries(pools);
    if (!poolRows.length) detailBody.append(node("p", "No reported idle capability pools in this snapshot.", "small muted"));
    for (const [capability, workers] of poolRows.slice(0, 30)) detailBody.append(node("div", capability + ": " + compact(workers), "small"));
    const sources = Object.entries(snapshot.coverage || {});
    detailBody.append(node("h3", "Source coverage", "small muted"));
    if (!sources.length) detailBody.append(node("p", "UNKNOWN", "small"));
    for (const [name, coverage] of sources.slice(0, 20)) {
      const entry = node("details"); entry.append(node("summary", name + " · " + (coverage?.complete === true ? "complete for stated scope" : "partial / unknown")), node("pre", compact(coverage, 3000), "small")); detailBody.append(entry);
    }
    if (Array.isArray(snapshot.collisions) && snapshot.collisions.length) {
      const collisions = node("details"); collisions.append(node("summary", "Recent collisions"), node("pre", JSON.stringify(snapshot.collisions.slice(-20), null, 2), "small")); detailBody.append(collisions);
    }
  }
  async function read(force = false) {
    if (inFlight || document.hidden) return inFlight;
    const shared = cache();
    if (validSnapshot(shared?.snapshot) && (!snapshot || Date.parse(shared.checked_at) > Date.parse(observation?.checked_at))) {
      snapshot = shared.snapshot; observation = {checked_at: shared.checked_at}; offset = 0;
    }
    retryAt = Math.max(retryAt, Number(shared?.retry_at) || 0);
    if (Date.now() < retryAt) { render(); return; }
    inFlight = Promise.resolve().then(async () => {
      try {
        const age = Date.now() - Date.parse(observation?.checked_at);
        if (force || !snapshot || !Number.isFinite(age) || age < 0 || age >= CACHE_MS) {
          const body = await helpers.fetchJson("https://raw.githubusercontent.com/" + REPO + "/" + BRANCH + "/" + PATH,
            {maxBytes: MAX_BYTES});
          if (!validSnapshot(body)) throw new Error("Unrecognized canonical status snapshot");
          if (snapshot?.source_ledger_sha256 !== body.source_ledger_sha256 || snapshot?.projected_at !== body.projected_at) offset = 0;
          snapshot = body; observation = {checked_at: new Date().toISOString()};
          save({...observation, snapshot, retry_at: 0});
        }
        failure = ""; retryAt = 0;
      } catch (error) {
        failure = String(error.message || error);
        retryAt = Math.max(Number(error.retryAt) || 0, Date.now() + ([403, 429].includes(error.status) ? 300000 : CACHE_MS));
        save({...cache(), retry_at: retryAt});
      } finally { inFlight = null; render(); }
    });
    render(); return inFlight;
  }
  refresh.addEventListener("click", () => read(true));
  panel.addEventListener("toggle", () => { if (panel.open && !snapshot) read(); else render(); });
  search.addEventListener("input", () => {
    if (exactTask) { const url = new URL(location.href); url.searchParams.delete("swarm_task"); history.replaceState(null, "", url); }
    exactTask = ""; offset = 0; render();
  });
  filter.addEventListener("change", () => { offset = 0; render(); });
  previous.addEventListener("click", () => { offset = Math.max(0, offset - PAGE); render(); });
  next.addEventListener("click", () => { offset += PAGE; render(); });
  document.addEventListener("visibilitychange", render);
  render();
  if (queryTask || location.hash === "#canonical-swarm") panel.open = true;
})();
