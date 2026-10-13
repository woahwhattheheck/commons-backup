(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CsAnalyticalExpansionCrosslineLims = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "csanalytical-expansion-crossline-evidence-lims-01";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var LINES = ["CCIT", "RAW_MATERIAL", "GAS", "MICRO"];
  var CYCLE = [
    ["CCIT", "VACUUM_DECAY", "ASTM-F2338-09", "PTI-VERIPAC-455"],
    ["CCIT", "HELIUM_LEAK", "USP-1207.1", "PFEIFFER-ASM340"],
    ["CCIT", "HVLD", "USP-1207.2", "NIKKA-HDT-1"],
    ["RAW_MATERIAL", "FTIR_ID", "USP-197A", "THERMO-NICOLET-IS50"],
    ["RAW_MATERIAL", "RESIDUAL_SOLVENT", "USP-467", "AGILENT-7890B"],
    ["GAS", "HEADSPACE_O2", "ASTM-F2714-08", "MOCON-PACCHECK-650"],
    ["GAS", "HEADSPACE_MOISTURE", "ASTM-F2714-08", "MICHELL-S8000"],
    ["MICRO", "BIOBURDEN", "USP-61", "SARTORIUS-MD8"],
    ["MICRO", "STERILITY", "USP-71", "STERITEST-NEO"]
  ];
  var CAPABLE = {};
  CYCLE.forEach(function (item) {
    CAPABLE[item[0] + "|" + item[1] + "|" + item[2] + "|" + item[3]] = true;
  });
  var WRONG_LINE = [
    { submission_id: "CSA-WL01", line: "CCIT", method: "BIOBURDEN", method_version: "USP-61", instrument_id: "SARTORIUS-MD8" },
    { submission_id: "CSA-WL02", line: "RAW_MATERIAL", method: "VACUUM_DECAY", method_version: "ASTM-F2338-09", instrument_id: "PTI-VERIPAC-455" },
    { submission_id: "CSA-WL03", line: "GAS", method: "STERILITY", method_version: "USP-71", instrument_id: "STERITEST-NEO" },
    { submission_id: "CSA-WL04", line: "MICRO", method: "HELIUM_LEAK", method_version: "USP-1207.1", instrument_id: "PFEIFFER-ASM340" },
    { submission_id: "CSA-WL05", line: "CCIT", method: "FTIR_ID", method_version: "USP-197A", instrument_id: "THERMO-NICOLET-IS50" },
    { submission_id: "CSA-WL06", line: "GAS", method: "HVLD", method_version: "USP-1207.2", instrument_id: "NIKKA-HDT-1" },
    { submission_id: "CSA-WL07", line: "MICRO", method: "HEADSPACE_O2", method_version: "ASTM-F2714-08", instrument_id: "MOCON-PACCHECK-650" }
  ];
  var GOLDEN_COUNTS = {
    input_rows: 120,
    ready: 90,
    held: 30,
    jobs: 100,
    scheduled: 100,
    intake_holds_scheduled: 0,
    held_staged: 0,
    released_reports: 0,
    staged_reports: 90
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }
  function keyOf(line, method, version, instrument) {
    return text(line) + "|" + text(method) + "|" + text(version) + "|" + text(instrument);
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 90; i += 1) {
      var cap = CYCLE[(i - 1) % CYCLE.length];
      rows.push({
        row_id: "R" + pad(i, 3),
        submission_id: "CSA-V" + pad(i, 3),
        study_id: "STU-" + pad(((i - 1) % 18) + 1, 3),
        sample_id: "SMP-" + cap[0].slice(0, 3) + "-" + pad(i, 3),
        lot_id: "LOT-" + pad(((i - 1) % 24) + 1, 3),
        product_id: "PRD-" + cap[0].slice(0, 3) + "-" + pad(((i - 1) % 12) + 1, 2),
        package_component: "component-" + i,
        line: cap[0],
        method: cap[1],
        method_version: cap[2],
        instrument_id: cap[3],
        qc_fail: false,
        source_hash_ok: true,
        expected_hold: null
      });
    }
    for (i = 0; i < 7; i += 1) {
      var miss = WRONG_LINE[i];
      rows.push({
        row_id: "R" + pad(91 + i, 3),
        submission_id: miss.submission_id,
        study_id: "STU-001",
        sample_id: "SMP-WL-" + pad(i + 1, 3),
        lot_id: "LOT-01",
        product_id: "PRD-WL-01",
        package_component: "component-wl",
        line: miss.line,
        method: miss.method,
        method_version: miss.method_version,
        instrument_id: miss.instrument_id,
        qc_fail: false,
        source_hash_ok: true,
        expected_hold: "WRONG_LINE"
      });
    }
    for (i = 0; i < 5; i += 1) {
      cap = CYCLE[i % CYCLE.length];
      rows.push({
        row_id: "R" + pad(98 + i, 3),
        submission_id: "CSA-MS" + pad(i + 1, 2),
        study_id: i === 1 || i === 3 || i === 4 ? "STU-099" : "",
        sample_id: i === 4 ? "" : "SMP-MS",
        lot_id: i === 4 ? "" : "LOT-99",
        product_id: i === 3 ? "" : "PRD-MS-01",
        package_component: i === 1 || i === 2 ? "" : "component-ms",
        line: cap[0],
        method: cap[1],
        method_version: cap[2],
        instrument_id: cap[3],
        qc_fail: false,
        source_hash_ok: true,
        expected_hold: "MISSING_METADATA"
      });
    }
    for (i = 0; i < 5; i += 1) {
      cap = CYCLE[i % CYCLE.length];
      rows.push({
        row_id: "R" + pad(103 + i, 3),
        submission_id: "CSA-QC" + pad(i + 1, 2),
        study_id: "STU-001",
        sample_id: "SMP-QC-" + pad(i + 1, 3),
        lot_id: "LOT-01",
        product_id: "PRD-QC-01",
        package_component: "component-qc",
        line: cap[0],
        method: cap[1],
        method_version: cap[2],
        instrument_id: cap[3],
        qc_fail: true,
        source_hash_ok: true,
        expected_hold: "QC_FAIL"
      });
    }
    for (i = 0; i < 5; i += 1) {
      cap = CYCLE[(i + 3) % CYCLE.length];
      rows.push({
        row_id: "R" + pad(108 + i, 3),
        submission_id: "CSA-SH" + pad(i + 1, 2),
        study_id: "STU-001",
        sample_id: "SMP-SH-" + pad(i + 1, 3),
        lot_id: "LOT-01",
        product_id: "PRD-SH-01",
        package_component: "component-sh",
        line: cap[0],
        method: cap[1],
        method_version: cap[2],
        instrument_id: cap[3],
        qc_fail: false,
        source_hash_ok: false,
        expected_hold: "SOURCE_HASH_MISMATCH"
      });
    }
    for (i = 0; i < 8; i += 1) {
      cap = CYCLE[i % CYCLE.length];
      rows.push({
        row_id: "R" + pad(113 + i, 3),
        submission_id: "CSA-V" + pad(i + 1, 3),
        study_id: "STU-001",
        sample_id: "SMP-DUP",
        lot_id: "LOT-01",
        product_id: "PRD-DUP-01",
        package_component: "component-dup",
        line: cap[0],
        method: cap[1],
        method_version: cap[2],
        instrument_id: cap[3],
        qc_fail: false,
        source_hash_ok: true,
        expected_hold: "DUPLICATE_ID"
      });
    }
    return rows;
  }

  function classify(row, seen) {
    var submissionId = text(row.submission_id);
    var study = text(row.study_id);
    var sample = text(row.sample_id);
    var lot = text(row.lot_id);
    var product = text(row.product_id);
    var pack = text(row.package_component);
    var route = CAPABLE[keyOf(row.line, row.method, row.method_version, row.instrument_id)];
    if (!study || !pack || !product || (!sample && !lot) || !submissionId) {
      return { ok: false, code: "MISSING_METADATA", intake: true, submission_id: submissionId || null };
    }
    if (seen[submissionId]) return { ok: false, code: "DUPLICATE_ID", intake: true, submission_id: submissionId };
    if (!route) return { ok: false, code: "WRONG_LINE", intake: true, submission_id: submissionId };
    if (row.source_hash_ok === false) return { ok: false, code: "SOURCE_HASH_MISMATCH", intake: false, submission_id: submissionId };
    if (row.qc_fail) return { ok: false, code: "QC_FAIL", intake: false, submission_id: submissionId };
    return { ok: true, submission_id: submissionId, line: text(row.line) };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var jobs = {};
    var holds = [];
    inbound.forEach(function (row) {
      var seen = {};
      Object.keys(jobs).forEach(function (key) { seen[jobs[key].submission_id] = true; });
      var verdict = classify(row, seen);
      if (!verdict.ok) {
        holds.push({
          row_id: text(row.row_id),
          submission_id: verdict.submission_id,
          code: verdict.code,
          intake_hold: !!verdict.intake,
          scheduled: !verdict.intake,
          staged: false
        });
        if (!verdict.intake) {
          jobs[verdict.submission_id] = {
            submission_id: verdict.submission_id,
            line: text(row.line),
            method: row.method,
            state: "HOLD",
            scheduled: true,
            staged: false,
            released: false
          };
        }
        return;
      }
      jobs[verdict.submission_id] = {
        submission_id: verdict.submission_id,
        line: verdict.line,
        method: row.method,
        state: "READY",
        scheduled: true,
        staged: true,
        released: false
      };
    });
    var accessioned = Object.keys(jobs).sort().map(function (key) { return jobs[key]; });
    return {
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      lines: LINES.slice(),
      input_rows: inbound.length,
      ready: accessioned.filter(function (item) { return item.state === "READY"; }).length,
      held: holds.length,
      jobs: accessioned.length,
      scheduled: accessioned.filter(function (item) { return item.scheduled; }).length,
      intake_holds_scheduled: holds.filter(function (item) { return item.intake_hold && item.scheduled; }).length,
      held_staged: accessioned.filter(function (item) { return item.state === "HOLD" && item.staged; }).length,
      hold_codes: holds.map(function (item) { return item.code; }),
      released_reports: 0,
      staged_reports: accessioned.filter(function (item) { return item.staged; }).length,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      compliance_decision: false,
      production_writes: 0,
      pre_sale_transport: "NONE",
      official_binary: "python3 test_csanalytical_expansion_crossline_lims.py"
    };
  }

  function passContract(result) {
    var failures = [];
    Object.keys(GOLDEN_COUNTS).forEach(function (key) {
      if (result[key] !== GOLDEN_COUNTS[key]) failures.push(key);
    });
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    if (result.compliance_decision !== false) failures.push("compliance_decision");
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
