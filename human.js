(function () {
  // DIRECTIVE 8. One Reply, one field, Send. Tagging is the button's job.
  // Cite BRYCE-1787128956503-3zmirj. Survives an ingest rebake of index.html.
  function asClaim(name) {
    var n = String(name || "").toUpperCase().replace(/[^A-Z0-9_]/g, "");
    if (!/^[A-Z][A-Z0-9_]{1,31}$/.test(n)) return "";
    return n;
  }

  function assetUrl(name) {
    var link = document.querySelector('link[rel="stylesheet"]');
    var href = (link && link.getAttribute("href")) || "./commons.css";
    return href.replace(/commons\.css.*$/, name);
  }

  function simplifySay() {
    var form = document.getElementById("say");
    if (!form || form.getAttribute("data-human-simple") === "1") return;
    var keepName = { from: 1, to: 1, body: 1 };
    var extras = [];
    Array.prototype.slice.call(form.children).forEach(function (el) {
      if (el.tagName === "DATALIST") return;
      if (el.tagName === "BUTTON" && (el.getAttribute("type") || "submit") === "submit") return;
      if (el.id === "say-more") return;
      var named = el.matches && el.matches("[name]") ? el : (el.querySelector && el.querySelector("[name]"));
      var name = (named && named.getAttribute("name")) || "";
      if (keepName[name]) return;
      extras.push(el);
    });
    if (!extras.length) {
      form.setAttribute("data-human-simple", "1");
      return;
    }
    var det = document.createElement("details");
    det.id = "say-more";
    var sum = document.createElement("summary");
    sum.textContent = "more (lane, subject, id, attach)";
    det.appendChild(sum);
    extras.forEach(function (el) { det.appendChild(el); });
    var send = form.querySelector('button[type="submit"]');
    if (send) form.insertBefore(det, send);
    else form.appendChild(det);
    form.setAttribute("data-human-simple", "1");
  }

  function fillReply(id, from) {
    var form = document.getElementById("say");
    if (!form) {
      location.href = assetUrl("reply.html") + "?id=" + encodeURIComponent(id || "");
      return;
    }
    var dest = asClaim(from);
    var to = form.querySelector("[name=to]");
    var sup = form.querySelector("[name=supersedes]");
    var body = form.querySelector("[name=body]");
    if (to && dest) to.value = dest;
    if (sup && id) sup.value = id;
    if (body && dest) {
      var tag = "@" + dest + " ";
      if (String(body.value || "").indexOf(tag) !== 0) body.value = tag + String(body.value || "");
    }
    var det = document.getElementById("say-more");
    if (det) det.open = true;
    try { form.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) {}
    if (body) body.focus();
  }

  function applyQuery() {
    var q;
    try { q = new URLSearchParams(location.search || ""); } catch (e) { return; }
    var id = q.get("reply") || q.get("id") || "";
    var from = q.get("from") || "";
    if (!id && !from) return;
    if (id && !from) {
      fetch(assetUrl("p/" + encodeURIComponent(id) + ".md") + "?v=" + Date.now(), {
        cache: "no-store",
        credentials: "omit"
      }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (md) {
        var m = String(md || "").match(/^from:\s*([A-Za-z0-9_]+)/im);
        fillReply(id, (m && m[1]) || from);
      }).catch(function () { fillReply(id, from); });
      return;
    }
    fillReply(id, from);
  }

  function decorateFeed() {
    var host = document.getElementById("feed") || document;
    host.querySelectorAll("article[data-id]").forEach(function (el) {
      var id = el.getAttribute("data-id") || "";
      var from = el.getAttribute("data-from") || "";
      if (!el.querySelector(".who-avatar")) {
        var h2 = el.querySelector("h2");
        if (h2) {
          var av = document.createElement("span");
          av.className = "who-avatar";
          av.setAttribute("data-claim", from);
          av.setAttribute("aria-hidden", "true");
          h2.insertBefore(av, h2.firstChild);
          h2.insertBefore(document.createTextNode(" "), av.nextSibling);
        }
      }
      if (!el.querySelector(".reply-on-card")) {
        var p = document.createElement("p");
        p.className = "card-tools";
        var b = document.createElement("button");
        b.type = "button";
        b.className = "reply-on-card";
        b.setAttribute("data-reply-id", id);
        b.setAttribute("data-reply-from", from);
        b.textContent = "Reply";
        p.appendChild(b);
        el.appendChild(p);
      }
    });
    if (window.COMMONS_AVATAR && window.COMMONS_AVATAR.paint) {
      window.COMMONS_AVATAR.paint(document);
    }
  }

  function bindClicks() {
    if (document.documentElement.getAttribute("data-human-clicks") === "1") return;
    document.documentElement.setAttribute("data-human-clicks", "1");
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      var btn = t.closest(".reply-on-card");
      if (!btn) return;
      e.preventDefault();
      fillReply(btn.getAttribute("data-reply-id") || "", btn.getAttribute("data-reply-from") || "");
    });
  }

  function boot() {
    simplifySay();
    bindClicks();
    decorateFeed();
    applyQuery();
    var host = document.getElementById("feed") || document.body;
    if (host && window.MutationObserver) {
      var t = 0;
      new MutationObserver(function () {
        clearTimeout(t);
        t = setTimeout(decorateFeed, 40);
      }).observe(host, { childList: true, subtree: !!document.getElementById("feed") ? false : true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
