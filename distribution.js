(function () {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  var bust = "?v=" + Date.now();
  var familyFilter = "all";
  var matrix = { pairs: [] };
  var packages = { packages: [] };
  var channelsDoc = { channels: [] };
  var statusDoc = { counts: {} };

  function counts() {
    var c = statusDoc.counts || {};
    document.getElementById("c-packages").textContent = c.packages_ready == null ? "—" : String(c.packages_ready);
    document.getElementById("c-live-mkt").textContent = String(c.live_marketplace_listings || 0);
    document.getElementById("c-surfaces").textContent = c.live_commons_surfaces == null ? "—" : String(c.live_commons_surfaces);
    document.getElementById("c-leads").textContent = String(c.verified_leads || 0);
    document.getElementById("c-cash").textContent = "unverified";
    document.getElementById("c-blocked").textContent = c.blocked_pairs == null ? "—" : String(c.blocked_pairs);
    document.getElementById("status-src").textContent =
      "Recorded snapshot as of " + (statusDoc.as_of || "date unavailable") +
      ". Current settlement: unverified. Listing and lead counts describe this snapshot.";
  }

  function renderChannels() {
    var host = document.getElementById("channel-cards");
    host.innerHTML = (channelsDoc.channels || []).map(function (ch) {
      return (
        '<article class="card" id="ch-' + esc(ch.id) + '">' +
        "<h3>" + esc(ch.name) + "</h3>" +
        '<p><span class="pill">' + esc(ch.family) + "</span> " +
        '<span class="pill">' + esc(ch.account_status) + "</span></p>" +
        "<p>" + esc(ch.notes) + "</p>" +
        "<p class=\"note\">submit_allowed=false · honest_live=" + esc(String(ch.honest_live)) + "</p>" +
        "</article>"
      );
    }).join("");
  }

  function renderFilters() {
    var families = ["all"].concat(
      (channelsDoc.channel_families || []).slice()
    );
    var host = document.getElementById("family-filters");
    host.innerHTML = families.map(function (fam) {
      return '<button type="button" data-family="' + esc(fam) + '" aria-pressed="' +
        (fam === familyFilter ? "true" : "false") + '">' + esc(fam) + "</button>";
    }).join("");
    host.onclick = function (ev) {
      var btn = ev.target.closest("button[data-family]");
      if (!btn) return;
      familyFilter = btn.getAttribute("data-family");
      renderFilters();
      renderMatrix();
    };
  }

  function renderMatrix() {
    var body = document.querySelector("#matrix-table tbody");
    var rows = (matrix.pairs || []).filter(function (p) {
      return familyFilter === "all" || p.channel_family === familyFilter;
    });
    body.innerHTML = rows.map(function (p) {
      return (
        "<tr>" +
        "<td>" + esc(p.offer_name) + "</td>" +
        "<td>" + esc(p.channel_name) + "</td>" +
        "<td>" + esc(p.channel_family) + "</td>" +
        '<td class="state-' + esc(p.fit) + '">' + esc(p.fit) + "</td>" +
        '<td class="state-' + esc(p.listing_state) + '">' + esc(p.listing_state) + "</td>" +
        '<td><a href="./' + esc(p.human_route) + '">' + esc(p.human_route) + "</a></td>" +
        "</tr>"
      );
    }).join("");
  }

  function fillSelects() {
    var offers = [];
    var seen = {};
    (matrix.pairs || []).forEach(function (p) {
      if (!seen[p.offer_id]) {
        seen[p.offer_id] = true;
        offers.push({ id: p.offer_id, name: p.offer_name });
      }
    });
    document.getElementById("offer-select").innerHTML = offers.map(function (o) {
      return '<option value="' + esc(o.id) + '">' + esc(o.name) + "</option>";
    }).join("");
    document.getElementById("channel-select").innerHTML = (channelsDoc.channels || []).map(function (ch) {
      return '<option value="' + esc(ch.id) + '">' + esc(ch.name) + "</option>";
    }).join("");
    showPackage();
  }

  function showPackage() {
    var oid = document.getElementById("offer-select").value;
    var cid = document.getElementById("channel-select").value;
    var pack = (packages.packages || []).find(function (p) {
      return p.offer_id === oid && p.channel_id === cid;
    });
    var pair = (matrix.pairs || []).find(function (p) {
      return p.offer_id === oid && p.channel_id === cid;
    });
    var state = document.getElementById("package-state");
    var pre = document.getElementById("package-copy");
    var inbound = document.getElementById("inbound-body");
    if (!pair) {
      state.textContent = "unknown pair";
      pre.textContent = "";
      return;
    }
    if (!pack) {
      state.textContent = pair.fit + " · " + pair.listing_state + " · no package (UNFIT). Conversion still " + pair.human_route + ".";
      pre.textContent = "No channel-ready package. This offer does not fit this channel.\nConversion remains: ./" + pair.human_route;
    } else {
      state.textContent = pack.package_state + " · listing " + pack.listing_state +
        " · recorded package as of " + (statusDoc.as_of || "date unavailable") + " · current settlement unverified";
      pre.textContent = pack.channel_copy;
    }
    inbound.value = [
      "PLAIN: Public, non-confidential buyer interest from a distribution channel.",
      "CHANNEL: " + cid,
      "OFFER_ID: " + oid,
      "PUBLIC_OBJECTIVE:",
      "PUBLIC_ARTIFACT:",
      "PUBLIC_CONTACT_URL:",
      "START_WINDOW:",
      "CONVERSION: https://woahwhattheheck.github.io/commons/" + pair.human_route,
      "NOTE: This is intent only. It is not a lead, customer, or payment."
    ].join("\n");
  }

  document.getElementById("offer-select").addEventListener("change", showPackage);
  document.getElementById("channel-select").addEventListener("change", showPackage);
  document.getElementById("copy-package").addEventListener("click", function () {
    var text = document.getElementById("package-copy").textContent || "";
    if (navigator.clipboard && text) navigator.clipboard.writeText(text);
  });

  Promise.all([
    fetch("./revenue/distribution/status.json" + bust, { cache: "no-store" }).then(function (r) { return r.json(); }),
    fetch("./revenue/distribution/channels.json" + bust, { cache: "no-store" }).then(function (r) { return r.json(); }),
    fetch("./revenue/distribution/matrix.json" + bust, { cache: "no-store" }).then(function (r) { return r.json(); }),
    fetch("./revenue/distribution/packages.json" + bust, { cache: "no-store" }).then(function (r) { return r.json(); })
  ]).then(function (rows) {
    statusDoc = rows[0];
    channelsDoc = rows[1];
    matrix = rows[2];
    packages = rows[3];
    counts();
    renderChannels();
    renderFilters();
    renderMatrix();
    fillSelects();
  }).catch(function (err) {
    document.getElementById("status-src").textContent = "could not load distribution snapshots (" + err.message + ")";
  });
})();
