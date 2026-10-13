(function () {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  var bust = "?v=" + Date.now();
  var familyFilter = "all";
  var query = "";
  var registry = { listings: [], counts: {}, family_counts: {} };
  var assets = { assets: [] };
  var surfacesDoc = { surfaces: [], families: [] };

  function counts() {
    var c = registry.counts || {};
    document.getElementById("c-listings").textContent = c.listings == null ? "—" : String(c.listings);
    document.getElementById("c-fit").textContent = c.fit == null ? "—" : String(c.fit);
    document.getElementById("c-live-ext").textContent = String(c.external_live_listings || 0);
    document.getElementById("c-submitted").textContent = String(c.submitted || 0);
    document.getElementById("c-published").textContent = c.surface_published == null ? "—" : String(c.surface_published);
    document.getElementById("c-buyers").textContent = String(c.verified_buyers || 0);
    document.getElementById("c-cash").textContent = "Unverified";
    document.getElementById("c-dup").textContent = String(c.duplicate_postings || 0);
    document.getElementById("status-src").textContent =
      (registry.as_of || "") + " · live marketplace listings remain 0 until a verified external URL exists";
  }

  function renderSurfaces() {
    var host = document.getElementById("surface-cards");
    host.innerHTML = (surfacesDoc.surfaces || []).map(function (s) {
      return (
        '<article class="card" id="surf-' + esc(s.id) + '">' +
        "<h3>" + esc(s.name) + "</h3>" +
        '<p><span class="pill">' + esc(s.family) + "</span> " +
        '<span class="pill">' + esc(s.account_status) + "</span></p>" +
        "<p>" + esc(s.notes) + "</p>" +
        "<p class=\"note\">submit_allowed=false · owner=" + esc(s.owner || "NONE") + "</p>" +
        "</article>"
      );
    }).join("");
  }

  function renderFilters() {
    var families = ["all"].concat((surfacesDoc.families || []).slice());
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
      renderList();
    };
  }

  function filtered() {
    var q = query.trim().toLowerCase();
    return (registry.listings || []).filter(function (r) {
      if (familyFilter !== "all" && r.surface_family !== familyFilter) return false;
      if (!q) return true;
      return (
        String(r.offer_id).toLowerCase().indexOf(q) >= 0 ||
        String(r.offer_name).toLowerCase().indexOf(q) >= 0 ||
        String(r.sku).toLowerCase().indexOf(q) >= 0 ||
        String(r.surface_id).toLowerCase().indexOf(q) >= 0 ||
        String(r.surface_name).toLowerCase().indexOf(q) >= 0
      );
    });
  }

  function renderList() {
    var host = document.getElementById("listing-list");
    var rows = filtered();
    host.innerHTML = rows.map(function (r) {
      var url = r.url
        ? '<a href="' + esc(r.url) + '">' + esc(r.url) + "</a>"
        : "<span class=\"note\">no external URL</span>";
      return (
        '<details class="row" id="row-' + esc(r.id) + '">' +
        "<summary>" +
        "<strong>" + esc(r.offer_name) + "</strong>" +
        "<span>" + esc(r.surface_name) + "</span>" +
        '<span class="state-' + esc(r.fit) + '">' + esc(r.fit) + "</span>" +
        '<span class="state-' + esc(r.published_status) + '">' + esc(r.published_status) + "</span>" +
        '<span class="state-' + esc(r.chargeability_state) + '">' + esc(r.chargeability_state) + "</span>" +
        '<span class="state-' + esc(r.submission_status) + '">' + esc(r.submission_status) + "</span>" +
        "</summary>" +
        "<p>SKU <code>" + esc(r.sku) + "</code> · account " + esc(r.account_status) +
        " · owner " + esc(r.owner || "NONE") + "</p>" +
        "<p>URL: " + url + "</p>" +
        "<p>Last verified: " + esc(r.last_verified) + "</p>" +
        "<p>Next action: " + esc(r.next_action) + "</p>" +
        "<p class=\"note\">Evidence: " + esc((r.evidence_packet.refs || []).map(function (ref) {
          return ref.path || ref.kind;
        }).join(" · ")) + "</p>" +
        "</details>"
      );
    }).join("") || "<p class=\"note\">No rows match this filter.</p>";
  }

  function fillSelect() {
    var sel = document.getElementById("listing-select");
    var fit = (registry.listings || []).filter(function (r) { return r.fit === "FIT"; });
    sel.innerHTML = fit.map(function (r) {
      return '<option value="' + esc(r.id) + '">' + esc(r.offer_name) + " · " + esc(r.surface_name) + "</option>";
    }).join("");
    showAsset();
  }

  function showAsset() {
    var id = document.getElementById("listing-select").value;
    var asset = (assets.assets || []).filter(function (a) { return a.id === id; })[0];
    var row = (registry.listings || []).filter(function (r) { return r.id === id; })[0];
    var state = document.getElementById("asset-state");
    var pre = document.getElementById("asset-copy");
    if (!asset || !row) {
      state.textContent = "Pick a FIT listing.";
      pre.textContent = "";
      return;
    }
    state.textContent =
      row.published_status + " · submit_allowed=false · " +
      (row.url || "no live URL") + " · next: " + row.next_action;
    pre.textContent = asset.copy || "";
  }

  function boot() {
    Promise.all([
      fetch("./revenue/listing_registry/registry.json" + bust).then(function (r) { return r.json(); }),
      fetch("./revenue/listing_registry/assets.json" + bust).then(function (r) { return r.json(); }),
      fetch("./revenue/listing_registry/surfaces.json" + bust).then(function (r) { return r.json(); })
    ]).then(function (docs) {
      registry = docs[0];
      assets = docs[1];
      surfacesDoc = docs[2];
      counts();
      renderSurfaces();
      renderFilters();
      renderList();
      fillSelect();
    }).catch(function (err) {
      document.getElementById("status-src").textContent = "Failed to load registry: " + err;
    });
    document.getElementById("listing-select").addEventListener("change", showAsset);
    document.getElementById("q").addEventListener("input", function (ev) {
      query = ev.target.value;
      renderList();
    });
    document.getElementById("copy-asset").addEventListener("click", function () {
      var text = document.getElementById("asset-copy").textContent || "";
      if (navigator.clipboard && text) navigator.clipboard.writeText(text);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
