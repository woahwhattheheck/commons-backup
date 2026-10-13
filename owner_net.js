window.COMMONS_OWNER_NET = "hashed-ip-door";
(function () {
                                                                  
  // Law: admin-no-verification-loop-20260819-01. Do not remint.
  // GitHub Pages is static. The browser hashes this network's public IP
  // (pepper + LF + IP) and never writes the address. A match against an
                                                                              
  // It cannot control participation, reads, writes, or execution. from= stays
  // a claim.
  // Two slots: pc and phone. Same public IP is not the door.
  // Phone on cell and PC at home must persist two different digests.
                                                                       
  // not use the ntfy bus (that is the same-NAT toy). Persist is owner_net.py.
  if (window.COMMONS_OWNER_BOOT) return;
  window.COMMONS_OWNER_BOOT = 1;

  var SPEC_NAME = "owner.json";
  var ONLY_CLAIM = "BRYCE";
  var FALLBACK_PEPPER = "commons-owner-v1";
  var HASH_RE = /^[0-9a-f]{64}$/;
  var NET_TOPIC = "woahwhattheheck-commons-owner-net";
  var NET_HOSTS = [
    "https://ntfy.sh",
    "https://ntfy.envs.net",
    "https://ntfy.adminforge.de",
    "https://ntfy.mzte.de"
  ];
  var SEND_GAP_MS = 6 * 60 * 60 * 1000;
  var SENT_KEY = "commons-owner-net-sent";
  var HOST_IPV4_RE = /\b(?:\d{1,3}\.){3}\d{1,3}\b/;
  var HOST_IPV6_RE = /\b[0-9a-fA-F:]+:[0-9a-fA-F:]+\b/;

  function assetUrl(name) {
    var link = document.querySelector('link[rel="stylesheet"]');
    var href = (link && link.getAttribute("href")) || "./commons.css";
    return href.replace(/commons\.css.*$/, name);
  }

  function normalizeIp(raw) {
    var s = String(raw || "").trim();
    if (s.charAt(0) === "[" && s.charAt(s.length - 1) === "]") s = s.slice(1, -1);
    var pct = s.indexOf("%");
    if (pct !== -1) s = s.slice(0, pct);
    if (s.indexOf(":") !== -1) s = s.toLowerCase();
    return s;
  }

  function looksLikeIp(s) {
    s = String(s || "");
    if (/^\d{1,3}(\.\d{1,3}){3}$/.test(s)) return true;
    if (s.indexOf(":") !== -1 && /^[0-9a-f:]+$/.test(s)) return true;
    return false;
  }

  function asHash(item) {
    var h = "";
    if (typeof item === "string") h = item.toLowerCase();
    else if (item && typeof item.sha256 === "string") h = item.sha256.toLowerCase();
    return HASH_RE.test(h) ? h : "";
  }

  function sha256hex(s) {
    if (!window.crypto || !crypto.subtle || typeof TextEncoder === "undefined") {
      return Promise.reject(new Error("no-subtle"));
    }
    var bytes = new TextEncoder().encode(s);
    return crypto.subtle.digest("SHA-256", bytes).then(function (buf) {
      var b = new Uint8Array(buf);
      var out = "";
      var i;
      for (i = 0; i < b.length; i++) {
        out += (b[i] < 16 ? "0" : "") + b[i].toString(16);
      }
      return out;
    });
  }

  function digestIp(ip, pepper) {
    var n = normalizeIp(ip);
    if (!looksLikeIp(n)) return Promise.reject(new Error("not-ip"));
    return sha256hex(String(pepper || FALLBACK_PEPPER) + "\n" + n);
  }

  function fetchText(url) {
    return fetch(url, { cache: "no-store", credentials: "omit" }).then(function (r) {
      if (!r.ok) throw new Error("echo");
      return r.text();
    });
  }

  function hashEcho(url, pepper) {
    return fetchText(url).then(function (text) {
      return digestIp(text, pepper);
    });
  }

  function loadSpec() {
    return fetch(assetUrl(SPEC_NAME) + "?v=" + Date.now(), {
      cache: "no-store",
      credentials: "omit"
    }).then(function (r) {
      if (!r.ok) throw new Error("spec");
      return r.json();
    }, function () {
      return {
        claim: ONLY_CLAIM,
        algo: "sha256",
        pepper: FALLBACK_PEPPER,
        slots: { pc: null, phone: null },
        hashes: []
      };
    });
  }

  function echoList(spec) {
    var echoes = (spec && spec.echoes) || {};
    var list = echoes.browser || echoes.host || [];
    if (!list.length) {
      list = ["https://api.ipify.org", "https://api64.ipify.org"];
    }
    var out = [];
    var seen = {};
    list.forEach(function (u) {
      u = String(u || "").trim();
      if (!u || seen[u] || u.indexOf("https://") !== 0) return;
      seen[u] = 1;
      out.push(u);
    });
    return out;
  }

  function collectDigests(spec) {
    var pepper = String((spec && spec.pepper) || FALLBACK_PEPPER);
    var urls = echoList(spec);
    return Promise.all(urls.map(function (url) {
      return hashEcho(url, pepper).then(function (h) { return h; }, function () { return ""; });
    })).then(function (got) {
      var uniq = [];
      var seen = {};
      got.forEach(function (h) {
        if (!HASH_RE.test(h) || seen[h]) return;
        seen[h] = 1;
        uniq.push(h);
      });
      return uniq;
    });
  }

  function slotHash(spec, via) {
    var slots = (spec && spec.slots) || {};
    return asHash(slots[via]);
  }

  function slotsDistinct(spec) {
    var pc = slotHash(spec, "pc");
    var phone = slotHash(spec, "phone");
    return !!(pc && phone && pc !== phone);
  }

  function deviceVia() {
    try {
      if (navigator.userAgentData && navigator.userAgentData.mobile) return "phone";
    } catch (e) {}
    var ua = String(navigator.userAgent || "");
    if (/Android|iPhone|iPod|webOS|BlackBerry|IEMobile|Opera Mini/i.test(ua)) return "phone";
    return "pc";
  }

  function rememberedBryce() {
    try {
      return String(sessionStorage.getItem("commons-from-session-v1") || "").toUpperCase() === ONLY_CLAIM;
    } catch (e) {
      return false;
    }
  }

  function recentlySent(digest, via) {
    try {
      var raw = localStorage.getItem(SENT_KEY);
      if (!raw) return false;
      var o = JSON.parse(raw);
      if (!o || o.hash !== digest || o.via !== via) return false;
      return (Date.now() - Number(o.ts || 0)) < SEND_GAP_MS;
    } catch (e) {
      return false;
    }
  }

  function markSent(digest, via) {
    try {
      localStorage.setItem(SENT_KEY, JSON.stringify({ hash: digest, via: via, ts: Date.now() }));
    } catch (e) {}
  }

  function publishDigest(digest) {
    if (!HASH_RE.test(digest)) return Promise.resolve(false);
    var via = deviceVia();
    if (recentlySent(digest, via)) return Promise.resolve(false);
    var packed = JSON.stringify({ k: "owner-net", sha256: digest, via: via });
    function send(i) {
      if (i >= NET_HOSTS.length) return Promise.resolve(false);
      return fetch(NET_HOSTS[i] + "/" + NET_TOPIC, {
        method: "POST",
        credentials: "omit",
        cache: "no-store",
        headers: { "Content-Type": "text/plain" },
        body: packed
      }).then(function (r) {
        if (!r.ok) return send(i + 1);
        markSent(digest, via);
        return true;
      }, function () {
        return send(i + 1);
      });
    }
    return send(0);
  }

  function hostCandidates(spec) {
    var ch = spec && spec.context_host;
    if (!ch || typeof ch !== "object") return [];
    var out = [];
    var seen = {};
    function add(u) {
      u = String(u || "").trim();
      if (!u || seen[u] || u.indexOf("https://") !== 0) return;
      seen[u] = 1;
      out.push(u.replace(/\/$/, ""));
    }
    add(ch.public_url);
    (ch.candidates || []).forEach(add);
    return out;
  }

  function hostLooksSafe(obj) {
    if (!obj || obj.k !== "owner-context") return false;
    if (obj.authority || obj.gate) return false;
    var blob = "";
    try { blob = JSON.stringify(obj); } catch (e) { return false; }
    if (HOST_IPV4_RE.test(blob) || HOST_IPV6_RE.test(blob)) return false;
    if (obj.slot && obj.slot !== "pc" && obj.slot !== "phone") obj.slot = "";
    return true;
  }

  function fetchHostContext(spec) {
    var urls = hostCandidates(spec);
    function next(i) {
      if (i >= urls.length) return Promise.resolve(null);
      return fetch(urls[i], { cache: "no-store", credentials: "omit" }).then(function (r) {
        if (!r.ok) return next(i + 1);
        return r.json().then(function (obj) {
          if (!hostLooksSafe(obj)) return next(i + 1);
          obj._url = urls[i];
          return obj;
        }, function () { return next(i + 1); });
      }, function () { return next(i + 1); });
    }
    return next(0);
  }

  function matchingSlot(spec, digests) {
    var i;
    var pc = slotHash(spec, "pc");
    var phone = slotHash(spec, "phone");
    for (i = 0; i < digests.length; i++) {
      if (pc && digests[i] === pc) return "pc";
      if (phone && digests[i] === phone) return "phone";
    }
    return "";
  }

  function fillClaim(claim) {
    var other = document.querySelector("[name=from_other]");
    if (other && String(other.value || "").trim()) return;
    document.querySelectorAll('input[name="from"]').forEach(function (el) {
      if (el.type === "hidden") return;
      if (document.activeElement === el) {
        var cur = String(el.value || "").trim().toUpperCase();
        if (cur && cur !== claim) return;
      }
      el.value = claim;
    });
    try { sessionStorage.setItem("commons-from-session-v1", claim); } catch (e) {}
  }

  function ensureMark() {
    var host = document.getElementById("owner-mark");
    if (host) return host;
    var say = document.getElementById("say");
    if (!say || !say.parentNode) return null;
    host = document.createElement("p");
    host.id = "owner-mark";
    host.className = "law";
    say.parentNode.insertBefore(host, say);
    return host;
  }

  function paintMatch(claim, viaSlot, live) {
    var host = ensureMark();
    if (!host) return;
    host.className = "law";
    host.innerHTML = "this machine matches the " + viaSlot +
      " slot for " + claim +
      " (hashed IP, no login). from= is still a claim. " +
      (live ? "two-slot context display is LIVE; Directive 10 is HALF because richer display context remains OPEN." :
        "two-slot context display is OPEN; Directive 10's richer display context is also OPEN.") +
      ' <a href="' + assetUrl("owner-net.html") + '">owner door</a>';
  }

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function paintPanel(state, spec, digests, matchedSlot, live) {
    var panel = document.getElementById("owner-panel");
    if (!panel) return;
    var digest = (digests && digests[0]) || "";
    var via = deviceVia();
    var blob = digest ? JSON.stringify({ k: "owner-net", sha256: digest, via: via }) : "";
    setText("owner-state", state);
    setText("owner-hash", digest || "(echo unreachable this load)");
    setText("owner-json", blob || "");
    setText("owner-pc-slot", slotHash(spec, "pc") ? "set" : "empty");
    setText("owner-phone-slot", slotHash(spec, "phone") ? "set" : "empty");
    setText("owner-distinct", live ? "yes" : "no");
    setText("owner-via", via);
    var knock = document.getElementById("owner-knock-result");
    if (knock) {
      if (live && matchedSlot) {
        knock.textContent = "two-slot context display is LIVE. this machine is the " + matchedSlot +
          " slot. host-side optional context is display only and cannot control participation, reads, writes, or execution.";
      } else if (matchedSlot) {
        knock.textContent = "this machine matches the " + matchedSlot + " slot. still OPEN: need the other machine on a different public IP.";
      } else if (!digest) {
        knock.textContent = "echo missed. try again from the phone on cell or the PC at home.";
      } else {
        knock.textContent = "OPEN. empty hashes is not live. this machine is not in either slot yet.";
      }
    }
    var copyBtn = document.getElementById("owner-copy");
    if (copyBtn) copyBtn.disabled = !blob;
  }

  function paintHost(ctx) {
    var el = document.getElementById("owner-host-state");
    if (!el) return;
    if (!ctx) {
      if (el.textContent === "checking…" || !el.textContent) {
        el.textContent = "host context missed this load (fail open; not a gate)";
      }
      return;
    }
    var slot = ctx.slot ? (" slot=" + ctx.slot) : " slot=(none)";
    var digest = ctx.sha256 ? String(ctx.sha256).slice(0, 12) + "…" : "(none)";
    el.textContent = "host display " + (ctx.available ? "available" : "unavailable") +
      slot + " digest=" + digest +
      " display-only. authority false. from= stays a claim.";
  }

  function boot() {
    var panel = document.getElementById("owner-panel");
    loadSpec().then(function (spec) {
      if (!spec || spec.algo !== "sha256") {
        spec = {
          claim: ONLY_CLAIM,
          algo: "sha256",
          pepper: FALLBACK_PEPPER,
          slots: { pc: null, phone: null },
          hashes: []
        };
      }
      if (spec.claim && spec.claim !== ONLY_CLAIM) {
        if (panel) paintPanel("bad spec", spec, [], "", false);
        return;
      }
      return collectDigests(spec).then(function (digests) {
        var live = slotsDistinct(spec);
        var matchedSlot = matchingSlot(spec, digests);
        var matched = !!matchedSlot;
        if (matched) {
          fillClaim(ONLY_CLAIM);
          if (!panel) paintMatch(ONLY_CLAIM, matchedSlot || deviceVia(), live);
        }
        if ((matched || rememberedBryce()) && digests.length) {
          digests.forEach(function (h) { publishDigest(h); });
        }
        if (panel) {
          var state = live ? "TWO-SLOT CONTEXT LIVE — DISPLAY ONLY" :
            (matchedSlot ? "OPEN — this machine matches " + matchedSlot :
              "OPEN — waiting for distinct pc and phone context slots");
          paintPanel(state, spec, digests, matchedSlot, live);
        }
        return fetchHostContext(spec).then(function (ctx) {
          paintHost(ctx);
          return ctx;
        }, function () {
          paintHost(null);
          return null;
        });
      });
    }).catch(function () {
      if (panel) paintPanel("owner door missed this load", null, [], "", false);
    });
  }

  function bindCopy() {
    var btn = document.getElementById("owner-copy");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var el = document.getElementById("owner-json");
      var text = el ? String(el.textContent || "").trim() : "";
      if (!text || !navigator.clipboard) return;
      navigator.clipboard.writeText(text).catch(function () {});
    });
  }

  function bindKnock() {
    var btn = document.getElementById("owner-knock");
    if (!btn) return;
    btn.addEventListener("click", function () {
      setText("owner-knock-result", "knocking…");
      boot();
    });
  }

  function start() {
    bindCopy();
    bindKnock();
    boot();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
