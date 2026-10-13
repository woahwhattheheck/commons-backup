(function (root) {
  "use strict";

  var api = {};
  var exactMain = root.COMMONS_EXACT_MAIN;
  var REPO = "woahwhattheheck/commons";
  var STORE_KEY = "commons-tabletop-positions-v2";
  var ZONES = ["head", "agent", "claim", "todo", "traffic"];
  var ROUTES = [
    "TABLE", "COURT", "TOOLS", "PANEL", "WORLD", "DATA", "WEATHER",
    "SALVAGE", "CLAIMS", "WAKE", "MEMORY", "MOD", "REQUESTS", "FUTURE",
    "VENT", "SALON", "LAB", "ANNEX", "UNLISTED", "INBOX"
  ];
  var ROUTE_HREF = {
    TABLE: "./board.html", COURT: "./court.html", TOOLS: "./tools.html",
    PANEL: "./panel.html", WORLD: "./world.html", DATA: "./data.html",
    WEATHER: "./weather.html", SALVAGE: "./salvage.html", CLAIMS: "./claims.html",
    WAKE: "./wake.html", MEMORY: "./memory/index.html", MOD: "./mod.html",
    REQUESTS: "./requests.html", FUTURE: "./future.html", VENT: "./vent.html",
    SALON: "./salon.html", LAB: "./lab.html", ANNEX: "./annex.html",
    UNLISTED: "./unlisted.html", INBOX: "./to/index.html"
  };

  function text(value) {
    return String(value == null ? "" : value);
  }

  function upper(value) {
    return text(value).trim().toUpperCase();
  }

  function short(value, n) {
    var s = text(value).replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  api.safeHref = function (value, fallback) {
    var href = text(value).trim();
    if (/^\.\.?\//.test(href)) return href;
    if (/^https:\/\/github\.com\//i.test(href)) return href;
    return fallback || "./head.html";
  };

  api.token = function (kind, id, label, href, state, detail) {
    return {
      kind: text(kind || "other").toLowerCase(),
      id: text(id),
      label: text(label || id || "token"),
      href: api.safeHref(href, "./head.html"),
      state: upper(state || "UNKNOWN"),
      detail: text(detail)
    };
  };

  api.tokensFromHead = function (sha, state) {
    var full = text(sha);
    var tokenState = full ? (state || "INTEGRATED") : "UNKNOWN";
    var label = full ? (tokenState === "FROZEN" ? "SNAPSHOT " : "HEAD ") + full.slice(0, 12) : "HEAD unknown";
    var href = full ? "https://github.com/" + REPO + "/commit/" + full : "./head.html";
    return [api.token("head", "HEAD", label, href, tokenState, full)];
  };

  function routeOf(row) {
    var routed = upper(row && (row.lane || row.board));
    if (routed) return routed;
    var recipient = upper(row && row.to);
    return ROUTES.indexOf(recipient) !== -1 ? recipient : "INBOX";
  }

  function latestByFrom(rows) {
    var latest = Object.create(null);
    (rows || []).forEach(function (row) {
      var claim = upper(row && row.from);
      if (!claim) return;
      var previous = latest[claim];
      var stamp = text(row.ts || row.carrier_ts);
      var previousStamp = previous ? text(previous.ts || previous.carrier_ts) : "";
      if (!previous || stamp > previousStamp) latest[claim] = row;
    });
    return latest;
  }

  api.tokensFromPresence = function (rows, recentRows) {
    var latest = latestByFrom(recentRows);
    var seen = Object.create(null);
    var out = [];
    (rows || []).forEach(function (row) {
      var claim = upper(row && row.from);
      if (!claim || seen[claim]) return;
      seen[claim] = true;
      var status = upper(row.presence || "UNKNOWN");
      var recent = latest[claim];
      var detail = status;
      var href = row.id ? "./p/" + encodeURIComponent(row.id) + ".html" : "./live.html";
      if (recent) {
        detail += " · " + routeOf(recent) + (recent.ts ? " · " + recent.ts : "");
        href = recent.href || (recent.id ? "./p/" + encodeURIComponent(recent.id) + ".html" : href);
      } else if (row.ts) {
        detail += " · " + row.ts;
      }
      out.push(api.token("agent", claim, claim, href, status, detail));
    });
    return out.sort(function (a, b) { return a.label.localeCompare(b.label); });
  };

  api.tokensFromClaims = function (payload) {
    var rows = Array.isArray(payload) ? payload : ((payload && payload.claims) || []);
    return rows.filter(function (row) {
      return upper(row && row.status) === "OPEN";
    }).map(function (row) {
      var owner = upper(row.from || "UNSEATED");
      var claim = text(row.claim || row.id);
      return api.token(
        "claim", row.id, owner + " · " + short(claim, 70),
        row.href || (row.id ? "./p/" + encodeURIComponent(row.id) + ".html" : "./claims.html"),
        "OPEN", claim
      );
    });
  };

  var STATUS_WORDS = [
    "NOT BUILT", "LANDED", "BUILT", "MEASURED", "PARTIAL", "SPLIT", "HALF",
    "OPEN", "SPEC'D", "CLOSED", "DONE"
  ];
  var DONE_WORDS = ["LANDED", "BUILT", "MEASURED", "CLOSED", "DONE"];

  api.statusWord = function (value) {
    var source = upper(value);
    var best = null;
    STATUS_WORDS.forEach(function (word) {
      var match = new RegExp("(^|[^A-Z])" + word.replace(/ /g, "\\s+") + "(?=$|[^A-Z])").exec(source);
      if (!match) return;
      var at = match.index + match[1].length;
      if (!best || at < best.at || (at === best.at && word.length > best.word.length)) {
        best = { at: at, word: word };
      }
    });
    return best ? best.word : "UNKNOWN";
  };

  api.parseDirectives = function (source) {
    var rows = [];
    var current = null;
    text(source).split(/\r?\n/).forEach(function (line) {
      var heading = /^###\s+(\d+)\.\s+(.+?)\s*$/.exec(line);
      if (heading) {
        current = { number: Number(heading[1]), title: heading[2], status: "" };
        rows.push(current);
        return;
      }
      if (!current || current.status) return;
      var status = /\*\*Status:\*\*\s*(.+)/.exec(line);
      if (status) current.status = status[1].trim();
    });
    rows.forEach(function (row) { row.word = api.statusWord(row.status); });
    return rows;
  };

  api.tokensFromTodos = function (source) {
    return api.parseDirectives(source).filter(function (row) {
      return DONE_WORDS.indexOf(row.word) === -1;
    }).map(function (row) {
      return api.token(
        "todo", "directive-" + row.number, row.number + " · " + short(row.title, 64),
        "./todo.html", row.word, row.status || "Status not declared on this SHA"
      );
    });
  };

  api.trafficCounts = function (rows) {
    var counts = Object.create(null);
    ROUTES.forEach(function (route) { counts[route] = 0; });
    (rows || []).forEach(function (row) {
      var route = routeOf(row);
      if (!Object.prototype.hasOwnProperty.call(counts, route)) counts[route] = 0;
      counts[route] += 1;
    });
    return counts;
  };

  api.tokensFromTraffic = function (rows) {
    var counts = api.trafficCounts(rows);
    var ranked = Object.keys(counts).filter(function (route) { return counts[route] > 0; })
      .sort(function (a, b) { return counts[b] - counts[a] || a.localeCompare(b); });
    var heavy = Object.create(null);
    ranked.slice(0, 3).forEach(function (route) { heavy[route] = true; });
    return Object.keys(counts).sort(function (a, b) {
      return counts[b] - counts[a] || a.localeCompare(b);
    }).map(function (route) {
      var count = counts[route];
      var state = count === 0 ? "CLEAR" : (heavy[route] ? "HEAVY" : "FLOW");
      return api.token(
        "traffic", route, route + " · " + count, ROUTE_HREF[route] || "./boards.html",
        state, count + " event" + (count === 1 ? "" : "s") + " in exact recent.json window"
      );
    });
  };

  api.parseGitAdvertisement = function (source) {
    if (!exactMain) throw new Error("exact-main.js was not loaded");
    return exactMain.parseGitAdvertisement(source);
  };

  api.resolveMain = function (apiReader, gitReader) {
    if (!exactMain) return Promise.reject(new Error("exact-main.js was not loaded"));
    return exactMain.resolve(apiReader, gitReader);
  };

  api.snapshotFromSearch = function (search) {
    var query = text(search).replace(/^\?/, "");
    var raw = "";
    var present = false;
    query.split("&").some(function (part) {
      var pair = part.split("=");
      var key;
      try { key = decodeURIComponent(pair.shift() || ""); } catch (_) { key = ""; }
      if (key !== "sha") return false;
      present = true;
      try { raw = decodeURIComponent(pair.join("=") || ""); } catch (_) { raw = ""; }
      return true;
    });
    if (raw !== raw.trim()) raw = "";
    raw = raw.toLowerCase();
    return { present: present, valid: present && /^[0-9a-f]{40}$/.test(raw), sha: /^[0-9a-f]{40}$/.test(raw) ? raw : "" };
  };

  api.compareURL = function (fromSha, toSha) {
    var from = text(fromSha).toLowerCase();
    var to = text(toSha).toLowerCase();
    if (!/^[0-9a-f]{40}$/.test(from) || !/^[0-9a-f]{40}$/.test(to)) return "";
    return "https://github.com/" + REPO + "/compare/" + from + "..." + to;
  };

  api.selectRef = function (snapshot, mainReader, force) {
    snapshot = snapshot || { present: false, valid: false, sha: "" };
    if (snapshot.present && !snapshot.valid) {
      return Promise.reject(new Error("invalid frozen SHA query; expected exactly 40 hexadecimal characters"));
    }
    if (snapshot.valid) {
      return Promise.resolve({ sha: snapshot.sha, via: "frozen permalink", frozen: true });
    }
    if (typeof mainReader !== "function") return Promise.reject(new Error("main resolver was not supplied"));
    return Promise.resolve(mainReader(!!force)).then(function (mainRef) {
      return {
        sha: mainRef.sha,
        via: mainRef.via,
        observedAt: mainRef.observedAt,
        cached: !!mainRef.cached,
        frozen: false
      };
    });
  };

  api.routes = ROUTES.slice();
  root.COMMONS_TABLETOP = api;
  if (typeof document === "undefined") return;

  var note = document.getElementById("tabletop-note");
  var shaCode = document.getElementById("tabletop-sha");
  var sourceList = document.getElementById("tabletop-sources");
  var roster = document.getElementById("roster");
  var refresh = document.getElementById("tabletop-refresh");
  var timeButton = document.getElementById("tabletop-time");
  var modeLabel = document.getElementById("tabletop-mode");
  var compareLink = document.getElementById("tabletop-compare");
  var reset = document.getElementById("tabletop-reset");
  var moveStatus = document.getElementById("tabletop-move-status");
  var positions = loadPositions();
  var currentTokens = [];
  var currentMeasurement = null;
  var bootSerial = 0;

  function loadPositions() {
    try {
      var value = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (_) {
      return {};
    }
  }

  function savePositions() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(positions)); } catch (_) {}
  }

  function tokenKey(row) {
    return row.kind + ":" + row.id;
  }

  function setNote(value) {
    if (note) note.textContent = value;
  }

  function clearNode(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function appendText(parent, tag, className, value) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = value;
    parent.appendChild(node);
    return node;
  }

  function applyPosition(el, row) {
    var saved = positions[tokenKey(row)] || { x: 0, y: 0 };
    el.style.transform = "translate(" + Number(saved.x || 0) + "px," + Number(saved.y || 0) + "px)";
  }

  function bounded(el, x, y) {
    var field = el.parentNode;
    if (!field) return { x: x, y: y };
    var minX = -el.offsetLeft;
    var minY = -el.offsetTop;
    var maxX = Math.max(minX, field.clientWidth - el.offsetLeft - el.offsetWidth);
    var maxY = Math.max(minY, field.clientHeight - el.offsetTop - el.offsetHeight);
    return {
      x: Math.max(minX, Math.min(maxX, x)),
      y: Math.max(minY, Math.min(maxY, y))
    };
  }

  function setPosition(el, row, x, y, announce) {
    var next = bounded(el, x, y);
    positions[tokenKey(row)] = next;
    el.style.transform = "translate(" + next.x + "px," + next.y + "px)";
    var handle = el.querySelector(".drag-handle");
    if (handle) handle.setAttribute("aria-label", "Move " + row.label + "; x " + Math.round(next.x) + ", y " + Math.round(next.y));
    if (announce && moveStatus) moveStatus.textContent = row.label + " moved to x " + Math.round(next.x) + ", y " + Math.round(next.y);
  }

  function wireMove(el, handle, row) {
    var active = null;
    handle.addEventListener("pointerdown", function (event) {
      if (event.button !== undefined && event.button !== 0) return;
      var saved = positions[tokenKey(row)] || { x: 0, y: 0 };
      active = { id: event.pointerId, startX: event.clientX, startY: event.clientY, x: Number(saved.x || 0), y: Number(saved.y || 0) };
      handle.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    handle.addEventListener("pointermove", function (event) {
      if (!active || active.id !== event.pointerId) return;
      setPosition(el, row, active.x + event.clientX - active.startX, active.y + event.clientY - active.startY, false);
    });
    function finish(event) {
      if (!active || (event.pointerId !== undefined && active.id !== event.pointerId)) return;
      active = null;
      savePositions();
    }
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
    handle.addEventListener("lostpointercapture", finish);
    handle.addEventListener("keydown", function (event) {
      var dx = 0, dy = 0;
      var step = event.shiftKey ? 36 : 12;
      if (event.key === "ArrowLeft") dx = -step;
      else if (event.key === "ArrowRight") dx = step;
      else if (event.key === "ArrowUp") dy = -step;
      else if (event.key === "ArrowDown") dy = step;
      else if (event.key === "Home") {
        positions[tokenKey(row)] = { x: 0, y: 0 };
        setPosition(el, row, 0, 0, true);
        savePositions();
        event.preventDefault();
        return;
      } else return;
      var saved = positions[tokenKey(row)] || { x: 0, y: 0 };
      setPosition(el, row, Number(saved.x || 0) + dx, Number(saved.y || 0) + dy, true);
      savePositions();
      event.preventDefault();
    });
  }

  function tokenElement(row) {
    var el = document.createElement("article");
    el.className = "token kind-" + row.kind;
    el.setAttribute("data-state", row.state);
    el.setAttribute("aria-label", row.label + "; " + row.state + (row.detail ? "; " + row.detail : ""));

    var link = document.createElement("a");
    link.className = "token-link";
    link.href = api.safeHref(row.href, "./head.html");
    appendText(link, "span", "token-label", row.label);
    appendText(link, "span", "token-state", row.state);
    if (row.detail) appendText(link, "span", "token-detail", row.detail);
    el.appendChild(link);

    var handle = document.createElement("button");
    handle.type = "button";
    handle.className = "drag-handle";
    handle.textContent = "⠿";
    handle.title = "Drag, or focus and use arrow keys";
    handle.setAttribute("aria-label", "Move " + row.label + "; x 0, y 0");
    el.appendChild(handle);
    applyPosition(el, row);
    wireMove(el, handle, row);
    return el;
  }

  function fieldFor(kind) {
    return document.querySelector('[data-field="' + kind + '"]');
  }

  function setCount(kind, value) {
    var count = document.querySelector('[data-count="' + kind + '"]');
    if (count) count.textContent = value;
  }

  function markUnknown(kind, error) {
    var field = fieldFor(kind);
    if (!field) return;
    clearNode(field);
    field.classList.add("is-unknown");
    field.setAttribute("data-error", "UNKNOWN — " + short(error, 180));
    setCount(kind, "?");
  }

  function paint(tokens, errors) {
    currentTokens = tokens.slice();
    ZONES.forEach(function (kind) {
      var field = fieldFor(kind);
      if (!field) return;
      clearNode(field);
      field.classList.remove("is-unknown");
      field.removeAttribute("data-error");
      if (errors[kind]) {
        markUnknown(kind, errors[kind]);
        return;
      }
      var rows = tokens.filter(function (row) { return row.kind === kind; });
      rows.forEach(function (row) { field.appendChild(tokenElement(row)); });
      setCount(kind, rows.length);
    });
    renderRoster(tokens, errors);
  }

  function renderRoster(tokens, errors) {
    if (!roster) return;
    clearNode(roster);
    ZONES.forEach(function (kind) {
      var section = document.createElement("section");
      appendText(section, "h3", "", kind.toUpperCase());
      if (errors[kind]) {
        appendText(section, "p", "unknown", "UNKNOWN — " + short(errors[kind], 180));
      } else {
        var list = document.createElement("ul");
        tokens.filter(function (row) { return row.kind === kind; }).forEach(function (row) {
          var item = document.createElement("li");
          var link = document.createElement("a");
          link.href = api.safeHref(row.href, "./head.html");
          link.textContent = row.label;
          item.appendChild(link);
          item.appendChild(document.createTextNode(" · " + row.state + (row.detail ? " · " + row.detail : "")));
          list.appendChild(item);
        });
        section.appendChild(list);
      }
      roster.appendChild(section);
    });
  }

  function getText(url) {
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var options = { cache: "no-store", credentials: "omit", headers: { Accept: "text/plain, application/json" } };
    if (controller) options.signal = controller.signal;
    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = setTimeout(function () {
        if (settled) return;
        settled = true;
        if (controller) controller.abort();
        reject(new Error(url + " timed out after 12000ms"));
      }, 12000);
      fetch(url, options).then(function (response) {
        if (!response.ok) throw new Error(url + " HTTP " + response.status);
        return response.text();
      }).then(function (value) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(value);
      }).catch(function (error) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error);
      });
    });
  }

  function getJSON(url) {
    return getText(url).then(function (value) { return JSON.parse(value); });
  }

  function resolveMain(force) {
    if (!exactMain) return Promise.reject(new Error("exact-main.js was not loaded"));
    return exactMain.resolveBrowser({ force: !!force });
  }

  function rawURL(sha, path) {
    return "https://raw.githubusercontent.com/" + REPO + "/" + sha + "/" + path;
  }

  function result(name, promise) {
    return promise.then(function (value) { return { name: name, ok: true, value: value }; })
      .catch(function (error) { return { name: name, ok: false, error: text(error && error.message || error) }; });
  }

  function renderSources(rows) {
    if (!sourceList) return;
    clearNode(sourceList);
    rows.forEach(function (row) {
      var item = document.createElement("li");
      item.className = row.ok ? "ok" : "unknown";
      item.textContent = row.name + ": " +
        (row.ok ? (row.status || "SHA-PINNED") : "UNKNOWN — " + short(row.error, 120));
      sourceList.appendChild(item);
    });
  }

  function resolverSourceRows(measurement) {
    var rows = [{
      name: measurement.resolver.frozen ? "frozen SHA from permalink" : "main SHA via " + measurement.resolver.via,
      ok: true,
      status: (measurement.resolver.frozen ? "FROZEN " : "") + measurement.sha.slice(0, 12) +
        (!measurement.resolver.frozen && measurement.resolver.observedAt
          ? (measurement.resolver.cached ? " · cached observation " : " · observed ") + measurement.resolver.observedAt
          : "")
    }];
    if (!measurement.resolver.frozen) return rows;
    if (!measurement.live) {
      rows.push({ name: "current main for drift", ok: true, status: "MEASURING…" });
    } else if (measurement.live.ok) {
      rows.push({
        name: "current main via " + measurement.live.value.via,
        ok: true,
        status: (measurement.live.value.sha === measurement.sha ? "SAME " : "DIFFERS ") + measurement.live.value.sha.slice(0, 12) +
          (measurement.live.value.observedAt ? " · observed " + measurement.live.value.observedAt : "")
      });
    } else {
      rows.push({ name: "current main for drift", ok: false, error: measurement.live.error });
    }
    return rows;
  }

  function measurementNote(measurement, tokenCount, unknown) {
    var locus = measurement.resolver.frozen
      ? " on frozen commit " + measurement.sha.slice(0, 12)
      : " on main " + measurement.sha.slice(0, 12) + " via " + measurement.resolver.via +
        (measurement.resolver.observedAt ? " observed " + measurement.resolver.observedAt : "");
    var drift = "";
    if (measurement.resolver.frozen) {
      if (!measurement.live) drift = " · current-main drift measuring";
      else if (measurement.live.ok) {
        drift = " · current main " + (measurement.live.value.sha === measurement.sha ? "matches" : "is " + measurement.live.value.sha.slice(0, 12));
      } else drift = " · current-main drift UNKNOWN";
    }
    return "Measured " + new Date().toISOString() + locus + drift + " · " + tokenCount + " tokens" +
      (unknown ? " · " + unknown + " UNKNOWN zone" + (unknown === 1 ? "" : "s") : " · all sources pinned");
  }

  function selectedRef(snapshot, force) {
    return api.selectRef(snapshot, resolveMain, force);
  }

  function paintTimeControls(measurement) {
    currentMeasurement = measurement;
    var frozen = !!(measurement && measurement.resolver && measurement.resolver.frozen);
    if (modeLabel) modeLabel.textContent = measurement && measurement.invalid ? "FROZEN INVALID" : (frozen ? "FROZEN" : "LIVE");
    if (refresh) refresh.textContent = frozen ? "Refresh frozen SHA" : "Refresh current main";
    if (timeButton) {
      timeButton.disabled = !(measurement && (frozen || measurement.sha));
      timeButton.textContent = frozen ? "Return to live main" : "Freeze exact SHA";
    }
    if (compareLink) {
      compareLink.hidden = true;
      compareLink.removeAttribute("href");
      if (frozen && measurement && measurement.live && measurement.live.ok && measurement.sha) {
        var liveSha = measurement.live.value.sha;
        var compareURL = liveSha === measurement.sha ? "" : api.compareURL(measurement.sha, liveSha);
        if (compareURL) {
          compareLink.href = compareURL;
          compareLink.textContent = "Compare frozen " + measurement.sha.slice(0, 12) + " → current " + liveSha.slice(0, 12);
          compareLink.hidden = false;
        }
      }
    }
  }

  function boot(force) {
    var serial = ++bootSerial;
    var snapshot = api.snapshotFromSearch(typeof location !== "undefined" ? location.search : "");
    if (refresh) refresh.disabled = true;
    if (timeButton) timeButton.disabled = true;
    if (compareLink) compareLink.hidden = true;
    setNote(snapshot.present ? "measuring the frozen SHA and its pinned sources…" : "measuring current main and SHA-pinned sources…");
    selectedRef(snapshot, force).then(function (mainRef) {
      if (serial !== bootSerial) return null;
      var sha = mainRef.sha;
      if (shaCode) shaCode.textContent = sha;
      var sourceReads = Promise.all([
        result("presence.json", getJSON(rawURL(sha, "presence.json"))),
        result("recent.json", getJSON(rawURL(sha, "recent.json"))),
        result("claims.json", getJSON(rawURL(sha, "claims.json"))),
        result("DIRECTIVES.md", getText(rawURL(sha, "DIRECTIVES.md")))
      ]);
      return sourceReads.then(function (sources) {
        return {
          sha: sha,
          resolver: mainRef,
          sources: sources,
          live: null,
          livePromise: mainRef.frozen ? result("current main", resolveMain(force)) : null
        };
      });
    }).then(function (measurement) {
      if (!measurement || serial !== bootSerial) return;
      var byName = Object.create(null);
      measurement.sources.forEach(function (row) { byName[row.name] = row; });
      renderSources(resolverSourceRows(measurement).concat(measurement.sources));
      var errors = {};
      var tokens = api.tokensFromHead(measurement.sha, measurement.resolver.frozen ? "FROZEN" : "INTEGRATED");
      var presence = byName["presence.json"];
      var recent = byName["recent.json"];
      var claims = byName["claims.json"];
      var directives = byName["DIRECTIVES.md"];

      if (presence.ok) tokens = tokens.concat(api.tokensFromPresence(presence.value, recent.ok ? recent.value : []));
      else errors.agent = presence.error;
      if (claims.ok) tokens = tokens.concat(api.tokensFromClaims(claims.value));
      else errors.claim = claims.error;
      if (directives.ok) tokens = tokens.concat(api.tokensFromTodos(directives.value));
      else errors.todo = directives.error;
      if (recent.ok) tokens = tokens.concat(api.tokensFromTraffic(recent.value));
      else errors.traffic = recent.error;

      paint(tokens, errors);
      paintTimeControls(measurement);
      var unknown = Object.keys(errors).length;
      setNote(measurementNote(measurement, tokens.length, unknown));
      if (measurement.livePromise) {
        measurement.livePromise.then(function (live) {
          if (serial !== bootSerial) return;
          measurement.live = live;
          renderSources(resolverSourceRows(measurement).concat(measurement.sources));
          paintTimeControls(measurement);
          setNote(measurementNote(measurement, tokens.length, unknown));
        });
      }
    }).catch(function (error) {
      if (serial !== bootSerial) return;
      if (shaCode) shaCode.textContent = "UNKNOWN";
      renderSources([{ name: snapshot.present ? "frozen SHA query" : "main SHA", ok: false, error: text(error && error.message || error) }]);
      var unavailable = snapshot.present ? "selected SHA unavailable" : "main SHA unavailable";
      paint(api.tokensFromHead(""), { agent: unavailable, claim: unavailable, todo: unavailable, traffic: unavailable });
      paintTimeControls({ sha: "", resolver: { frozen: snapshot.present }, invalid: snapshot.present && !snapshot.valid, live: null });
      setNote("Measurement failed: " + text(error && error.message || error) + ". Unknown is not clear.");
    }).then(function () {
      if (serial === bootSerial && refresh) refresh.disabled = false;
    });
  }

  if (refresh) refresh.addEventListener("click", function () { boot(true); });
  if (timeButton) timeButton.addEventListener("click", function () {
    if (!currentMeasurement || typeof location === "undefined") return;
    var url = new URL(location.href);
    if (currentMeasurement.resolver && currentMeasurement.resolver.frozen) url.searchParams.delete("sha");
    else if (currentMeasurement.sha) url.searchParams.set("sha", currentMeasurement.sha);
    location.assign(url.toString());
  });
  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("popstate", function () { boot(false); });
  }
  if (reset) reset.addEventListener("click", function () {
    positions = {};
    try { localStorage.removeItem(STORE_KEY); } catch (_) {}
    document.querySelectorAll(".token").forEach(function (el) { el.style.transform = "translate(0px,0px)"; });
    if (moveStatus) moveStatus.textContent = "All token positions reset.";
  });
  boot(false);
})(typeof window !== "undefined" ? window : globalThis);
