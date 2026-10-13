(function (root) {
  "use strict";

  var api = {};
  var REPO = "woahwhattheheck/commons";
  var MAIN_API = "https://api.github.com/repos/" + REPO + "/commits/main";
  var MAIN_GIT_ADVERTISEMENT = "https://cors.isomorphic-git.org/github.com/" + REPO +
    ".git/info/refs?service=git-upload-pack";
  var CACHE_KEY = "commons-exact-main-v1";
  var CACHE_MS = 60000;
  var TIMEOUT_MS = 12000;
  var MAX_ADVERTISEMENT_BYTES = 2 * 1024 * 1024;
  var inFlight = null;

  function text(value) {
    return String(value == null ? "" : value);
  }

  api.isSha = function (value) {
    var sha = text(value);
    if (sha !== sha.trim()) return false;
    return /^[0-9a-f]{40}$/.test(sha.toLowerCase());
  };

  function bytesFrom(source) {
    var input;
    if (typeof source === "string") {
      input = new Uint8Array(source.length);
      for (var i = 0; i < source.length; i += 1) {
        if (source.charCodeAt(i) > 255) throw new Error("git advertisement string was not byte-safe");
        input[i] = source.charCodeAt(i);
      }
    } else if (typeof ArrayBuffer !== "undefined" && source instanceof ArrayBuffer) {
      input = new Uint8Array(source);
    } else if (typeof Uint8Array !== "undefined" && source instanceof Uint8Array) {
      input = source;
    } else {
      throw new Error("git advertisement was not bytes");
    }
    if (input.length > MAX_ADVERTISEMENT_BYTES) throw new Error("git advertisement exceeded 2 MiB");
    return input;
  }

  api.parseGitAdvertisement = function (source) {
    var input = bytesFrom(source);

    function ascii(start, end) {
      var value = "";
      for (var at = start; at < end; at += 1) value += String.fromCharCode(input[at]);
      return value;
    }

    var offset = 0;
    var main = "";
    var symbolicHead = "";
    while (offset < input.length) {
      if (offset + 4 > input.length) throw new Error("truncated git pkt-line header");
      var prefix = ascii(offset, offset + 4);
      if (!/^[0-9a-fA-F]{4}$/.test(prefix)) throw new Error("invalid git pkt-line header");
      var length = parseInt(prefix, 16);
      offset += 4;
      if (length === 0 || length === 1 || length === 2) continue;
      if (length < 4 || offset + length - 4 > input.length) {
        throw new Error("truncated git pkt-line payload");
      }
      var payload = ascii(offset, offset + length - 4);
      offset += length - 4;
      var ref = /^([0-9a-fA-F]{40})\s+(HEAD|refs\/heads\/main)(?:\x00|\n|$)/.exec(payload);
      if (!ref) {
        if (/\srefs\/heads\/main(?:\x00|\n|$)/.test(payload)) {
          throw new Error("git advertisement contained an invalid main SHA");
        }
        continue;
      }
      var sha = ref[1].toLowerCase();
      if (ref[2] === "refs/heads/main") {
        if (main && main !== sha) throw new Error("git advertisement contained conflicting main refs");
        main = sha;
      }
      if (ref[2] === "HEAD" && /\x00[^\n]*\bsymref=HEAD:refs\/heads\/main(?:\s|$)/.test(payload)) {
        if (symbolicHead && symbolicHead !== sha) {
          throw new Error("git advertisement contained conflicting symbolic HEAD refs");
        }
        symbolicHead = sha;
      }
    }
    if (main && symbolicHead && main !== symbolicHead) {
      throw new Error("git advertisement main disagreed with symbolic HEAD");
    }
    return main || symbolicHead;
  };

  api.resolve = function (apiReader, gitReader) {
    if (typeof apiReader !== "function" || typeof gitReader !== "function") {
      return Promise.reject(new Error("main resolvers were not supplied"));
    }
    return Promise.resolve().then(apiReader).then(function (commit) {
      var sha = text(commit && commit.sha).toLowerCase();
      if (!api.isSha(sha)) throw new Error("main commit response did not include a SHA");
      return { sha: sha, via: "GitHub commits API", observedAt: new Date().toISOString() };
    }).catch(function (apiError) {
      return Promise.resolve().then(gitReader).then(function (advertisement) {
        var sha = api.parseGitAdvertisement(advertisement);
        if (!sha) throw new Error("git advertisement did not include refs/heads/main");
        return {
          sha: sha,
          via: "anonymous git smart-HTTP fallback",
          observedAt: new Date().toISOString(),
          primaryError: text(apiError && apiError.message || apiError)
        };
      }).catch(function (gitError) {
        throw new Error("GitHub API: " + text(apiError && apiError.message || apiError) +
          "; git smart-HTTP: " + text(gitError && gitError.message || gitError));
      });
    });
  };

  function timedRead(url, options, timeoutMs, reader) {
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var opts = options || {};
    if (controller) opts.signal = controller.signal;
    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = setTimeout(function () {
        if (settled) return;
        settled = true;
        if (controller) controller.abort();
        reject(new Error(url + " timed out after " + timeoutMs + "ms"));
      }, timeoutMs);
      Promise.resolve().then(function () {
        return fetch(url, opts);
      }).then(function (response) {
        if (settled) return null;
        return reader(response);
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

  function readApi(timeoutMs) {
    return timedRead(MAIN_API, {
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      headers: { Accept: "application/json" }
    }, timeoutMs, function (response) {
      if (!response.ok) throw new Error(MAIN_API + " HTTP " + response.status);
      return response.json();
    });
  }

  function readAdvertisement(timeoutMs) {
    return timedRead(MAIN_GIT_ADVERTISEMENT, {
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      headers: { Accept: "application/x-git-upload-pack-advertisement" }
    }, timeoutMs, function (response) {
      if (!response.ok) throw new Error(MAIN_GIT_ADVERTISEMENT + " HTTP " + response.status);
      var contentType = text(response.headers && response.headers.get("content-type")).toLowerCase();
      if (contentType.indexOf("application/x-git-upload-pack-advertisement") !== 0) {
        throw new Error(MAIN_GIT_ADVERTISEMENT + " returned unexpected content type " + (contentType || "UNKNOWN"));
      }
      var contentLength = Number(response.headers && response.headers.get("content-length") || 0);
      if (isFinite(contentLength) && contentLength > MAX_ADVERTISEMENT_BYTES) {
        throw new Error("git advertisement exceeded 2 MiB");
      }
      return response.arrayBuffer();
    }).then(function (buffer) {
      if (!buffer || buffer.byteLength > MAX_ADVERTISEMENT_BYTES) {
        throw new Error("git advertisement exceeded 2 MiB");
      }
      return buffer;
    });
  }

  function cached() {
    try {
      var value = JSON.parse(sessionStorage.getItem(CACHE_KEY) || "null");
      if (!value || !api.isSha(value.sha) || !value.savedAt || Date.now() - value.savedAt >= CACHE_MS) return null;
      return {
        sha: value.sha,
        via: value.via,
        observedAt: value.observedAt,
        cached: true
      };
    } catch (_) {
      return null;
    }
  }

  function save(value) {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({
        sha: value.sha,
        via: value.via,
        observedAt: value.observedAt,
        savedAt: Date.now()
      }));
    } catch (_) {}
  }

  api.resolveBrowser = function (options) {
    options = options || {};
    var timeoutMs = Number(options.timeoutMs);
    if (!isFinite(timeoutMs) || timeoutMs < 1 || timeoutMs > 60000) timeoutMs = TIMEOUT_MS;
    if (!options.force) {
      var hit = cached();
      if (hit) return Promise.resolve(hit);
      if (inFlight) return inFlight;
    }
    var request = api.resolve(
      function () { return readApi(timeoutMs); },
      function () { return readAdvertisement(timeoutMs); }
    ).then(function (value) {
      save(value);
      return value;
    });
    if (!options.force) {
      inFlight = request.then(function (value) {
        inFlight = null;
        return value;
      }).catch(function (error) {
        inFlight = null;
        throw error;
      });
      return inFlight;
    }
    return request;
  };

  api.repo = REPO;
  api.mainApi = MAIN_API;
  api.mainGitAdvertisement = MAIN_GIT_ADVERTISEMENT;
  root.COMMONS_EXACT_MAIN = api;
})(typeof window !== "undefined" ? window : globalThis);
