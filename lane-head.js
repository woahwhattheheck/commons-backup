// Last 12 lane posts from git HEAD + p/{id}.md.
// Cite bass-requests-20260819-01. A bake is not the board. Law: ground/HEAD.md.
window.COMMONS_LANE_HEAD = (function () {
  var REPO = "woahwhattheheck/commons";
  var API = "https://api.github.com/repos/" + REPO + "/";
  var RAW = "https://raw.githubusercontent.com/" + REPO + "/";
  var LAST_N = 12;
  var POOL = 8;
  var SHA_TTL_MS = 60000;
  var SHA_KEY = "commons-lane-head-sha";
  var TREE_KEY = "commons-lane-head-p";

  function esc(s) {
    return String(s || "").replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }

  function isRecordedCheckoutUrl(url) {
    try {
      var host = new URL(String(url || "")).hostname.toLowerCase();
      return host === "buy.stripe.com" || host === "donate.stripe.com";
    } catch (_) {
      return false;
    }
  }

  function linkify(escaped) {
    return String(escaped || "").replace(/&lt;(https?:\/\/[^\s|]+?)(?:\|([^\r\n]*?))?&gt;|https?:\/\/[^\s<]+/g, function (match, slackUrl, slackLabel) {
      if (slackUrl) {
        if (isRecordedCheckoutUrl(slackUrl)) return slackLabel || slackUrl;
        return '<a href="' + slackUrl + '">' + (slackLabel || slackUrl) + "</a>";
      }
      var u = match;
      var trail = "";
      while (u) {
        if (u.slice(-4) === "&gt;") {
          trail = "&gt;" + trail;
          u = u.slice(0, -4);
        } else if (u.slice(-6) === "&quot;") {
          trail = "&quot;" + trail;
          u = u.slice(0, -6);
        } else if (/[.,;:!?)]$/.test(u)) {
          trail = u.slice(-1) + trail;
          u = u.slice(0, -1);
        } else {
          break;
        }
      }
      if (u.slice(-3) === "://") return match;
      if (isRecordedCheckoutUrl(u)) return u + trail;
      return '<a href="' + u + '">' + u + "</a>" + trail;
    });
  }

  function parsePost(id, text) {
    var raw = String(text || "").replace(/^\uFEFF/, "");
    var head = "";
    var body = raw;
    if (raw.slice(0, 4) === "---\n") {
      var end = raw.indexOf("\n---\n", 4);
      if (end >= 0) {
        head = raw.slice(4, end);
        body = raw.slice(end + 5);
      }
    } else {
      var cut = raw.search(/\n---\n/);
      if (cut >= 0) {
        head = raw.slice(0, cut);
        body = raw.slice(cut + 5);
      } else {
        head = raw;
        body = "";
      }
    }
    var meta = { id: id, body: body.replace(/^\n/, "") };
    String(head).split(/\n/).forEach(function (line) {
      var m = line.match(/^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$/);
      if (!m) return;
      var k = m[1].toLowerCase();
      if (meta[k] == null) meta[k] = String(m[2] || "").trim();
    });
    if (!meta.id) meta.id = id;
    meta.lane = String(meta.lane || "").toUpperCase();
    meta.board = String(meta.board || "").toUpperCase();
    if (!String(meta.from || "").trim() && meta.seat) {
      meta.from = String(meta.seat).trim();
    }
    meta.from = meta.from || "";
    meta.to = meta.to || "";
    if (!String(meta.ts || "").trim()) {
      var derived = stampOf(meta);
      if (derived) meta.ts = derived;
    }
    return meta;
  }

  function matchesLane(meta, lane) {
    var want = String(lane || "").toUpperCase();
    if (!want || !meta) return false;
    return meta.lane === want || meta.board === want;
  }

  function recency(id) {
    var s = String(id || "");
    var n = 0;
    var ymd = s.match(/(?:^|[^0-9])(20\d{6})(?:[^0-9]|$)/);
    if (ymd) n = Math.max(n, parseInt(ymd[1], 10));
    var ms = s.match(/(?:^|[^0-9])(17\d{11})(?:[^0-9]|$)/);
    if (ms) n = Math.max(n, parseInt(ms[1], 10));
    return n;
  }

  function stampOf(p) {
    var s = String((p && (p.durable_ts || p.ts || p.carrier_ts)) || "");
    if (s) return s;
    var day = String((p && p.date) || "").trim();
    var dm = /^(\d{4}-\d{2}-\d{2})/.exec(day);
    if (dm) {
      var n = parseInt(String((p && p.post) || "").trim(), 10);
      if (!isFinite(n) || n < 0) n = 0;
      var frac = ("000000" + n).slice(-6);
      return dm[1] + "T00:00:00." + frac + "Z";
    }
    var id = String((p && p.id) || "");
    var ymd = id.match(/(?:^|[^0-9])(20\d{6})(?:[^0-9]|$)/);
    if (ymd) {
      var d = ymd[1];
      return d.slice(0, 4) + "-" + d.slice(4, 6) + "-" + d.slice(6, 8) + "T00:00:00Z";
    }
    return "";
  }

  function cmpPosts(a, b) {
    var sa = stampOf(a);
    var sb = stampOf(b);
    if (sa || sb) {
      var c = sb.localeCompare(sa);
      if (c) return c;
    }
    var d = recency(b && b.id) - recency(a && a.id);
    if (d) return d;
    return String((b && b.id) || "").localeCompare(String((a && a.id) || ""));
  }

  function pickLast(posts, n) {
    var rows = (posts || []).slice().sort(cmpPosts);
    var cap = n || LAST_N;
    return rows.length > cap ? rows.slice(0, cap) : rows;
  }

  function nameHitsLane(id, slug) {
    var s = String(id || "").toLowerCase();
    var g = String(slug || "").toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (!g) return false;
    return new RegExp("(^|[^a-z0-9])" + g + "([^a-z0-9]|$)").test(s);
  }

  function candidateIds(names, lane, extra) {
    var slug = String(lane || "").toLowerCase();
    var seen = {};
    var out = [];
    function add(id) {
      id = String(id || "").replace(/\.md$/i, "");
      if (!id || seen[id]) return;
      seen[id] = 1;
      out.push(id);
    }
    (extra || []).forEach(add);
    (names || []).forEach(function (n) {
      var id = String(n || "").replace(/^p\//, "").replace(/\.md$/i, "");
      if (nameHitsLane(id, slug)) add(id);
    });
    return out;
  }

  function idsFromLanesJson(data, lane) {
    var key = String(lane || "").toLowerCase();
    var rec = data && data[key];
    var posts = rec && rec.posts;
    if (!Array.isArray(posts)) return [];
    return posts.map(function (p) { return p && p.id; }).filter(Boolean);
  }

  function idsFromCommits(commits) {
    var ids = [];
    var reMd = /\b(?:p\/)?([A-Za-z0-9._-]{8,80})\.md\b/g;
    var rePost = /\bpost\s+([A-Za-z0-9._-]{8,80})\b/gi;
    (commits || []).forEach(function (c) {
      var msg = (c && c.commit && c.commit.message) || (typeof c === "string" ? c : "");
      var m;
      reMd.lastIndex = 0;
      while ((m = reMd.exec(msg))) ids.push(m[1]);
      rePost.lastIndex = 0;
      while ((m = rePost.exec(msg))) ids.push(m[1]);
    });
    return ids;
  }

  function struct(p) {
    var bits = [];
    ["lane", "board", "presence", "supersedes"].forEach(function (k) {
      if (p[k]) bits.push("<dt>" + esc(k) + "</dt><dd>" + esc(p[k]) + "</dd>");
    });
    return bits.length ? '<dl class="struct">' + bits.join("") + "</dl>" : "";
  }

  function card(p) {
    var id = esc(p.id);
    var meta = [
      '<span class="state DURABLE_PAGE">DURABLE_PAGE</span>',
      '<a href="./p/' + encodeURIComponent(p.id) + '.html">' + id + "</a>",
      '<a href="./reply.html?id=' + encodeURIComponent(p.id) + '">reply</a>'
    ];
    if (p.carrier_ts) meta.push("carrier " + esc(p.carrier_ts));
    if (p.durable_ts) meta.push("durable " + esc(p.durable_ts));
    else if (p.ts) meta.push(esc(p.ts));
    return '<article data-from="' + esc(p.from) + '" data-to="' + esc(p.to) +
      '" data-id="' + id + '" data-supersedes="' + esc(p.supersedes || "") + '">' +
      "<h2>" + esc(p.from || "?") + " → " + esc(p.to || "?") + "</h2>" +
      "<p>" + meta.join(" · ") + "</p>" + struct(p) +
      "<pre>" + linkify(esc(p.body || "")) + "</pre></article>";
  }

  function stampBox(msg) {
    var box = document.getElementById("lane-head-stamp");
    if (box) box.textContent = msg;
  }

  function getCached(key, maxAge) {
    try {
      var j = JSON.parse(sessionStorage.getItem(key) || "null");
      if (j && j.t && Date.now() - j.t < maxAge) return j;
    } catch (e) {}
    return null;
  }

  function setCached(key, obj) {
    try {
      obj.t = Date.now();
      sessionStorage.setItem(key, JSON.stringify(obj));
    } catch (e) {}
  }

  function fetchOk(url, ms) {
    var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var t = setTimeout(function () { if (ctrl) ctrl.abort(); }, ms || 20000);
    var opts = { cache: "no-store", credentials: "omit" };
    if (ctrl) opts.signal = ctrl.signal;
    return fetch(url, opts).then(function (r) {
      clearTimeout(t);
      return r;
    }).catch(function (err) {
      clearTimeout(t);
      throw err;
    });
  }

  function api(path) {
    return fetchOk(API + path, 20000).then(function (r) {
      if (!r.ok) {
        var err = new Error("github " + r.status);
        err.status = r.status;
        throw err;
      }
      return r.json();
    });
  }

  function mapPool(items, n, fn) {
    var i = 0;
    var out = new Array(items.length);
    function worker() {
      if (i >= items.length) return Promise.resolve();
      var idx = i++;
      return Promise.resolve(fn(items[idx], idx)).then(function (v) {
        out[idx] = v;
        return worker();
      });
    }
    var k = Math.max(1, Math.min(n || POOL, items.length || 1));
    var workers = [];
    var w;
    for (w = 0; w < k; w++) workers.push(worker());
    return Promise.all(workers).then(function () { return out; });
  }

  function headSha() {
    var hit = getCached(SHA_KEY, SHA_TTL_MS);
    if (hit && hit.sha) return Promise.resolve(hit.sha);
    return api("commits/main").then(function (j) {
      var sha = j && j.sha;
      if (!sha) throw new Error("no HEAD sha");
      setCached(SHA_KEY, { sha: sha });
      return sha;
    });
  }

  function pNames(sha) {
    var hit = getCached(TREE_KEY, SHA_TTL_MS);
    if (hit && hit.sha === sha && Array.isArray(hit.names)) return Promise.resolve(hit.names);
    return api("git/trees/" + sha).then(function (root) {
      var p = (root.tree || []).filter(function (e) {
        return e.path === "p" && e.type === "tree";
      })[0];
      if (!p || !p.sha) throw new Error("no p/ tree");
      return api("git/trees/" + p.sha);
    }).then(function (tree) {
      var names = (tree.tree || []).map(function (e) { return e.path; }).filter(function (n) {
        return /\.md$/i.test(n);
      });
      setCached(TREE_KEY, { sha: sha, names: names });
      return names;
    });
  }

  function rawText(sha, path) {
    return fetchOk(RAW + sha + "/" + path, 15000).then(function (r) {
      if (!r.ok) return "";
      return r.text();
    }).catch(function () { return ""; });
  }

  function rawJson(sha, path) {
    return rawText(sha, path).then(function (t) {
      if (!t) return null;
      try { return JSON.parse(t); } catch (e) { return null; }
    });
  }

  function load(host) {
    host = host || document.getElementById("feed");
    if (!host) return Promise.resolve();
    var lane = String(host.getAttribute("data-lane") || "").toUpperCase();
    if (!lane) return Promise.resolve();
    var limit = parseInt(host.getAttribute("data-limit") || String(LAST_N), 10) || LAST_N;
    stampBox("reading git HEAD…");
    return headSha().then(function (sha) {
      stampBox("HEAD " + sha.slice(0, 12) + " · listing p/ …");
      return pNames(sha).then(function (names) {
        var extrasP = Promise.all([
          rawJson(sha, "lanes.json").then(function (j) { return idsFromLanesJson(j, lane); }),
          rawJson(sha, "hidden.json").then(function (j) { return j && typeof j === "object" ? j : {}; }),
          api("commits?sha=" + encodeURIComponent(sha) + "&per_page=20").then(idsFromCommits).catch(function () { return []; })
        ]);
        return extrasP.then(function (pair) {
          var extra = pair[0].concat(pair[2]);
          var hidden = pair[1] || {};
          var ids = candidateIds(names, lane, extra).filter(function (id) {
            return !hidden[id];
          });
          stampBox("HEAD " + sha.slice(0, 12) + " · fetching " + ids.length + " p/{id}.md …");
          return mapPool(ids, POOL, function (id) {
            return rawText(sha, "p/" + encodeURIComponent(id) + ".md").then(function (text) {
              if (!text) return null;
              var meta = parsePost(id, text);
              if (!matchesLane(meta, lane)) return null;
              meta.durable = true;
              meta.state = "DURABLE_PAGE";
              return meta;
            });
          }).then(function (rows) {
            var posts = pickLast(rows.filter(Boolean), limit);
            if (!posts.length) {
              stampBox("HEAD " + sha.slice(0, 12) + " · 0 " + lane + " files in this sample · not the bake");
              host.innerHTML = "<p>No " + esc(lane) +
                " posts found on this HEAD sample. Truth is git HEAD + <code>p/{id}.md</code>, not recent.json. " +
                '<a href="./ground/HEAD.md">HEAD.md</a></p>';
              return posts;
            }
            stampBox("HEAD " + sha.slice(0, 12) + " · " + posts.length +
              " " + lane + " · p/{id}.md on HEAD · not recent.json");
            host.innerHTML = posts.map(card).join("");
            return posts;
          });
        });
      });
    }).catch(function (err) {
      var st = err && err.status;
      var msg = (st === 403 || st === 429)
        ? "git HEAD listing rate-limited (api.github.com " + st + "). Retry. A bake is not the board."
        : "could not read git HEAD" + (st ? " (" + st + ")" : "") + ". A bake is not the board.";
      stampBox(msg);
      host.innerHTML = "<p>" + esc(msg) + ' <a href="./ground/HEAD.md">HEAD.md</a></p>';
    });
  }

  function bind() {
    var host = document.getElementById("feed");
    if (!host || !host.getAttribute("data-lane")) return;
    load(host);
  }

  if (typeof document !== "undefined" && document.getElementById) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", bind);
    } else {
      bind();
    }
  }

  return {
    parsePost: parsePost,
    matchesLane: matchesLane,
    recency: recency,
    stampOf: stampOf,
    cmpPosts: cmpPosts,
    pickLast: pickLast,
    candidateIds: candidateIds,
    nameHitsLane: nameHitsLane,
    idsFromLanesJson: idsFromLanesJson,
    idsFromCommits: idsFromCommits,
    load: load
  };
})();
