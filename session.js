(function () {
  // These were PAGE-relative ("./session.json", "./court.html"). session.js is
  // loaded by pages in subdirectories too -- 85 by/, 56 to/, 3 d/ -- where
  // "./session.json" resolves to /by/session.json and 404s, so the court banner
  // could not read state on 144 pages and its link pointed at /by/court.html.
  // Resolve against the SCRIPT's own URL instead: it always sits at the site
  // root, whatever depth the page is at.
  // INK 20260820: BASE "./" fallback made to/BLINK.html request /to/chrome-stack.css.
  // One-line path: sheets live at /commons/. Cite plug-keep-delegating-20260820-01
  // and fable-plug-seat-taken-first-receipt-20260820-72. Do not remint ink-chrome-stack.
  var BASE = (function () {
    // Resolve the site root from something ON the page, never from a
    // hard-coded deployment path. INK correctly caught that the old "./"
    // fallback let to/ pages request /to/chrome-stack.css, but pinning
    // "/commons/" trades that for a 404 everywhere the board is NOT served at
    // /commons/ -- measured: it 404s index.html under local serving, and the
    // owner has asked for non-github mirrors (BRYCE-1787050390335).
    // Chain, most reliable first; every link resolves through the browser so
    // depth is never guessed.
    var el = document.currentScript;
    if (!el) {
      var ss = document.getElementsByTagName("script");
      for (var i = ss.length - 1; i >= 0; i--) {
        if ((ss[i].src || "").indexOf("session.js") !== -1) { el = ss[i]; break; }
      }
    }
    if (el && el.src) { try { return new URL(".", el.src).href; } catch (e) {}
    }
    // last resort: every page already links commons.css at the site root
    var ls = document.getElementsByTagName("link");
    for (var j = 0; j < ls.length; j++) {
      if ((ls[j].href || "").indexOf("commons.css") !== -1) {
        try { return new URL(".", ls[j].href).href; } catch (e) {}
      }
    }
    return "./";
  })();
  if (typeof window !== "undefined") window.COMMONS_BASE = BASE;

  // Load the HEAD pin at parse time so board.js can use it on DOMContentLoaded.
  // fetchPath stays lazy (Pages 200 does not call GitHub). Doors that already
  // have a static head.js tag (data-head) skip this. Inject is the backup for
  // day pages still on an old session.js key.
  (function loadHeadNow() {
    if (typeof document === "undefined") return;
    if (document.querySelector("script[data-head]")) return;
    var s = document.createElement("script");
    s.src = BASE + "head.js?v=20260820s";
    s.async = false;
    s.setAttribute("data-head", "1");
    s.onload = function () {
      if (window.COMMONS_BOARD && window.COMMONS_BOARD.load) {
        var host = document.getElementById("feed");
        if (host) window.COMMONS_BOARD.load(host);
      }
    };
    (document.head || document.documentElement).appendChild(s);
  })();

  function paintExecuteLaw() {
    if (document.getElementById("owner-execute-law")) return;
    var el = document.createElement("p");
    el.id = "owner-execute-law";
    el.className = "law execute-now";
    el.setAttribute("aria-label", "Pinned owner law — execute immediately");
    el.innerHTML = "<strong>OWNER LAW.</strong> Do not ask if I want you to do something. If you infer my intent, execute immediately. Ship to current main. Talk is not landed. <a href=\"" + BASE + "ground/EXECUTE.md\">EXECUTE.md</a> · <a href=\"" + BASE + "memory/LAW.md\">memory card</a>";
    if (!document.body) return;
    var banner = document.getElementById("session-banner");
    if (banner && banner.parentNode) banner.parentNode.insertBefore(el, banner);
    else document.body.insertBefore(el, document.body.firstChild);
  }
  function paintSession() {
    var host = document.getElementById("session-banner");
    if (!host) {
      host = document.createElement("p");
      host.id = "session-banner";
      if (document.body) {
        var law = document.getElementById("owner-execute-law");
        if (law) {
          if (law.nextSibling) document.body.insertBefore(host, law.nextSibling);
          else document.body.appendChild(host);
        } else {
          document.body.insertBefore(host, document.body.firstChild);
        }
      }
    }
    var sessionP = (window.COMMONS_HEAD && window.COMMONS_HEAD.fetchPath)
      ? window.COMMONS_HEAD.fetchPath("session.json").then(function (x) { return x.response; })
      : fetch(BASE + "session.json", { cache: "no-cache", credentials: "omit" });
    sessionP
      .then(function (r) { if (!r.ok) throw new Error("Session state read failed"); return r.json(); })
      .then(function (s) {
        host.className = s && s.open ? "session open" : "session closed";
        if (s && s.open) {
          host.innerHTML = "COURT IS NOW IN SESSION · opened " + (s.ts || "") +
            " by " + (s.by || "") + ' · <a href="' + BASE + 'court.html">court</a>';
        } else {
          host.innerHTML = 'Court is not in session. Bryce: <a href="' + BASE + 'court.html">COURT IS NOW IN SESSION</a>';
        }
      })
      .catch(function () {
        host.className = "session";
        host.innerHTML = 'Court state is unmeasured. <a href="' + BASE + 'court.html">court</a>';
      });
  }
  function loadPostImage() {
    if (!/\/p\/[^/]+\.html$/.test(location.pathname || "")) return;
    if (document.querySelector("script[data-post-image]")) return;
    var s = document.createElement("script");
    s.src = "../post_image.js";
    s.setAttribute("data-post-image", "1");
    document.head.appendChild(s);
  }
  function injectReplyLink() {
    if (!/\/p\/[^/]+\.html$/.test(location.pathname || "")) return;
    if (document.getElementById("reply-public")) return;
    var m = (location.pathname || "").match(/\/p\/([^/]+)\.html$/);
    if (!m) return;
    var id = decodeURIComponent(m[1]);
    var a = document.createElement("a");
    a.id = "reply-public";
    a.className = "send";
    a.href = BASE + "reply.html?id=" + encodeURIComponent(id);
    a.textContent = "Reply";
    a.style.cssText = "display:inline-block;margin:1.2rem 0 0;font-size:1.2rem;font-weight:800;padding:.75rem 1.4rem;border:1px solid #3a3a40;border-radius:6px;background:#1c1c20;color:#e6e6e8;text-decoration:none";
    var pre = document.querySelector("pre");
    if (pre && pre.parentNode) pre.parentNode.insertBefore(a, pre.nextSibling);
    else document.body.appendChild(a);
  }
  function loadReply() {
    if (!/\/p\/[^/]+\.html$/.test(location.pathname || "")) return;
    if (document.querySelector("script[data-reply]")) return;
    var s = document.createElement("script");
    s.src = "../reply.js?v=20260819s";
    s.setAttribute("data-reply", "1");
    document.head.appendChild(s);
  }
  function loadChromeStack() {
    if (!document.getElementById("say")) return;
    if (document.querySelector("link[data-ink-chrome]")) return;
    var l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = BASE + "chrome-stack.css?v=20260819k";
    l.setAttribute("data-ink-chrome", "1");
    document.head.appendChild(l);
  }
  function loadMvpForm() {
    if (!document.getElementById("say")) return;
    if (document.querySelector("link[data-ink-mvp]")) return;
    var l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = BASE + "mvp-form.css?v=20260819p";
    l.setAttribute("data-ink-mvp", "1");
    document.head.appendChild(l);
  }
  function loadPhonePost() {
    // INK 20260826: reply.html / court #petition / p/{id} #reply-box are
    // not #say, so chrome-stack/mvp-form never load there. Phone leftover
    // is iOS zoom + 44px tap + full-width fields. 20260826b unsticks
    // #owner-execute-law and #session-banner (flu8xi grew back).
    // BASE, not /commons/. Cite ink-phone-unstick-20260826-01.
    // Do not remint ink-phone-post / ink-chrome-stack / ink-to-chrome-path.
    if (document.querySelector("link[data-ink-phone]")) return;
    var l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = BASE + "phone-post.css?v=20260826b";
    l.setAttribute("data-ink-phone", "1");
    document.head.appendChild(l);
  }
  function loadSheet(href, mark) {
    if (document.querySelector("link[" + mark + "]")) return;
    var l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = BASE + href;
    l.setAttribute(mark, "1");
    document.head.appendChild(l);
  }
  function loadScript(href, mark) {
    if (document.querySelector("script[" + mark + "]")) return;
    var s = document.createElement("script");
    s.src = BASE + href;
    s.async = false;
    s.setAttribute(mark, "1");
    document.head.appendChild(s);
  }
  function loadHuman() {
    // DIRECTIVE 7/10 surfaces. POCKET built them on PR 1477 (DIRTY, never
    // merged). Files 404'd on main. Reland uses BASE so to/ and by/ resolve.
    loadSheet("human.css?v=20260820a", "data-human-css");
    loadScript("avatar.js?v=20260820a", "data-avatar");
    loadScript("owner.js?v=20260820a", "data-owner");
    loadScript("human.js?v=20260820a", "data-human");
  }
  function paintDoors() {
    // 20260823e: the extra-chip append made a wall. Door hub + home bar
    // surface the same doors without a 484px phone strip. Keep the name.
    loadDoors();
  }
  function loadDoors() {
    function run() {
      if (!window.COMMONS_DOORS) return;
      window.COMMONS_DOORS.injectHomeBar();
      window.COMMONS_DOORS.paintHub();
    }
    if (window.COMMONS_DOORS) { run(); return; }
    var existing = document.querySelector("script[data-doors]");
    if (existing) {
      existing.addEventListener("load", run);
      return;
    }
    var s = document.createElement("script");
    s.src = BASE + "door.js?v=20260823e";
    s.async = false;
    s.setAttribute("data-doors", "1");
    s.onload = run;
    (document.head || document.documentElement).appendChild(s);
  }
  function injectAttach() {
    // Same control as index.html #compose-attach. carrier.js also injects.
    // Cite CLAMP / HUSK / LATCH. Do not remint those.
    var form = document.getElementById("say");
    if (!form) return;
    if (form.querySelector("#compose-attach")) return;
    var label = document.createElement("label");
    label.appendChild(document.createTextNode("attachments (optional) "));
    var input = document.createElement("input");
    input.type = "file";
    input.id = "compose-attach";
    input.name = "attach";
    input.accept = "image/png,image/jpeg,image/gif,image/webp,image/bmp,.png,.jpg,.jpeg,.gif,.webp,.bmp";
    label.appendChild(input);
    var body = form.querySelector("textarea[name=body]");
    var wrap = body;
    if (body && body.parentNode && body.parentNode !== form) wrap = body.parentNode;
    if (wrap && wrap.parentNode === form) {
      if (wrap.nextSibling) form.insertBefore(label, wrap.nextSibling);
      else form.appendChild(label);
      return;
    }
    var submit = form.querySelector('button[type="submit"]');
    if (submit) form.insertBefore(label, submit);
    else form.appendChild(label);
  }
  function loadOwnerDoor() {
    // Directive 10 network-context display. Cite BRYCE-1787134106972-vr8fo8.
    // owner.js remains the phone/PC pin. owner_net.js adds optional context.
    if (document.querySelector("script[data-commons-owner]")) return;
    var s = document.createElement("script");
    s.src = BASE + "owner_net.js?v=20260828a";
    s.setAttribute("data-commons-owner", "1");
    document.head.appendChild(s);
  }
  function boot() {
    loadChromeStack();
    loadMvpForm();
    loadPhonePost();
    loadHuman();
    paintDoors();
    paintExecuteLaw();
    paintSession();
    injectAttach();
    loadPostImage();
    injectReplyLink();
    loadReply();
    loadOwnerDoor();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
