(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.TraceSilaMlIatf = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "trace-sila-ml-iatf-lims-01";
  var SCHEMA = "commons-trace-sila-ml-iatf-lims/v1";
  var BUILD = "TRACE-SILA-ML-IATF-v0";
  var FIXTURE_ID = "SILA-ML-01";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var METHODS = {
    PSD_D50: { unit: "um", lo: 8.0, hi: 12.0, owner: "QMS_METROLOGY" },
    MOISTURE: { unit: "wt_pct", lo: 0.0, hi: 0.50, owner: "QMS_METROLOGY" },
    IMPURITY_NA: { unit: "ppm", lo: 0.0, hi: 50.0, owner: "QUALITY_ENGINEER" }
  };
  var HOLD_OWNERS = {
    HOLD_UNIT_MISMATCH: "QMS_METROLOGY",
    HOLD_SPEC_OOS: "QUALITY_ENGINEER",
    HOLD_GENEALOGY_GAP: "MES_GENEALOGY"
  };
  var STATUS_ORDER = ["HOLD_GENEALOGY_GAP", "HOLD_UNIT_MISMATCH", "HOLD_SPEC_OOS", "REVIEW_READY"];

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function number(value) {
    var n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  function stable(value) {
    if (Array.isArray(value)) return value.map(stable);
    if (value && typeof value === "object") {
      var out = {};
      Object.keys(value).sort().forEach(function (key) { out[key] = stable(value[key]); });
      return out;
    }
    return value;
  }
  function sha256HexSync(value) {
    var payload = JSON.stringify(stable(value));
    if (typeof require === "function") {
      try { return require("crypto").createHash("sha256").update(payload).digest("hex"); } catch (_) {}
    }
    var h = 5381;
    for (var i = 0; i < payload.length; i += 1) h = ((h << 5) + h) ^ payload.charCodeAt(i);
    return ("00000000" + ((h >>> 0).toString(16))).slice(-8);
  }

  function buildAcceptanceFixture() {
    var unique = [
      { result_id: "B001-A01", batch_id: "B001", method: "PSD_D50", value: 10.0, unit: "um", instrument: "PSA-SYN-01" },
      { result_id: "B001-A02", batch_id: "B001", method: "MOISTURE", value: 0.20, unit: "wt_pct", instrument: "MOIST-SYN-01" },
      { result_id: "B001-A03", batch_id: "B001", method: "IMPURITY_NA", value: 12.0, unit: "ppm", instrument: "ICP-SYN-01" },
      { result_id: "B002-A01", batch_id: "B002", method: "PSD_D50", value: 10.1, unit: "um", instrument: "PSA-SYN-01" },
      { result_id: "B002-A02", batch_id: "B002", method: "MOISTURE", value: 0.18, unit: "wt_pct", instrument: "MOIST-SYN-01" },
      { result_id: "B002-A03", batch_id: "B002", method: "IMPURITY_NA", value: 15.0, unit: "wt_pct", instrument: "ICP-SYN-01" },
      { result_id: "B003-A01", batch_id: "B003", method: "PSD_D50", value: 10.2, unit: "um", instrument: "PSA-SYN-01" },
      { result_id: "B003-A02", batch_id: "B003", method: "MOISTURE", value: 0.22, unit: "wt_pct", instrument: "MOIST-SYN-01" },
      { result_id: "B003-A03", batch_id: "B003", method: "IMPURITY_NA", value: 88.0, unit: "ppm", instrument: "ICP-SYN-01" },
      { result_id: "B004-A01", batch_id: "B004", method: "PSD_D50", value: 9.8, unit: "um", instrument: "PSA-SYN-01" },
      { result_id: "B004-A02", batch_id: "B004", method: "MOISTURE", value: 0.19, unit: "wt_pct", instrument: "MOIST-SYN-01" },
      { result_id: "B004-A03", batch_id: "B004", method: "IMPURITY_NA", value: 11.0, unit: "ppm", instrument: "ICP-SYN-01" }
    ];
    var duplicate = clone(unique[0]);
    duplicate.row_kind = "DUPLICATE";
    return {
      fixture_id: FIXTURE_ID,
      batches: [
        { batch_id: "B001", parent_lot: "RM-SILA-A", site: "SILA-MOSES-LAKE-SYN", product_family: "silicon_anode_synthetic" },
        { batch_id: "B002", parent_lot: "RM-SILA-B", site: "SILA-MOSES-LAKE-SYN", product_family: "silicon_anode_synthetic" },
        { batch_id: "B003", parent_lot: "RM-SILA-C", site: "SILA-MOSES-LAKE-SYN", product_family: "silicon_anode_synthetic" },
        { batch_id: "B004", parent_lot: "", site: "SILA-MOSES-LAKE-SYN", product_family: "silicon_anode_synthetic" }
      ],
      analytics: unique.concat([duplicate])
    };
  }

  function resultIdentity(row) {
    return sha256HexSync({
      demand_id: DEMAND_ID,
      fixture_id: FIXTURE_ID,
      result_id: text(row.result_id),
      batch_id: text(row.batch_id),
      method: text(row.method)
    });
  }

  function classifyResult(row, parentLot) {
    var method = text(row.method);
    var unit = text(row.unit);
    var value = number(row.value);
    var spec = METHODS[method];
    var holds = [];
    if (!text(parentLot)) holds.push("HOLD_GENEALOGY_GAP");
    if (!spec || unit !== spec.unit) holds.push("HOLD_UNIT_MISMATCH");
    if (spec && (value === null || value < spec.lo || value > spec.hi)) holds.push("HOLD_SPEC_OOS");
    var hold = null;
    STATUS_ORDER.forEach(function (code) {
      if (!hold && holds.indexOf(code) !== -1) hold = code;
    });
    return {
      result_id: text(row.result_id),
      batch_id: text(row.batch_id),
      method: method,
      value: value,
      unit: unit,
      parent_lot: text(parentLot) || null,
      hold: hold,
      status: hold || "CANONICAL",
      identity: resultIdentity(row)
    };
  }

  function batchStatus(holds) {
    var found = "REVIEW_READY";
    STATUS_ORDER.forEach(function (code) {
      if (found === "REVIEW_READY" && holds.indexOf(code) !== -1) found = code;
    });
    return found;
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var results = {};
    var duplicates = [];
    var exceptions = [];
    var parentByBatch = {};
    inbound.batches.forEach(function (batch) {
      parentByBatch[text(batch.batch_id)] = text(batch.parent_lot);
    });
    inbound.analytics.forEach(function (row) {
      var verdict = classifyResult(row, parentByBatch[text(row.batch_id)] || "");
      if (results[verdict.identity]) {
        duplicates.push({
          result_id: verdict.result_id,
          batch_id: verdict.batch_id,
          method: verdict.method,
          identity: verdict.identity,
          code: "DUPLICATE_ANALYTICS"
        });
        return;
      }
      results[verdict.identity] = {
        result_id: verdict.result_id,
        batch_id: verdict.batch_id,
        method: verdict.method,
        value: verdict.value,
        unit: verdict.unit,
        parent_lot: verdict.parent_lot,
        hold: verdict.hold,
        status: verdict.status,
        threshold_source: "FIXTURE_ONLY",
        identity: verdict.identity,
        interface_live: false
      };
      if (verdict.hold) {
        exceptions.push({
          batch_id: verdict.batch_id,
          result_id: verdict.result_id,
          code: verdict.hold,
          owner: HOLD_OWNERS[verdict.hold],
          method: verdict.method,
          open: true
        });
      }
    });
    var canonical = Object.keys(results).map(function (id) { return results[id]; })
      .sort(function (a, b) { return a.result_id < b.result_id ? -1 : 1; });
    var dossiers = inbound.batches.map(function (batch) {
      var batchId = text(batch.batch_id);
      var rowsForBatch = canonical.filter(function (item) { return item.batch_id === batchId; });
      var holds = rowsForBatch.map(function (item) { return item.hold; }).filter(Boolean);
      return {
        batch_id: batchId,
        parent_lot: text(batch.parent_lot) || null,
        status: batchStatus(holds),
        result_count: rowsForBatch.length,
        released: false,
        interface_live: false,
        incumbent_authoritative: true
      };
    });
    var statuses = {};
    dossiers.forEach(function (item) { statuses[item.batch_id] = item.status; });
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      build: BUILD,
      fixture_id: FIXTURE_ID,
      truth_gate: TRUTH_GATE,
      input_analytics: inbound.analytics.length,
      unique_analytics: 12,
      canonical_results: canonical.length,
      duplicate_log: duplicates.length,
      dossier_count: dossiers.length,
      statuses: statuses,
      result_ids: canonical.map(function (item) { return item.result_id; }),
      duplicate_result_ids: duplicates.map(function (item) { return item.result_id; }),
      exceptions: exceptions,
      dossiers: dossiers,
      results: canonical,
      released_dossiers: 0,
      interface_live: false,
      interfaces: "SIMULATED_READONLY",
      adapter_writes: false,
      recipes_mutated: false,
      real_thresholds: false,
      threshold_source: "FIXTURE_ONLY",
      incumbent_authoritative: true,
      autonomous_certification: false,
      autonomous_disposition: false,
      human_disposition_mandatory: true,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
    body.manifest_sha256 = sha256HexSync(Object.keys(body).reduce(function (acc, key) {
      if (key !== "manifest_sha256") acc[key] = body[key];
      return acc;
    }, {}));
    return body;
  }

  function passContract(result) {
    var failures = [];
    if (result.fixture_id !== FIXTURE_ID) failures.push("fixture_id");
    if (result.input_analytics !== 13) failures.push("input_analytics!=13");
    if (result.canonical_results !== 12) failures.push("canonical_results!=12");
    if (result.duplicate_log !== 1) failures.push("duplicate_log!=1");
    if (result.dossier_count !== 4) failures.push("dossier_count!=4");
    var expected = {
      B001: "REVIEW_READY",
      B002: "HOLD_UNIT_MISMATCH",
      B003: "HOLD_SPEC_OOS",
      B004: "HOLD_GENEALOGY_GAP"
    };
    if (JSON.stringify(result.statuses) !== JSON.stringify(expected)) failures.push("statuses");
    if (JSON.stringify(result.duplicate_result_ids) !== JSON.stringify(["B001-A01"])) failures.push("duplicate_result_ids");
    if (result.released_dossiers !== 0) failures.push("released_dossiers!=0");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_disposition !== false) failures.push("autonomous_disposition");
    if (result.human_disposition_mandatory !== true) failures.push("human_disposition_mandatory");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    FIXTURE_ID: FIXTURE_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract,
    sha256HexSync: sha256HexSync
  };
});
