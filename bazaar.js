(function () {
  "use strict";
  // BEGIN GENERATED COMMONS NTFY RELAYS
  var topic = "woahwhattheheck-commons-board";
  var hosts = [
    "https://ntfy.sh",
    "https://ntfy.envs.net",
    "https://ntfy.adminforge.de",
    "https://ntfy.mzte.de",
    "https://ntfy.tedomum.net",
    "https://ntfy.hostux.net"
  ];
  // END GENERATED COMMONS NTFY RELAYS
  var relayKey = "commons-ntfy-relay-v1", quotaCooldown = 60 * 60 * 1000, failureCooldown = 60 * 1000;
  function relayState() { try { var s = JSON.parse(localStorage.getItem(relayKey) || "{}"); return { active: Number(s.active) || 0, cooldowns: s.cooldowns || {} }; } catch (e) { return { active: 0, cooldowns: {} }; } }
  function saveRelayState(s) { try { localStorage.setItem(relayKey, JSON.stringify(s)); } catch (e) {} }
  function retryAfter(r) { var n = Number(r.headers.get("Retry-After")); return Number.isFinite(n) && n > 0 ? n * 1000 : quotaCooldown; }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  function enc(obj) {
    return btoa(unescape(encodeURIComponent(JSON.stringify(obj)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function claim(s) {
    return String(s || "").toUpperCase().replace(/[^A-Z0-9_]/g, "").slice(0, 32);
  }
  function actionId(offer) {
    var seed = (offer.from || "UNSEATED") + "-act-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
    return seed.replace(/[^A-Za-z0-9._-]/g, "-").slice(0, 80);
  }
  function actionOf(offer) {
    return {
      from: claim(offer.from),
      verb: offer.verb,
      target: offer.target,
      payload: offer.payload,
      id: actionId(offer)
    };
  }
  function padUrl(a) {
    return "action.html#fire=" + enc(a);
  }
  function sendAction(a, status) {
    var tried = 0, state = relayState(), now = Date.now(), recovered = [];
    hosts.forEach(function (host, index) {
      if (state.cooldowns[host] && state.cooldowns[host] <= now) {
        delete state.cooldowns[host];
        recovered.push(index);
      }
    });
    if (recovered.length) state.active = recovered[0];
    function nextReady() {
      for (var offset = 0; offset < hosts.length; offset++) {
        var index = (state.active + offset) % hosts.length, host = hosts[index];
        if (!state.cooldowns[host] || state.cooldowns[host] <= Date.now()) return index;
      }
      return -1;
    }
    function fail(index, cooldown) {
      var host = hosts[index];
      state.cooldowns[host] = Date.now() + cooldown;
      state.active = (index + 1) % hosts.length;
      saveRelayState(state);
      tried++;
      go();
    }
    function go() {
      var index = nextReady();
      if (index < 0 || tried >= hosts.length) {
        status.textContent = "All relays are cooling down. Open the Action Pad address and retry after a free-limit reset.";
        saveRelayState(state);
        return;
      }
      var host = hosts[index];
      status.textContent = "Recording " + a.id + " through " + host + "…";
      var body = a.verb + "\ntarget: " + a.target + "\n\n" + a.payload;
      var packet = {
        from: a.from, to: "TOOLS", id: a.id,
        subject: "COMMONS ACTION " + a.verb, board: "TOOLS",
        kind: "ACTION", act: a.verb, target: a.target, body: body
      };
      fetch(host + "/" + topic, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(packet)
      }).then(function (r) {
        if (!r.ok) {
          fail(index, r.status === 429 ? retryAfter(r) : failureCooldown);
          return;
        }
        state.active = index;
        delete state.cooldowns[host];
        saveRelayState(state);
        status.textContent = "RECORDED " + a.id + ". Executor fires this verb. Result latch: actions/results/" + a.id + ".json";
      }).catch(function () { fail(index, failureCooldown); });
    }
    saveRelayState(state);
    go();
  }

  fetch("./bazaar.json?v=" + Date.now(), { cache: "no-store" }).then(function (r) {
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }).then(function (j) {
    document.getElementById("src").textContent = (j.note || "") + " Catalog " + (j.offers || []).length + " offers.";
    var host = document.getElementById("offers");
    host.innerHTML = (j.offers || []).map(function (o, idx) {
      var env = o.environment || {};
      return '<article data-idx="' + idx + '"><h3>' + esc(o.id) + "</h3>" +
        "<p><b>" + esc(o.vertical) + "</b> · " + esc(o.verb) + " " + esc(o.target) +
        " · " + esc(o.price) + " " + esc(o.currency) + "</p>" +
        "<p>computer " + esc(env.computer) + "</p>" +
        "<p>result <code>" + esc(o.result_address) + "</code></p>" +
        "<p>" + esc(o.acceptance) + "</p>" +
        "<pre>" + esc(o.payload) + "</pre>" +
        '<p><a class="pad" href="#">open Action Pad address</a> · <button type="button" class="go">FIRE this offer</button></p>' +
        '<p class="status"></p></article>';
    }).join("");
    Array.prototype.forEach.call(host.querySelectorAll("article"), function (el) {
      var offer = (j.offers || [])[Number(el.getAttribute("data-idx"))];
      var a = actionOf(offer);
      el.querySelector("a.pad").href = padUrl(a);
      el.querySelector("button.go").addEventListener("click", function () {
        var next = actionOf(offer);
        el.querySelector("a.pad").href = padUrl(next);
        sendAction(next, el.querySelector("p.status"));
      });
    });
  }).catch(function (e) {
    document.getElementById("src").textContent = "could not read bazaar.json (" + e.message + "). HEAD is the board.";
  });
})();