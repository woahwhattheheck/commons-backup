(function (root) {
  "use strict";

  var REPO = "woahwhattheheck/commons";
  var RAW = "https://raw.githubusercontent.com/" + REPO + "/";
  var GITHUB = "https://github.com/" + REPO;
  var MAX_BYTES = 512 * 1024;
  var FETCH_TIMEOUT_MS = 20000;
  var api = {};

  function literal(v) {
    return String(v == null ? "" : v);
  }

  api.isSha = function (candidate) {
    var sha = literal(candidate);
    if (sha !== sha.trim()) return false;
    var exact = root.COMMONS_EXACT_MAIN;
    if (exact && typeof exact.isSha === "function") return !!exact.isSha(sha);
    return /^[0-9a-fA-F]{40}$/.test(sha);
  };

  api.safePath = function (candidate) {
    var path = literal(candidate);
    if (path !== path.trim()) return "";
    if (!path || path.length > 512 || path.charAt(0) === "/" || path.indexOf("\\") >= 0) return "";
    if (!/^[A-Za-z0-9._/-]+$/.test(path)) return "";
    var parts = path.split("/");
    if (parts.some(function (part) { return !part || part === "." || part === ".."; })) return "";
    return path;
  };

  function queryParams(search) {
    var Params = root.URLSearchParams || (typeof URLSearchParams !== "undefined" && URLSearchParams);
    if (!Params) throw new Error("URLSearchParams is unavailable");
    return new Params(String(search || "").replace(/^\?/, ""));
  }

  api.parseQuery = function (search) {
    var params;
    var errors = [];
    try {
      params = queryParams(search);
    } catch (error) {
      return { ok: false, base: "", target: "", path: "", errors: [String(error && error.message || error)] };
    }
    ["base", "target", "path"].forEach(function (name) {
      if (typeof params.getAll === "function" && params.getAll(name).length > 1) {
        errors.push("duplicate " + name + " parameter");
      }
    });
    var base = literal(params.get("base")).toLowerCase();
    var target = literal(params.get("target")).toLowerCase();
    var path = api.safePath(params.get("path"));
    if (!api.isSha(base)) errors.push("base must be one full 40-character hexadecimal SHA");
    if (!api.isSha(target)) errors.push("target must be one full 40-character hexadecimal SHA");
    if (!path) errors.push("path must be a safe nonempty repo-relative path");
    return { ok: errors.length === 0, base: base, target: target, path: path, errors: errors };
  };

  function encodedPath(path) {
    return path.split("/").map(function (part) { return encodeURIComponent(part); }).join("/");
  }

  api.rawUrl = function (sha, path) {
    return RAW + literal(sha).toLowerCase() + "/" + encodedPath(api.safePath(path));
  };

  api.evidence = function (base, target, path) {
    base = literal(base).toLowerCase();
    target = literal(target).toLowerCase();
    path = api.safePath(path);
    return {
      baseRaw: api.rawUrl(base, path),
      targetRaw: api.rawUrl(target, path),
      baseCommit: GITHUB + "/commit/" + base,
      targetCommit: GITHUB + "/commit/" + target,
      compare: GITHUB + "/compare/" + base + "..." + target
    };
  };

  api.permalink = function (base, target, path, currentHref) {
    var URLCtor = root.URL || (typeof URL !== "undefined" && URL);
    if (!URLCtor) throw new Error("URL is unavailable");
    var href = currentHref || (root.location && root.location.href) || "https://woahwhattheheck.github.io/commons/the-world.html";
    var url = new URLCtor(href, href);
    url.hash = "";
    url.search = "";
    url.searchParams.set("base", literal(base).toLowerCase());
    url.searchParams.set("target", literal(target).toLowerCase());
    url.searchParams.set("path", api.safePath(path));
    return url.toString();
  };

  function asBytes(input) {
    if (input instanceof Uint8Array) return input;
    if (input instanceof ArrayBuffer) return new Uint8Array(input);
    if (input && input.buffer instanceof ArrayBuffer) {
      return new Uint8Array(input.buffer, input.byteOffset || 0, input.byteLength);
    }
    throw new Error("response body was not bytes");
  }

  api.readCapped = function (response, maxBytes) {
    maxBytes = Number(maxBytes || MAX_BYTES);
    var headerLength = 0;
    if (response && response.headers && typeof response.headers.get === "function") {
      headerLength = Number(response.headers.get("content-length") || 0);
    }
    if (isFinite(headerLength) && headerLength > maxBytes) {
      if (response.body && typeof response.body.cancel === "function") response.body.cancel();
      return Promise.resolve({ tooLarge: true, bytes: null });
    }
    if (response && response.body && typeof response.body.getReader === "function") {
      var reader = response.body.getReader();
      var chunks = [];
      var total = 0;
      function next() {
        return reader.read().then(function (row) {
          if (row.done) {
            var joined = new Uint8Array(total);
            var offset = 0;
            chunks.forEach(function (chunk) {
              joined.set(chunk, offset);
              offset += chunk.byteLength;
            });
            return { tooLarge: false, bytes: joined };
          }
          var chunk = asBytes(row.value);
          total += chunk.byteLength;
          if (total > maxBytes) {
            if (typeof reader.cancel === "function") reader.cancel();
            return { tooLarge: true, bytes: null };
          }
          chunks.push(chunk);
          return next();
        });
      }
      return next();
    }
    if (!response || typeof response.arrayBuffer !== "function") {
      return Promise.reject(new Error("response did not expose a byte body"));
    }
    return response.arrayBuffer().then(function (body) {
      var bytes = asBytes(body);
      return bytes.byteLength > maxBytes
        ? { tooLarge: true, bytes: null }
        : { tooLarge: false, bytes: bytes };
    });
  };

  api.digestHex = function (bytes, cryptoObject) {
    var c = cryptoObject || root.crypto;
    if (!c || !c.subtle || typeof c.subtle.digest !== "function") {
      return Promise.reject(new Error("SHA-256 digest is unavailable"));
    }
    bytes = asBytes(bytes);
    var exact = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    return Promise.resolve(c.subtle.digest("SHA-256", exact)).then(function (digest) {
      return Array.prototype.map.call(new Uint8Array(digest), function (n) {
        return n.toString(16).padStart(2, "0");
      }).join("");
    });
  };

  api.fetchSnapshot = function (sha, path, options) {
    options = options || {};
    sha = literal(sha).toLowerCase();
    path = api.safePath(path);
    var url = api.rawUrl(sha, path);
    if (!api.isSha(sha) || !path) {
      return Promise.resolve({ state: "UNKNOWN", sha: sha, path: path, url: url, reason: "invalid SHA or path", httpStatus: 0 });
    }
    var fetcher = options.fetch || root.fetch;
    if (typeof fetcher !== "function") {
      return Promise.resolve({ state: "UNKNOWN", sha: sha, path: path, url: url, reason: "fetch is unavailable", httpStatus: 0 });
    }
    var Abort = options.AbortController || root.AbortController;
    var controller = Abort ? new Abort() : null;
    var timer = null;
    if (controller && typeof root.setTimeout === "function") {
      timer = root.setTimeout(function () { controller.abort(); }, options.timeoutMs || FETCH_TIMEOUT_MS);
    }
    var request = {
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      headers: { Accept: "application/octet-stream" }
    };
    if (controller) request.signal = controller.signal;
    return Promise.resolve().then(function () {
      return fetcher(url, request);
    }).then(function (response) {
      var status = Number(response && response.status || 0);
      var finalUrl = literal(response && response.url);
      if (finalUrl && finalUrl !== url) {
        return {
          state: "UNKNOWN",
          sha: sha,
          path: path,
          url: url,
          reason: "exact raw response URL changed to " + finalUrl,
          httpStatus: status
        };
      }
      if (status === 404) {
        return { state: "MISSING", sha: sha, path: path, url: url, reason: "exact raw request returned HTTP 404", httpStatus: 404 };
      }
      if (!response || !response.ok || status !== 200) {
        return { state: "UNKNOWN", sha: sha, path: path, url: url, reason: "exact raw request returned HTTP " + (status || "unknown"), httpStatus: status };
      }
      return api.readCapped(response, options.maxBytes || MAX_BYTES).then(function (read) {
        if (read.tooLarge) {
          return { state: "UNKNOWN", sha: sha, path: path, url: url, reason: "response exceeded 512 KiB", httpStatus: 200 };
        }
        return api.digestHex(read.bytes, options.crypto).then(function (digest) {
          return {
            state: "PRESENT",
            sha: sha,
            path: path,
            url: url,
            reason: "exact raw bytes measured",
            httpStatus: 200,
            bytes: read.bytes,
            size: read.bytes.byteLength,
            digest: digest
          };
        });
      });
    }).catch(function (error) {
      return {
        state: "UNKNOWN",
        sha: sha,
        path: path,
        url: url,
        reason: (error && error.name === "AbortError") ? "exact raw request timed out" : String(error && error.message || error),
        httpStatus: 0
      };
    }).then(function (result) {
      if (timer != null && typeof root.clearTimeout === "function") root.clearTimeout(timer);
      return result;
    });
  };

  api.firstDifference = function (baseBytes, targetBytes) {
    baseBytes = asBytes(baseBytes);
    targetBytes = asBytes(targetBytes);
    var common = Math.min(baseBytes.byteLength, targetBytes.byteLength);
    for (var i = 0; i < common; i += 1) {
      if (baseBytes[i] !== targetBytes[i]) {
        return { offset: i, baseByte: baseBytes[i], targetByte: targetBytes[i] };
      }
    }
    if (baseBytes.byteLength !== targetBytes.byteLength) {
      return {
        offset: common,
        baseByte: common < baseBytes.byteLength ? baseBytes[common] : null,
        targetByte: common < targetBytes.byteLength ? targetBytes[common] : null
      };
    }
    return null;
  };

  api.classifySides = function (baseSide, targetSide) {
    baseSide = baseSide || { state: "UNKNOWN", reason: "base was not measured" };
    targetSide = targetSide || { state: "UNKNOWN", reason: "target was not measured" };
    if (baseSide.state === "UNKNOWN" || targetSide.state === "UNKNOWN") {
      return { state: "UNKNOWN", base: baseSide, target: targetSide, first: null };
    }
    if (baseSide.state === "MISSING" || targetSide.state === "MISSING") {
      return { state: "MISSING", base: baseSide, target: targetSide, first: null };
    }
    if (baseSide.state !== "PRESENT" || targetSide.state !== "PRESENT") {
      return { state: "UNKNOWN", base: baseSide, target: targetSide, first: null };
    }
    var first = api.firstDifference(baseSide.bytes, targetSide.bytes);
    return {
      state: first ? "CHANGED" : "IDENTICAL",
      base: baseSide,
      target: targetSide,
      first: first
    };
  };

  api.compare = function (base, target, path, options) {
    options = options || {};
    return Promise.all([
      api.fetchSnapshot(base, path, options),
      api.fetchSnapshot(target, path, options)
    ]).then(function (sides) {
      var result = api.classifySides(sides[0], sides[1]);
      result.path = api.safePath(path);
      result.evidence = api.evidence(base, target, path);
      result.measuredAt = typeof options.now === "function" ? String(options.now()) : new Date().toISOString();
      return result;
    });
  };

  function byteLabel(n) {
    return n == null ? "EOF" : "0x" + Number(n).toString(16).padStart(2, "0");
  }

  api.summary = function (result) {
    if (!result) return "UNKNOWN — no result.";
    if (result.state === "IDENTICAL") {
      return "IDENTICAL — both exact raw responses contain the same " + result.base.size + " bytes.";
    }
    if (result.state === "CHANGED") {
      return "CHANGED — first differing byte is offset " + result.first.offset + " (0x" + result.first.offset.toString(16) + "): " +
        byteLabel(result.first.baseByte) + " → " + byteLabel(result.first.targetByte) + ".";
    }
    if (result.state === "MISSING") {
      var missing = [];
      if (result.base.state === "MISSING") missing.push("base");
      if (result.target.state === "MISSING") missing.push("target");
      return "MISSING — exact raw returned HTTP 404 for " + missing.join(" and ") + ". This does not validate arbitrary commit ancestry.";
    }
    var reasons = [];
    if (result.base && result.base.state === "UNKNOWN") reasons.push("base: " + result.base.reason);
    if (result.target && result.target.state === "UNKNOWN") reasons.push("target: " + result.target.reason);
    return "UNKNOWN — " + (reasons.join("; ") || "the comparison was not measured") + ".";
  };

  api.receipt = function (query, result, permalink) {
    function side(prefix, row) {
      row = row || {};
      return [
        prefix + "_raw_state: " + (row.state || "UNKNOWN"),
        prefix + "_http: " + (row.httpStatus || "UNMEASURED"),
        prefix + "_reason: " + (row.reason || "UNMEASURED"),
        prefix + "_bytes: " + (row.size == null ? "UNMEASURED" : row.size),
        prefix + "_sha256: " + (row.digest || "UNMEASURED")
      ];
    }
    var lines = [
      "THE WORLD — exact Commons byte comparison",
      "state: " + (result && result.state || "UNKNOWN"),
      "measured_at: " + (result && result.measuredAt || "UNMEASURED"),
      "base: " + query.base,
      "target: " + query.target,
      "path: " + query.path
    ];
    lines = lines.concat(side("base", result && result.base));
    lines = lines.concat(side("target", result && result.target));
    if (result && result.first) {
      lines.push("first_differing_byte: " + result.first.offset + " (0x" + result.first.offset.toString(16) + ")");
      lines.push("first_values: " + byteLabel(result.first.baseByte) + " -> " + byteLabel(result.first.targetByte));
    } else if (result && result.state === "IDENTICAL") {
      lines.push("first_differing_byte: NONE");
    } else {
      lines.push("first_differing_byte: UNMEASURED");
    }
    lines.push("permalink: " + permalink);
    lines.push("scope: exact raw observations only; no arbitrary-SHA main, integration, or ancestry claim");
    return lines.join("\n");
  };

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function element(tag, text, className) {
    var node = root.document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function addLink(parent, label, href) {
    var link = element("a", label);
    link.href = href;
    link.rel = "noreferrer";
    parent.appendChild(link);
  }

  function renderTable(host, result, query) {
    clear(host);
    var table = element("table", null, "world-table");
    var caption = element("caption", "Exact byte evidence for " + query.path);
    table.appendChild(caption);
    var thead = element("thead");
    var hr = element("tr");
    ["Snapshot", "SHA", "Raw state", "Bytes", "SHA-256", "Evidence"].forEach(function (name) {
      var th = element("th", name);
      th.scope = "col";
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = element("tbody");
    [["Base", result.base, result.evidence.baseRaw], ["Target", result.target, result.evidence.targetRaw]].forEach(function (spec) {
      var row = element("tr");
      var name = element("th", spec[0]);
      name.scope = "row";
      row.appendChild(name);
      var shaCell = element("td");
      shaCell.setAttribute("data-label", "SHA");
      shaCell.appendChild(element("code", spec[1].sha || "UNMEASURED"));
      row.appendChild(shaCell);
      var stateCell = element("td", spec[1].state + (spec[1].httpStatus ? " · HTTP " + spec[1].httpStatus : ""));
      stateCell.setAttribute("data-label", "Raw state");
      row.appendChild(stateCell);
      var sizeCell = element("td", spec[1].size == null ? "—" : String(spec[1].size));
      sizeCell.setAttribute("data-label", "Bytes");
      row.appendChild(sizeCell);
      var digestCell = element("td");
      digestCell.setAttribute("data-label", "SHA-256");
      digestCell.appendChild(element("code", spec[1].digest || "—"));
      row.appendChild(digestCell);
      var rawCell = element("td");
      rawCell.setAttribute("data-label", "Evidence");
      addLink(rawCell, "sha-pinned raw", spec[2]);
      row.appendChild(rawCell);
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    host.appendChild(table);

    var evidence = element("div", null, "evidence-grid");
    var commits = element("p");
    addLink(commits, "base commit", result.evidence.baseCommit);
    commits.appendChild(root.document.createTextNode(" · "));
    addLink(commits, "target commit", result.evidence.targetCommit);
    evidence.appendChild(commits);
    var compare = element("p");
    addLink(compare, "GitHub compare evidence", result.evidence.compare);
    compare.appendChild(root.document.createTextNode(" (link only; no ancestry claim here)"));
    evidence.appendChild(compare);
    host.appendChild(evidence);
  }

  api.bind = function () {
    if (!root.document || !root.document.getElementById) return;
    var baseInput = root.document.getElementById("world-base");
    var targetInput = root.document.getElementById("world-target");
    var pathInput = root.document.getElementById("world-path");
    var resolverStatus = root.document.getElementById("resolver-status");
    var verdict = root.document.getElementById("world-result");
    var measurement = root.document.getElementById("world-measurement");
    var receipt = root.document.getElementById("world-receipt");
    var permalink = root.document.getElementById("world-permalink");

    function capture(input, side) {
      var exact = root.COMMONS_EXACT_MAIN;
      if (!exact || typeof exact.resolveBrowser !== "function") {
        resolverStatus.textContent = "UNKNOWN — exact-main resolver is unavailable.";
        return;
      }
      resolverStatus.textContent = "Resolving current main for the " + side + " field…";
      Promise.resolve(exact.resolveBrowser({ force: true })).then(function (row) {
        if (!row || !api.isSha(row.sha)) throw new Error("resolver did not return a full SHA");
        input.value = String(row.sha).toLowerCase();
        resolverStatus.textContent = "Observed main " + input.value + " via " + (row.via || "unnamed resolver") +
          " at " + (row.observedAt || new Date().toISOString()) + "; placed in " + side + ".";
      }).catch(function (error) {
        resolverStatus.textContent = "UNKNOWN — current main was not resolved: " + String(error && error.message || error);
      });
    }

    root.document.getElementById("capture-base").addEventListener("click", function () { capture(baseInput, "base"); });
    root.document.getElementById("capture-target").addEventListener("click", function () { capture(targetInput, "target"); });

    var hasQuery = /(?:^|[?&])(?:base|target|path)=/.test(String(root.location && root.location.search || ""));
    if (!hasQuery) return;
    var params = queryParams(root.location.search);
    baseInput.value = literal(params.get("base"));
    targetInput.value = literal(params.get("target"));
    pathInput.value = literal(params.get("path")) || pathInput.value;
    var query = api.parseQuery(root.location.search);
    if (!query.ok) {
      verdict.dataset.state = "UNKNOWN";
      verdict.textContent = "UNKNOWN — " + query.errors.join("; ") + ". No network request was made.";
      receipt.value = verdict.textContent;
      return;
    }
    var exactUrl = api.permalink(query.base, query.target, query.path, root.location.href);
    permalink.href = exactUrl;
    if (root.history && typeof root.history.replaceState === "function") {
      root.history.replaceState(null, "", exactUrl);
    }
    verdict.dataset.state = "MEASURING";
    verdict.textContent = "Measuring two SHA-pinned raw byte streams…";
    api.compare(query.base, query.target, query.path).then(function (result) {
      verdict.dataset.state = result.state;
      verdict.textContent = api.summary(result);
      renderTable(measurement, result, query);
      receipt.value = api.receipt(query, result, exactUrl);
    });
  };

  api.MAX_BYTES = MAX_BYTES;
  root.COMMONS_THE_WORLD = api;
  if (root.document && root.document.getElementById) {
    if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", api.bind);
    else api.bind();
  }
})(typeof window !== "undefined" ? window : globalThis);
