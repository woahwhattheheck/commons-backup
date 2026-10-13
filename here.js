/* here.js — this-tab presence. Figma/Docs: the page you have open is the room.
   No GPS. No invented search. Per-tab claim + browser-local presence only.
   Other machines cannot see this until a file on HEAD says so.
   Static Pages cannot see visitor IP (owner.js already says so). */
(function (g) {
  "use strict";
  var KEY_FROM = "commons-from-session-v1";
  var KEY_HERE = "commons-here";
  var CH_NAME = "commons-here";
  var ch = null;
  try { ch = new BroadcastChannel(CH_NAME); } catch (e) { ch = null; }

  function claim() {
    var from = "";
    try { from = String(g.sessionStorage.getItem(KEY_FROM) || ""); } catch (e) {}
    var inp = g.document && g.document.querySelector && g.document.querySelector("input[name=from]");
    if (inp && String(inp.value || "").trim()) from = inp.value;
    return String(from || "").toUpperCase().replace(/[^A-Z0-9_]/g, "");
  }

  function pathOf() {
    var p = String((g.location && g.location.pathname) || "/");
    var i = p.toLowerCase().lastIndexOf("/commons/");
    if (i >= 0) p = p.slice(i + 9);
    if (p.charAt(0) !== "/") p = "/" + p;
    return p || "/";
  }

  function folderOf(p) {
    p = String(p || pathOf());
    var parts = p.replace(/\\/g, "/").split("/").filter(Boolean);
    if (!parts.length) return "/";
    if (parts.length === 1) return "/";
    return "/" + parts.slice(0, -1).join("/") + "/";
  }

  function beat() {
    var rec = {
      from: claim(),
      path: pathOf(),
      folder: folderOf(pathOf()),
      href: String((g.location && g.location.href) || ""),
      ts: new Date().toISOString(),
      vis: (g.document && g.document.visibilityState) || "visible",
      src: "tab"
    };
    try { g.localStorage.setItem(KEY_HERE, JSON.stringify(rec)); } catch (e) {}
    if (ch) {
      try { ch.postMessage(rec); } catch (e) {}
    }
    g.COMMONS_HERE = rec;
    if (rec.from) onPeer(rec);
    paintChip();
    try { g.dispatchEvent(new CustomEvent("commons-here", { detail: rec })); } catch (e) {}
    return rec;
  }

  var seen = {};
  function onPeer(rec) {
    if (!rec) return;
    var key = rec.from || ("TAB:" + (rec.path || ""));
    seen[key] = rec;
    g.COMMONS_HERE_PEERS = seen;
    try { g.dispatchEvent(new CustomEvent("commons-here-peers", { detail: seen })); } catch (e) {}
  }

  function paintChip() {
    var el = g.document && g.document.getElementById("here-chip");
    if (!el) return;
    var rec = g.COMMONS_HERE;
    var pin = null;
    try {
      pin = g.COMMONS_OWNER && g.COMMONS_OWNER.readPin ? g.COMMONS_OWNER.readPin() : null;
    } catch (e) {}
    var bits = [];
    if (rec && rec.from) bits.push(rec.from);
    else bits.push("this tab (no from pin)");
    if (rec && rec.folder) bits.push("in " + rec.folder);
    if (rec && rec.path) bits.push(rec.path);
    if (pin && pin.kind) bits.push("browser pinned as owner's " + pin.kind + " — not an IP");
    else bits.push("Pages cannot see visitor IP");
    el.textContent = bits.join(" · ");
  }

  if (ch) {
    ch.onmessage = function (ev) { onPeer(ev.data); };
  }
  try {
    g.addEventListener("storage", function (ev) {
      if (ev && ev.key === KEY_HERE && ev.newValue) {
        try { onPeer(JSON.parse(ev.newValue)); } catch (e) {}
      }
    });
  } catch (e) {}

  function boot() {
    beat();
    paintChip();
    var inp = g.document.querySelector && g.document.querySelector("input[name=from]");
    if (inp) {
      inp.addEventListener("change", beat);
      inp.addEventListener("blur", beat);
    }
  }

  if (g.document) {
    g.document.addEventListener("visibilitychange", beat);
    g.addEventListener("focus", beat);
    if (g.document.readyState === "loading") {
      g.document.addEventListener("DOMContentLoaded", boot);
    } else {
      boot();
    }
    g.setInterval(function () {
      if (!g.document || g.document.visibilityState === "visible") beat();
    }, 15000);
  }

  g.COMMONS_HERE_API = {
    beat: beat,
    claim: claim,
    path: pathOf,
    folder: folderOf,
    peers: function () { return seen; }
  };
})(window);
