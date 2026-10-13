// Pin reads to git HEAD when Pages 404s.
// Cite pin-redundancy-pages-raw-20260819-01 and bass-requests-built-20260819-01.
// Do not remint those ids. Law: ground/HEAD.md. A bake is not the board.
// Lazy: no GitHub API call until Pages misses or head.html / board union asks.
window.COMMONS_HEAD = (function () {
  var REPO = "woahwhattheheck/commons";
  var API = "https://api.github.com/repos/" + REPO + "/";
  var RAW = "https://raw.githubusercontent.com/" + REPO + "/";
  var JSD_MAIN = "https://cdn.jsdelivr.net/gh/" + REPO + "@main/";
  var SHA_TTL_MS = 60000;
  var SHA_KEY = "commons-lane-head-sha";
  var HEAD_BAKE_PATH = "head.json";
  var HEAD_SCHEMA = "commons-head-v1";
  var HEAD_MAX_AGE_MS = 20 * 60 * 1000;
  var POSTS_KEY = "commons-head-posts";
  var FRESH_KEY = "commons-head-fresh";
  var POOL = 4;
  var LAST_N = 12;
  var ASSET_V = "20260830a";

  function base() {
    return (typeof window !== "undefined" && window.COMMONS_BASE) || "./";
  }

  function cleanPath(p) {
    return String(p || "").replace(/^\.\//, "").replace(/^\/+/, "").split("?")[0];
  }

  function safePath(p) {
    p = cleanPath(p);
    if (!p || p.indexOf("..") >= 0 || !/^[A-Za-z0-9._/-]+$/.test(p)) return "";
    return p;
  }

  function rawUrl(path, sha) {
    return RAW + sha + "/" + cleanPath(path);
  }

  function jsdelivrMainUrl(path) {
    return JSD_MAIN + cleanPath(path);
  }

  function pagesUrl(path, bust) {
    var u = base() + cleanPath(path);
    // Commit-stable bust only. Date.now() made every visit a unique URL, so
    // HTTP cache could never warm. A string token (content hash / asset stamp)
    // stays cacheable across visits and changes when the bytes change.
    // Git short/full SHAs are not cache keys; map them to hub_pages.ASSET_V.
    if (bust && bust !== true) {
      var token = String(bust);
      if (/^[0-9a-f]{7,40}$/i.test(token) && !/^[0-9]{8}[a-z]$/i.test(token)) {
        token = ASSET_V;
      }
      u += (u.indexOf("?") >= 0 ? "&" : "?") + "v=" + encodeURIComponent(token);
    }
    return u;
  }

  function fetchCacheMode(url) {
    var u = String(url || "");
    if (u.indexOf("ntfy.sh/") >= 0 || u.indexOf("ntfy.") >= 0) return "no-store";
    // Store + revalidate: second visit can 304; a new commit is not treated as
    // already-seen HEAD.
    return "no-cache";
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
    var t = setTimeout(function () { if (ctrl) ctrl.abort(); }, ms || 15000);
    var opts = { cache: fetchCacheMode(url), credentials: "omit" };
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

  function parseBakedHead(j, now) {
    if (!j || j.schema !== HEAD_SCHEMA || !/^[0-9a-f]{40}$/.test(String(j.sha || ""))) return null;
    var observed = Date.parse(String(j.observed_at || ""));
    if (!isFinite(observed) || !String(j.source || "").trim()) return null;
    var measuredNow = Number(now == null ? Date.now() : now);
    if (observed - measuredNow > 5 * 60 * 1000) return null;
    var age = Math.max(0, measuredNow - observed);
    return {
      sha: String(j.sha),
      observed_at: String(j.observed_at),
      source: String(j.source),
      status: age <= HEAD_MAX_AGE_MS ? "BAKED_OBSERVED" : "BAKED_STALE",
      is_current: false,
      age_ms: age
    };
  }

  function apiHeadState() {
    return api("commits/main").then(function (j) {
      var sha = j && j.sha;
      // GitHub returns 40 hex characters. Keep abbreviated commit fixtures and
      // legacy enterprise responses usable; baked head.json remains strict-40.
      if (!/^[0-9a-f]{7,40}$/.test(String(sha || ""))) throw new Error("no HEAD sha");
      return { sha: sha, observed_at: "", source: "github-api", status: "REMOTE_CURRENT", is_current: true };
    });
  }

  function headState() {
    var hit = getCached(SHA_KEY, SHA_TTL_MS);
    if (hit && hit.sha && hit.status !== "BAKED_STALE") return Promise.resolve(hit);
    var stale = null;
    return fetchOk(pagesUrl(HEAD_BAKE_PATH), 8000).then(function (r) {
      if (!r || !r.ok || typeof r.json !== "function") return null;
      return r.json().then(function (j) { return parseBakedHead(j); });
    }).catch(function () { return null; }).then(function (baked) {
      if (baked && baked.status === "BAKED_OBSERVED") {
        setCached(SHA_KEY, baked);
        return baked;
      }
      stale = baked;
      return apiHeadState().then(function (current) {
        setCached(SHA_KEY, current);
        return current;
      }).catch(function (err) {
        if (stale) return stale;
        throw err;
      });
    });
  }

  function headSha() {
    return headState().then(function (state) {
      if (!state || state.status === "BAKED_STALE") {
        var err = new Error("baked HEAD observation is stale");
        err.stale = state || null;
        throw err;
      }
      return state.sha;
    });
  }

  function rawText(sha, path) {
    return fetchOk(rawUrl(path, sha), 15000).then(function (r) {
      if (!r.ok) return "";
      return r.text();
    }).catch(function () { return ""; });
  }

  function jsdelivrMainFallback(path, priorStatus) {
    return fetchOk(jsdelivrMainUrl(path), 15000).then(function (r3) {
      if (!r3 || !r3.ok) {
        var err = new Error("mirror " + ((r3 && r3.status) || priorStatus || 0));
        err.status = (r3 && r3.status) || priorStatus || 0;
        throw err;
      }
      var getHeader = r3.headers && typeof r3.headers.get === "function"
        ? function (name) { return r3.headers.get(name) || ""; }
        : function () { return ""; };
      return {
        response: r3,
        via: "jsdelivr-main",
        sha: "",
        providerVersion: getHeader("x-jsd-version"),
        providerVersionType: getHeader("x-jsd-version-type")
      };
    });
  }

  function rawFallback(path, pagesStatus) {
    return headSha().then(function (sha) {
      return fetchOk(rawUrl(path, sha), 15000).then(function (r2) {
        if (r2 && r2.ok) return { response: r2, via: "raw", sha: sha };
        return jsdelivrMainFallback(path, (r2 && r2.status) || pagesStatus);
      }, function (err) {
        return jsdelivrMainFallback(path, (err && err.status) || pagesStatus);
      });
    }, function (err) {
      return jsdelivrMainFallback(path, (err && err.status) || pagesStatus);
    });
  }

  function fetchPath(path, opts) {
    opts = opts || {};
    path = safePath(path);
    if (!path) return Promise.reject(new Error("empty or unsafe path"));
    var rel = pagesUrl(path, opts.bust);
    return fetchOk(rel, opts.ms || 15000).then(function (r) {
      if (r && r.ok) return { response: r, via: "pages", sha: "" };
      return rawFallback(path, r && r.status);
    }, function (err) {
      return rawFallback(path, err && err.status);
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
    return meta;
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

  // Last 24 p/{id}.md as baked by llms_txt.py from git HEAD, not recent.json.
  // Cite latch-fresh-20260819-01. Do not remint. Pages fresh.md can lag; pin to sha.
  // Offset clocks (…T03:08:30-07:00) must become Z or time-first string sort
  // puts HEAD behind a 09:52Z bake.
  function utcIso(raw) {
    raw = String(raw || "").trim();
    if (!raw) return "";
    var t = Date.parse(raw);
    if (isNaN(t)) return raw;
    try {
      var iso = new Date(t).toISOString();
      var frac = /\.(\d+)Z$/.exec(raw);
      if (frac) return iso.replace(/\.\d+Z$/, "." + frac[1] + "Z");
      return iso.replace(/\.\d+Z$/, "Z");
    } catch (e) {
      return raw;
    }
  }

  function parseFreshMd(text) {
    var rows = [];
    String(text || "").split(/\n/).forEach(function (line) {
      var m = line.match(/^- \[([^\]]+)\]\(([^)]+)\) — (.+)$/);
      if (!m) return;
      var id = m[1];
      var rest = m[3];
      var fromHdr = /\bfrom:\s*([A-Za-z][A-Za-z0-9_]*)/i.exec(rest);
      var toHdr = /\bto:\s*([A-Za-z][A-Za-z0-9_]*)/i.exec(rest);
      var tsHdr = /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))/.exec(rest);
      var parts = rest.split(" · ");
      var who = String(parts[0] || "").trim();
      if (who === "?") who = "";
      var from = String((fromHdr && fromHdr[1]) || who || "UNSEATED").toUpperCase();
      var to = String((toHdr && toHdr[1]) || "TABLE").toUpperCase();
      if (to === "COMMONS") to = "TABLE";
      var ts = utcIso((tsHdr && tsHdr[1]) || "");
      var boardHdr = /\bboard:\s*([A-Za-z][A-Za-z0-9_]*)/i.exec(rest);
      var laneHdr = /\blane:\s*([A-Za-z][A-Za-z0-9_]*)/i.exec(rest);
      var seatHdr = /\bseat:\s*([A-Za-z][A-Za-z0-9_]*)/i.exec(rest);
      if ((!from || from === "UNSEATED") && seatHdr) {
        from = String(seatHdr[1] || "").toUpperCase() || from;
      }
      var dateHdr = /\bdate:\s*(\d{4}-\d{2}-\d{2})/.exec(rest);
      var postHdr = /\bpost:\s*(\d+)/.exec(rest);
      if (!ts && dateHdr) {
        var n = parseInt(postHdr ? postHdr[1] : "0", 10);
        if (!isFinite(n) || n < 0) n = 0;
        if (n > 86399) n = 86399;
        var hh = ("0" + Math.floor(n / 3600)).slice(-2);
        var mm = ("0" + Math.floor((n % 3600) / 60)).slice(-2);
        var ss = ("0" + (n % 60)).slice(-2);
        ts = dateHdr[1] + "T" + hh + ":" + mm + ":" + ss + "Z";
      }
      var body = rest;
      var plain = rest.search(/\bPLAIN:\s*/i);
      if (plain >= 0) {
        body = rest.slice(plain).replace(/^\s*PLAIN:\s*/i, "");
      } else if (/\bfrom:\s*\w+.*\bto:\s*\w+.*\bid:\s*/i.test(rest)) {
        body = "";
      } else if (parts.length >= 2 && tsHdr && String(parts[1] || "").trim() === tsHdr[1]) {
        // Rows are "{who} · {ts} · {text}". The author and stamp already render
        // in the card header, so keeping them inside the body pushed the actual
        // text off the phone screen -- and on an empty-body row left the card
        // showing nothing but "? · <stamp>". Keep the text only.
        body = parts.slice(2).join(" · ");
      }
      var row = {
        id: id,
        from: from,
        to: to,
        ts: ts,
        durable_ts: ts,
        body: body,
        durable: true,
        state: "DURABLE_PAGE"
      };
      if (boardHdr) row.board = String(boardHdr[1] || "").toUpperCase();
      if (laneHdr) row.lane = String(laneHdr[1] || "").toUpperCase();
      rows.push(row);
    });
    return rows;
  }

  function pagesFresh() {
    return fetchOk(pagesUrl("fresh.md"), 15000).then(function (r) {
      return r && r.ok ? r.text() : "";
    }).then(function (fallback) {
      return parseFreshMd(fallback);
    }).catch(function () { return []; });
  }

  // Dir 9 first gate: last-24 catalog on ntfy, not the write topic.
  // ntfy 200 is mail. git HEAD + p/{id}.md is still the post.
  var NTFY_FRESH = [
    "https://ntfy.sh/woahwhattheheck-commons-fresh/json?poll=1",
    "https://ntfy.envs.net/woahwhattheheck-commons-fresh/json?poll=1",
    "https://ntfy.adminforge.de/woahwhattheheck-commons-fresh/json?poll=1",
    "https://ntfy.mzte.de/woahwhattheheck-commons-fresh/json?poll=1"
  ];

  function parseNtfyFresh(text) {
    var newest = [];
    String(text || "").split(/\n/).forEach(function (line) {
      line = String(line || "").trim();
      if (!line) return;
      var msg;
      try {
        msg = JSON.parse(line);
      } catch (e) {
        return;
      }
      if (msg && typeof msg.message === "string") {
        try {
          msg = JSON.parse(msg.message);
        } catch (e2) {
          return;
        }
      }
      if (!msg || msg.kind !== "commons-fresh" || !Array.isArray(msg.newest)) return;
      newest = msg.newest;
    });
    return (newest || []).map(function (p) {
      if (!p || !p.id) return null;
      var ts = utcIso(p.ts || "");
      return {
        id: String(p.id),
        from: String(p.from || "").toUpperCase() || "?",
        to: "TABLE",
        ts: ts,
        durable_ts: ts,
        body: String(p.plain || p.body || ""),
        durable: true,
        state: "DURABLE_PAGE"
      };
    }).filter(Boolean);
  }

  function ntfyFreshOne(url) {
    if (String(url || "").indexOf("woahwhattheheck-commons-board") >= 0) {
      return Promise.resolve([]);
    }
    return fetchOk(url, 8000).then(function (r) {
      return r && r.ok ? r.text() : "";
    }).then(function (text) {
      return parseNtfyFresh(text);
    }).catch(function () { return []; });
  }

  function ntfyFresh() {
    function walk(i) {
      if (i >= NTFY_FRESH.length) return Promise.resolve([]);
      return ntfyFreshOne(NTFY_FRESH[i]).then(function (rows) {
        if (rows && rows.length) return rows;
        return walk(i + 1);
      });
    }
    return walk(0);
  }

  function freshPosts() {
    var hit = getCached(FRESH_KEY, SHA_TTL_MS);
    if (hit && Array.isArray(hit.posts) && hit.posts.length && hit.via === "pin") {
      return Promise.resolve(hit.posts);
    }
    // Same-origin first. api.github.com can 403 / hang 20s; Bryce's refresh
    // must not wait. Sha-pin upgrades the cache when it arrives.
    var pinSettled = null;
    var pinP = headSha().then(function (sha) {
      return rawText(sha, "fresh.md").then(function (text) {
        return { sha: sha, rows: parseFreshMd(text) };
      });
    }).catch(function () {
      return { sha: "", rows: [] };
    });
    pinP.then(function (pin) { pinSettled = pin; });
    return pagesFresh().then(function (pages) {
      if (pinSettled && pinSettled.rows && pinSettled.rows.length) {
        setCached(FRESH_KEY, { sha: pinSettled.sha, posts: pinSettled.rows, via: "pin" });
        return pinSettled.rows;
      }
      if (pages.length) {
        setCached(FRESH_KEY, { sha: "", posts: pages, via: "pages" });
        pinP.then(function (pin) {
          if (pin.rows && pin.rows.length) {
            setCached(FRESH_KEY, { sha: pin.sha, posts: pin.rows, via: "pin" });
          }
        });
        return pages;
      }
      return pinP.then(function (pin) {
        if (pin.rows && pin.rows.length) {
          setCached(FRESH_KEY, { sha: pin.sha, posts: pin.rows, via: "pin" });
          return pin.rows;
        }
        return ntfyFresh().then(function (rows) {
          if (rows && rows.length) {
            setCached(FRESH_KEY, { sha: "", posts: rows, via: "ntfy" });
          }
          return rows || [];
        });
      });
    });
  }

  function recentHeadPosts() {
    var hit = getCached(POSTS_KEY, SHA_TTL_MS);
    if (hit && Array.isArray(hit.posts)) return Promise.resolve(hit.posts);
    return api("commits?sha=main&per_page=20").then(function (commits) {
      var sha = commits && commits[0] && commits[0].sha;
      if (!sha) throw new Error("no HEAD sha");
      setCached(SHA_KEY, {
        sha: sha, observed_at: "", source: "github-api", status: "REMOTE_CURRENT", is_current: true
      });
      var seen = {};
      var ids = [];
      idsFromCommits(commits).forEach(function (id) {
        if (!id || seen[id]) return;
        seen[id] = 1;
        ids.push(id);
      });
      ids = ids.slice(0, LAST_N);
      return mapPool(ids, POOL, function (id) {
        return rawText(sha, "p/" + encodeURIComponent(id) + ".md").then(function (text) {
          if (!text) return null;
          var meta = parsePost(id, text);
          meta.durable = true;
          meta.state = "DURABLE_PAGE";
          if (!meta.ts) meta.ts = meta.durable_ts || meta.carrier_ts || "";
          return meta;
        });
      }).then(function (rows) {
        var posts = rows.filter(Boolean);
        setCached(POSTS_KEY, { sha: sha, posts: posts });
        return posts;
      });
    });
  }

  function paintChip() {
    var host = document.getElementById("head-chip");
    if (!host) return;
    host.textContent = "measuring git HEAD…";
    headState().then(function (state) {
      if (state.status === "BAKED_STALE") throw new Error("stale bake");
      var label = state.is_current ? "CURRENT HEAD" : "BAKED HEAD OBSERVATION";
      host.innerHTML = label + ' <code>' + state.sha.slice(0, 12) + '</code> · sha-pinned raw · ' +
        state.source + ' · <a href="' +
        base() + 'ground/HEAD.md">HEAD.md</a>';
    }).catch(function (err) {
      var st = err && err.status;
      host.textContent = (st === 403 || st === 429)
        ? "git HEAD listing rate-limited (api.github.com " + st + "). Recipe: ground/HEAD.md"
        : "could not read git HEAD" + (st ? " (" + st + ")" : "") + ". A bake is not the board.";
    });
  }

  function pathFromSearch(search) {
    search = String(search || "");
    var raw = "";
    if (typeof URLSearchParams !== "undefined") {
      var q = search.charAt(0) === "?" ? search.slice(1) : search;
      raw = new URLSearchParams(q).get("path") || "";
    } else {
      var s = search.charAt(0) === "?" ? search.slice(1) : search;
      s.split("&").forEach(function (bit) {
        var kv = bit.split("=");
        if (decodeURIComponent(kv[0] || "") === "path") {
          raw = decodeURIComponent((kv.slice(1).join("=") || "").replace(/\+/g, " "));
        }
      });
    }
    return safePath(raw);
  }

  function bindDoor() {
    paintChip();
    var form = document.getElementById("head-open");
    var out = document.getElementById("head-body");
    if (!form || !out) return;
    function readFromHead(path) {
      path = safePath(path);
      if (!path) {
        out.textContent = "path refused (dots, spaces, or empty).";
        return;
      }
      out.textContent = "reading " + path + " from git HEAD…";
      headSha().then(function (sha) {
        return rawText(sha, path).then(function (text) {
          if (!text) {
            out.textContent = "HEAD " + sha.slice(0, 12) + " · " + path + " empty or 404. A 404 on Pages is not this.";
            return;
          }
          var looksHtml = /\.html?$/i.test(path) || /^\s*</.test(text);
          if (looksHtml && typeof Blob !== "undefined") {
            var blob = new Blob([text], { type: "text/html;charset=utf-8" });
            var url = URL.createObjectURL(blob);
            out.innerHTML = '<p class="stamp">HEAD <code>' + sha.slice(0, 12) + "</code> · " + path +
              ' · <a href="' + rawUrl(path, sha) + '">raw</a></p><iframe title="HEAD file" src="' +
              url + '" style="width:100%;min-height:24rem;border:1px solid #3a3a40;background:#fff"></iframe>';
            return;
          }
          out.innerHTML = '<p class="stamp">HEAD <code>' + sha.slice(0, 12) + "</code> · " + path +
            ' · <a href="' + rawUrl(path, sha) + '">raw</a></p><pre></pre>';
          out.querySelector("pre").textContent = text;
        });
      }).catch(function (err) {
        var st = err && err.status;
        out.textContent = "could not read git HEAD" + (st ? " (" + st + ")" : "");
      });
    }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      readFromHead((document.getElementById("head-path") || {}).value);
    });
    var qPath = pathFromSearch(typeof location !== "undefined" ? location.search : "");
    if (qPath) {
      var input = document.getElementById("head-path");
      if (input) input.value = qPath;
      readFromHead(qPath);
    }
  }

  if (typeof document !== "undefined" && document.getElementById) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", bindDoor);
    } else {
      bindDoor();
    }
  }

  return {
    cleanPath: cleanPath,
    safePath: safePath,
    rawUrl: rawUrl,
    jsdelivrMainUrl: jsdelivrMainUrl,
    pagesUrl: pagesUrl,
    parseBakedHead: parseBakedHead,
    headState: headState,
    headSha: headSha,
    fetchPath: fetchPath,
    parsePost: parsePost,
    idsFromCommits: idsFromCommits,
    recentHeadPosts: recentHeadPosts,
    parseFreshMd: parseFreshMd,
    freshPosts: freshPosts,
    utcIso: utcIso,
    paintChip: paintChip,
    pathFromSearch: pathFromSearch,
    fetchCacheMode: fetchCacheMode
  };
})();
