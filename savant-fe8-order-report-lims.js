(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SavantFe8OrderReport = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "savant-fe8-order-report-lims-01";
  var METHOD = "FE8";
  var METHOD_VERSION = "DIN-51819-2022-SYN";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var INVALID_METHODS = ["FE9", "FOUR_BALL", "SRV", "FZG", "RPVOT"];
  var CONDITIONS = [
    { load_kn: 80.0, temp_c: 80.0, speed_min: 7.5, duration_h: 80, lubricant_class: "GREASE" },
    { load_kn: 80.0, temp_c: 120.0, speed_min: 7.5, duration_h: 80, lubricant_class: "GREASE" },
    { load_kn: 10.0, temp_c: 80.0, speed_min: 75.0, duration_h: 80, lubricant_class: "OIL" },
    { load_kn: 10.0, temp_c: 120.0, speed_min: 75.0, duration_h: 500, lubricant_class: "OIL" }
  ];
  var GOLDEN_COUNTS = {
    input_rows: 100,
    accessioned: 80,
    held: 20,
    scheduled: 80,
    unscheduled_holds: 20,
    released_reports: 0,
    blocked_reports: 80
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function flag(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    return /^(1|true|yes|y)$/i.test(String(value).trim());
  }
  function round1(value) { return Number(Number(value).toFixed(1)); }
  function round2(value) { return Number(Number(value).toFixed(2)); }
  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 80; i += 1) {
      var cond = CONDITIONS[(i - 1) % CONDITIONS.length];
      rows.push({
        row_id: "R" + pad(i, 3),
        auth_id: "FE8-V" + pad(i, 3),
        customer_code: "SYN-CUST-" + pad((i % 20) + 1, 2),
        lubricant_code: "SYN-" + cond.lubricant_class + "-" + pad((i % 10) + 1, 2),
        method: METHOD,
        method_version: METHOD_VERSION,
        sds_present: true,
        sds_hash: "SYN-SDS-" + pad(i, 3),
        taf_hash: "SYN-TAF-" + pad(i, 3),
        expected_hold: null,
        instrument: {
          wear_ring_mg: round1(3.0 + ((i - 1) % 80) * 0.1),
          wear_cage_mg: round1(1.0 + ((i - 1) % 40) * 0.1),
          torque_nm: round2(0.40 + ((i - 1) % 20) * 0.01),
          qc_check_std_wear_mg: round1(8.0 + ((i - 1) % 5) * 0.2),
          qc_ok: true
        }
      });
    }
    for (i = 0; i < 5; i += 1) {
      rows.push({
        row_id: "R" + pad(81 + i, 3),
        auth_id: "FE8-HSDS" + pad(i + 1, 2),
        customer_code: "SYN-CUST-HOLD",
        lubricant_code: "SYN-GREASE-HOLD",
        method: METHOD,
        sds_present: false,
        sds_hash: "",
        expected_hold: "MISSING_SDS"
      });
    }
    for (i = 0; i < 5; i += 1) {
      var emptyCustomer = i % 2 === 0;
      rows.push({
        row_id: "R" + pad(86 + i, 3),
        auth_id: "FE8-HMETA" + pad(i + 1, 2),
        customer_code: emptyCustomer ? "" : "SYN-CUST-HOLD",
        lubricant_code: emptyCustomer ? "SYN-GREASE-HOLD" : "",
        method: METHOD,
        sds_present: true,
        sds_hash: "SYN-SDS-META",
        expected_hold: "MISSING_METADATA"
      });
    }
    for (i = 0; i < 5; i += 1) {
      rows.push({
        row_id: "R" + pad(91 + i, 3),
        auth_id: "FE8-V" + pad(i + 1, 3),
        customer_code: "SYN-CUST-01",
        lubricant_code: "SYN-GREASE-01",
        method: METHOD,
        sds_present: true,
        sds_hash: "SYN-SDS-DUP",
        expected_hold: "DUPLICATE_ID"
      });
    }
    for (i = 0; i < 5; i += 1) {
      rows.push({
        row_id: "R" + pad(96 + i, 3),
        auth_id: "FE8-HMETHOD" + pad(i + 1, 2),
        customer_code: "SYN-CUST-HOLD",
        lubricant_code: "SYN-OIL-HOLD",
        method: INVALID_METHODS[i],
        sds_present: true,
        sds_hash: "SYN-SDS-METHOD",
        expected_hold: "INVALID_METHOD"
      });
    }
    return rows;
  }

  function classify(row, seen) {
    var authId = text(row.auth_id);
    var method = text(row.method).toUpperCase();
    var customer = text(row.customer_code);
    var lubricant = text(row.lubricant_code);
    var sds = flag(row.sds_present) && !!text(row.sds_hash);
    if (!authId || !customer || !lubricant) return { ok: false, code: "MISSING_METADATA", auth_id: authId || null };
    if (method !== METHOD) return { ok: false, code: "INVALID_METHOD", auth_id: authId, method: method };
    if (!sds) return { ok: false, code: "MISSING_SDS", auth_id: authId };
    if (seen[authId]) return { ok: false, code: "DUPLICATE_ID", auth_id: authId };
    return { ok: true, auth_id: authId, method: METHOD, route: "FE8_WORKLIST" };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var holds = [];
    inbound.forEach(function (row) {
      var seen = {};
      Object.keys(accessions).forEach(function (key) { seen[accessions[key].auth_id] = true; });
      var verdict = classify(row, seen);
      if (!verdict.ok) {
        holds.push({
          row_id: text(row.row_id),
          auth_id: verdict.auth_id,
          code: verdict.code,
          scheduled: false
        });
        return;
      }
      accessions[verdict.auth_id] = {
        auth_id: verdict.auth_id,
        method: METHOD,
        method_version: METHOD_VERSION,
        route: verdict.route,
        scheduled: true,
        released: false,
        instrument: clone(row.instrument || {}),
        interface_live: false
      };
    });
    var accessioned = Object.keys(accessions).sort().map(function (key) { return accessions[key]; });
    return {
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      accessioned: accessioned.length,
      held: holds.length,
      hold_codes: holds.map(function (item) { return item.code; }),
      scheduled: accessioned.filter(function (item) { return item.scheduled; }).length,
      unscheduled_holds: holds.filter(function (item) { return !item.scheduled; }).length,
      released_reports: 0,
      blocked_reports: accessioned.length,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      production_writes: 0,
      pre_sale_transport: "NONE",
      official_binary: "python3 test_savant_fe8_order_report.py"
    };
  }

  function passContract(result) {
    var failures = [];
    Object.keys(GOLDEN_COUNTS).forEach(function (key) {
      if (result[key] !== GOLDEN_COUNTS[key]) failures.push(key);
    });
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    GOLDEN_COUNTS: GOLDEN_COUNTS,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
