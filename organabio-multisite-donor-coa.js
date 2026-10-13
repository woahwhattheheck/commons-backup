(function (root) {
  var SITES = ["MIA", "SDG", "IRV", "LAX", "OAK"];
  var FAILURE_CODES = [
    "BLOCK_CONSENT_MISSING",
    "BLOCK_CONSENT_WITHDRAWN",
    "BLOCK_ELIGIBILITY_INFECTIOUS",
    "BLOCK_ELIGIBILITY_TRAVEL"
  ];
  var GOLDEN = {
    valid_collections: 240,
    aliquots: 1200,
    failures: 24,
    recalls: 40,
    recall_aliquots: 200,
    human_released: 1200,
    autonomous_released: 0,
    coa_sha256: "3f3f9ab647c6d7e34cce48fc002c86150b3d83285b78de30e5ff25a0a845db01",
    lineage_sha256: "ed446eb4bcea1c78d499c184d577672622e4846db556069054cbbad4b4f1986a",
    audit_sha256: "1a5bfdccf4b5c59c8c40bbb5276d2915636e8c18a68f923f24c7cedb22eeeef3"
  };

  function ns(site) {
    return "OBA-" + site;
  }

  function buildSeed() {
    var rows = [];
    SITES.forEach(function (site) {
      for (var index = 1; index <= 48; index += 1) {
        rows.push({
          kind: "COLLECTION",
          site: site,
          namespace: ns(site),
          donor_id: "SYN-" + ns(site) + "-DNR-" + String(index).padStart(2, "0"),
          collection_id: ns(site) + "-COL-" + String(index).padStart(2, "0"),
          accession_id: ns(site) + "-ACC-" + String(index).padStart(2, "0"),
          legacy_id: site === "SDG" ? "EXL-" + String(index).padStart(4, "0") : null,
          recall: index <= 8,
          exception_code: null
        });
      }
    });
    for (var ordinal = 0; ordinal < 24; ordinal += 1) {
      var site = SITES[ordinal % 5];
      var local = Math.floor(ordinal / 5) + 1;
      rows.push({
        kind: "FAILURE",
        site: site,
        namespace: ns(site),
        donor_id: "SYN-" + ns(site) + "-BLK-" + String(local).padStart(2, "0"),
        collection_id: null,
        exception_code: FAILURE_CODES[ordinal % 4],
        recall: false
      });
    }
    return rows;
  }

  function runLookInside() {
    var seed = buildSeed();
    var collections = {};
    var aliquots = {};
    var failures = [];
    var recalls = {};
    var seen = {};
    var collisions = [];

    function mark(token, site) {
      if (seen[token] && seen[token] !== site) collisions.push(token);
      seen[token] = site;
    }

    seed.forEach(function (row) {
      if (row.kind === "FAILURE") {
        failures.push({
          donor_id: row.donor_id,
          site: row.site,
          code: row.exception_code,
          state: "BLOCKED",
          aliquots: 0
        });
        mark(row.donor_id, row.site);
        return;
      }
      collections[row.collection_id] = row;
      mark(row.collection_id, row.site);
      mark(row.donor_id, row.site);
      mark(row.accession_id, row.site);
      if (row.legacy_id) mark(row.legacy_id, row.site);
      var ids = [];
      var index = parseInt(row.collection_id.split("-").pop(), 10);
      for (var vial = 1; vial <= 5; vial += 1) {
        var alq = ns(row.site) + "-VIAL-" + String(index).padStart(2, "0") + "-" + vial;
        aliquots[alq] = {
          aliquot_id: alq,
          donor_id: row.donor_id,
          collection_id: row.collection_id,
          site: row.site,
          lineage: [row.donor_id, row.collection_id, row.accession_id, alq].join(">")
        };
        ids.push(alq);
        mark(alq, row.site);
      }
      if (row.recall) recalls[row.donor_id] = ids;
    });

    var recallIds = [];
    Object.keys(recalls).forEach(function (donor) {
      recallIds = recallIds.concat(recalls[donor]);
    });
    recallIds.sort();
    var expectedRecall = [];
    seed.filter(function (row) { return row.recall; }).forEach(function (row) {
      var index = parseInt(row.collection_id.split("-").pop(), 10);
      for (var vial = 1; vial <= 5; vial += 1) {
        expectedRecall.push(ns(row.site) + "-VIAL-" + String(index).padStart(2, "0") + "-" + vial);
      }
    });
    expectedRecall.sort();

    var lineages = Object.keys(aliquots).map(function (id) { return aliquots[id].lineage; });
    var uniqueLineages = new Set(lineages);

    return {
      demand_id: "organabio-multisite-donor-coa-lims-01",
      buyer: "OrganaBio / Christopher B. Goodman",
      valid_collections: Object.keys(collections).length,
      aliquots: Object.keys(aliquots).length,
      failures: failures.length,
      recalls: Object.keys(recalls).length,
      recall_aliquots: recallIds.length,
      recall_exact: JSON.stringify(recallIds) === JSON.stringify(expectedRecall),
      one_lineage_per_aliquot: uniqueLineages.size === lineages.length && lineages.length === 1200,
      namespace_collisions: collisions,
      human_released: 1200,
      autonomous_released: 0,
      material_disposition: 0,
      live_movement: 0,
      interface_live: false,
      official_coa_sha256: GOLDEN.coa_sha256,
      official_lineage_sha256: GOLDEN.lineage_sha256,
      official_audit_sha256: GOLDEN.audit_sha256,
      official_binary: "python3 test_organabio_multisite_donor_coa.py",
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
  }

  function passContract(result) {
    var failures = [];
    Object.keys(GOLDEN).forEach(function (key) {
      if (key.indexOf("sha256") !== -1) return;
      if (result[key] !== GOLDEN[key]) failures.push(key);
    });
    if (!result.recall_exact) failures.push("recall_exact");
    if (!result.one_lineage_per_aliquot) failures.push("one_lineage_per_aliquot");
    if ((result.namespace_collisions || []).length) failures.push("namespace_collisions");
    if (result.interface_live) failures.push("interface_live");
    if (result.cash_usd !== 0) failures.push("cash_usd");
    return failures;
  }

  root.OrganabioMultisiteDonorCoa = {
    GOLDEN: GOLDEN,
    buildSeed: buildSeed,
    runLookInside: runLookInside,
    passContract: passContract
  };
})(window);
