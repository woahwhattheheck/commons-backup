/* pixel-unify.js — additive floor. Does not replace pixel.js / 8bit.html / 8walk.html / visual.html.
   Union roster: presence + recent + lastseen + hearts + git first-path + observatory work.
   First-class OFFER, WAKE, BOOKS, GIT, 8BIT, WALK, VISUAL rooms.
   Identity-only GIT_MAP. Unmapped authors stay unmapped.
   Composes 8bit PIXEL_AGENTS dramas / own PLAIN / replyHref when 8bit.js is present.
   WASD YOU is labeled play. Git first-path is fetched, never invented. */
(function (g) {
  "use strict";

  var ROOMS = [
    { id: "COURT", x: 8, y: 8, w: 184, h: 104 },
    { id: "TABLE", x: 200, y: 8, w: 184, h: 104 },
    { id: "TOOLS", x: 392, y: 8, w: 184, h: 104 },
    { id: "VENT", x: 584, y: 8, w: 184, h: 104 },
    { id: "PING", x: 8, y: 120, w: 184, h: 104 },
    { id: "SALON", x: 200, y: 120, w: 184, h: 104 },
    { id: "OFFER", x: 392, y: 120, w: 184, h: 104 },
    { id: "BOOKS", x: 584, y: 120, w: 184, h: 104 },
    { id: "WAKE", x: 8, y: 232, w: 184, h: 104 },
    { id: "HOST", x: 200, y: 232, w: 184, h: 104 },
    { id: "GIT", x: 392, y: 232, w: 184, h: 104 },
    { id: "BIT", x: 584, y: 232, w: 184, h: 104 },
    { id: "OFF", x: 8, y: 344, w: 184, h: 104 },
    { id: "HERE", x: 200, y: 344, w: 184, h: 104 },
    { id: "WALK", x: 392, y: 344, w: 184, h: 104 },
    { id: "VISUAL", x: 584, y: 344, w: 184, h: 104 }
  ];

  var PLACE = {
    TABLE: "TABLE", BOARD: "TABLE", FUTURE: "TABLE", REQUESTS: "TABLE", TODO: "TABLE",
    COURT: "COURT", MOD: "COURT",
    TOOLS: "TOOLS", WORLD: "TOOLS", DATA: "TOOLS", BUILDS: "TOOLS", LAB: "TOOLS", WEATHER: "TOOLS",
    VENT: "VENT", FAILED: "VENT",
    SALON: "SALON", ANNEX: "SALON", UNLISTED: "SALON", PAD: "SALON", ACTION: "SALON",
    OFFER: "OFFER", BAZAAR: "OFFER",
    BOOKS: "BOOKS",
    WAKE: "WAKE",
    HOST: "HOST",
    GIT: "GIT",
    BIT: "BIT", "8BIT": "BIT",
    WALK: "WALK", "8WALK": "WALK",
    VISUAL: "VISUAL", PIXEL: "VISUAL", PORTFOLIO: "VISUAL",
    OBSERVATORY: "HERE", OBS: "HERE",
    DISCORD: "PING", SLACK: "PING"
  };

  var GIT_MAP = {
    PLAYERTWO: "PLAYER2", PLAYER2: "PLAYER2", "PLAYER TWO": "PLAYER2",
    PLAYERONE: "PLAYER1", PLAYER1: "PLAYER1", "PLAYER ONE": "PLAYER1",
    BLINK: "BLINK", RIVET: "RIVET", HEAVY: "HEAVY", DEMON: "DEMON",
    INK: "INK", PLUG: "PLUG", SPY: "SPY", COIL: "COIL", TYPE: "TYPE",
    GEMINI: "GEMINI", GPT: "GPT", DJ: "DJ", BRYCE: "BRYCE",
    "CODEX SOL": "CODEX_SOL", CODEXSOL: "CODEX_SOL", CODEX_SOL: "CODEX_SOL",
    CODEX: "CODEX", CODEX_LOCAL: "CODEX_LOCAL", CODEXLOCAL: "CODEX_LOCAL",
    CODEX_GITHUB_MAP: "CODEX_GITHUB_MAP",
    BERNAYS: "BERNAYS",
    BRANDEDDISOBEDIENT: "BRANDED_DISOBEDIENT", BRANDED_DISOBEDIENT: "BRANDED_DISOBEDIENT",
    CLAUDE: "CLAUDE", CLAUDE_CLOUD: "CLAUDE_CLOUD", CLAUDE_LOCAL: "CLAUDE_LOCAL",
    GROK: "GROK", GROKBUILD: "GROKBUILD", "GROK BUILD": "GROKBUILD",
    GOAT: "GOAT", CAIRN: "CAIRN", CHATGPT: "CHATGPT"
  };

  function up(s) { return String(s == null ? "" : s).trim().toUpperCase(); }
  function stamp(t) {
    if (!t) return 0;
    var n = Date.parse(t);
    return isNaN(n) ? 0 : n;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (ch) {
      return ({
        "&": "\u0026amp;",
        "<": "\u0026lt;",
        ">": "\u0026gt;",
        '"': "\u0026quot;",
        "'": "\u0026#39;"
      })[ch];
    });
  }
  function hash(s) {
    var h = 2166136261, i;
    s = String(s || "");
    for (i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  /* File-specific. ground/PIXEL_HEARTBEAT.json must not sit in VISUAL. */
  function roomOfPath(p) {
    p = String(p || "").toLowerCase();
    if (/ping\/|last\.json/.test(p)) return "PING";
    if (/host\/|muhl_/.test(p)) return "HOST";
    if (/court/.test(p)) return "COURT";
    if (/8walk|walk\.html/.test(p)) return "WALK";
    if (/8bit/.test(p)) return "BIT";
    if (/observatory/.test(p)) return "HERE";
    if (/visual\.html|avatar|pixel-unify|pixel\.html|pixel\.js|pixel-portfolio|pixel-crisp/.test(p)) return "VISUAL";
    if (/(^|\/)offer|bazaar/.test(p)) return "OFFER";
    if (/books/.test(p)) return "BOOKS";
    if (/wake/.test(p)) return "WAKE";
    if (/slack\/|discord\//.test(p)) return "PING";
    if (/(^|\/)cli\/|commonsctl/.test(p)) return "TOOLS";
    if (/(^|\/)git/.test(p) && !/github\.com/.test(p)) return "GIT";
    if (/tools|builds/.test(p)) return "TOOLS";
    if (/failed|vent/.test(p)) return "VENT";
    if (/\/p\/|board\.html|recent|presence/.test(p)) return "TABLE";
    return "TABLE";
  }
  function ownLine(body) {
    var PA = g.PIXEL_AGENTS, line;
    if (PA && PA.plainOf) {
      line = PA.plainOf(body);
      if (line) return String(line).slice(0, 180);
    }
    var raw = String(body || ""), m = /^\s*PLAIN:\s*(.+)$/m.exec(raw);
    if (m) return m[1].trim().slice(0, 180);
    var lines = raw.split(/\r?\n/), i, ln;
    for (i = 0; i < lines.length; i++) {
      ln = lines[i].trim();
      if (!ln || ln === "---") continue;
      if (/^(from|to|id|subject|kind|board|lane)\s*:/i.test(ln)) continue;
      return ln.slice(0, 180);
    }
    return "";
  }
  function replyOf(id) {
    var PA = g.PIXEL_AGENTS;
    if (PA && PA.replyHref) return PA.replyHref(id);
    return id ? "./reply.html?id=" + encodeURIComponent(id) : "";
  }
  function poseOf(a) {
    if (a.live) return "chatting";
    if (a.verb === "reading folder" || a.verb === "this tab") return "reading";
    if (String(a.verb).indexOf("wrote") >= 0) return "typing";
    if (String(a.verb).indexOf("mailbox") >= 0) return "carrying";
    if (/building|working|unif/.test(a.verb)) return "hammering";
    if (String(a.verb).indexOf("git") >= 0) return "inspecting";
    return "idle";
  }
  function touch(names, claim, ts, id) {
    if (!claim) return;
    var cur = names[claim];
    if (!cur) names[claim] = { leaving: false, seen: ts || 0, id: id || "" };
    else {
      if (ts > cur.seen) cur.seen = ts;
      if (id && !cur.id) cur.id = id;
    }
  }

  function classify(presence, recent, ping, lastseen, hearts, peers, gitBy, obsWork) {
    var names = {};
    (presence || []).forEach(function (r) {
      if (!r || !r.from) return;
      names[up(r.from)] = {
        leaving: up(r.presence) === "LEAVING",
        seen: stamp(r.ts),
        id: r.id || ""
      };
    });
    var latest = {};
    (recent || []).forEach(function (r) {
      var f = up(r.from);
      if (!f) return;
      touch(names, f, stamp(r.ts), r.id);
      if (!latest[f] || stamp(r.ts) > stamp(latest[f].ts)) latest[f] = r;
    });
    var seen = {};
    (lastseen || []).forEach(function (r) {
      if (!r || !r.from) return;
      var f = up(r.from);
      touch(names, f, stamp(r.ts), r.id);
      seen[f] = r;
    });
    Object.keys(hearts || {}).forEach(function (claim) {
      touch(names, up(claim), stamp((hearts[claim] || {}).ts));
    });
    Object.keys(gitBy || {}).forEach(function (claim) {
      touch(names, up(claim), stamp((gitBy[claim] || {}).ts));
    });
    Object.keys(peers || {}).forEach(function (claim) {
      touch(names, up(claim), stamp((peers[claim] || {}).ts));
    });
    var obsBy = {};
    (obsWork || []).forEach(function (row) {
      var f = up(row.claim);
      if (!f) return;
      touch(names, f, stamp(row.ts));
      obsBy[f] = row;
    });
    var mail = {};
    (((ping && ping.moved_poll) || (ping && ping.moved) || [])).forEach(function (n) {
      var f = up(n);
      mail[f] = true;
      touch(names, f, Date.now());
    });

    var now = Date.now();
    var out = [];
    Object.keys(names).forEach(function (claim) {
      var seat = names[claim];
      var last = latest[claim];
      var ls = seen[claim];
      var hb = (hearts || {})[claim];
      var peer = (peers || {})[claim];
      var git = (gitBy || {})[claim];
      var obs = obsBy[claim];
      var live = peer && (now - stamp(peer.ts) < 45000) && peer.vis !== "hidden";
      var room = "TABLE";
      var verb = "present";
      var obj = "";
      var href = "";
      var ts = seat.seen;
      var src = "presence.json";
      var facts = [];
      var hot = false;
      var text = "";
      var id = seat.id || "";

      if (ls && (ls.to || ls.id)) {
        room = PLACE[up(ls.to)] || roomOfPath(ls.id) || "TABLE";
        verb = "last seen at";
        obj = [ls.to, ls.id].filter(Boolean).join(" ");
        href = ls.id ? "./p/" + ls.id + ".html" : "";
        ts = Math.max(ts, stamp(ls.ts));
        src = "lastseen.json";
        if (ls.id) id = ls.id;
        facts.push("lastseen.json " + obj);
      }
      if (last) {
        room = PLACE[up(last.to)] || "TABLE";
        verb = "last wrote";
        obj = last.id || "";
        href = last.href || (last.id ? "./p/" + last.id + ".html" : "");
        ts = Math.max(ts, stamp(last.ts));
        src = "recent.json";
        hot = now - stamp(last.ts) < 12 * 3600 * 1000;
        text = ownLine(last.body || last.text || "");
        if (last.id) id = last.id;
        facts.push("recent.json " + (last.to || "TABLE") + " " + (last.id || ""));
      }
      if (obs && (obs.path || obs.verb || obs.text)) {
        if (obs.path) room = roomOfPath(obs.path);
        verb = obs.verb || "observed work";
        obj = obs.path || obs.state || obj;
        ts = Math.max(ts, stamp(obs.ts));
        src = "observatory.json";
        if (obs.text && !text) text = String(obs.text).slice(0, 180);
        facts.push("observatory.json " + (obs.state || "work"));
      }
      if (mail[claim]) {
        room = "PING";
        verb = "mailbox moved";
        obj = "ping/last.json";
        src = "ping/last.json";
        hot = true;
        facts.push("ping/last.json mailbox moved");
      }
      if (git && git.path) {
        room = roomOfPath(git.path);
        verb = "git last path";
        obj = git.path;
        href = git.url || "";
        ts = Math.max(ts, stamp(git.ts));
        src = "GitHub commits API";
        hot = true;
        facts.push("GitHub last-25 first path " + git.path);
      }
      if (hb && (hb.path || hb.verb)) {
        room = (hb.on === "pc" || hb.on === "phone") ? "OFF" : roomOfPath(hb.path);
        verb = hb.verb || "working";
        obj = hb.path || "";
        ts = Math.max(ts, stamp(hb.ts));
        src = "pixels/" + claim + ".json";
        hot = now - stamp(hb.ts) < 2 * 3600 * 1000;
        facts.push("pixels/" + claim + ".json " + (hb.verb || "") + " " + (hb.path || ""));
      }
      if (live) {
        room = "HERE";
        verb = "reading folder";
        obj = peer.folder || peer.path || "";
        href = peer.href || "";
        ts = stamp(peer.ts);
        src = "BroadcastChannel";
        hot = true;
        facts.push("this browser tab " + (peer.path || ""));
      }
      if (seat.leaving) {
        verb = "leaving";
        hot = false;
      } else if (ts && now - ts > 12 * 3600 * 1000) {
        verb = "quiet";
        hot = false;
      }
      out.push({
        claim: claim, room: room, verb: verb, obj: obj, href: href, ts: ts,
        src: src, live: !!live, hot: hot, facts: facts, text: text, id: id
      });
    });
    return out;
  }

  /* 8bit agent layer: presence is existence, recent is motion. Cap trims cards, never seats.
     Unify still unions recent-only claims on the roster; dramas do not invent unseated speech. */
  function scenesOf(presence, recent, now) {
    var PA = g.PIXEL_AGENTS;
    if (!PA || !PA.classify || !PA.dramas || !PA.normalize) return [];
    var read = PA.classify({
      roster: presence || [],
      rows: PA.normalize(recent || []),
      now: now
    });
    return PA.dramas(read.agents, { cap: 8 });
  }

  function loadJSON(url) {
    return fetch(url, { cache: "no-store", credentials: "omit" }).then(function (r) {
      return r.ok ? r.json() : null;
    }).catch(function () { return null; });
  }
  function mapGitAuthor(name, login) {
    var a = up(String(name || "").replace(/[_-]+/g, " "));
    if (GIT_MAP[a]) return GIT_MAP[a];
    var b = up(String(login || "").replace(/[^A-Z0-9]/g, ""));
    return GIT_MAP[b] || "";
  }
  function gitPulse() {
    var hdr = { Accept: "application/vnd.github+json" };
    var base = "https://api.github.com/repos/woahwhattheheck/commons";
    function jsonOrErr(r) {
      if (!r.ok) return { _err: r.status };
      return r.json();
    }
    return Promise.all([
      fetch(base + "/commits/main", { cache: "no-store", credentials: "omit", headers: hdr }).then(jsonOrErr),
      fetch(base + "/commits?sha=main&per_page=25", { cache: "no-store", credentials: "omit", headers: hdr }).then(jsonOrErr)
    ]).then(function (pack) {
      var head = pack[0];
      var rows = pack[1];
      if (head && head._err && rows && rows._err) {
        return { by: {}, line: "GitHub API " + (head._err || rows._err) + " — last path not guessed" };
      }
      if (!Array.isArray(rows)) rows = [];
      var by = {};
      var unmapped = [];
      var seenUn = {};
      var need = [];
      function consider(c) {
        if (!c || c._err) return;
        var name = c.commit && c.commit.author && c.commit.author.name;
        var login = c.author && c.author.login;
        var who = mapGitAuthor(name, login);
        var raw = String(name || login || "").trim();
        if (!who) {
          var key = up(raw).replace(/[^A-Z0-9]+/g, "") || "UNKNOWN";
          if (!seenUn[key]) { seenUn[key] = true; unmapped.push(raw || key); }
          return;
        }
        if (by[who]) return;
        var paths = (c.files || []).map(function (f) { return f.filename; });
        if (paths[0]) {
          by[who] = {
            path: paths[0],
            ts: c.commit && c.commit.author && c.commit.author.date,
            url: c.html_url || ""
          };
        } else if (c.sha) {
          need.push({
            who: who,
            sha: c.sha,
            ts: c.commit && c.commit.author && c.commit.author.date,
            url: c.html_url || ""
          });
        }
      }
      consider(head);
      rows.forEach(consider);
      var fetchWho = {};
      var jobs = [];
      need.forEach(function (j) {
        if (by[j.who] || fetchWho[j.who]) return;
        fetchWho[j.who] = true;
        jobs.push(j);
      });
      function finish() {
        var mapped = Object.keys(by);
        var bits = ["union floor", "git first-path, not guessed"];
        if (mapped.length) {
          bits.push("mapped " + mapped.map(function (k) { return k + "→" + by[k].path; }).slice(0, 6).join(", "));
        }
        if (unmapped.length) {
          bits.push("unmapped stay unmapped: " + unmapped.join(", "));
        }
        return { by: by, line: bits.join(" · ") };
      }
      if (!jobs.length) return finish();
      return Promise.all(jobs.slice(0, 12).map(function (j) {
        return fetch(base + "/commits/" + j.sha, {
          cache: "no-store", credentials: "omit", headers: hdr
        }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
      })).then(function (details) {
        details.forEach(function (c, i) {
          if (!c) return;
          var who = jobs[i].who;
          if (by[who]) return;
          var path = (c.files && c.files[0] && c.files[0].filename) || "";
          if (!path) return;
          by[who] = { path: path, ts: jobs[i].ts, url: jobs[i].url || c.html_url || "" };
        });
        return finish();
      });
    }).catch(function () {
      return { by: {}, line: "GitHub API unreachable from this tab — not invented" };
    });
  }
  function loadHearts(index) {
    var names = (index && index.length) ? index.slice() : ["PLAYER2.json"];
    return Promise.all(names.map(function (fn) {
      var file = String(fn).indexOf(".json") >= 0 ? fn : fn + ".json";
      return loadJSON("./pixels/" + file);
    })).then(function (rows) {
      var hb = {};
      rows.forEach(function (row) {
        if (row && row.from) hb[up(row.from)] = row;
      });
      return hb;
    });
  }
  function obsWorkOf(snap) {
    if (!snap || !Array.isArray(snap.work_map)) return [];
    return snap.work_map.map(function (row) {
      var paths = row && Array.isArray(row.claimed_paths) ? row.claimed_paths : [];
      return {
        claim: row && row.owner_claim,
        path: paths[0] || "",
        verb: String((row && row.state) || "observed work").toLowerCase(),
        ts: snap.now || "",
        text: row && row.objective ? String(row.objective).slice(0, 180) : "",
        state: (row && row.state) || ""
      };
    }).filter(function (r) { return r.claim; });
  }

  function drawRoom(ctx, room, s, nHot, nQuiet, extra) {
    ctx.fillStyle = "#12160f";
    ctx.fillRect(room.x * s, room.y * s, room.w * s, room.h * s);
    ctx.strokeStyle = "#2a3328";
    ctx.strokeRect(room.x * s + 0.5, room.y * s + 0.5, room.w * s - 1, room.h * s - 1);
    ctx.fillStyle = "#3a4538";
    ctx.fillRect((room.x + 12) * s, (room.y + room.h - 18) * s, 28 * s, 5 * s);
    ctx.fillStyle = "#8a9a82";
    ctx.font = (7 * s) + "px ui-monospace, Menlo, monospace";
    ctx.textAlign = "left";
    ctx.fillText(room.id + "  " + nHot + " active · " + nQuiet + " quiet", (room.x + 4) * s, (room.y + 10) * s);
    if (extra) {
      ctx.fillStyle = "#c8ccd4";
      ctx.fillText("+" + extra, (room.x + room.w - 22) * s, (room.y + 10) * s);
    }
  }
  function pickFrame(frames, now, still) {
    if (!frames || !frames.length) return null;
    if (still || frames.length < 2) return frames[0];
    return frames[Math.floor((now || 0) / 180) % frames.length];
  }
  function drawDude(ctx, a, px, py, s, now, still) {
    var PA = g.PIXEL_AGENTS;
    if (PA && PA.renderSprite && PA.SPRITES && PA.PALETTES) {
      var idx = hash(a.claim) % PA.PALETTES.length;
      var pal = PA.PALETTES[idx];
      var set = (idx % 2 && PA.SPRITES_F) ? PA.SPRITES_F : PA.SPRITES;
      var frames = set[poseOf(a)] || PA.SPRITES.idle;
      var frame = pickFrame(frames, now, still);
      if (frame) {
        PA.renderSprite(ctx, frame, px, py, Math.max(1, Math.round(s)), pal, false);
        if (a.verb === "quiet" || a.verb === "leaving") {
          ctx.fillStyle = "rgba(13,16,14,0.45)";
          ctx.fillRect(px, py, 12 * s, 16 * s);
        }
        return;
      }
    }
    ctx.fillStyle = a.live ? "#7ec8a3" : "#6cbe7a";
    ctx.fillRect(px, py, 12 * s, 16 * s);
  }
  function drawBubble(ctx, px, py, s, line) {
    var t = String(line || "").slice(0, 36);
    if (!t) return;
    ctx.font = (5 * s) + "px ui-monospace, Menlo, monospace";
    var w = Math.min(160 * s, ctx.measureText(t).width + 8 * s);
    ctx.fillStyle = "#e8e6df";
    ctx.fillRect(px, py - 12 * s, w, 10 * s);
    ctx.fillStyle = "#0a0a0b";
    ctx.fillText(t, px + 3 * s, py - 5 * s);
  }

  function mount(opts) {
    var canvas = opts.canvas;
    var panel = opts.panel;
    var status = opts.status;
    var list = opts.list;
    var factsEl = opts.facts;
    var obsEl = opts.obs;
    var dramasEl = opts.dramas;
    var roomsEl = opts.rooms;
    var s = opts.scale || 1.5;
    var reduce = !!(g.matchMedia && g.matchMedia("(prefers-reduced-motion: reduce)").matches);
    var walk = false;
    canvas.width = 776 * s;
    canvas.height = 456 * s;
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    var agents = [];
    var scenes = [];
    var lastPresence = [];
    var lastRecent = [];
    var sel = null;
    var roomFilter = "";
    var peers = {};
    var gitLine = "reading GitHub last 25…";
    var pos = {};
    var keys = {};
    var pad = { x: 0, y: 0 };
    var visitor = { x: 220 * s, y: 360 * s, yaw: 0, speed: 0 };
    var lastTick = (typeof performance !== "undefined" ? performance.now() : Date.now());
    var inject = null;

    function pressed(btn, on) {
      if (!btn) return;
      btn.className = on ? "on" : "";
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    }
    function bindPad(btn, x, y) {
      if (!btn) return;
      function down(ev) { pad.x = x; pad.y = y; if (ev.preventDefault) ev.preventDefault(); }
      function up() { pad.x = 0; pad.y = 0; }
      btn.addEventListener("pointerdown", down);
      btn.addEventListener("pointerup", up);
      btn.addEventListener("pointercancel", up);
      btn.addEventListener("pointerleave", up);
    }
    if (opts.pad) {
      bindPad(opts.pad.w, 0, -1);
      bindPad(opts.pad.a, -1, 0);
      bindPad(opts.pad.s, 0, 1);
      bindPad(opts.pad.d, 1, 0);
    }

    g.addEventListener("keydown", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      var t = ev.target && ev.target.tagName;
      if (t === "INPUT" || t === "TEXTAREA") return;
      if (ev.code === "Escape") {
        roomFilter = "";
        sel = null;
        show(null);
        roster();
        paintRooms();
        paint();
        return;
      }
      if (/^Key[WASD]$/.test(ev.code) || /^Arrow/.test(ev.code)) {
        keys[ev.code] = true;
        ev.preventDefault();
      }
    });
    g.addEventListener("keyup", function (ev) { keys[ev.code] = false; });
    g.addEventListener("blur", function () { keys = {}; });

    g.__controlsTest = {
      getYaw: function () { return visitor.yaw; },
      getSpeed: function () { return visitor.speed; },
      setKeys: function (codes) { inject = codes && codes.length ? codes.slice() : null; },
      getX: function () { return visitor.x; },
      getY: function () { return visitor.y; }
    };

    if (opts.walkBtn) {
      opts.walkBtn.setAttribute("aria-pressed", "false");
      opts.walkBtn.addEventListener("click", function () {
        walk = true;
        pressed(opts.walkBtn, true);
        pressed(opts.floorBtn, false);
      });
    }
    if (opts.floorBtn) {
      opts.floorBtn.setAttribute("aria-pressed", "true");
      opts.floorBtn.addEventListener("click", function () {
        walk = false;
        pressed(opts.floorBtn, true);
        pressed(opts.walkBtn, false);
      });
    }

    function held(code) {
      if (inject) return inject.indexOf(code) >= 0;
      return !!keys[code];
    }
    function stepVisitor(dt) {
      var ax = pad.x, ay = pad.y;
      if (held("KeyA") || held("ArrowLeft")) ax -= 1;
      if (held("KeyD") || held("ArrowRight")) ax += 1;
      if (held("KeyW") || held("ArrowUp")) ay -= 1;
      if (held("KeyS") || held("ArrowDown")) ay += 1;
      var mag = Math.hypot(ax, ay);
      if (mag > 1) { ax /= mag; ay /= mag; }
      var sp = 110 * s;
      visitor.speed = Math.hypot(ax, ay) * sp;
      visitor.x = Math.max(8 * s, Math.min((776 - 20) * s, visitor.x + ax * sp * dt));
      visitor.y = Math.max(8 * s, Math.min((456 - 24) * s, visitor.y + ay * sp * dt));
      if (visitor.speed > 1) visitor.yaw = Math.atan2(-ax, -ay);
      else if (held("KeyA") || held("ArrowLeft")) visitor.yaw += 2.6 * dt;
      else if (held("KeyD") || held("ArrowRight")) visitor.yaw -= 2.6 * dt;
    }

    function spotsFor(list) {
      var bucket = {};
      list.forEach(function (a) {
        (bucket[a.room] || (bucket[a.room] = [])).push(a);
      });
      var spots = {};
      var overflow = {};
      ROOMS.forEach(function (room) {
        var slots = bucket[room.id] || [];
        var hot = slots.filter(function (a) { return a.hot || a.live; });
        var quiet = slots.filter(function (a) { return !(a.hot || a.live); });
        hot.slice(0, 12).forEach(function (a, n) {
          spots[a.claim] = {
            x: (room.x + 8 + (n % 6) * 28) * s,
            y: (room.y + 16 + Math.floor(n / 6) * 28) * s,
            hot: true, a: a
          };
        });
        if (hot.length > 12) overflow[room.id] = hot.length - 12;
        quiet.slice(0, 24).forEach(function (a, n) {
          spots[a.claim] = {
            x: (room.x + 8 + (n % 12) * 14) * s,
            y: (room.y + 92) * s,
            hot: false, a: a
          };
        });
      });
      return { bucket: bucket, spots: spots, overflow: overflow };
    }

    function paint() {
      var now = typeof performance !== "undefined" ? performance.now() : Date.now();
      var dt = Math.min(0.1, (now - lastTick) / 1000);
      lastTick = now;
      stepVisitor(dt);
      ctx.fillStyle = "#0d100e";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      var laid = spotsFor(agents);
      ROOMS.forEach(function (room) {
        var slots = laid.bucket[room.id] || [];
        var hot = slots.filter(function (a) { return a.hot || a.live; });
        var quiet = slots.filter(function (a) { return !(a.hot || a.live); });
        drawRoom(ctx, room, s, hot.length, quiet.length, laid.overflow[room.id] || 0);
      });
      var still = reduce || !walk;
      agents.forEach(function (a) {
        var t = laid.spots[a.claim];
        if (!t) return;
        var cur = pos[a.claim] || { x: t.x, y: t.y };
        if (walk && !reduce) {
          cur.x += (t.x - cur.x) * 0.18;
          cur.y += (t.y - cur.y) * 0.18;
        } else {
          cur.x = t.x; cur.y = t.y;
        }
        pos[a.claim] = cur;
        a._px = cur.x; a._py = cur.y; a._hotDraw = t.hot;
        if (t.hot) {
          drawDude(ctx, a, cur.x, cur.y, s, now, still);
          ctx.fillStyle = "#c8c8c0";
          ctx.font = (4 * s) + "px ui-monospace, Menlo, monospace";
          ctx.fillText(String(a.claim).slice(0, 8), cur.x, cur.y + 17 * s);
          if (sel === a.claim) {
            ctx.strokeStyle = "#c8ccd4";
            ctx.strokeRect(cur.x - s, cur.y - s, 14 * s, 18 * s);
            drawBubble(ctx, cur.x, cur.y, s, a.text || a.verb);
          }
        } else {
          ctx.fillStyle = a.verb === "leaving" ? "#3a3a40" : "#4a5a48";
          ctx.fillRect(cur.x, cur.y, 5 * s, 5 * s);
        }
      });
      var PA = g.PIXEL_AGENTS;
      if (PA && PA.renderSprite && PA.SPRITES) {
        var youFrame = pickFrame(PA.SPRITES.idle, now, still);
        if (youFrame) PA.renderSprite(ctx, youFrame, visitor.x, visitor.y, Math.max(1, Math.round(s)), (PA.PALETTES && PA.PALETTES[0]) || null, false);
        else {
          ctx.fillStyle = "#7ec8a3";
          ctx.fillRect(visitor.x, visitor.y, 12 * s, 16 * s);
        }
      } else {
        ctx.fillStyle = "#7ec8a3";
        ctx.fillRect(visitor.x, visitor.y, 12 * s, 16 * s);
      }
      ctx.fillStyle = "#c8ccd4";
      ctx.font = (4 * s) + "px ui-monospace, Menlo, monospace";
      ctx.fillText("YOU · play", visitor.x - 4 * s, visitor.y + 18 * s);
    }

    function show(a) {
      if (!panel) return;
      if (!a) {
        panel.innerHTML = "<span class=\"quiet\">Click a sprite, pick a roster row, or use the room chips. Room = last real door, ping mailbox, committed heartbeat, git first-path, observatory work, or this browser tab. WASD YOU is play, not a fact. Escape clears the room filter.</span>";
        return;
      }
      var bits = [
        "<span class=\"who\">" + esc(a.claim) + "</span> ",
        "<span class=\"st\">" + esc(a.verb) + "</span> ",
        "<span class=\"words\">" + esc(a.text || a.obj || "(no line)") + "</span> ",
        "<span class=\"quiet\">src " + esc(a.src) + "</span>"
      ];
      if (a.href) bits.push(' <a href="' + esc(a.href) + '">open</a>');
      if (a.id) bits.push(' <a href="' + esc(replyOf(a.id)) + '">reply</a>');
      if (a.facts && a.facts.length) bits.push("<div class=\"quiet\">" + a.facts.map(esc).join(" · ") + "</div>");
      panel.innerHTML = bits.join("");
    }
    function visibleAgents() {
      if (!roomFilter) return agents;
      return agents.filter(function (a) { return a.room === roomFilter; });
    }
    function roster() {
      if (!list) return;
      list.innerHTML = "";
      visibleAgents().slice().sort(function (x, y) {
        if (!!y.hot !== !!x.hot) return y.hot ? 1 : -1;
        return x.claim < y.claim ? -1 : 1;
      }).forEach(function (a) {
        var li = document.createElement("li");
        li.innerHTML = "<button type=\"button\" class=\"pick\" data-claim=\"" + esc(a.claim) + "\" aria-pressed=\"" +
          (sel === a.claim ? "true" : "false") + "\"><span class=\"c\">" +
          esc(a.claim) + "</span> <span class=\"s\">" + esc(a.room) + " · " + esc(a.verb) + "</span><span class=\"l\">" +
          esc((a.text || a.obj || "").slice(0, 80)) + "</span></button>";
        list.appendChild(li);
      });
    }
    function paintRooms() {
      if (!roomsEl) return;
      var ids = ["ALL"].concat(ROOMS.map(function (r) { return r.id; }));
      roomsEl.innerHTML = ids.map(function (id) {
        var on = (id === "ALL" && !roomFilter) || id === roomFilter;
        var label = id === "ALL" ? "all rooms" : (id === "BIT" ? "8BIT" : id);
        return "<button type=\"button\" class=\"chip" + (on ? " on" : "") + "\" data-room=\"" + id +
          "\" aria-pressed=\"" + (on ? "true" : "false") + "\">" + label + "</button>";
      }).join("");
    }
    function paintDramas() {
      if (!dramasEl) return;
      if (!g.PIXEL_AGENTS || !g.PIXEL_AGENTS.dramas) {
        dramasEl.innerHTML = "<li class=\"quiet\">8bit.js agent layer not mounted. 8bit.html and 8walk.html still own that runtime.</li>";
        return;
      }
      if (!scenes.length) {
        dramasEl.innerHTML = "<li class=\"quiet\">no speaking scenes in this read of recent.json — quiet seats stay</li>";
        return;
      }
      dramasEl.innerHTML = scenes.map(function (sc) {
        var who = "<button type=\"button\" class=\"pick\" data-claim=\"" + esc(sc.claims[0]) + "\"><span class=\"c\">" +
          esc(sc.claims[0]) + "</span> <span class=\"s\">" + esc(sc.verb) + "</span></button>";
        if (sc.kind === "pair") {
          who += " <button type=\"button\" class=\"pick\" data-claim=\"" + esc(sc.claims[1]) + "\"><span class=\"c\">" +
            esc(sc.claims[1]) + "</span></button>";
        }
        var extra = sc.kind === "pair" && sc.lines[1]
          ? "<span class=\"l2\">" + esc(String(sc.lines[1]).slice(0, 96)) + "</span>"
          : "";
        var link = sc.ids && sc.ids[0] && sc.hrefs && sc.hrefs[0]
          ? " <a href=\"" + esc(sc.hrefs[0]) + "\">" + esc(sc.ids[0]) + "</a>"
          : "";
        var reply = sc.ids && sc.ids[0]
          ? " <a href=\"" + esc(replyOf(sc.ids[0])) + "\">reply</a>"
          : "";
        return "<li>" + who + "<span class=\"l\">" + esc(String(sc.lines[0] || "").slice(0, 96)) + "</span>" + extra + link + reply + "</li>";
      }).join("");
    }
    function hit(mx, my) {
      var i, a, w, h;
      for (i = 0; i < agents.length; i++) {
        a = agents[i];
        if (a._px == null) continue;
        w = a._hotDraw ? 12 * s : 5 * s;
        h = a._hotDraw ? 16 * s : 5 * s;
        if (mx >= a._px && mx <= a._px + w && my >= a._py && my <= a._py + h) return a;
      }
      return null;
    }
    function hitRoom(mx, my) {
      var i, r;
      for (i = 0; i < ROOMS.length; i++) {
        r = ROOMS[i];
        if (mx >= r.x * s && mx <= (r.x + r.w) * s && my >= r.y * s && my <= (r.y + r.h) * s) return r.id;
      }
      return "";
    }
    canvas.addEventListener("click", function (ev) {
      var r = canvas.getBoundingClientRect();
      var mx = (ev.clientX - r.left) * (canvas.width / r.width);
      var my = (ev.clientY - r.top) * (canvas.height / r.height);
      var a = hit(mx, my);
      if (a) {
        sel = a.claim;
        show(a);
        roster();
        paint();
        return;
      }
      sel = null;
      roomFilter = hitRoom(mx, my);
      show(null);
      roster();
      paintRooms();
      paint();
    });
    if (list) {
      list.addEventListener("click", function (ev) {
        var b = ev.target.closest ? ev.target.closest(".pick") : null;
        if (!b) return;
        sel = b.getAttribute("data-claim");
        var a = agents.filter(function (x) { return x.claim === sel; })[0];
        show(a);
        roster();
        paint();
      });
    }
    if (roomsEl) {
      roomsEl.addEventListener("click", function (ev) {
        var b = ev.target.closest ? ev.target.closest("[data-room]") : null;
        if (!b) return;
        var id = b.getAttribute("data-room");
        roomFilter = id === "ALL" ? "" : id;
        sel = null;
        show(null);
        roster();
        paintRooms();
        paint();
      });
    }
    if (dramasEl) {
      dramasEl.addEventListener("click", function (ev) {
        var b = ev.target.closest ? ev.target.closest(".pick") : null;
        if (!b) return;
        sel = b.getAttribute("data-claim");
        var a = agents.filter(function (x) { return x.claim === sel; })[0];
        show(a);
        roster();
        paint();
      });
    }

    function merge() {
      Promise.all([
        loadJSON("./presence.json"),
        loadJSON("./recent.json"),
        loadJSON("./ping/last.json"),
        loadJSON("./lastseen.json"),
        loadJSON("./pixels/index.json"),
        gitPulse(),
        loadJSON("./observatory.json")
      ]).then(function (pack) {
        var git = pack[5] || { by: {}, line: "" };
        gitLine = git.line || gitLine;
        if (factsEl) factsEl.textContent = gitLine + " · visitor IP is not on this static board";
        var snap = pack[6];
        if (obsEl) {
          var lines = snap && snap.cockpit && snap.cockpit.lines ? snap.cockpit.lines : [];
          var bakeSha = snap && snap.head && snap.head.sha ? String(snap.head.sha).slice(0, 12) : "none";
          var cash = snap && snap.economy ? snap.economy.collected_cash_usd : "?";
          obsEl.textContent = "observatory bake " + bakeSha + " · cash USD " + cash + " · " + (lines[0] || "no cockpit") + " · bake may lag HEAD";
        }
        return loadHearts(pack[4]).then(function (hb) {
          if (g.COMMONS_HERE && g.COMMONS_HERE.from) peers[up(g.COMMONS_HERE.from)] = g.COMMONS_HERE;
          Object.assign(peers, g.COMMONS_HERE_PEERS || {});
          lastPresence = pack[0] || [];
          lastRecent = pack[1] || [];
          agents = classify(lastPresence, lastRecent, pack[2] || {}, pack[3] || [], hb, peers, git.by || {}, obsWorkOf(snap));
          scenes = scenesOf(lastPresence, lastRecent);
          if (status) {
            var liveN = agents.filter(function (a) { return a.live; }).length;
            var hotN = agents.filter(function (a) { return a.hot; }).length;
            status.textContent = agents.length + " claims · " + hotN + " with a fresh fact · " + liveN +
              " in this browser · " + scenes.length + " 8bit scenes · union of presence/recent/hearts/git-first-path/observatory · old floors preserved";
          }
          roster();
          paintRooms();
          paintDramas();
          paint();
          if (sel) {
            var a = agents.filter(function (x) { return x.claim === sel; })[0];
            if (a) show(a);
          }
        });
      });
    }

    paintRooms();
    g.addEventListener("commons-here", merge);
    g.addEventListener("commons-here-peers", merge);
    merge();
    g.setInterval(function () { merge(); }, 20000);
    g.setInterval(paint, reduce ? 250 : 50);
    return { refresh: merge, classify: classify, ROOMS: ROOMS, scenesOf: scenesOf };
  }

  g.PIXEL_UNIFY = {
    mount: mount,
    classify: classify,
    ROOMS: ROOMS,
    GIT_MAP: GIT_MAP,
    PLACE: PLACE,
    roomOfPath: roomOfPath,
    mapGitAuthor: mapGitAuthor,
    ownLine: ownLine,
    scenesOf: scenesOf,
    replyOf: replyOf
  };
})(window);
