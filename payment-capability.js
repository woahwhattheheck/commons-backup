(function () {
  "use strict";
  var STRIPE_CHECKOUT_HOSTS = { "buy.stripe.com": true, "donate.stripe.com": true };
  var STRIPE_CHECKOUT_PATH = /^\/[A-Za-z0-9_-]+$/;
  var OWNER_HOSTS = {
    "dashboard.stripe.com": true,
    "www.paypal.com": true,
    "paypal.com": true,
    "github.com": true,
    "squareup.com": true,
    "www.squareup.com": true
  };
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
    if (parsed.port !== "") return false;
    if (raw.indexOf("?") !== -1 || raw.indexOf("#") !== -1) return false;
    if (!Object.prototype.hasOwnProperty.call(STRIPE_CHECKOUT_HOSTS, parsed.hostname)) return false;
    if (!STRIPE_CHECKOUT_PATH.test(parsed.pathname)) return false;
    return parsed.href === raw;
  }
  function isOwnerActionUrl(raw) {
    if (typeof raw !== "string" || !raw) return false;
    var parsed;
    try { parsed = new URL(raw); } catch (err) { return false; }
    if (parsed.protocol !== "https:") return false;
    if (parsed.username || parsed.password) return false;
    return Object.prototype.hasOwnProperty.call(OWNER_HOSTS, parsed.hostname);
  }
  function evidenceOk(rail) {
    var evidence = rail && rail.evidence;
    if (!evidence || typeof evidence !== "object") return false;
    if (typeof evidence.reference !== "string" || !evidence.reference.trim()) return false;
    if (typeof evidence.observed_at !== "string" || !/(?:Z|[+-]\d\d:\d\d)$/.test(evidence.observed_at)) return false;
    return !Number.isNaN(Date.parse(evidence.observed_at));
  }
  function publicEligible(rail) {
    return rail &&
      rail.capability_state === "CHARGEABLE" &&
      rail.public_presentation === "EXPOSE" &&
      rail.charges_enabled === true &&
      rail.payouts_enabled === true &&
      evidenceOk(rail);
  }
  function ownerUsable(rail) {
    return rail &&
      (rail.capability_state === "CHARGEABLE" ||
        rail.capability_state === "CHARGEABLE_ACCOUNT_OWNER_DASHBOARD") &&
      rail.charges_enabled === true;
  }
  function renderSwitcher(registry, rails) {
    var publicRails = rails.filter(publicEligible);
    var usable = rails.filter(ownerUsable);
    var active = publicRails[0] || null;
    var status = document.getElementById("js-switcher-status");
    if (status) {
      if (active) {
        status.textContent = "Active public storefront: " + active.id + " (" + active.provider + "). A click is intent, not cash.";
      } else {
        status.textContent = "No CHARGEABLE public rail. Storefront stays inert. Use owner one-click actions or mailto.";
      }
    }
    var truth = document.getElementById("js-switcher-truth");
    if (truth) {
      truth.innerHTML =
        "<span><b>" + esc(active ? active.provider : "none") + "</b>active rail</span>" +
        "<span><b>" + esc(publicRails.length) + "</b>public</span>" +
        "<span><b>" + esc(usable.length) + "</b>owner-usable</span>" +
        "<span><b>Unverified</b>current settlement</span>";
    }
  }
  function linkList(rail) {
    if (!publicEligible(rail) || !Array.isArray(rail.canonical_links)) return "";
    return rail.canonical_links.map(function (link) {
      if (!isStripeCheckoutUrl(link.url) || link.link_active !== true) return "";
      var label = link.exposure === "CHECKOUT_FIRST" ? "Verified chargeable checkout" : "Verified rail (intake first)";
      var href = link.exposure === "CHECKOUT_FIRST" ? esc(link.url) : "./commerce.html#" + esc(link.sku);
      var cls = link.exposure === "CHECKOUT_FIRST" ? "checkout-active" : "funnel-intake";
      return '<p><a class="' + cls + '" href="' + href + '" rel="noopener noreferrer" target="_blank">' +
        esc(label) + " · " + esc(link.sku) + "</a></p>";
    }).join("");
  }
  function renderRails(rails) {
    var host = document.getElementById("js-rail-list");
    if (!host) return;
    host.innerHTML = rails.map(function (rail) {
      var dest = rail.settlement_destination || {};
      var state = esc(rail.capability_state);
      var publicBit = publicEligible(rail) ? "public EXPOSE" : "public INERT";
      var destLine = dest.kind === "stripe_external_account"
        ? esc(dest.bank_name) + " · verified last4 " + esc(dest.last4) + " · " + esc(dest.currency)
        : esc(dest.kind) + " · " + esc(dest.status);
      return '<article class="card" id="' + esc(rail.id) + '">' +
        '<p class="state-' + state + '"><b>' + state + "</b> · " + esc(publicBit) + "</p>" +
        "<h3>" + esc(rail.provider) + "</h3>" +
        '<p class="note">' + esc((rail.account_provenance || {}).display_name || (rail.account_provenance || {}).login || (rail.account_provenance || {}).note || "no account evidenced") + "</p>" +
        "<p><b>SKUs:</b> " + esc((rail.supported_skus || []).join(", ") || "none until chargeable") + "</p>" +
        "<p><b>Currencies:</b> " + esc((rail.currencies || []).join(", ") || "none") + "</p>" +
        "<p><b>Settlement:</b> " + destLine + "</p>" +
        '<p class="note">evidence ' + esc((rail.evidence || {}).observed_at) + " · " + esc((rail.evidence || {}).reference) + "</p>" +
        (publicEligible(rail) ? linkList(rail) : '<p class="provider-inert">No public checkout. Unverified URLs stay unpublished.</p>') +
        "</article>";
    }).join("");
  }
  function renderOwnerActions(rails, registry) {
    var host = document.getElementById("js-owner-actions");
    if (!host) return;
    var actions = [];
    rails.forEach(function (rail) {
      (rail.required_owner_actions || []).concat(rail.optional_owner_actions || []).forEach(function (action) {
        if (action && action.kind === "EXTERNAL_OWNER_ACTION" && isOwnerActionUrl(action.url)) {
          actions.push(action);
        }
      });
    });
    var intake = (registry && registry.intake_fallback) || {};
    var html = actions.map(function (action) {
      return '<p><a class="failover-owner-action" href="' + esc(action.url) +
        '" rel="noopener noreferrer" target="_blank">' + esc(action.label) + "</a></p>" +
        '<p class="note">' + esc(action.note || "") + "</p>";
    }).join("");
    html += '<p><a class="funnel-intake" href="' + esc(intake.url || "mailto:tokenjunkielabs@gmail.com") + '">' +
      esc(intake.label || "Email Token Junkie Labs") + "</a></p>";
    host.innerHTML = html || '<p class="note">No owner action required for charges on the measured Stripe rail.</p>';
  }
  fetch("./revenue/payment_capability/registry.json?v=" + Date.now(), { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    })
    .then(function (registry) {
      var rails = registry.rails || [];
      renderSwitcher(registry, rails);
      renderRails(rails);
      renderOwnerActions(rails, registry);
    })
    .catch(function (error) {
      var list = document.getElementById("js-rail-list");
      if (list) list.textContent = "Registry unavailable: " + error.message + ". Checkout URLs stay inert.";
    });
})();
