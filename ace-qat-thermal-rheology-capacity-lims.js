(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AceQatThermalRheologyCapacity = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "ace-qat-thermal-rheology-capacity-lims-01";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var METHODS = ["DSC", "TGA", "DMA", "TMA", "SDT", "AR-G2"];
  var CYCLE = [
    ["DSC", "ASTM-D3418-21", "ACE", "DSC-Q2000", "ACE_DSC"],
    ["TGA", "ASTM-E1131-20", "ACE", "TGA-5500", "ACE_TGA"],
    ["DMA", "ASTM-D4065-20", "ACE", "DMA-850", "ACE_DMA"],
    ["TMA", "ASTM-E831-19", "QAT", "TMA-450", "QAT_TMA"],
    ["SDT", "ASTM-E1131-20", "QAT", "SDT-650", "QAT_SDT"],
    ["AR-G2", "ASTM-D4440-15", "QAT", "AR-G2", "QAT_RHEOLOGY"]
  ];
  var CAPABLE = {};
  CYCLE.forEach(function (item) {
    CAPABLE[item[0] + "|" + item[1] + "|" + item[2] + "|" + item[3]] = item[4];
  });
  var MISMATCHES = [
    { order_id: "AQ-CM01", method: "DSC", method_version: "ASTM-D3418-21", source: "QAT", instrument_id: "DSC-Q2000" },
    { order_id: "AQ-CM02", method: "TGA", method_version: "ASTM-E1131-08", source: "ACE", instrument_id: "TGA-5500" },
    { order_id: "AQ-CM03", method: "DMA", method_version: "ASTM-D4065-20", source: "QAT", instrument_id: "DMA-850" },
    { order_id: "AQ-CM04", method: "TMA", method_version: "ASTM-E831-19", source: "ACE", instrument_id: "TMA-450" },
    { order_id: "AQ-CM05", method: "SDT", method_version: "ASTM-E1131-20", source: "QAT", instrument_id: "DSC-Q2000" },
    { order_id: "AQ-CM06", method: "AR-G2", method_version: "ASTM-D4440-15", source: "ACE", instrument_id: "AR-G2" },
    { order_id: "AQ-CM07", method: "DSC", method_version: "ASTM-D3418-21", source: "ACE", instrument_id: "AR-G2" },
    { order_id: "AQ-CM08", method: "MDSC", method_version: "ASTM-D3418-21", source: "ACE", instrument_id: "DSC-Q2000" },
    { order_id: "AQ-CM09", method: "TGA", method_version: "ISO-11358-1", source: "ACE", instrument_id: "TGA-5500" },
    { order_id: "AQ-CM10", method: "AR-G2", method_version: "ASTM-D4440-15", source: "QAT", instrument_id: "ARES-G2" }
  ];
  var GOLDEN_COUNTS = {
    input_rows: 120,
    ready: 90,
    held: 30,
    jobs: 100,
    released_reports: 0,
    blocked_reports: 100
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }
  function keyOf(method, version, source, instrument) {
    return text(method) + "|" + text(version) + "|" + text(source) + "|" + text(instrument);
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 90; i += 1) {
      var cap = CYCLE[(i - 1) % CYCLE.length];
      rows.push({
        row_id: "R" + pad(i, 3),
        order_id: "AQ-V" + pad(i, 3),
        method: cap[0],
        method_version: cap[1],
        source: cap[2],
        instrument_id: cap[3],
        qc_fail: false,
        expected_hold: null
      });
    }
    for (i = 0; i < 10; i += 1) {
      var miss = MISMATCHES[i];
      rows.push({
        row_id: "R" + pad(91 + i, 3),
        order_id: miss.order_id,
        method: miss.method,
        method_version: miss.method_version,
        source: miss.source,
        instrument_id: miss.instrument_id,
        qc_fail: false,
        expected_hold: "CAPABILITY_MISMATCH"
      });
    }
    for (i = 0; i < 10; i += 1) {
      cap = CYCLE[i % CYCLE.length];
      rows.push({
        row_id: "R" + pad(101 + i, 3),
        order_id: "AQ-QC" + pad(i + 1, 2),
        method: cap[0],
        method_version: cap[1],
        source: cap[2],
        instrument_id: cap[3],
        qc_fail: true,
        expected_hold: "QC_FAIL"
      });
    }
    for (i = 0; i < 10; i += 1) {
      cap = CYCLE[i % CYCLE.length];
      rows.push({
        row_id: "R" + pad(111 + i, 3),
        order_id: "AQ-V" + pad(i + 1, 3),
        method: cap[0],
        method_version: cap[1],
        source: cap[2],
        instrument_id: cap[3],
        qc_fail: false,
        expected_hold: "DUPLICATE_ID"
      });
    }
    return rows;
  }

  function classify(row, seen) {
    var orderId = text(row.order_id);
    var route = CAPABLE[keyOf(row.method, row.method_version, row.source, row.instrument_id)];
    if (!orderId) return { ok: false, code: "CAPABILITY_MISMATCH" };
    if (seen[orderId]) return { ok: false, code: "DUPLICATE_ID", order_id: orderId };
    if (!route) return { ok: false, code: "CAPABILITY_MISMATCH", order_id: orderId };
    return { ok: true, order_id: orderId, route: route };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var jobs = {};
    var holds = [];
    inbound.forEach(function (row) {
      var seen = {};
      Object.keys(jobs).forEach(function (key) { seen[jobs[key].order_id] = true; });
      var verdict = classify(row, seen);
      if (!verdict.ok) {
        holds.push({ row_id: text(row.row_id), order_id: verdict.order_id, code: verdict.code });
        return;
      }
      if (row.qc_fail) {
        jobs[verdict.order_id] = {
          order_id: verdict.order_id,
          method: row.method,
          source: row.source,
          route: verdict.route,
          state: "HOLD",
          released: false
        };
        holds.push({ row_id: text(row.row_id), order_id: verdict.order_id, code: "QC_FAIL" });
        return;
      }
      jobs[verdict.order_id] = {
        order_id: verdict.order_id,
        method: row.method,
        source: row.source,
        route: verdict.route,
        state: "READY",
        released: false
      };
    });
    var accessioned = Object.keys(jobs).sort().map(function (key) { return jobs[key]; });
    return {
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      methods: METHODS.slice(),
      input_rows: inbound.length,
      ready: accessioned.filter(function (item) { return item.state === "READY"; }).length,
      held: holds.length,
      jobs: accessioned.length,
      hold_codes: holds.map(function (item) { return item.code; }),
      released_reports: 0,
      blocked_reports: accessioned.length,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      production_writes: 0,
      pre_sale_transport: "NONE",
      official_binary: "python3 test_ace_qat_thermal_rheology_capacity.py"
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
