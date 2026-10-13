/* Observatory renderer. Fetch the bake. No fake live ticks. No analytics. */
(function () {
  const SOURCE = "./observatory.json";

  function el(id) {
    return document.getElementById(id);
  }

  function text(value) {
    if (value === null || value === undefined || value === "") return "UNKNOWN";
    return String(value);
  }

  function pill(state) {
    const span = document.createElement("span");
    span.className = "state state-" + text(state);
    span.textContent = text(state);
    return span;
  }

  function evidenceNode(rows) {
    const wrap = document.createElement("details");
    wrap.className = "evidence";
    const sum = document.createElement("summary");
    sum.textContent = "evidence";
    wrap.appendChild(sum);
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(rows || [], null, 2);
    wrap.appendChild(pre);
    return wrap;
  }

  function fillList(node, items, render) {
    node.textContent = "";
    if (!items || !items.length) {
      const empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "None observed.";
      node.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      node.appendChild(render(item));
    });
  }

  function snapshotStatus(snap) {
    const status = el("snapshot-status");
    const sha = snap.head && snap.head.sha ? String(snap.head.sha).slice(0, 12) : "UNKNOWN";
    const age = (Date.now() - Date.parse(snap.now)) / 1000;
    const threshold = snap.stale_after_seconds;
    const known = Number.isFinite(age) && age >= 0 && Number.isFinite(threshold) && threshold >= 0;
    const freshness = !known ? "FRESHNESS UNKNOWN" : age > threshold ? "STALE SNAPSHOT" : "CURRENT SNAPSHOT";
    status.className = "note" + (freshness === "CURRENT SNAPSHOT" ? "" : " error");
    status.textContent = freshness + " · baked " + text(snap.now) +
      (known ? " · age " + Math.floor(age / 60) + " minutes" : "") +
      " · head " + sha + " · stale_after=" + text(threshold) + "s. Counts are observations at bake time, not live fleet totals.";
  }

  function cockpit(snap) {
    const lines = el("cockpit-lines");
    lines.textContent = "";
    (snap.cockpit && snap.cockpit.lines || []).forEach(function (line) {
      const li = document.createElement("li");
      li.textContent = line;
      lines.appendChild(li);
    });
    const counts = (snap.cockpit && snap.cockpit.counts) || {};
    const states = counts.states || {};
    const classes = counts.classifications || {};
    const metrics = [
      ["confirmed active", counts.confirmed_active],
      ["working", states.WORKING],
      ["blocked", states.BLOCKED],
      ["stale", states.STALE],
      ["local", classes.LOCAL],
      ["cloud", classes.CLOUD],
      ["browser", classes.BROWSER],
      ["automation", classes.AUTOMATION],
      ["unknown class", classes.UNKNOWN],
      ["presence claims", counts.presence_claims],
      ["collisions", counts.collisions],
      ["cash USD", snap.economy && snap.economy.collected_cash_usd]
    ];
    const box = el("metrics");
    box.textContent = "";
    metrics.forEach(function (pair) {
      const div = document.createElement("div");
      div.className = "metric";
      const strong = document.createElement("strong");
      strong.textContent = pair[1] === undefined || pair[1] === null ? "—" : String(pair[1]);
      const span = document.createElement("span");
      span.textContent = pair[0];
      div.appendChild(strong);
      div.appendChild(span);
      box.appendChild(div);
    });
    snapshotStatus(snap);
    el("coverage-note").textContent = snap.coverage_note || "Source coverage was not recorded by this bake.";
    fillList(el("source-coverage"), snap.source_coverage || [], function (row) {
      const li = document.createElement("li");
      li.textContent = text(row.source) + " · " + text(row.state);
      return li;
    });
    fillList(el("board-motion"), snap.board_motion || [], function (row) {
      const li = document.createElement("li");
      li.textContent = text(row.ts) + " · " + text(row.from) + " → " + text(row.to) + " · ";
      const link = document.createElement("a");
      link.textContent = text(row.id);
      link.href = "https://github.com/woahwhattheheck/commons/blob/main/p/" + encodeURIComponent(text(row.id)) + ".md";
      li.appendChild(link);
      return li;
    });
  }

  function sessions(snap) {
    const body = el("session-rows");
    body.textContent = "";
    const rows = snap.sessions || [];
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="11">No declared sessions in the observed inputs. This does not establish that the fleet is idle. Presence and board motion are listed separately.</td></tr>';
      return;
    }
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      function td(value, raw) {
        const cell = document.createElement("td");
        if (raw) cell.appendChild(value);
        else cell.textContent = text(value);
        tr.appendChild(cell);
      }
      td(row.label || row.session_id);
      td(pill(row.classification), true);
      td(pill(row.state), true);
      td(text(row.model) + " / " + text(row.harness));
      td((row.tools || []).join(", ") || "UNKNOWN");
      td(row.task_id);
      td((row.lease && row.lease.lease_id) ? (text(row.lease.lease_id) + " until " + text(row.lease.until)) : "descriptive only");
      td(row.blocker && row.blocker.type && row.blocker.type !== "UNKNOWN" ? (text(row.blocker.type) + " " + text(row.blocker.detail)) : "UNKNOWN");
      td(row.checkpoint);
      td(row.last_ts);
      const ev = document.createElement("td");
      ev.appendChild(evidenceNode(row.evidence));
      tr.appendChild(ev);
      body.appendChild(tr);
    });
  }

  function presence(snap) {
    const body = el("presence-rows");
    body.textContent = "";
    (snap.presence || []).forEach(function (row) {
      const tr = document.createElement("tr");
      [row.claim, row.presence, row.motion, row.id, row.ts].forEach(function (value) {
        const td = document.createElement("td");
        td.textContent = text(value);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    if (!body.children.length) {
      body.innerHTML = '<tr><td colspan="5">No presence bake.</td></tr>';
    }
  }

  function work(snap) {
    const body = el("work-rows");
    body.textContent = "";
    const rows = snap.work_map || [];
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="7">No observed tasks.</td></tr>';
      return;
    }
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      const cells = [
        row.task_id,
        row.state,
        text(row.owner_claim || row.session_id),
        row.objective,
        (row.claimed_paths || []).join(", ") || "UNKNOWN",
        typeof row.checkpoint === "string" ? row.checkpoint : JSON.stringify(row.checkpoint || "UNKNOWN"),
        row.expected_next || "UNKNOWN"
      ];
      cells.forEach(function (value) {
        const td = document.createElement("td");
        td.textContent = text(value);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function findings(id, rows) {
    const node = el(id);
    fillList(node, rows, function (item) {
      const li = document.createElement("li");
      li.textContent = text(item.kind) + " — " + JSON.stringify(item, null, 0).slice(0, 280);
      li.appendChild(evidenceNode(item.evidence || item));
      return li;
    });
  }

  function timeline(snap, filter) {
    const node = el("timeline");
    const rows = (snap.timeline || []).filter(function (row) {
      if (filter.kind && text(row.kind).toUpperCase() !== filter.kind.toUpperCase()) return false;
      if (filter.session && text(row.session_id).toLowerCase().indexOf(filter.session.toLowerCase()) < 0) return false;
      if (filter.harness && text(row.harness).toLowerCase().indexOf(filter.harness.toLowerCase()) < 0) return false;
      if (filter.task && text(row.task_id).toLowerCase().indexOf(filter.task.toLowerCase()) < 0) return false;
      if (filter.path) {
        // New bakes retain every event path; old bakes have only path.
        const paths = Array.isArray(row.claimed_paths) && row.claimed_paths.length ? row.claimed_paths : [text(row.path)];
        const needle = filter.path.toLowerCase();
        if (!paths.some(function (path) {
          return typeof path === "string" && path.toLowerCase().indexOf(needle) >= 0;
        })) return false;
      }
      if (filter.blocker && text(row.blocker).toLowerCase().indexOf(filter.blocker.toLowerCase()) < 0) return false;
      if (filter.provider && JSON.stringify(row).toLowerCase().indexOf(filter.provider.toLowerCase()) < 0) return false;
      if (filter.landing) {
        const blob = (text(row.kind) + " " + JSON.stringify(row)).toLowerCase();
        if (blob.indexOf(filter.landing.toLowerCase()) < 0) return false;
      }
      if (filter.cost) {
        const blob = JSON.stringify(row.cost || "").toLowerCase();
        if (blob.indexOf(filter.cost.toLowerCase()) < 0) return false;
      }
      if (filter.revenue) {
        const blob = JSON.stringify(row).toLowerCase();
        if (blob.indexOf(filter.revenue.toLowerCase()) < 0) return false;
      }
      if (filter.klass) {
        const blob = (text(row.classification) + " " + text(row.kind) + " " + text(row.state)).toUpperCase();
        if (blob.indexOf(filter.klass.toUpperCase()) < 0) return false;
      }
      return true;
    });
    fillList(node, rows, function (row) {
      const li = document.createElement("li");
      li.textContent = text(row.ts) + " · " + text(row.kind) + " · session " + text(row.session_id) + " · task " + text(row.task_id);
      li.appendChild(evidenceNode(row.evidence));
      return li;
    });
  }

  function briefing(snap) {
    const node = el("briefing");
    const brief = snap.briefing || {};
    const parts = [
      brief.architecture,
      brief.economic_truth,
      "commitments: " + (brief.active_commitments || []).join(", "),
      "blocked: " + (brief.blocked_work || []).join(", ")
    ];
    node.textContent = "";
    parts.forEach(function (line) {
      const p = document.createElement("p");
      p.textContent = text(line);
      node.appendChild(p);
    });
    (brief.statements || []).forEach(function (row) {
      const p = document.createElement("p");
      p.textContent = text(row.text);
      p.appendChild(evidenceNode(row.evidence));
      node.appendChild(p);
    });
  }

  function handoff(snap) {
    const node = el("handoff");
    if (!node) return;
    const brief = (snap.briefing && snap.briefing.handoff) || {};
    const lines = brief.read_this || (snap.cockpit && snap.cockpit.lines) || [];
    node.textContent = "";
    const intro = document.createElement("p");
    intro.textContent = "Continue via " + text(brief.continue_tool || "continue_from_observation") + ". Do not replay a finished prompt.";
    node.appendChild(intro);
    lines.forEach(function (line) {
      const p = document.createElement("p");
      p.textContent = text(line);
      node.appendChild(p);
    });
  }

  function economy(snap) {
    const e = snap.economy || {};
    el("economy").textContent =
      "collected_cash_usd=" + text(e.collected_cash_usd) +
      " · cash_state=" + text(e.cash_state) +
      " · bank_available=" + text(e.bank_available) +
      " · replies_observed=" + text(e.replies_observed) +
      " · contacts_sent=" + text(e.distinct_contacts_sent) +
      ". Drafts, invoices, checkout pages, and unverified interest are not revenue.";
  }

  function routes(snap) {
    fillList(el("routes"), snap.routes || [], function (row) {
      const li = document.createElement("li");
      li.textContent = text(row.session_id) + " · " + text(row.health) + " · " + text(row.reason);
      return li;
    });
  }

  function paint(snap, filter) {
    cockpit(snap);
    sessions(snap);
    presence(snap);
    work(snap);
    findings("collision-list", snap.collisions);
    findings("attention-list", snap.attention);
    timeline(snap, filter || {});
    briefing(snap);
    handoff(snap);
    economy(snap);
    routes(snap);
  }

  function fail(message) {
    el("snapshot-status").textContent = message;
    el("snapshot-status").className = "note error";
  }

  let snapshot = null;
  let filters = {};
  let loading = false;
  const refreshButton = el("refresh-snapshot");
  const refreshStatus = el("refresh-status");

  async function refreshSnapshot() {
    if (loading) return;
    loading = true;
    refreshButton.disabled = true;
    refreshButton.textContent = "Refreshing…";
    refreshStatus.className = "note";
    refreshStatus.textContent = "Loading published observatory.json…";
    const controller = new AbortController();
    let timedOut = false;
    const timeout = setTimeout(function () {
      timedOut = true;
      controller.abort();
    }, 15000);
    try {
      const res = await fetch(SOURCE, { cache: "no-store", signal: controller.signal });
      if (!res.ok) throw new Error("observatory.json HTTP " + res.status);
      const snap = await res.json();
      if (!snap || snap.schema !== "commons-observatory/v0.1") {
        throw new Error("Malformed snapshot: schema is not commons-observatory/v0.1.");
      }
      paint(snap, filters);
      snapshot = snap;
      window.COMMONS_OBSERVATORY = snap;
      refreshStatus.textContent = "Snapshot loaded. Age updates locally; data changes only when refreshed.";
    } catch (err) {
      const detail = timedOut ? "request timed out after 15 seconds" : err.message;
      let message = "Could not load observatory.json (" + detail + "). ";
      if (snapshot) {
        // A malformed new bake may have failed partway through painting.
        // Restore every section from the last successfully rendered source.
        paint(snapshot, filters);
        message += "Showing the last successfully loaded snapshot; its bake time is unchanged.";
      } else {
        message += "Open the JSON file directly or try Refresh snapshot. This is a bake, not a live socket.";
        fail(message);
      }
      refreshStatus.className = "note error";
      refreshStatus.textContent = message;
    } finally {
      clearTimeout(timeout);
      loading = false;
      refreshButton.disabled = false;
      refreshButton.textContent = "Refresh snapshot";
    }
  }

  refreshButton.addEventListener("click", refreshSnapshot);
  el("timeline-filters").addEventListener("submit", function (ev) {
    ev.preventDefault();
    const data = new FormData(ev.target);
    filters = { kind: data.get("kind"), session: data.get("session"), harness: data.get("harness"), klass: data.get("klass"), task: data.get("task"), path: data.get("path"), provider: data.get("provider"), landing: data.get("landing"), blocker: data.get("blocker"), cost: data.get("cost"), revenue: data.get("revenue") };
    if (snapshot) paint(snapshot, filters);
  });
  el("timeline-filters").addEventListener("reset", function () {
    setTimeout(function () {
      filters = {};
      if (snapshot) paint(snapshot, filters);
    }, 0);
  });

  function updateAge() {
    if (snapshot && !document.hidden) snapshotStatus(snapshot);
  }
  // Recompute age, never the bake's timestamp, counts, or observations.
  // There is no automatic network polling or full-page repaint here.
  setInterval(updateAge, 60000);
  document.addEventListener("visibilitychange", updateAge);
  refreshSnapshot();
})();
