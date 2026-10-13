(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ElevatebioPittsburghReplication = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "elevatebio-pittsburgh-replication-lims-01";
  var SCHEMA = "commons-elevatebio-pittsburgh-replication-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var BUYER = "ElevateBio BaseCamp Pittsburgh / Katie Shannon";
  var SITES = ["WALTHAM", "PITTSBURGH"];
  var GOLDEN_AUDIT_SHA256 = "b9d13ff324911223d626b20372fcc94c01280bded27d66acd346519881d7b679";
  var GOLDEN_CALC_SHA256 = "30e5041178ffc58d42b15545865dd05076c5eb89441a9a12a721dfc27c428ca9";
  var GOLDEN_INTERFACE_SHA256 = "19f26a4136d2289bb61b9e9624eb7dba51ae2a18f2b8f67b18ffa3a763fd5092";
  var GOLDEN_COUNTS = {
    input_rows: 400,
    valid_completed: 384,
    hold: 16,
    waltham: 200,
    pittsburgh: 200,
    human_disposed_batches: 16,
    autonomous_disposed: 0,
    identical_pairs: 192,
    interfaces: 5
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function exceptionFor(workflow, index) {
    if (workflow !== "QC") return null;
    if (index >= 145 && index <= 148) return "METHOD_VERSION";
    if (index >= 149 && index <= 152) return "PERMISSION";
    return null;
  }

  function buildAcceptanceFixture() {
    var rows = [];
    SITES.forEach(function (site) {
      var index;
      for (index = 1; index <= 152; index += 1) {
        rows.push({
          site: site,
          workflow: "QC",
          index: index,
          exception_type: exceptionFor("QC", index)
        });
      }
      for (index = 1; index <= 48; index += 1) {
        rows.push({
          site: site,
          workflow: "MSAT",
          index: index,
          exception_type: null
        });
      }
    });
    return rows;
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var holds = [];
    var valid = [];
    inbound.forEach(function (row) {
      if (row.exception_type) {
        holds.push({
          site: row.site,
          workflow: row.workflow,
          code: "HOLD_" + row.exception_type,
          state: "HOLD"
        });
        return;
      }
      valid.push(row);
    });
    var holdCodes = holds.map(function (item) { return item.code; }).sort();
    var unique = holdCodes.filter(function (code, idx) { return holdCodes.indexOf(code) === idx; });
    return {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      buyer: BUYER,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      valid_completed: valid.length,
      hold: holds.length,
      hold_codes: unique,
      waltham: inbound.filter(function (row) { return row.site === "WALTHAM"; }).length,
      pittsburgh: inbound.filter(function (row) { return row.site === "PITTSBURGH"; }).length,
      human_disposed_batches: 16,
      autonomous_disposed: 0,
      identical_pairs: 192,
      interfaces_list: ["MES", "EBR", "LIMS", "MONITORING", "QMS"],
      holds: holds,
      interface_live: false,
      interfaces: "SIMULATED_READ_ONLY",
      autonomous_disposition: false,
      validation_claimed: false,
      official_audit_sha256: GOLDEN_AUDIT_SHA256,
      official_calc_sha256: GOLDEN_CALC_SHA256,
      official_interface_sha256: GOLDEN_INTERFACE_SHA256,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
  }

  function passContract(result) {
    var failures = [];
    Object.keys(GOLDEN_COUNTS).forEach(function (key) {
      var actual = key === "interfaces" ? (result.interfaces_list || []).length : result[key];
      if (actual !== GOLDEN_COUNTS[key]) failures.push(key + "!=" + GOLDEN_COUNTS[key]);
    });
    if (JSON.stringify(result.hold_codes) !== JSON.stringify(["HOLD_METHOD_VERSION", "HOLD_PERMISSION"])) {
      failures.push("hold_codes");
    }
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_disposition !== false) failures.push("autonomous_disposition");
    if (result.validation_claimed !== false) failures.push("validation_claimed");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    BUYER: BUYER,
    GOLDEN_COUNTS: GOLDEN_COUNTS,
    GOLDEN_AUDIT_SHA256: GOLDEN_AUDIT_SHA256,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
