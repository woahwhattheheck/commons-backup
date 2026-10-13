(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ClarkD4172Proficiency = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "clark-d4172-proficiency-lims-01";
  var SCHEMA = "commons-clark-d4172-proficiency-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var METHOD_VERSION = "D4172-21";
  var REQUIRED_REPLICATES = 2;
  var R_MM = 12;
  var BIG_R_MM = 28;
  var LEAK_TOKENS = ["Clark Testing", "Paul Heffernan", "Heffernan", "LAB-SYN-", "OIL-SYN-"];
  var VALID_SET_IDS = [];
  var MISSING_SET_IDS = [];
  var R_BREACH_SET_IDS = [];
  var R_CAP_BREACH_SET_IDS = [];
  var i;
  for (i = 1; i <= 48; i += 1) VALID_SET_IDS.push("D4172-PT-" + String(i).padStart(2, "0"));
  for (i = 49; i <= 54; i += 1) MISSING_SET_IDS.push("D4172-PT-" + String(i).padStart(2, "0"));
  for (i = 55; i <= 57; i += 1) R_BREACH_SET_IDS.push("D4172-PT-" + String(i).padStart(2, "0"));
  for (i = 58; i <= 60; i += 1) R_CAP_BREACH_SET_IDS.push("D4172-PT-" + String(i).padStart(2, "0"));

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function cents(value) { return Math.round(Number(value) * 100); }
  function money(centsValue) { return (centsValue / 100).toFixed(2); }
  function evenRound(value) {
    var floor = Math.floor(value);
    var frac = value - floor;
    if (frac < 0.5) return floor;
    if (frac > 0.5) return floor + 1;
    return floor % 2 === 0 ? floor : floor + 1;
  }
  function runWsd(measurements) {
    var sum = 0;
    for (var n = 0; n < measurements.length; n += 1) sum += cents(measurements[n]);
    return evenRound(sum / measurements.length);
  }
  function leakTokensIn(value) {
    var blob = JSON.stringify(value);
    return LEAK_TOKENS.filter(function (token) { return blob.indexOf(token) !== -1; });
  }
  function calculateSet(row) {
    var runs = [];
    (row.replicates || []).forEach(function (item) {
      var measurements = item.measurements_mm || [];
      if (measurements.length !== 6) return;
      runs.push({
        run_id: item.run_id,
        measurements_mm: measurements.map(function (m) { return money(cents(m)); }),
        wsd_mm: money(runWsd(measurements))
      });
    });
    var hold = null;
    var wsd = null;
    var repeatDelta = null;
    var reproDelta = null;
    if (String(row.method_version || "") !== METHOD_VERSION) {
      hold = "HOLD_METHOD_VERSION";
    } else if (runs.length < REQUIRED_REPLICATES) {
      hold = "HOLD_MISSING_REPLICATE";
    } else {
      var first = cents(runs[0].wsd_mm);
      var second = cents(runs[1].wsd_mm);
      wsd = evenRound((first + second) / 2);
      repeatDelta = Math.abs(first - second);
      reproDelta = Math.abs(wsd - cents(row.assigned_wsd_mm));
      if (repeatDelta > R_MM) hold = "HOLD_QC_REPEATABILITY";
      else if (reproDelta > BIG_R_MM) hold = "HOLD_QC_REPRODUCIBILITY";
    }
    return {
      run_results: runs,
      wsd_mm: wsd == null ? null : money(wsd),
      repeatability_delta_mm: repeatDelta == null ? null : money(repeatDelta),
      reproducibility_delta_mm: reproDelta == null ? null : money(reproDelta),
      hold: hold,
      state: hold || "READY_FOR_HUMAN"
    };
  }
  function publicPacket(row, calc) {
    return {
      set_id: row.set_id,
      cycle: row.cycle,
      procedure: row.procedure,
      method_version: row.method_version,
      load_n: row.load_n,
      participant_blind_id: row.participant_blind_id,
      sample_blind_id: row.sample_blind_id,
      assigned_wsd_mm: row.assigned_wsd_mm,
      wsd_mm: calc.wsd_mm,
      unit: "mm",
      r_mm: row.r_mm,
      R_mm: row.R_mm,
      repeatability_delta_mm: calc.repeatability_delta_mm,
      reproducibility_delta_mm: calc.reproducibility_delta_mm,
      state: calc.state,
      hold: calc.hold,
      released: false
    };
  }
  function runGate(pack) {
    var inbound = clone(pack);
    var records = inbound.sets.map(function (row) {
      var calc = calculateSet(row);
      return publicPacket(row, calc);
    });
    var ready = records.filter(function (item) { return item.state === "READY_FOR_HUMAN"; });
    var held = records.filter(function (item) { return String(item.state).indexOf("HOLD") === 0; });
    var holdCodes = Array.from(new Set(held.map(function (item) { return item.hold; }))).sort();
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_sets: inbound.sets.length,
      processed: records.length,
      ready: ready.length,
      held: held.length,
      ready_ids: ready.map(function (item) { return item.set_id; }),
      hold_ids: held.map(function (item) { return item.set_id; }),
      hold_codes: holdCodes,
      released_coas: 0,
      sample_swaps: 0,
      participant_swaps: 0,
      identity_leaks: leakTokensIn({
        packets: records,
        fixture_has_sealed: Object.prototype.hasOwnProperty.call(inbound, "sealed")
      }),
      public_packets: records,
      fixture_sha256: inbound.fixture_sha256 || null,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_certification: false,
      autonomous_release: false,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
    if (inbound.sealed) body.identity_leaks.push("sealed-map-present");
    return body;
  }
  function passContract(result) {
    var failures = [];
    if (result.input_sets !== 60) failures.push("input_sets!=60");
    if (result.ready !== 48) failures.push("ready!=48");
    if (result.held !== 12) failures.push("held!=12");
    if (JSON.stringify(result.ready_ids) !== JSON.stringify(VALID_SET_IDS)) failures.push("ready_ids");
    if (JSON.stringify(result.hold_ids) !== JSON.stringify(MISSING_SET_IDS.concat(R_BREACH_SET_IDS, R_CAP_BREACH_SET_IDS))) {
      failures.push("hold_ids");
    }
    if (JSON.stringify(result.hold_codes) !== JSON.stringify([
      "HOLD_MISSING_REPLICATE",
      "HOLD_QC_REPEATABILITY",
      "HOLD_QC_REPRODUCIBILITY"
    ])) failures.push("hold_codes");
    if (result.released_coas !== 0) failures.push("released_coas");
    if (result.sample_swaps !== 0) failures.push("sample_swaps");
    if (result.participant_swaps !== 0) failures.push("participant_swaps");
    if (result.identity_leaks && result.identity_leaks.length) failures.push("identity_leaks");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    var first = (result.public_packets || []).find(function (item) { return item.set_id === "D4172-PT-01"; });
    if (!first || first.wsd_mm !== "0.41") failures.push("pt01_wsd");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    SCHEMA: SCHEMA,
    TRUTH_GATE: TRUTH_GATE,
    runGate: runGate,
    passContract: passContract,
    leakTokensIn: leakTokensIn
  };
});
