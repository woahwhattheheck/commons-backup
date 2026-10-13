(function () {
  "use strict";
  var data;
  var STRIPE_CHECKOUT_HOSTS = { "buy.stripe.com": true, "donate.stripe.com": true };
  var STRIPE_CHECKOUT_PATH = /^\/[A-Za-z0-9_-]+$/;
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c];
    });
  }
  function isStripeCheckoutUrl(raw) {
    if (typeof raw !== "string" || !raw) return false;
    var parsed;
    try {
      parsed = new URL(raw);
    } catch (err) {
      return false;
    }
    if (parsed.protocol !== "https:") return false;
    if (parsed.username || parsed.password) return false;
    if (/^https:\/\/[^/]*:\d+/i.test(raw)) return false;
    if (parsed.port !== "") return false;
    if (raw.indexOf("?") !== -1 || raw.indexOf("#") !== -1) return false;
    if (parsed.search !== "" || parsed.hash !== "") return false;
    if (!Object.prototype.hasOwnProperty.call(STRIPE_CHECKOUT_HOSTS, parsed.hostname)) return false;
    if (!STRIPE_CHECKOUT_PATH.test(parsed.pathname)) return false;
    if (parsed.href !== raw) return false;
    return true;
  }
  function hasDurableCapabilityEvidence(checkout) {
    var evidence = checkout && checkout.capability_evidence;
    if (!evidence || typeof evidence !== "object") return false;
    if (typeof evidence.reference !== "string" || !evidence.reference.trim()) return false;
    if (typeof evidence.observed_at !== "string" ||
        !/(?:Z|[+-]\d\d:\d\d)$/.test(evidence.observed_at)) return false;
    return !Number.isNaN(Date.parse(evidence.observed_at));
  }
  function termsSource(row) {
    return row.source || row.source_artifact || {};
  }
  function termsLabel(row) {
    var src = termsSource(row);
    var label = esc(src.path);
    if (Object.prototype.hasOwnProperty.call(src, "pointer")) label += "#" + esc(src.pointer);
    return label;
  }
  function checkoutAnchor(row, funnel) {
    var checkout = row.checkout;
    if (!checkout || checkout.provider !== "stripe") return "";
    if (!isStripeCheckoutUrl(checkout.url)) return "";
    if (checkout.status === "LIVEMODE_URL_RECORDED") {
      return '<p class="note">Stripe URL recorded for provenance. Payment capability is unverified, so no checkout link is exposed.</p>';
    }
    if (checkout.status !== "ACTIVE_CHARGEABLE") return "";
    if (checkout.link_active !== true || checkout.account_charges_enabled !== true) return "";
    if (checkout.account_payouts_enabled !== true) return "";
    if (!hasDurableCapabilityEvidence(checkout)) return "";
    if (funnel && funnel.readiness !== "READY_FOR_CHECKOUT") {
      return '<p class="note">Provider capability is verified, but checkout stays behind the scope-first intake until the missing terms are written.</p>';
    }
    var label = "Verified chargeable Stripe checkout";
    return '<p><a class="checkout-active" href="' + esc(checkout.url) + '" rel="noopener noreferrer" target="_blank" data-funnel-sku="' +
      esc(row.id) + '" data-funnel-action="checkout-open">' + esc(label) + '</a></p>';
  }
  function amount(component, quantity) {
    var kind = component.kind, q = Number(quantity || 0), total = 0;
    if (["fixed", "subscription", "milestone", "license"].indexOf(kind) >= 0) total = Number(component.amount || 0) * q;
    else if (["usage", "outcome", "sponsorship"].indexOf(kind) >= 0) total = Number(component.unit_amount || 0) * Math.max(0, q - Number(component.included || 0));
    else if (kind === "take_rate") total = q * Number(component.rate_bps || 0) / 10000;
    return total;
  }
  function componentText(c) {
    if (c.amount != null) return "$" + Number(c.amount).toLocaleString() + " " + esc(c.kind);
    if (c.unit_amount != null) return "$" + esc(c.unit_amount) + "/" + esc(c.meter || "unit") + " " + esc(c.kind);
    if (c.rate_bps != null) return (Number(c.rate_bps) / 100).toFixed(2) + "% " + esc(c.kind);
    return esc(c.kind);
  }
  function funnelFor(row) {
    if (!data.funnels || !Object.prototype.hasOwnProperty.call(data.funnels, row.id)) {
      throw new Error("missing funnel for " + row.id);
    }
    var funnel = data.funnels[row.id];
    var clickTruth = funnel.measurement.click_truth;
    if ((clickTruth !== "INTENT_ONLY" && clickTruth !== "NO_CLICK_SURFACE") ||
        funnel.measurement.success_state !== "BANK_AVAILABLE") {
      throw new Error("invalid funnel truth for " + row.id);
    }
    return funnel;
  }
  function itemList(items) {
    if (!items || !items.length) return '<p class="note">none</p>';
    return '<ul>' + items.map(function (item) { return '<li>' + esc(item) + '</li>'; }).join("") + '</ul>';
  }
  function intakeAnchor(row, funnel) {
    if (!funnel || funnel.qualification.route === "NONE") return "";
    var shared = funnel.qualification.route.indexOf("commerce.html#") === 0;
    var href = shared ? "#sku-intake" : "./" + funnel.qualification.route;
    return '<p><a class="funnel-intake" href="' + esc(href) + '" data-funnel-sku="' + esc(row.id) +
      '" data-funnel-action="qualification-open">Start public, non-confidential intake</a></p>';
  }
  function funnelDetails(row, funnel) {
    if (!funnel) return '<p class="note">Funnel contract unavailable.</p>';
    var next = funnel.next_offer.length ? funnel.next_offer : ["none named"];
    return '<details class="funnel"><summary>Sales funnel · priority ' + esc(funnel.priority) + ' · ' +
      esc(funnel.readiness) + '</summary>' +
      '<p><b>Buyer:</b> ' + esc(funnel.buyer) + '</p>' +
      '<p><b>Trigger:</b> ' + esc(funnel.trigger) + '</p>' +
      '<p><b>Message:</b> ' + esc(funnel.acquisition.message) + '</p>' +
      '<p><b>Primary channel:</b> ' + esc(funnel.acquisition.primary_channel) + '</p>' +
      '<p><b>Qualification:</b></p>' + itemList(funnel.qualification.required) +
      '<p><b>Conversion:</b> ' + esc(funnel.conversion.next_step) + '</p>' +
      '<p class="note">Evidence to advance: ' + esc(funnel.conversion.evidence_required) + '</p>' +
      '<p><b>Deliverables:</b></p>' + itemList(funnel.fulfillment.deliverables) +
      '<p><b>Acceptance:</b></p>' + itemList(funnel.fulfillment.acceptance) +
      '<p><b>Refund:</b> ' + esc(funnel.fulfillment.refund) + '</p>' +
      '<p><b>Next offer:</b> ' + next.map(esc).join(" · ") + '</p>' +
      '<p><b>Open gaps:</b></p>' + itemList(funnel.gaps) +
      '<p class="note">' + esc(funnel.measurement.dom_action) + ' is ' + esc(funnel.measurement.click_truth) +
      '; first durable evidence: ' + esc(funnel.measurement.first_evidence_state) +
      '; success: ' + esc(funnel.measurement.success_state) + '.</p></details>';
  }
  function renderPriority() {
    var rows = data.listings.slice().sort(function (a, b) {
      return funnelFor(a).priority - funnelFor(b).priority;
    }).slice(0, 3);
    document.getElementById("priority-offers").innerHTML = rows.map(function (row) {
      var funnel = funnelFor(row);
      return '<article class="card"><p class="note">priority ' + esc(funnel.priority) + '</p><h3>' + esc(row.name) +
        '</h3><p>' + esc(funnel.acquisition.message) + '</p><p><a href="#' + esc(row.id) + '">' + esc(funnel.acquisition.cta) + '</a></p></article>';
    }).join("");
    var truth = data.funnel_truth;
    var snapshotDate = truth.as_of ? " as of " + truth.as_of : "";
    var recordedCash = truth.collected_cash_usd == null ? "unverified" : "$" + truth.collected_cash_usd;
    document.getElementById("funnel-truth").textContent = "Recorded funnel snapshot" + snapshotDate + ": " +
      truth.distinct_targets + " distinct targets · " +
      truth.delivered_transports + " delivered transports · " + truth.verified_positive_replies +
      " verified-positive replies · " + truth.accepted_scopes + " accepted scopes · " +
      recordedCash + " recorded collected cash · current settlement: unverified · next edge: " + truth.next_edge;
  }
  function renderCatalog() {
    document.getElementById("catalog-status").textContent = data.listings.length + " adapters; source terms remain canonical.";
    var rows = data.listings.slice().sort(function (a, b) {
      return funnelFor(a).priority - funnelFor(b).priority;
    });
    document.getElementById("catalog").innerHTML = rows.map(function (row) {
      var funnel = funnelFor(row);
      return '<article class="card" id="' + esc(row.id) + '"><p class="state-' + esc(row.state) + '"><b>' + esc(row.state) + '</b></p><h3>' + esc(row.name) + '</h3>' +
        '<p class="money">' + row.pricing.components.map(componentText).join(" + ") + ' ' + esc(row.pricing.currency) + '</p>' +
        '<p>' + row.pricing.components.map(function(c){return '<span class="pill">' + esc(c.kind) + '</span>';}).join("") + '</p>' +
        '<p class="note">terms: <code>' + termsLabel(row) + '</code></p>' +
        '<p><a href="./' + esc(row.routes.human) + '" data-funnel-sku="' + esc(row.id) + '" data-funnel-action="qualification-open">human door</a> · <a href="./' + esc(row.routes.machine) + '">machine source</a></p>' +
        intakeAnchor(row, funnel) + checkoutAnchor(row, funnel) + funnelDetails(row, funnel) + '</article>';
    }).join("");
  }
  function selectIntake(sku) {
    var row = data.listings.filter(function (item) { return item.id === sku; })[0];
    if (!row || !data.funnels || !Object.prototype.hasOwnProperty.call(data.funnels, sku)) return false;
    var funnel = data.funnels[sku];
    if (!funnel.qualification || funnel.qualification.route === "NONE") return false;
    var body = document.getElementById("sku-intake-body");
    var selected = document.getElementById("sku-intake-selected");
    selected.textContent = sku;
    body.value = "PLAIN: Public, non-confidential Commons SKU purchase intent.\nOFFER_ID: " + sku +
      "\nPUBLIC_OBJECTIVE:\nPUBLIC_ARTIFACT:\nPUBLIC_CONTACT_URL:\nSTART_WINDOW:\nSELECTED_DELIVERABLE (if applicable):";
    return true;
  }
  function wireIntake() {
    Array.prototype.forEach.call(document.querySelectorAll(".funnel-intake"), function (link) {
      link.addEventListener("click", function () {
        selectIntake(link.getAttribute("data-funnel-sku"));
      });
    });
  }
  function resolveHashIntake() {
    if (!window.location.hash || window.location.hash.length < 2) return false;
    var sku;
    try {
      sku = decodeURIComponent(window.location.hash.slice(1));
    } catch (error) {
      return false;
    }
    if (!data || !data.funnels || !Object.prototype.hasOwnProperty.call(data.funnels, sku)) return false;
    var funnel = data.funnels[sku];
    if (!funnel.qualification || funnel.qualification.route !== "commerce.html#" + sku) return false;
    var target = document.getElementById(sku);
    if (!target || !selectIntake(sku)) return false;
    var intake = target.querySelector(".funnel-intake");
    if (intake) intake.focus({preventScroll: true});
    target.scrollIntoView({block: "start"});
    return true;
  }
  function renderMetrics() {
    var id = document.getElementById("listing").value;
    var row = data.listings.filter(function (x) { return x.id === id; })[0];
    var host = document.getElementById("metrics");
    host.innerHTML = row.pricing.components.map(function (c) {
      var initial = ["fixed", "subscription", "milestone", "license"].indexOf(c.kind) >= 0 ? "1" : "0";
      var label = c.kind === "take_rate" ? "gross amount" : (c.meter || c.basis || "quantity");
      return '<label>' + esc(c.id) + ' · ' + esc(c.kind) + ' · ' + esc(label) + '<input type="number" min="0" step="any" value="' + initial + '" data-component="' + esc(c.id) + '"></label>';
    }).join("");
    Array.prototype.forEach.call(host.querySelectorAll("input"), function (input) { input.addEventListener("input", calculate); });
    calculate();
  }
  function calculate() {
    var id = document.getElementById("listing").value;
    var row = data.listings.filter(function (x) { return x.id === id; })[0];
    var values = {};
    Array.prototype.forEach.call(document.querySelectorAll("#metrics input"), function (input) { values[input.getAttribute("data-component")] = input.value; });
    var total = row.pricing.components.reduce(function (sum, c) { return sum + amount(c, values[c.id]); }, 0);
    document.getElementById("total").textContent = total.toLocaleString(undefined, {style:"currency", currency:row.pricing.currency, minimumFractionDigits:2});
    document.getElementById("quote-state").textContent = "QUOTED · " + row.state + " · not authorized, settled, paid out, or bank-available";
  }
  fetch("./revenue/outcome_commerce/catalog.json?v=" + Date.now(), {cache:"no-store"}).then(function (response) {
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }).then(function (catalog) {
    data = catalog;
    renderPriority();
    renderCatalog();
    wireIntake();
    resolveHashIntake();
    var select = document.getElementById("listing");
    select.innerHTML = data.listings.map(function (row) { return '<option value="' + esc(row.id) + '">' + esc(row.name) + '</option>'; }).join("");
    select.addEventListener("change", renderMetrics);
    renderMetrics();
  }).catch(function (error) {
    document.getElementById("catalog-status").textContent = "Catalog unavailable: " + error.message;
  });
})();
