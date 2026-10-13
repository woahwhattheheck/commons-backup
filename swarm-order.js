/* Existing command-center work observations. No inference or dispatch. */
(() => {
  "use strict";
  const root = "https://raw.githubusercontent.com/woahwhattheheck/commons/state/coordination/";
  const panel = document.getElementById("swarm-order");
  if (!panel) return;
  let previous = null, state = null, busy = false;
  const row = (tag, text, parent) => {
    const node = document.createElement(tag); node.textContent = text; parent.appendChild(node); return node;
  };
  async function read(name) {
    const response = await fetch(root + name, {cache: "no-store", signal: AbortSignal.timeout(12000)});
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }
  function render(error) {
    const box = document.getElementById("swarm-rows");
    box.replaceChildren();
    const observed = state && state.observed_at;
    const age = observed ? (Date.now() - Date.parse(observed)) / 1000 : NaN;
    const stale = !Number.isFinite(age) || age < -300 || age >= 600 || !!error;
    const freshness = document.getElementById("swarm-freshness");
    freshness.textContent = !state ? "UNREAD" : stale ? "STALE / refresh live work" : "Current observation";
    freshness.className = "pill " + (!state ? "UNKNOWN" : stale ? "STALE" : "LIVE");
    if (!state) {
      row("li", "Work state could not be read. Open the repository queue or refresh; unread data does not mean no work.", box);
    } else {
      const counts = state.counts || {};
      row("li", "Open PRs: " + (counts.open_prs ?? "unknown") +
        " · Listed: " + (counts.listed_open ?? "unknown") +
        " · Main: " + (state.main?.sha?.slice(0, 12) || "unknown"), box);
      const queue = state.queue || {};
      row("li", "Hosted runs: " + (queue.queued ?? "unknown") + " queued · " +
        (queue.in_progress ?? "unknown") + " running", box);
      if ((state.degraded || []).length) {
        row("li", "Observation gaps: " + state.degraded.join(" · "), box).className = "note bad";
      }
      const prs = Array.isArray(state.prs) ? state.prs : [];
      if (!prs.length) row("li", "No open PR rows in this observation.", box);
      for (const pr of prs.slice(0, 50)) {
        const item = row("li", "", box);
        const link = row("a", "#" + pr.number + " " + pr.title, item);
        link.href = "https://github.com/woahwhattheheck/commons/pull/" + Number(pr.number);
        const work = pr.swarm?.work || {};
        row("div", (work.seat || "owner undeclared") +
          (work.operation ? " · " + work.operation : "") +
          " · " + (pr.draft ? "draft" : "open") +
          " · source " + (pr.drift?.status || "unknown") +
          " · head " + (pr.head?.slice(0, 12) || "unknown"), item);
        if (work.next_action) row("div", "Next: " + work.next_action, item);
        if (pr.updated_at) row("div", "Updated " + pr.updated_at, item).className = "small muted";
      }
      if (prs.length > 50) row("li", (prs.length - 50) + " more PRs in the coordination snapshot.", box);
    }
    document.getElementById("swarm-source").textContent =
      "Observed " + (observed || "unknown") + (error ? " · Read failed: " + error : "") +
      ". This snapshot records work, not merge clearance. Reconcile against live source before landing.";
  }
  async function refresh() {
    if (busy || document.visibilityState === "hidden") return;
    busy = true;
    const button = document.getElementById("swarm-refresh");
    button.disabled = true;
    try {
      const head = await read("coordination-head.json");
      if (!state || head.observed_at !== previous) {
        const next = await read("coordination.json");
        state = next; previous = state.observed_at;
      }
      render(null);
    } catch (error) { render(String(error.message)); }
    finally { busy = false; button.disabled = false; }
  }
  document.getElementById("swarm-refresh").addEventListener("click", () => { previous = null; refresh(); });
  document.addEventListener("visibilitychange", refresh);
  refresh(); setInterval(refresh, 60000);
})();
