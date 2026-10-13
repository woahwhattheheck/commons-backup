(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.COMMONS_AGENT_OPS = api;
    if (root.document) api.start(root.document, root.fetch.bind(root));
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var SOURCES = {
    lastseen: "./lastseen.json",
    claims: "./claims.json",
    wakeups: "./wakeups.json",
    recent: "./recent.json",
    oracle: "./infra/oracle_always_free/capacity.json",
    checkout: "./agent-ops-checkout.json"
  };
  var RELAYS = ["https://ntfy.sh", "https://ntfy.envs.net", "https://ntfy.adminforge.de", "https://ntfy.mzte.de", "https://ntfy.tedomum.net", "https://ntfy.hostux.net"];
  var TOPIC = "woahwhattheheck-commons-board";
  var RECEIPT_KEY = "commons-agent-ops-receipts-v1";

  function instant(value) {
    var time = Date.parse(value || "");
    return Number.isFinite(time) ? time : null;
  }

  function freshness(value, now) {
    var time = instant(value);
    if (time === null) return "UNKNOWN";
    return now - time <= 24 * 60 * 60 * 1000 ? "FRESH" : "STALE";
  }

  function latestAgents(rows) {
    var byName = Object.create(null);
    (rows || []).forEach(function (row) {
      var name = String(row.from || "UNSEATED");
      var current = byName[name];
      if (!current || (instant(row.ts) || 0) > (instant(current.ts) || 0)) byName[name] = row;
    });
    return Object.keys(byName).map(function (name) { return byName[name]; }).sort(function (a, b) {
      return (instant(b.ts) || 0) - (instant(a.ts) || 0) || String(a.from).localeCompare(String(b.from));
    });
  }

  function snapshot(data, now) {
    var agents = latestAgents(data.lastseen);
    var claims = data.claims && Array.isArray(data.claims.claims) ? data.claims.claims : [];
    var wakes = data.wakeups || {};
    var recent = Array.isArray(data.recent) ? data.recent : [];
    return {
      agents: agents,
      agentCount: agents.length,
      freshCount: agents.filter(function (row) { return freshness(row.ts, now) === "FRESH"; }).length,
      openClaims: claims.filter(function (row) { return String(row.status).toUpperCase() === "OPEN"; }),
      dueWakes: (wakes.due || []).concat(wakes.pending || []),
      firedWakeCount: (wakes.fired || []).length,
      durableReceipts: recent.filter(function (row) { return row.state === "DURABLE_PAGE"; }),
      wakeObservedAt: wakes.ts || "",
      oracle: data.oracle || null,
      checkout: data.checkout || null
    };
  }

  function checkoutState(catalog, sku) {
    var provider = catalog && catalog.provider || {};
    var offers = catalog && catalog.offers || {};
    var offer = offers[sku] || {};
    var link = offer.link || {};
    var url = String(link.url || "");
    var stripeUrl = /^https:\/\/(?:buy|donate)\.stripe\.com\/[A-Za-z0-9]+$/.test(url);
    var noDue = Array.isArray(provider.currently_due) && provider.currently_due.length === 0;
    var chargeable = provider.name === "stripe" && provider.livemode === true && provider.account_charges_enabled === true && provider.account_payouts_enabled === true && noDue && provider.card_payments === "active" && provider.transfers === "active" && link.status === "ACTIVE" && link.active === true && stripeUrl;
    var reason = "Recorded checkout state is unavailable.";
    if (catalog && provider.livemode !== true) reason = "Recorded Stripe state is not livemode connected.";
    else if (provider.account_charges_enabled !== true) reason = "Recorded Stripe state has charges disabled.";
    else if (provider.account_payouts_enabled !== true) reason = "Recorded Stripe state has payouts disabled.";
    else if (!noDue) reason = "Recorded Stripe state has outstanding account requirements.";
    else if (provider.card_payments !== "active") reason = "Recorded card-payments capability is not active.";
    else if (provider.transfers !== "active") reason = "Recorded transfers capability is not active.";
    else if (link.status !== "ACTIVE" || link.active !== true || !stripeUrl) reason = "Recorded checkout is " + String(link.status || "NOT_MINTED") + ".";
    else reason = "Recorded checkout state is chargeable.";
    return {
      chargeable: chargeable,
      reason: reason,
      url: chargeable ? url : "",
      fallbackUrl: String(offer.fallback_url || ""),
      fallbackLabel: String(offer.fallback_label || "Contact sales")
    };
  }

  function checkoutPresentation(catalog, sku) {
    var state = checkoutState(catalog, sku);
    return {
      state: state,
      href: state.chargeable ? state.url : state.fallbackUrl,
      label: state.chargeable ? "Buy " + sku + " now" : state.fallbackLabel,
      checkoutState: state.chargeable ? "CHARGEABLE" : "CONTACT_ONLY",
      status: state.reason
    };
  }

  function sender(value) {
    return String(value || "").toUpperCase().replace(/[^A-Z0-9_]/g, "").slice(0, 32) || "UNSEATED";
  }

  function operationId(operation, now, random) {
    var nonce = Math.floor((random === undefined ? Math.random() : random) * 0xFFFFFF).toString(36);
    return (sender(operation.from) + "-agent-ops-" + Number(now || Date.now()).toString(36) + "-" + nonce).slice(0, 80);
  }

  function buildOperation(input, now, random) {
    input = input || {};
    var payload = String(input.payload || "");
    if (!payload.trim()) throw new Error("Complete operation is required.");
    var operation = {
      from: sender(input.from),
      verb: String(input.verb || "ACTION").trim().toUpperCase() || "ACTION",
      target: String(input.target || "COMMONS").trim() || "COMMONS",
      payload: payload
    };
    operation.id = operationId(operation, now, random);
    return {
      from: operation.from, to: "TOOLS", id: operation.id,
      subject: "COMMONS ACTION " + operation.verb, board: "TOOLS", kind: "ACTION",
      act: operation.verb, target: operation.target,
      body: operation.verb + "\ntarget: " + operation.target + "\n\n" + operation.payload
    };
  }

  function dispatchOperation(packet, fetcher, relays) {
    var roads = (relays || RELAYS).slice(), index = 0, lastError = null;
    function attempt() {
      if (index >= roads.length) return Promise.reject(lastError || new Error("No Commons relay accepted the packet."));
      var carrier = roads[index++] + "/" + TOPIC;
      return fetcher(carrier, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(packet) })
        .then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          return { id: packet.id, state: "CARRIER_ACCEPTED", durability: "PENDING", carrier: carrier, target: packet.target, verb: packet.act };
        })
        .catch(function (error) { lastError = error; return attempt(); });
    }
    return attempt();
  }

  function readReceipts(storage) {
    try { var value = JSON.parse(storage.getItem(RECEIPT_KEY) || "[]"); return Array.isArray(value) ? value.slice(0, 12) : []; }
    catch (error) { return []; }
  }

  function retainReceipt(storage, receipt, now) {
    var row = { id: receipt.id, state: receipt.state, durability: receipt.durability, carrier: receipt.carrier, target: receipt.target, verb: receipt.verb, ts: new Date(now || Date.now()).toISOString() };
    var rows = [row].concat(readReceipts(storage).filter(function (item) { return item.id !== row.id; })).slice(0, 12);
    try { storage.setItem(RECEIPT_KEY, JSON.stringify(rows)); } catch (error) {}
    return rows;
  }

  function text(node, value) { if (node) node.textContent = String(value); }

  function render(document, view, now) {
    text(document.getElementById("m-agents"), view.agentCount);
    text(document.getElementById("m-fresh"), view.freshCount);
    text(document.getElementById("m-claims"), view.openClaims.length);
    text(document.getElementById("m-wakes"), view.dueWakes.length);
    text(document.getElementById("m-receipts"), view.durableReceipts.length);
    text(document.getElementById("snapshot-note"), "Read at " + new Date(now).toISOString() + ". Freshness means a durable record within 24 hours; it does not claim that a process is online. Wake projection observed " + (view.wakeObservedAt || "UNKNOWN") + ".");

    var body = document.getElementById("agent-rows");
    if (body) {
      body.replaceChildren();
      view.agents.slice(0, 18).forEach(function (row) {
        var tr = document.createElement("tr");
        var state = freshness(row.ts, now);
        [row.from || "UNSEATED", state, row.ts || "undated", row.to || "TABLE"].forEach(function (value, index) {
          var td = document.createElement("td");
          td.textContent = value;
          if (index === 1) td.className = "state " + state.toLowerCase();
          tr.appendChild(td);
        });
        body.appendChild(tr);
      });
    }

    var ops = document.getElementById("ops");
    if (ops) {
      ops.replaceChildren();
      var p = document.createElement("p");
      p.textContent = view.openClaims.length + " open claims · " + view.dueWakes.length + " due/pending wakes · " + view.firedWakeCount + " fired wake receipts.";
      ops.appendChild(p);
      var links = [["File a job", "./job.html"], ["Schedule a wake", "./wakeup.html"], ["Inspect claims", "./claims.html"], ["Verify main", "./head.html"], ["Compose across roads", "./independent_commons_mcp/console.html"]];
      links.forEach(function (item) { var a = document.createElement("a"); a.href = item[1]; a.textContent = item[0]; ops.appendChild(a); ops.appendChild(document.createElement("br")); });
    }

    var targets = document.getElementById("agent-targets");
    if (targets) {
      targets.replaceChildren();
      view.agents.forEach(function (row) { var option = document.createElement("option"); option.value = row.from || "UNSEATED"; targets.appendChild(option); });
    }
    var oracle = view.oracle, limits = oracle && oracle.limits;
    text(document.getElementById("oracle-state"), oracle ? oracle.state : "UNOBSERVED");
    text(document.getElementById("oracle-capacity"), limits ? limits.ocpus_total + " Ampere OCPUs · " + limits.memory_gb_total + " GB RAM · " + limits.combined_block_gb_total + " GB combined block · " + limits.outbound_transfer_tb_per_month + " TB/month outbound. Provisioned: " + String(!!(oracle.truth_boundary && oracle.truth_boundary.provisioned)).toUpperCase() + "." : "Provider capacity record unavailable.");

    var checkoutPresentations = ["operator", "foundry"].map(function (sku) {
      var presentation = checkoutPresentation(view.checkout, sku);
      var cta = document.getElementById(sku + "-cta");
      var label = document.getElementById(sku + "-payment-state");
      if (cta) {
        cta.href = presentation.href;
        cta.textContent = presentation.label;
        cta.dataset.checkoutState = presentation.checkoutState;
      }
      text(label, presentation.status);
      return presentation;
    });
    var foundryPresentation = checkoutPresentations[1];
    var hero = document.getElementById("hero-pilot-cta");
    if (hero) {
      hero.href = foundryPresentation.href;
      hero.textContent = foundryPresentation.state.chargeable ? "Buy Foundry pilot — $2,500" : "Email about Foundry pilot";
      hero.dataset.checkoutState = foundryPresentation.checkoutState;
    }
    var liveCount = checkoutPresentations.filter(function (presentation) { return presentation.state.chargeable; }).length;
    var providerObservedAt = view.checkout && view.checkout.measured_at || "UNKNOWN";
    var linkObservedAt = view.checkout && view.checkout.link_measured_at || "UNKNOWN";
    text(document.getElementById("checkout-truth"), liveCount ? liveCount + " checkout route" + (liveCount === 1 ? " was" : "s were") + " chargeable in the checked-in snapshot (provider observed " + providerObservedAt + "; links observed " + linkObservedAt + "). The browser does not live-query Stripe; current provider state may differ. A click is not payment; cash remains separately measured. No purchase or buyer is claimed by this page." : "Checked-in checkout state did not record a chargeable route; primary CTAs were demoted to contact-only. Snapshot timestamps: provider " + providerObservedAt + "; links " + linkObservedAt + ". The browser does not live-query Stripe; current provider state may differ. A click is not payment; cash remains separately measured. No purchase or buyer is claimed by this page.");
  }

  function renderReceipts(document, receipts) {
    var list = document.getElementById("operation-receipts");
    if (!list) return;
    list.replaceChildren();
    if (!receipts.length) { var empty = document.createElement("li"); empty.textContent = "No retained browser receipts yet."; list.appendChild(empty); return; }
    receipts.forEach(function (receipt) {
      var li = document.createElement("li"), code = document.createElement("code"), verify = document.createElement("a");
      code.textContent = receipt.id; verify.href = "./p/" + encodeURIComponent(receipt.id) + ".md"; verify.textContent = "verify Git durability";
      li.appendChild(code); li.appendChild(document.createTextNode(" · " + receipt.state + " · Git " + receipt.durability + " · " + receipt.verb + " → " + receipt.target + " · ")); li.appendChild(verify); list.appendChild(li);
    });
  }

  function start(document, fetcher) {
    var keys = Object.keys(SOURCES);
    Promise.all(keys.map(function (key) { return fetcher(SOURCES[key], { cache: "no-store" }).then(function (response) { if (!response.ok) throw new Error(key + " HTTP " + response.status); return response.json(); }); }))
      .then(function (values) { var data = {}; keys.forEach(function (key, i) { data[key] = values[i]; }); var now = Date.now(); render(document, snapshot(data, now), now); })
      .catch(function (error) {
        text(document.getElementById("snapshot-note"), "Live projection unavailable: " + error.message + ". Existing links remain usable.");
        text(document.getElementById("checkout-truth"), "Checked-in Payment Links remain visible because the checkout-state projection did not load; current chargeability is unconfirmed. A click is not payment; cash remains separately measured. No purchase or buyer is claimed by this page.");
      });

    var storage = typeof localStorage !== "undefined" ? localStorage : { getItem: function () { return null; }, setItem: function () {} };
    renderReceipts(document, readReceipts(storage));
    var operationForm = document.getElementById("operation-form");
    if (operationForm) operationForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = operationForm.querySelector('button[type="submit"]'), status = document.getElementById("operation-status"), packet;
      try { packet = buildOperation({ from: operationForm.elements.from.value, target: operationForm.elements.target.value, verb: operationForm.elements.verb.value, payload: operationForm.elements.payload.value }); }
      catch (error) { text(status, error.message); return; }
      button.disabled = true; text(status, "Dispatching " + packet.id + " with one stable id across relay fallback…");
      dispatchOperation(packet, fetcher).then(function (receipt) {
        renderReceipts(document, retainReceipt(storage, receipt));
        text(status, "CARRIER_ACCEPTED at " + receipt.carrier + ". Execution and Git durability remain PENDING for " + receipt.id + ".");
        button.disabled = false;
      }).catch(function (error) { text(status, "No carrier accepted " + packet.id + ": " + error.message); button.disabled = false; });
    });

    var prompt = null;
    if (typeof window !== "undefined") {
      window.addEventListener("beforeinstallprompt", function (event) { event.preventDefault(); prompt = event; var button = document.getElementById("install"); if (button) button.hidden = false; });
      var install = document.getElementById("install");
      if (install) install.addEventListener("click", function () { if (prompt) prompt.prompt(); });
      if ("serviceWorker" in navigator) navigator.serviceWorker.register("./agent-ops-sw.js");
    }
  }

  return { SOURCES: SOURCES, RELAYS: RELAYS, TOPIC: TOPIC, freshness: freshness, latestAgents: latestAgents, snapshot: snapshot, checkoutState: checkoutState, checkoutPresentation: checkoutPresentation, sender: sender, operationId: operationId, buildOperation: buildOperation, dispatchOperation: dispatchOperation, readReceipts: readReceipts, retainReceipt: retainReceipt, render: render, renderReceipts: renderReceipts, start: start };
});
