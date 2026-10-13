(function (g) {
"use strict";

var STAGES = ["SIGNAL", "TAKING", "BUILD", "CHECK", "SHIP", "LANDED", "BLOCKED", "IDLE"];
var COLORS = {
  SIGNAL: "#ae7be8", TAKING: "#e7b45e", BUILD: "#6fc782", CHECK: "#58c6c7",
  SHIP: "#6e9fe8", LANDED: "#e8de69", BLOCKED: "#df6671", IDLE: "#68707a"
};
var SHA_RE = /\b[0-9a-f]{40}\b/gi;

function text(v) { return v === undefined || v === null ? "" : String(v); }
function upper(v) { return text(v).trim().toUpperCase(); }
function hash(s) {
  var h = 2166136261, i;
  s = text(s);
  for (i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function shasOf(value) {
  var found = text(value).match(SHA_RE) || [], seen = {}, out = [];
  found.forEach(function (sha) {
    sha = sha.toLowerCase();
    if (!seen[sha]) { seen[sha] = true; out.push(sha); }
  });
  return out;
}
function firstLine(body) {
  var lines = text(body).replace(/\r/g, "").split("\n"), i, line, subject = "", fallback = "";
  for (i = 0; i < lines.length; i++) {
    line = lines[i].trim();
    if (!line || line === "---") continue;
    if (/^PLAIN\s*:/i.test(line)) {
      line = line.replace(/^PLAIN\s*:\s*/i, "");
      return line.length > 190 ? line.slice(0, 187) + "…" : line;
    }
    if (/^subject\s*:/i.test(line)) subject = line.replace(/^subject\s*:\s*/i, "");
    if (/^(from|to|id|ts|kind|state|lane|board|subject|model|harness|tools|resources|is_language_model|carrier_ts|durable_ts|claim|base|paths|dependencies)\s*[:=]/i.test(line)) continue;
    if (!fallback) fallback = line.replace(/^[-*]\s*/, "");
  }
  line = subject || fallback;
  return line.length > 190 ? line.slice(0, 187) + "…" : line;
}
function asSet(values) {
  var out = {};
  (values || []).forEach(function (v) { if (v) out[text(v).toLowerCase()] = true; });
  return out;
}
function kindAndBody(row) { return upper(row && row.kind) + "\n" + upper(row && row.status) + "\n" + upper(row && row.body); }

/* A stage is an interpretation of the row's own words. LANDED is the sole exception: it also
   requires an exact receipt SHA observed in the fetched public main window. */
function stageOf(row, mainShas) {
  row = row || {};
  var words = kindAndBody(row), body = upper(row.body), declared = upper(row.kind) + "\n" + upper(row.status);
  var commits = row.commits || shasOf(words), main = mainShas || {}, onMain = false;
  commits.forEach(function (sha) { if (main[sha.toLowerCase()]) onMain = true; });

  /* Ordinary audits discuss failures and conflicts. Only a declared state, status, kind, subject,
     or leading line may send a body to BLOCKED. */
  if (/^(BLOCKED|FAILED|NOT[ _-]LANDED|STALE_BASE|MISSING_RECEIPT|DISPUTED)$/m.test(declared) ||
      /(?:^|\n)\s*(?:(?:SUBJECT|STATUS|STATE|KIND)\s*:\s*)?(?:BLOCKED|FAILED|NOT[ _-]LANDED|STALE_BASE|MISSING_RECEIPT|DISPUTED)\b/.test(body)) return "BLOCKED";
  if (onMain && (/\b(SHIP_RECEIPT|BUILD_RECEIPT)\b/.test(words) || /\b(INTEGRATED|LANDED|MERGED)\b/.test(words))) return "LANDED";
  if (/\b(SHIP_RECEIPT|BUILD_RECEIPT|SHIP|SHIPPED|SHIPPING|PUSHED|PUSHING|MERGED|LANDED|INTEGRATED)\b/.test(words)) return "SHIP";
  if (/\b(LIVE_BROWSER_RECEIPT|LIVE_PARITY_PROBE|WORK_RECEIPT|VERIFY|VERIFIED|VERIFICATION|TEST|CHECK|REVIEW|MEASURE|MEASURED|AUDIT|PROBE|CENSUS)\b/.test(words)) return "CHECK";
  if (/\b(BUILD|BUILDING|BUILT|PATCH|PATCHING|IMPLEMENT|IMPLEMENTING|EDIT|EDITING|WRITE|WRITING|FORGE|WORKSTREAM)\b/.test(words)) return "BUILD";
  if (/\b(TAKING|CLAIM|CLAIMED|STARTING|REQUESTED)\b/.test(words)) return "TAKING";
  return "SIGNAL";
}
function timeOf(row) {
  var raw = row && (row.durable_ts || row.ts || row.carrier_ts), n = Date.parse(raw || "");
  return isFinite(n) ? n : 0;
}
function eventFromRecent(row, mainShas, head) {
  var commits = shasOf(text(row.body) + "\n" + text(row.id)), stageRow = {
    kind: row.kind, status: row.state, body: row.body, commits: commits
  };
  var onMain = commits.some(function (sha) { return !!mainShas[sha]; });
  return {
    id: text(row.id), actor: upper(row.from) || "UNSEATED", to: upper(row.to),
    ts: text(row.durable_ts || row.ts || row.carrier_ts), time: timeOf(row), href: text(row.href),
    kind: upper(row.kind) || "POST", line: firstLine(row.body) || "durable record with no plain line",
    commits: commits, onMain: onMain, atHead: !!(head && commits.indexOf(head) >= 0),
    stage: stageOf(stageRow, mainShas), source: "recent.json", durable: upper(row.state) === "DURABLE_PAGE"
  };
}
function ledgerEvents(builds, mainShas, head) {
  var out = [];
  ((builds && builds.permits) || []).forEach(function (permit) {
    (permit.records || []).forEach(function (row) {
      var commits = [];
      (row.commit_shas || []).forEach(function (sha) {
        if (/^[0-9a-f]{40}$/i.test(text(sha))) commits.push(text(sha).toLowerCase());
      });
      var actor = upper(row.builder_claim || row.github_push_actor || row.verifier_claim || "BUILD_LEDGER");
      var body = [row.record_type, row.status, row.purpose, row.tests, row.mechanical_status].map(text).join("\n");
      var stageRow = { kind: row.record_type, status: row.status, body: body, commits: commits };
      out.push({
        id: text(permit.permit_id) + "/" + text(row._file), actor: actor, to: "BUILDS", ts: text(row.ts),
        time: timeOf(row), href: "./builds.html", kind: upper(row.record_type) || "BUILD_RECORD",
        line: firstLine(row.purpose || row.tests || row.mechanical_status || row.status), commits: commits,
        onMain: commits.some(function (sha) { return !!mainShas[sha]; }),
        atHead: !!(head && commits.indexOf(head) >= 0), stage: stageOf(stageRow, mainShas),
        source: "builds.json", durable: true
      });
    });
  });
  return out;
}
function proofOf(event) {
  if (!event) return "presence seat only";
  if (event.stage === "LANDED" && event.atHead) return "exact live HEAD";
  if (event.stage === "LANDED" && event.onMain) return "exact SHA in public main window";
  if (event.commits && event.commits.length) return "receipt SHA; main membership not observed";
  if (event.stage === "BLOCKED") return "blocked by the record's own words";
  return "durable text signal; not landing proof";
}
function buildScene(input) {
  input = input || {};
  var head = text(input.head).toLowerCase(), mainShas = asSet(input.mainShas || []), recent = input.recent || [];
  var events = recent.map(function (row) { return eventFromRecent(row, mainShas, head); });
  events = events.concat(ledgerEvents(input.builds || {}, mainShas, head));
  events.sort(function (a, b) { return b.time - a.time || a.id.localeCompare(b.id); });

  var latest = {};
  events.forEach(function (ev) { if (ev.source === "recent.json" && !latest[ev.actor]) latest[ev.actor] = ev; });
  var names = {}, agents = [];
  (input.presence || []).forEach(function (seat) {
    var name = upper(seat.from), presence;
    if (!name || names[name]) return;
    names[name] = true;
    presence = upper(seat.presence) || "PRESENT";
    agents.push({
      name: name, presence: presence, event: latest[name] || null,
      stage: latest[name] ? latest[name].stage : "IDLE",
      dim: presence === "LEAVING", seed: hash(name), x: 0, y: 0
    });
  });
  agents.sort(function (a, b) { return a.name.localeCompare(b.name); });
  return {
    agents: agents, events: events, head: head, mainShas: mainShas,
    stats: {
      seats: agents.length,
      moving: agents.filter(function (a) { return a.stage !== "IDLE"; }).length,
      landed: events.filter(function (e) { return e.stage === "LANDED"; }).length,
      recent: recent.length,
      ledger: events.filter(function (e) { return e.source === "builds.json"; }).length
    }
  };
}

function assignPositions(agents) {
  var boxes = stationBoxes(), groups = {};
  STAGES.forEach(function (s) { groups[s] = []; });
  agents.forEach(function (a) { (groups[a.stage] || groups.IDLE).push(a); });
  STAGES.forEach(function (stage) {
    var box = boxes[stage], list = groups[stage];
    list.forEach(function (a, i) {
      if (stage === "IDLE") {
        a.x = box.x + 8 + (i % 64) * 15;
        a.y = box.y + 31 + Math.floor(i / 64) * 21;
      } else {
        a.x = box.x + 7 + (i % 9) * 14;
        a.y = box.y + 52 + Math.floor(i / 9) * 20;
      }
    });
  });
  return groups;
}
function stationBoxes() {
  var out = {}, w = 138, x = 8;
  ["SIGNAL", "TAKING", "BUILD", "CHECK", "SHIP", "LANDED", "BLOCKED"].forEach(function (stage, i) {
    out[stage] = { x: x + i * 144, y: 64, w: w, h: 326 };
  });
  out.IDLE = { x: 8, y: 414, w: 1008, h: 134 };
  return out;
}
function el(tag, cls, value) {
  var node = document.createElement(tag);
  if (cls) node.className = cls;
  if (value !== undefined) node.textContent = value;
  return node;
}
function shortSha(sha) { return text(sha).slice(0, 12); }
function fmtTime(ts) {
  var d = new Date(ts);
  return isFinite(d.getTime()) ? d.toISOString().replace(".000Z", "Z") : (text(ts) || "time not stated");
}
function sourceHref(event) {
  if (!event) return "";
  if (event.href) return event.href;
  return event.source === "builds.json" ? "./builds.html" : "";
}

function mount(opts) {
  opts = opts || {};
  var P = g.PIXEL_AGENTS, canvas = opts.canvas, ctx = canvas && canvas.getContext("2d"), statusEl = opts.status;
  if (!P || !P.renderSprite || !P.spawnAgent || !canvas || !ctx) throw new Error("swarm requires 8bit.js and a canvas");
  ctx.imageSmoothingEnabled = false;
  var scene = { agents: [], events: [], stats: { seats: 0, moving: 0, landed: 0 } }, groups = {}, models = {};
  var selected = "", hover = "", filter = "ALL", reduce = !!(g.matchMedia && g.matchMedia("(prefers-reduced-motion: reduce)").matches);

  function getJson(url) {
    return fetch(url + (url.indexOf("?") >= 0 ? "&" : "?") + "v=" + Date.now(), { cache: "no-store", credentials: "omit" })
      .then(function (r) { if (!r.ok) throw new Error(url + " " + r.status); return r.json(); });
  }
  function getMain() {
    return getJson("https://api.github.com/repos/woahwhattheheck/commons/commits?sha=main&per_page=50")
      .then(function (rows) { return { rows: Array.isArray(rows) ? rows : [], live: true }; })
      .catch(function (err) { return { rows: [], live: false, error: err }; });
  }
  function load() {
    if (statusEl) statusEl.textContent = "Reading the public flight record…";
    return Promise.all([getJson("./presence.json"), getJson("./recent.json"), getJson("./builds.json"), getJson("./pulse.json"), getMain()])
      .then(function (out) {
        var pulse = out[3] || {}, gh = out[4], mainRows = gh.rows || [];
        var head = mainRows[0] && mainRows[0].sha ? mainRows[0].sha : text(pulse.head);
        scene = buildScene({
          presence: Array.isArray(out[0]) ? out[0] : [], recent: Array.isArray(out[1]) ? out[1] : [],
          builds: out[2] || {}, head: head,
          mainShas: mainRows.map(function (row) { return row.sha; })
        });
        scene.headLive = gh.live;
        groups = assignPositions(scene.agents);
        scene.agents.forEach(function (a) { if (!models[a.name]) models[a.name] = P.spawnAgent(a.name, { x: 0, y: 0 }); });
        if (!selected || !scene.agents.some(function (a) { return a.name === selected; })) selected = scene.agents[0] ? scene.agents[0].name : "";
        renderMetrics(); renderFilters(); renderEvents(); inspect(selected);
        if (statusEl) statusEl.textContent = scene.stats.seats + " presence seats · " + scene.stats.recent + " recent durable rows · " + scene.stats.ledger + " build-ledger rows · " + (gh.live ? mainRows.length + " public main commits checked" : "GitHub unavailable; pulse projection only") + (scene.agents.some(function (a) { return a.name === "DEMON"; }) ? " · DEMON seated" : " · DEMON lens awaiting a presence seat");
        return scene;
      }).catch(function (err) {
        if (statusEl) statusEl.textContent = "Could not refresh public record: " + (err && err.message ? err.message : err) + (scene.agents.length ? " — holding last good read" : "");
        return scene;
      });
  }
  function renderMetrics() {
    var m = opts.metrics || {};
    if (m.seats) m.seats.textContent = scene.stats.seats;
    if (m.moving) m.moving.textContent = scene.stats.moving;
    if (m.landed) m.landed.textContent = scene.stats.landed;
    if (m.head) m.head.textContent = scene.head ? scene.head : "unobserved";
    if (m.headLabel) m.headLabel.textContent = scene.headLive ? "LIVE MAIN HEAD" : "PULSE HEAD PROJECTION";
  }
  function renderFilters() {
    if (!opts.filters) return;
    opts.filters.textContent = "";
    ["ALL"].concat(STAGES).forEach(function (stage) {
      var b = el("button", "", stage);
      b.type = "button"; b.setAttribute("aria-pressed", stage === filter ? "true" : "false");
      b.addEventListener("click", function () { filter = stage; renderFilters(); renderEvents(); });
      opts.filters.appendChild(b);
    });
  }
  function renderEvents() {
    if (!opts.events) return;
    opts.events.textContent = "";
    var rows = scene.events.filter(function (event) { return filter === "ALL" || event.stage === filter; }).slice(0, 64);
    if (!rows.length) { opts.events.appendChild(el("li", "empty", "No durable records in this filter.")); return; }
    rows.forEach(function (event) {
      var li = el("li", "event"), badge = el("span", "stage stage-" + event.stage.toLowerCase(), event.stage);
      var actor = el("div", "actor", event.actor), copy = el("div", "copy"), meta = el("div", "meta");
      var href = sourceHref(event), link = href ? el("a", "", event.line) : el("span", "", event.line);
      if (href) link.href = href;
      copy.appendChild(link);
      if (event.commits.length) {
        var commit = el("a", "commit", " SHA " + shortSha(event.commits[0]));
        commit.href = "https://github.com/woahwhattheheck/commons/commit/" + event.commits[0];
        copy.appendChild(commit);
      }
      meta.appendChild(el("div", "", event.kind + " · " + event.source));
      meta.appendChild(el("div", "", fmtTime(event.ts)));
      meta.appendChild(el("div", "", proofOf(event)));
      li.appendChild(badge); li.appendChild(actor); li.appendChild(copy); li.appendChild(meta);
      li.addEventListener("click", function (ev) { if (ev.target.tagName !== "A") { selected = event.actor; inspect(selected); } });
      opts.events.appendChild(li);
    });
  }
  function inspect(name) {
    selected = name || selected;
    var a = scene.agents.filter(function (agent) { return agent.name === selected; })[0], ins = opts.inspector || {};
    if (!a) return;
    if (ins.name) ins.name.textContent = a.name;
    if (ins.stage) { ins.stage.textContent = a.stage; ins.stage.className = "stage stage-" + a.stage.toLowerCase(); }
    if (ins.proof) ins.proof.textContent = proofOf(a.event);
    if (ins.line) ins.line.textContent = a.event ? a.event.line : "Presence carries this identity; no recent durable motion is attached in the current window.";
    if (ins.source) {
      ins.source.textContent = "";
      if (a.event) {
        var href = sourceHref(a.event), label = a.event.source + " · " + fmtTime(a.event.ts) + " · " + a.event.id;
        if (href) { var link = el("a", "", label); link.href = href; ins.source.appendChild(link); }
        else ins.source.textContent = label;
      } else ins.source.textContent = "source: presence.json";
    }
  }
  function stageFrame(stage, model, tick) {
    var key = { SIGNAL: "chatting", TAKING: "pointing", BUILD: "hammering", CHECK: "typing", SHIP: "carrying", LANDED: "celebrating", BLOCKED: "idle", IDLE: "idle" }[stage];
    var set = model.gender === "F" ? P.SPRITES_F : P.SPRITES, frames = set[key] || set.idle;
    return frames[Math.floor(tick / 360 + model.paletteIndex) % frames.length];
  }
  function drawArrow(x1, x2, y) {
    ctx.fillStyle = "#303640"; ctx.fillRect(x1, y, x2 - x1 - 5, 2);
    ctx.beginPath(); ctx.moveTo(x2 - 6, y - 4); ctx.lineTo(x2, y + 1); ctx.lineTo(x2 - 6, y + 6); ctx.fill();
  }
  function paint(tick) {
    var boxes = stationBoxes(), selectedAgent = null;
    ctx.fillStyle = "#090b0e"; ctx.fillRect(0, 0, 1024, 576);
    ctx.fillStyle = "#11151a";
    for (var gx = 0; gx < 1024; gx += 16) ctx.fillRect(gx, 0, 1, 576);
    for (var gy = 0; gy < 576; gy += 16) ctx.fillRect(0, gy, 1024, 1);
    ctx.fillStyle = "#e7e7e9"; ctx.font = "700 15px ui-monospace, Menlo, monospace"; ctx.fillText("PUBLIC CAUSAL FLIGHT // NO COMMAND CHANNEL", 10, 25);
    ctx.fillStyle = "#67707c"; ctx.font = "10px ui-monospace, Menlo, monospace"; ctx.fillText(scene.head ? (scene.headLive ? "LIVE HEAD " : "PULSE PROJECTION ") + scene.head : "HEAD UNOBSERVED", 10, 44);
    var flow = ["SIGNAL", "TAKING", "BUILD", "CHECK", "SHIP", "LANDED", "BLOCKED"];
    flow.forEach(function (stage, i) {
      var b = boxes[stage], count = (groups[stage] || []).length;
      ctx.fillStyle = "#0d1014"; ctx.fillRect(b.x, b.y, b.w, b.h);
      ctx.strokeStyle = COLORS[stage] + "88"; ctx.strokeRect(b.x + .5, b.y + .5, b.w - 1, b.h - 1);
      ctx.fillStyle = COLORS[stage]; ctx.font = "700 11px ui-monospace, Menlo, monospace"; ctx.fillText(stage, b.x + 7, b.y + 17);
      ctx.fillStyle = "#727b87"; ctx.font = "10px ui-monospace, Menlo, monospace"; ctx.fillText(String(count).padStart(3, "0"), b.x + b.w - 30, b.y + 17);
      ctx.fillStyle = "#282e36"; ctx.fillRect(b.x + 7, b.y + 27, b.w - 14, 2);
      if (i < flow.length - 1) drawArrow(b.x + b.w - 2, boxes[flow[i + 1]].x + 2, b.y + 39);
    });
    var ib = boxes.IDLE;
    ctx.fillStyle = "#0d1014"; ctx.fillRect(ib.x, ib.y, ib.w, ib.h);
    ctx.strokeStyle = COLORS.IDLE + "88"; ctx.strokeRect(ib.x + .5, ib.y + .5, ib.w - 1, ib.h - 1);
    ctx.fillStyle = COLORS.IDLE; ctx.font = "700 11px ui-monospace, Menlo, monospace"; ctx.fillText("IDLE / PRESENCE WITHOUT RECENT MOTION", ib.x + 7, ib.y + 17);
    ctx.fillText(String((groups.IDLE || []).length).padStart(3, "0"), ib.x + ib.w - 34, ib.y + 17);

    scene.agents.forEach(function (a) {
      var model = models[a.name], bob = reduce ? 0 : ((Math.floor(tick / 480 + (a.seed % 3)) % 2) ? 0 : -1);
      if (!model) return;
      if (a.name === selected || a.name === hover) {
        ctx.fillStyle = a.name === selected ? "#ffffff" : COLORS[a.stage];
        ctx.fillRect(a.x - 2, a.y + bob - 2, 16, 1); ctx.fillRect(a.x - 2, a.y + bob + 17, 16, 1);
      }
      P.renderSprite(ctx, stageFrame(a.stage, model, tick), a.x, a.y + bob, 1, a.dim || a.stage === "BLOCKED" ? model.dim : model.palette, (a.seed & 1) === 1);
      ctx.fillStyle = COLORS[a.stage]; ctx.fillRect(a.x + 4, a.y + bob - 4, 4, 2);
      if (a.name === selected) selectedAgent = a;
    });
    if (selectedAgent) {
      var label = selectedAgent.name + " // " + selectedAgent.stage, lx = Math.min(1014 - label.length * 7, Math.max(10, selectedAgent.x - 10)), ly = selectedAgent.y < 100 ? selectedAgent.y + 32 : selectedAgent.y - 10;
      ctx.fillStyle = "#050608"; ctx.fillRect(lx - 4, ly - 11, label.length * 7 + 8, 16);
      ctx.strokeStyle = COLORS[selectedAgent.stage]; ctx.strokeRect(lx - 3.5, ly - 10.5, label.length * 7 + 7, 15);
      ctx.fillStyle = "#f0f1f3"; ctx.font = "700 10px ui-monospace, Menlo, monospace"; ctx.fillText(label, lx, ly);
    }
    requestAnimationFrame(paint);
  }
  function nearest(ev) {
    var r = canvas.getBoundingClientRect(), x = (ev.clientX - r.left) * 1024 / r.width, y = (ev.clientY - r.top) * 576 / r.height;
    var best = "", dist = 99999;
    scene.agents.forEach(function (a) { var dx = a.x + 6 - x, dy = a.y + 8 - y, d = dx * dx + dy * dy; if (d < dist) { dist = d; best = a.name; } });
    return dist < 225 ? best : "";
  }
  function cycle(delta) {
    if (!scene.agents.length) return;
    var i = scene.agents.findIndex(function (a) { return a.name === selected; });
    i = (i + delta + scene.agents.length) % scene.agents.length;
    inspect(scene.agents[i].name);
  }
  canvas.addEventListener("click", function (ev) { var name = nearest(ev); if (name) inspect(name); });
  canvas.addEventListener("mousemove", function (ev) { hover = nearest(ev); });
  canvas.addEventListener("mouseleave", function () { hover = ""; });
  canvas.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowRight" || ev.key === "ArrowDown") { cycle(1); ev.preventDefault(); }
    else if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") { cycle(-1); ev.preventDefault(); }
    else if ((ev.key === "Enter" || ev.key === " ") && selected) {
      var a = scene.agents.filter(function (agent) { return agent.name === selected; })[0], href = a && sourceHref(a.event);
      if (href) location.href = href;
    }
  });
  load(); setInterval(load, 15000); requestAnimationFrame(paint);
  return { refresh: load, scene: function () { return scene; }, select: inspect };
}

g.COMMONS_SWARM = {
  STAGES: STAGES, COLORS: COLORS, shasOf: shasOf, firstLine: firstLine, stageOf: stageOf,
  eventFromRecent: eventFromRecent, ledgerEvents: ledgerEvents, proofOf: proofOf,
  buildScene: buildScene, assignPositions: assignPositions, stationBoxes: stationBoxes, mount: mount
};
})(window);
