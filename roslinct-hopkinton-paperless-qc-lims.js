(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.RoslinctHopkintonPaperlessQc = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "roslinct-hopkinton-paperless-qc-lims-01";
  var SCHEMA = "commons-roslinct-hopkinton-paperless-qc-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var BUYER = "RoslinCT US Hopkinton / Lisa Mello";
  var CLASSES = ["RAW", "IN_PROCESS", "RELEASE", "RETAIN", "STABILITY"];
  var PREFIX = { RAW: "RAW", IN_PROCESS: "IPC", RELEASE: "REL", RETAIN: "RET", STABILITY: "STB" };
  var INSTRUMENTS = ["INST-01", "INST-02", "INST-03", "INST-04", "INST-05", "INST-06", "INST-07", "INST-08", "INST-09", "INST-10", "INST-11", "INST-12"];
  var CONTRACT_LABS = ["CLAB-ALPHA", "CLAB-BRAVO", "CLAB-CHARLIE"];
  var GOLDEN_AUDIT_SHA256 = "93e5ce0ef00ca6de9ac87203b67ec05f9eb80d1cb10ffb284b1948a195dab83a";
  var GOLDEN_CUSTODY_SHA256 = "185cea2779565cbc000a2caeabd021c6405b05ee7d83afdf4cccd0cc0cd646a9";
  var GOLDEN_RESULTS_SHA256 = "2973a64b14ac91f8a5358bf0a6b80790439c885d630b058da3cb826d4affd1fc";
  var GOLDEN_COUNTS = {
    input_rows: 240,
    valid_completed: 216,
    hold: 24,
    accessioned: 216,
    human_released: 216,
    autonomous_released: 0,
    instruments: 12,
    contract_labs: 3
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function exceptionFor(sampleClass, index) {
    if (sampleClass === "STABILITY") {
      return { 45: "LABEL", 46: "TEMPERATURE", 47: "DUPLICATE", 48: "LATE" }[index] || null;
    }
    return { 44: "LABEL", 45: "TEMPERATURE", 46: "DUPLICATE", 47: "LATE", 48: "OOS" }[index] || null;
  }

  function buildAcceptanceFixture() {
    var rows = [];
    CLASSES.forEach(function (sampleClass) {
      for (var index = 1; index <= 48; index += 1) {
        var exception = exceptionFor(sampleClass, index);
        rows.push({
          row_id: PREFIX[sampleClass] + "-" + String(index).padStart(2, "0"),
          sample_class: sampleClass,
          exception_type: exception
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
          row_id: row.row_id,
          sample_class: row.sample_class,
          code: "HOLD_" + row.exception_type,
          state: "HOLD",
          testing_started: false
        });
        return;
      }
      valid.push(row);
    });
    var instruments = {};
    var labs = {};
    valid.forEach(function (_, index) {
      if (index < 180) instruments[INSTRUMENTS[index % 12]] = true;
      else labs[CONTRACT_LABS[(index - 180) % 3]] = true;
    });
    var holdCodes = holds.map(function (item) { return item.code; }).sort();
    var unique = holdCodes.filter(function (code, idx) { return holdCodes.indexOf(code) === idx; });
    var classCounts = { RAW: 0, IN_PROCESS: 0, RELEASE: 0, RETAIN: 0, STABILITY: 0 };
    valid.forEach(function (row) { classCounts[row.sample_class] += 1; });
    return {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      buyer: BUYER,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      valid_completed: valid.length,
      hold: holds.length,
      hold_codes: unique,
      accessioned: valid.length,
      human_released: valid.length,
      autonomous_released: 0,
      instruments: Object.keys(instruments).sort(),
      contract_labs: Object.keys(labs).sort(),
      class_counts: classCounts,
      holds: holds,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      part11_validated: false,
      official_audit_sha256: GOLDEN_AUDIT_SHA256,
      official_custody_sha256: GOLDEN_CUSTODY_SHA256,
      official_results_sha256: GOLDEN_RESULTS_SHA256,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
  }

  function passContract(result) {
    var failures = [];
    Object.keys(GOLDEN_COUNTS).forEach(function (key) {
      var actual = key === "instruments" ? (result.instruments || []).length
        : key === "contract_labs" ? (result.contract_labs || []).length
        : result[key];
      if (actual !== GOLDEN_COUNTS[key]) failures.push(key + "!=" + GOLDEN_COUNTS[key]);
    });
    if (JSON.stringify(result.hold_codes) !== JSON.stringify(["HOLD_DUPLICATE", "HOLD_LABEL", "HOLD_LATE", "HOLD_OOS", "HOLD_TEMPERATURE"])) {
      failures.push("hold_codes");
    }
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
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
