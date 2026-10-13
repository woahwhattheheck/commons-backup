(function () {
  "use strict";
  var STRIPE_CHECKOUT_HOSTS = { "buy.stripe.com": true, "donate.stripe.com": true };
  var STRIPE_CHECKOUT_PATH = /^\/[A-Za-z0-9_-]+$/;
  var FIXED_BUY_PRODUCTS = [
    { path: "./hotel-room-turn-evidence.html", label: "Buy hotel pilot" },
    { path: "./late-cancel-noshow-fee-leakage.html", label: "Buy fee-leakage diagnostic" },
    { path: "./chargeback-evidence-readiness.html", label: "Buy chargeback desk" }
  ];
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      if (c === "&") return "&amp;";
      if (c === "<") return "&lt;";
      if (c === ">") return "&gt;";
      if (c === '"') return "&quot;";
      return "&#39;";
    });
  }
  function isStripeCheckoutUrl(raw) {
    if (typeof raw !== "string" || !raw) return false;
    var parsed;
    try { parsed = new URL(raw); } catch (err) { return false; }
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
    if (typeof evidence.observed_at !== "string" || !/(?:Z|[+-]\d\d:\d\d)$/.test(evidence.observed_at)) return false;
    return !Number.isNaN(Date.parse(evidence.observed_at));
  }
  function canonicalRailMatches(snapshot, listing) {
    var checkout = listing && listing.checkout;
    var sku = listing && listing.id;
    var capability = checkout && checkout.capability_evidence;
    if (typeof sku !== "string" || !sku || !checkout || !capability) return false;
    var rails = snapshot && Array.isArray(snapshot.canonical_rails) ? snapshot.canonical_rails : [];
    var snapshotEvidence = snapshot && snapshot.evidence && typeof snapshot.evidence === "object" ? snapshot.evidence : {};
    for (var i = 0; i < rails.length; i += 1) {
      var rail = rails[i];
      if (!rail || typeof rail !== "object") continue;
      if (rail.sku !== sku || rail.url !== checkout.url) continue;
      if (rail.link_active !== true || rail.livemode !== true) continue;
      if (rail.exposure !== "CHECKOUT_FIRST" && rail.exposure !== "INTAKE_FIRST") continue;
      var evidence = rail.evidence && typeof rail.evidence === "object" ? rail.evidence : {
        reference: snapshotEvidence.reference,
        observed_at: snapshot && snapshot.observed_at
      };
      if (evidence.reference !== capability.reference) continue;
      if (evidence.observed_at !== capability.observed_at) continue;
      return true;
    }
    return false;
  }
  function accountReady(snapshot) {
    var provider = snapshot && snapshot.provider || {};
    return provider.name === "stripe" &&
      provider.livemode === true &&
      provider.charges_enabled === true &&
      provider.payouts_enabled === true &&
      provider.card_payments === "active" &&
      provider.transfers === "active" &&
      Array.isArray(provider.currently_due) &&
      provider.currently_due.length === 0;
  }
  function railEligible(snapshot, listing) {
    var checkout = listing && listing.checkout;
    if (!accountReady(snapshot)) return false;
    if (!checkout || checkout.provider !== "stripe") return false;
    if (checkout.status !== "ACTIVE_CHARGEABLE") return false;
    if (checkout.link_active !== true) return false;
    if (checkout.account_charges_enabled !== true) return false;
    if (checkout.account_payouts_enabled !== true) return false;
    if (!isStripeCheckoutUrl(checkout.url)) return false;
    if (!hasDurableCapabilityEvidence(checkout)) return false;
    if (!canonicalRailMatches(snapshot, listing)) return false;
    var inert = snapshot.inert_duplicate_urls || [];
    if (inert.indexOf(checkout.url) !== -1) return false;
    return true;
  }
  function tipPayDoor() {
    var path = (typeof window !== "undefined" && window.location && window.location.pathname) || "";
    var root = typeof document !== "undefined" ? document.documentElement : null;
    if (root && root.getAttribute("data-checkout-first") === "1") return true;
    return /(?:^|\/)(?:tips|pay)\.html$/i.test(path);
  }
  function fixedBuyContainer() {
    if (typeof document === "undefined" || typeof window === "undefined" || !window.location) return null;
    var path = window.location.pathname || "";
    if (!/(?:^|\/)(?:tips|commerce|bazaar|tools-cash)\.html$/i.test(path)) return null;
    return document.querySelector("#tip-shelf, #live-cash-doors, #live-cash, #cash-doors");
  }
  function uniqueSafeCheckoutFromHtml(text) {
    if (typeof DOMParser === "undefined" || typeof text !== "string") return "";
    var parsed;
    try { parsed = new DOMParser().parseFromString(text, "text/html"); } catch (err) { return ""; }
    var seen = {};
    Array.prototype.forEach.call(parsed.querySelectorAll("a[href]"), function (anchor) {
      var href = anchor.getAttribute("href");
      if (isStripeCheckoutUrl(href)) seen[href] = true;
    });
    var urls = Object.keys(seen);
    return urls.length === 1 ? urls[0] : "";
  }
  function appendFixedBuy(anchor, url, label) {
    var parent = anchor && anchor.parentNode;
    if (!parent || !isStripeCheckoutUrl(url)) return;
    if (parent.querySelector && parent.querySelector('a[data-fixed-buy-road="1"]')) return;
    var spacer = document.createTextNode(" · ");
    var checkout = document.createElement("a");
    checkout.className = "checkout-active fixed-buy-road";
    checkout.setAttribute("href", url);
    checkout.setAttribute("rel", "noopener noreferrer");
    checkout.setAttribute("target", "_blank");
    checkout.setAttribute("data-fixed-buy-road", "1");
    checkout.textContent = label;
    var next = anchor.nextSibling;
    parent.insertBefore(spacer, next);
    parent.insertBefore(checkout, next);
  }
  function exposeFixedBuyRoads(snapshot) {
    var container = fixedBuyContainer();
    if (!container || !accountReady(snapshot) || typeof fetch !== "function") return;
    FIXED_BUY_PRODUCTS.forEach(function (product) {
      var anchor = container.querySelector('a[href="' + product.path + '"]');
      if (!anchor || !anchor.parentNode) return;
      fetch(product.path, { cache: "no-store" }).then(function (response) {
        if (!response.ok) throw new Error(String(response.status));
        return response.text();
      }).then(function (text) {
        var checkout = uniqueSafeCheckoutFromHtml(text);
        if (checkout) appendFixedBuy(anchor, checkout, product.label);
      }).catch(function () {
        // Canonical product page or rail proof unavailable: keep the product-page link only.
      });
    });
  }
  function fillSlot(slot, listing, snapshot, funnel) {
    if (!railEligible(snapshot, listing)) {
      slot.innerHTML = '<p class="note">Provider rail is inert. Unverified URLs stay unpublished.</p>';
      return;
    }
    // tips.html + pay.html: exact catalog checkout URL (same as land/sku-*.md). commerce keeps funnel gate.
    var checkoutFirst = tipPayDoor() || (funnel && funnel.readiness === "READY_FOR_CHECKOUT");
    if (checkoutFirst) {
      slot.innerHTML = '<p><a class="checkout-active" href="' + esc(listing.checkout.url) +
        '" rel="noopener noreferrer" target="_blank" data-funnel-sku="' + esc(listing.id) +
        '" data-funnel-action="checkout-open">Verified chargeable Stripe checkout</a></p>' +
        '<p class="note">A click is intent, not authorization, settlement, payout, or cash.</p>';
      return;
    }
    slot.innerHTML = '<p><a class="funnel-intake" href="./commerce.html#' + esc(listing.id) +
      '" data-funnel-sku="' + esc(listing.id) +
      '" data-funnel-action="qualification-open">Start public intake, then pay</a></p>' +
      '<p class="note">Provider is chargeable and payout-capable. Missing terms stay in front of checkout.</p>';
  }
  function fillOwner(snapshot) {
    var node = document.getElementById("owner-action");
    if (!node) return;
    var action = snapshot.owner_action || {};
    var fallback = snapshot.fallback || {};
    node.innerHTML = '<p><b>Remaining owner Stripe onboarding:</b> ' + esc(action.id || "UNKNOWN") +
      '</p><p>' + esc(action.summary || "") + '</p>' +
      (action.optional_nonblocking ? '<p class="note">' + esc(action.optional_nonblocking) + '</p>' : "") +
      '<p><b>If Stripe later fails closed:</b> <a href="' + esc(fallback.url || "mailto:tokenjunkielabs@gmail.com") +
      '">' + esc(fallback.label || "Email Token Junkie Labs") + '</a></p>' +
      '<p class="note">Settlement is not verified in this view.</p>';
  }
  function ownerActionUrlOk(raw) {
    if (typeof raw !== "string" || !raw) return false;
    var parsed;
    try { parsed = new URL(raw); } catch (err) { return false; }
    if (parsed.protocol !== "https:") return false;
    if (parsed.username || parsed.password) return false;
    return parsed.hostname === "dashboard.stripe.com" ||
      parsed.hostname === "www.paypal.com" ||
      parsed.hostname === "paypal.com" ||
      parsed.hostname === "github.com" ||
      parsed.hostname === "squareup.com" ||
      parsed.hostname === "www.squareup.com";
  }
  function fillFailover(registry, snapshot) {
    var node = document.getElementById("rail-failover");
    if (!node) return;
    var rails = (registry && registry.rails) || [];
    var stripeReady = accountReady(snapshot);
    var actions = [];
    rails.forEach(function (rail) {
      var list = (rail.required_owner_actions || []).concat(rail.optional_owner_actions || []);
      list.forEach(function (action) {
        if (action && action.kind === "EXTERNAL_OWNER_ACTION" && ownerActionUrlOk(action.url)) {
          if (!stripeReady || action.blocking) actions.push(action);
        }
      });
    });
    if (stripeReady && !actions.length) {
      node.innerHTML = '<p class="note">Measured Stripe rail is CHARGEABLE. Failover owner actions stay one-click and unpublished as checkout. Full registry: <a href="./payment-capability.html">payment rails</a>.</p>';
      return;
    }
    var html = '<p><b>Storefront failover.</b> Unverified rails stay inert. Official provider UIs only:</p>';
    actions.forEach(function (action) {
      html += '<p><a class="failover-owner-action" href="' + esc(action.url) +
        '" rel="noopener noreferrer" target="_blank">' + esc(action.label) + "</a></p>";
    });
    html += '<p><a href="mailto:tokenjunkielabs@gmail.com">tokenjunkielabs@gmail.com</a></p>';
    node.innerHTML = html;
  }
  function render(snapshot, catalog, registry) {
    var byId = {};
    (catalog.listings || []).forEach(function (row) { byId[row.id] = row; });
    Array.prototype.forEach.call(document.querySelectorAll(".js-checkout-slot"), function (slot) {
      var sku = slot.getAttribute("data-sku");
      fillSlot(slot, byId[sku], snapshot, (catalog.funnels || {})[sku]);
    });
    exposeFixedBuyRoads(snapshot);
    fillOwner(snapshot);
    fillFailover(registry, snapshot);
  }
  var snapshotUrl = "./revenue/checkout_capability/snapshot.json?v=" + Date.now();
  var catalogUrl = "./revenue/outcome_commerce/catalog.json?v=" + Date.now();
  var registryUrl = "./revenue/payment_capability/registry.json?v=" + Date.now();
  Promise.all([
    fetch(snapshotUrl, { cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }),
    fetch(catalogUrl, { cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }),
    fetch(registryUrl, { cache: "no-store" }).then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }).catch(function () { return { rails: [] }; })
  ]).then(function (pair) {
    render(pair[0], pair[1], pair[2]);
  }).catch(function (error) {
    Array.prototype.forEach.call(document.querySelectorAll(".js-checkout-slot"), function (slot) {
      slot.textContent = "Catalog unavailable: " + error.message + ". Stripe URLs stay inert.";
    });
  });
})();
