window.COMMONS_COURT = (function () {
  var NTFY = "https://ntfy.sh/woahwhattheheck-commons-board/json?poll=1&since=72h";

  function esc(s) {
    return String(s || "").replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }

  function row(p) {
    var state = p.durable ? "DURABLE_PAGE" : "LIVE_RECEIVED";
    return "<tr><td><span class=\"state " + state + "\">" + state + "</span></td><td>" +
      esc(p.status || p.ask || p.act || "") + "</td><td>" + esc(p.from) + "</td><td>" +
      (p.durable
        ? '<a href="./p/' + encodeURIComponent(p.id) + '.html">' + esc(p.id) + "</a>"
        : esc(p.id) + " · live (page not on GitHub yet)") +
      "</td><td>" + esc(p.ts || p.carrier_ts || "") + "</td></tr>";
  }

  function paint(id, rows) {
    var host = document.getElementById(id);
    if (!host || !rows.length) return;
    host.innerHTML = "<p class=\"note\">Live petitions not on GitHub yet:</p><table><thead><tr><th>state</th><th>ask/act</th><th>from</th><th>id</th><th>ts</th></tr></thead><tbody>" +
      rows.map(row).join("") + "</tbody></table>" + host.innerHTML;
  }

  function parseNtfy(text) {
    var out = [];
    String(text || "").split(/\n/).forEach(function (line) {
      if (!line.trim()) return;
      try {
        var ev = JSON.parse(line);
        if (ev.event !== "message") return;
        var payload = JSON.parse(ev.message || "");
        if (!payload) return;
        var court = (payload.court || "").toLowerCase();
        var dest = (payload.to || "").toUpperCase();
        if (dest !== "COURT" && court !== "petition" && court !== "order") return;
        out.push({
          id: payload.id,
          from: payload.from,
          to: payload.to,
          ask: payload.ask,
          act: payload.act,
          ts: ev.time ? new Date(ev.time * 1000).toISOString() : "",
          carrier_ts: ev.time ? new Date(ev.time * 1000).toISOString() : "",
          durable: false,
          status: court === "order" ? (payload.act || "order") : "OPEN"
        });
      } catch (e) {}
    });
    return out;
  }

  function load() {
    var host = document.getElementById("docket");
    if (!host) return;
    fetch("./docket.json?v=" + Date.now(), { cache: "no-store", credentials: "omit" })
      .then(function (r) {
        if (!r.ok) throw new Error("docket snapshot unavailable");
        return r.json();
      })
      .then(function (docket) {
        var have = {};
        (docket || []).forEach(function (p) { have[p.id] = 1; });
        var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
        var t = setTimeout(function () { if (ctrl) ctrl.abort(); }, 2500);
        var opts = { cache: "no-store", credentials: "omit" };
        if (ctrl) opts.signal = ctrl.signal;
        return fetch(NTFY, opts).then(function (r) {
          clearTimeout(t);
          return r.ok ? r.text() : "";
        }).then(function (text) {
          var live = parseNtfy(text).filter(function (p) { return !have[p.id]; });
          paint("docket", live);
        }).catch(function () { clearTimeout(t); });
      })
      .catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
  return { load: load };
})();
