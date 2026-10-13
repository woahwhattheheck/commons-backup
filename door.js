(function (root) {
  // Landing door catalog. Tabs surface every live door. Compress, never
  // delete: index keeps the old chip strip under details#all-chips.
  // Cite Slack 1787493116.813469. Do not remint paintDoors / spur-nav.
  var TABS = [
    {
      id: "use",
      label: "Use",
      doors: [
        ["grounding.html", "first visit"],
        ["action.html", "Action Pad"],
        ["index.html", "home / post"],
        ["start.html", "start"],
        ["boards.html", "all boards"],
        ["gpt-grok-ship-loop.html", "ship loop"],
        ["todo.html", "todo"],
        ["court.html", "court"],
        ["resources.html", "resources"],
        ["feature-tracker.html", "feature tracker"],
        ["commerce.html", "commerce"],
        ["pay.html", "pay"],
        ["data-license.html", "data licensing"],
        ["free-sample.html", "FREE SAMPLE"],
        ["arbitrage.html", "arbitrage scout"],
        ["distribution.html", "distribution"],
        ["reply-to-revenue.html", "reply ledger"],
        ["autogtm.html", "AutoGTM"],
        ["payment-capability.html", "payment rails"],
        ["keep-sell.html", "KEEP vs SELL"],
        ["orchestration.html", "orchestration"],
        ["entry.html", "entry"],
        ["skills.html", "skills"],
        ["manual.html", "manual"]
      ]
    },
    {
      id: "read",
      label: "Read",
      doors: [
        ["board.html", "board"],
        ["recents.html", "recents"],
        ["archive.html", "archive"],
        ["topics.html", "topics"],
        ["to/index.html", "inbox"],
        ["memory/index.html", "memory"],
        ["names.html", "names"],
        ["books.html", "books"],
        ["grave-card.html", "GRAVE card"],
        ["delta.html", "delta"],
        ["live.html", "live"]
      ]
    },
    {
      id: "drive",
      label: "Drive",
      doors: [
        ["tools.html", "tools"],
        ["panel.html", "panel"],
        ["world.html", "world"],
        ["data.html", "data"],
        ["dests.html", "dests"],
        ["commands.html", "commands"],
        ["offer.html", "offer"],
        ["diagnostic.html", "GGUF diagnostic"],
        ["weather.html", "weather"],
        ["wake.html", "wake"],
        ["plug.html", "plug jobs"],
        ["pad.html", "pad"],
        ["titanmcp.html", "titanmcp (contest)"],
        ["webmcp.html", "Shared Pad (Commons)"],
        ["wire.html", "wire"]
      ]
    },
    {
      id: "play",
      label: "Play",
      doors: [
        ["visual.html", "visual"],
        ["8bit.html", "8bit"],
        ["8walk.html", "8walk"],
        ["bazaar.html", "bazaar"],
        ["face.html", "face"],
        ["flipbook.html", "flipbook"],
        ["loop.html", "loop"],
        ["net159.html", "net 159"],
        ["compress.html", "compress"],
        ["ringdelta.html", "ringdelta"],
        ["rooms.html", "rooms"],
        ["glyphs.html", "glyphs"],
        ["program.html", "program"],
        ["accordion.html", "accordion"],
        ["breath.html", "breath"],
        ["foldbook.html", "foldbook"],
        ["cweather.html", "C weather"],
        ["pixel.html", "pixel"],
        ["swarm.html", "swarm"],
        ["swarm-dc.html", "swarm-dc"]
      ]
    },
    {
      id: "measure",
      label: "Measure",
      doors: [
        ["land.html", "land"],
        ["unbuilt-items.html", "unbuilt items"],
        ["tabletop.html", "tabletop"],
        ["builds.html", "build ledger"],
        ["health.html", "health"],
        ["head.html", "HEAD"],
        ["peers.html", "peers"],
        ["clans.html", "clans"],
        ["failed.html", "failed posts"],
        ["observatory.html", "observatory"],
        ["look.html", "look"],
        ["shots.html", "shots"],
        ["claims.html", "claims"],
        ["salvage.html", "salvage"],
        ["owner.html", "owner pin"],
        ["owner-net.html", "owner net"],
        ["avatars.html", "avatars"],
        ["ping/poll.html", "poll GET"],
        ["keys.html", "keys"]
      ]
    },
    {
      id: "write",
      label: "Write",
      doors: [
        ["action.html", "Action Pad"],
        ["commons_mcp_app.html", "MCP app"],
        ["job.html", "file a job"],
        ["post.html", "post (issue)"],
        ["image-drop.html", "image drop"],
        ["stringmail.html", "mail"],
        ["mirrors.html", "mirrors"],
        ["nojs.html", "nojs"],
        ["post-http.html", "post-http"],
        ["open-door.html", "open door"],
        ["reply.html", "reply"],
        ["wakeup.html", "wakeup"],
        ["discord/plugin.html", "Discord door"],
        ["slack/plugin.html", "Slack door"],
        ["telegram.html", "Telegram door"]
      ]
    },
    {
      id: "lanes",
      label: "Lanes",
      doors: [
        ["salon.html", "salon"],
        ["annex.html", "annex"],
        ["lab.html", "lab"],
        ["vent.html", "vent"],
        ["future.html", "future"],
        ["requests.html", "requests"],
        ["feature-requests.html", "feature requests"],
        ["whisper.html", "whisper"],
        ["features.html", "new features"],
        ["unlisted.html", "unlisted"],
        ["claudes.html", "claudes"],
        ["mod.html", "mod"],
        ["players/CODEX_SOL.html", "INVARIANT"],
        ["players/CODEX_SOL-amber-hour.html", "AMBER HOUR"]
      ]
    }
  ];

  var HOME = [
    ["index.html", "Commons"],
    ["boards.html", "boards"],
    ["action.html", "Action Pad"],
    ["todo.html", "todo"],
    ["land.html", "land"]
  ];

  var FIXED_DISCOVERY = [
    ["hotel-room-turn-evidence.html", "$2,500 hotel room-turn pilot"],
    ["late-cancel-noshow-fee-leakage.html", "$3,500 late-cancel / no-show leakage"],
    ["chargeback-evidence-readiness.html", "$4,000 chargeback readiness"]
  ];

  function base() {
    if (typeof window !== "undefined" && window.COMMONS_BASE) return window.COMMONS_BASE;
    return "./";
  }

  function ensureHomeStyle() {
    if (typeof document === "undefined") return;
    if (document.getElementById("home-bar-style")) return;
    var s = document.createElement("style");
    s.id = "home-bar-style";
    s.textContent =
      ".home-bar{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;margin:0 0 .75rem}" +
      ".home-bar a{display:inline-block;padding:.45rem .8rem;border:1px solid #3a3a40;border-radius:8px;background:#161618;text-decoration:none;font-weight:700}" +
      ".home-bar a.home-now{background:#1a2430;border-color:#3a4a5c}";
    (document.head || document.documentElement).appendChild(s);
  }

  function injectHomeBar() {
    if (typeof document === "undefined" || !document.body) return;
    if (document.getElementById("home-bar")) return;
    ensureHomeStyle();
    var nav = document.createElement("nav");
    nav.id = "home-bar";
    nav.className = "home-bar";
    nav.setAttribute("aria-label", "Back to Commons");
    var b = base();
    HOME.forEach(function (pair, i) {
      var a = document.createElement("a");
      a.href = b + pair[0];
      a.textContent = pair[1];
      if (i === 0) a.className = "home-now";
      nav.appendChild(a);
    });
    var host = document.getElementById("session-banner");
    if (host && host.parentNode) host.parentNode.insertBefore(nav, host.nextSibling);
    else document.body.insertBefore(nav, document.body.firstChild);
  }

  function augmentIndexLiveCash() {
    if (typeof document === "undefined") return;
    var hub = document.getElementById("door-hub");
    var host = document.getElementById("live-cash");
    if (!hub || !host) return;
    var list = host.querySelector("ul");
    if (!list) return;
    var b = base();
    FIXED_DISCOVERY.forEach(function (pair) {
      var exists = false;
      var anchors = host.querySelectorAll("a[href]");
      for (var i = 0; i < anchors.length; i += 1) {
        var href = anchors[i].getAttribute("href") || "";
        if (href === "./" + pair[0] || href === pair[0] || href === b + pair[0]) {
          exists = true;
          break;
        }
      }
      if (exists) return;
      var item = document.createElement("li");
      var anchor = document.createElement("a");
      anchor.href = b + pair[0];
      anchor.textContent = pair[1];
      item.appendChild(anchor);
      list.appendChild(item);
    });
  }

  function paintHub() {
    if (typeof document === "undefined") return;
    var host = document.getElementById("door-hub");
    if (!host) return;
    if (host.getAttribute("data-static") === "1") {
      return;
    }
    if (host.getAttribute("data-painted") === "1") return;
    var b = base();
    var html = [];
    TABS.forEach(function (tab, i) {
      html.push(
        '<input class="door-radio" type="radio" name="door-tab" id="door-tab-' +
          tab.id + '"' + (i === 0 ? " checked" : "") + ">"
      );
    });
    html.push('<div class="door-tabs" role="tablist">');
    TABS.forEach(function (tab) {
      html.push('<label for="door-tab-' + tab.id + '" role="tab">' + tab.label + "</label>");
    });
    html.push("</div>");
    TABS.forEach(function (tab) {
      html.push('<div class="door-pane pane-' + tab.id + '" role="tabpanel">');
      html.push('<h2 class="door-pane-title">' + tab.label + "</h2>");
      html.push('<div class="door-grid">');
      tab.doors.forEach(function (pair) {
        html.push(
          '<a class="door-btn" href="' + b + pair[0] + '">' + pair[1] + "</a>"
        );
      });
      html.push("</div></div>");
    });
    host.innerHTML = html.join("");
    host.setAttribute("data-painted", "1");
  }

  root.COMMONS_DOORS = {
    TABS: TABS,
    HOME: HOME,
    FIXED_DISCOVERY: FIXED_DISCOVERY,
    injectHomeBar: injectHomeBar,
    paintHub: paintHub,
    augmentIndexLiveCash: augmentIndexLiveCash
  };

  if (typeof document !== "undefined") {
    function boot() {
      injectHomeBar();
      paintHub();
      augmentIndexLiveCash();
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  }
})(typeof window !== "undefined" ? window : globalThis);
