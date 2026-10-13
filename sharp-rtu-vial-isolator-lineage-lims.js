(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SharpRtuVialIsolatorLineageLims = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "sharp-rtu-vial-isolator-lineage-lims-01";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var LINES = ["ISOLATOR_FILL", "LYOPHILIZER", "ANALYTICAL", "STABILITY", "STERILITY"];
  var CYCLE = [
    ["ISOLATOR_FILL", "RTU_2R", "FILL_WEIGHT", "FW-2R-v3"],
    ["ISOLATOR_FILL", "RTU_6R", "FILL_WEIGHT", "FW-6R-v2"],
    ["ISOLATOR_FILL", "RTU_10R", "FILL_WEIGHT", "FW-10R-v4"],
    ["ISOLATOR_FILL", "RTU_20R", "FILL_WEIGHT", "FW-20R-v1"],
    ["LYOPHILIZER", "RTU_2R", "LYO_CYCLE", "LYO-2R-C21"],
    ["LYOPHILIZER", "RTU_6R", "LYO_CYCLE", "LYO-6R-C18"],
    ["LYOPHILIZER", "RTU_10R", "LYO_CYCLE", "LYO-10R-C12"],
    ["LYOPHILIZER", "RTU_20R", "LYO_CYCLE", "LYO-20R-C09"],
    ["ANALYTICAL", "RTU_2R", "HPLC_ASSAY", "USP-621-v1"],
    ["ANALYTICAL", "RTU_6R", "UV_ID", "USP-197-v2"],
    ["ANALYTICAL", "RTU_10R", "HPLC_ASSAY", "USP-621-v1"],
    ["STABILITY", "RTU_2R", "ICH_PULL", "ICH-Q1A-v3"],
    ["STABILITY", "RTU_10R", "ICH_PULL", "ICH-Q1A-v3"],
    ["STERILITY", "RTU_20R", "USP71_STERILITY", "USP-71-v1"],
    ["STERILITY", "RTU_6R", "ISOLATOR_BIOBURDEN", "USP-61-v2"]
  ];
  var CAPABLE = {};
  var KNOWN_METHODS = {};
  var METHOD_VERSIONS = {};
  CYCLE.forEach(function (item) {
    CAPABLE[item[0] + "|" + item[1] + "|" + item[2] + "|" + item[3]] = true;
    KNOWN_METHODS[item[2]] = true;
    if (!METHOD_VERSIONS[item[2]]) METHOD_VERSIONS[item[2]] = {};
    METHOD_VERSIONS[item[2]][item[3]] = true;
  });
  var FORMAT_LINE = [
    { submission_id: "SHP-FM01", line: "ISOLATOR_FILL", format: "PFS_1ML", method: "FILL_WEIGHT", method_version: "FW-2R-v3" },
    { submission_id: "SHP-FM02", line: "LYOPHILIZER", format: "CARTRIDGE_3ML", method: "LYO_CYCLE", method_version: "LYO-2R-C21" },
    { submission_id: "SHP-FM03", line: "ANALYTICAL", format: "AMPULE_1ML", method: "HPLC_ASSAY", method_version: "USP-621-v1" },
    { submission_id: "SHP-FM04", line: "STERILITY", format: "PFS_1ML", method: "USP71_STERILITY", method_version: "USP-71-v1" },
    { submission_id: "SHP-FM05", line: "STABILITY", format: "CARTRIDGE_3ML", method: "ICH_PULL", method_version: "ICH-Q1A-v3" },
    { submission_id: "SHP-FM06", line: "ISOLATOR_FILL", format: "RTU_2R", method: "USP71_STERILITY", method_version: "USP-71-v1" },
    { submission_id: "SHP-FM07", line: "LYOPHILIZER", format: "RTU_6R", method: "HPLC_ASSAY", method_version: "USP-621-v1" }
  ];
  var GOLDEN_COUNTS = {
    input_rows: 120,
    ready: 90,
    held: 30,
    jobs: 100,
    scheduled: 100,
    intake_holds_scheduled: 0,
    held_staged: 0,
    released_packs: 0,
    staged_packs: 90
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }
  function keyOf(line, fmt, method, version) {
    return text(line) + "|" + text(fmt) + "|" + text(method) + "|" + text(version);
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 90; i += 1) {
      var cap = CYCLE[(i - 1) % CYCLE.length];
      rows.push({
        row_id: "R" + pad(i, 3),
        submission_id: "SHP-V" + pad(i, 3),
        component_id: "CMP-" + pad(i, 3),
        batch_id: "BAT-" + pad(((i - 1) % 30) + 1, 3),
        line: cap[0],
        format: cap[1],
        method: cap[2],
        method_version: cap[3],
        isolator_slot: "ISO-" + cap[1].slice(-2) + "-" + pad(i, 2),
        lyo_shelf: "LYO-" + pad(i, 2),
        weight_ok: true,
        qc_fail: false,
        expected_hold: null
      });
    }
    for (i = 0; i < 7; i += 1) {
      var miss = FORMAT_LINE[i];
      rows.push({
        row_id: "R" + pad(91 + i, 3),
        submission_id: miss.submission_id,
        component_id: "CMP-FM" + pad(i + 1, 2),
        batch_id: "BAT-FM" + pad(i + 1, 2),
        line: miss.line,
        format: miss.format,
        method: miss.method,
        method_version: miss.method_version,
        isolator_slot: "ISO-FM-" + pad(i + 1, 2),
        lyo_shelf: "LYO-FM-" + pad(i + 1, 2),
        weight_ok: true,
        qc_fail: false,
        expected_hold: "FORMAT_LINE_MISMATCH"
      });
    }
    var missing = [
      { submission_id: "SHP-MV01", method: "", method_version: "FW-2R-v3" },
      { submission_id: "SHP-MV02", method: "FILL_WEIGHT", method_version: "" },
      { submission_id: "SHP-MV03", method: "", method_version: "" },
      { submission_id: "SHP-MV04", method: "NOT_A_METHOD", method_version: "USP-621-v1" },
      { submission_id: "SHP-MV05", method: "FILL_WEIGHT", method_version: "NO-SUCH-VERSION" }
    ];
    for (i = 0; i < 5; i += 1) {
      cap = CYCLE[i % CYCLE.length];
      rows.push({
        row_id: "R" + pad(98 + i, 3),
        submission_id: missing[i].submission_id,
        component_id: "CMP-MV" + pad(i + 1, 2),
        batch_id: "BAT-MV" + pad(i + 1, 2),
        line: cap[0],
        format: cap[1],
        method: missing[i].method,
        method_version: missing[i].method_version,
        isolator_slot: "ISO-MV-" + pad(i + 1, 2),
        lyo_shelf: "LYO-MV-" + pad(i + 1, 2),
        weight_ok: true,
        qc_fail: false,
        expected_hold: "MISSING_METHOD_VERSION"
      });
    }
    for (i = 0; i < 5; i += 1) {
      cap = CYCLE[i % CYCLE.length];
      rows.push({
        row_id: "R" + pad(103 + i, 3),
        submission_id: "SHP-WS" + pad(i + 1, 2),
        component_id: "CMP-WS" + pad(i + 1, 2),
        batch_id: "BAT-WS" + pad(i + 1, 2),
        line: cap[0],
        format: cap[1],
        method: cap[2],
        method_version: cap[3],
        isolator_slot: i < 3 ? rows[i].isolator_slot : "ISO-WS-" + pad(i + 1, 2),
        lyo_shelf: i === 1 ? rows[1].lyo_shelf : "LYO-WS-" + pad(i + 1, 2),
        weight_ok: i < 3,
        qc_fail: false,
        expected_hold: "WEIGHT_SLOT_CONFLICT"
      });
    }
    for (i = 0; i < 5; i += 1) {
      cap = CYCLE[(i + 8) % CYCLE.length];
      rows.push({
        row_id: "R" + pad(108 + i, 3),
        submission_id: "SHP-QC" + pad(i + 1, 2),
        component_id: "CMP-QC" + pad(i + 1, 2),
        batch_id: "BAT-QC" + pad(i + 1, 2),
        line: cap[0],
        format: cap[1],
        method: cap[2],
        method_version: cap[3],
        isolator_slot: "ISO-QC-" + pad(i + 1, 2),
        lyo_shelf: "LYO-QC-" + pad(i + 1, 2),
        weight_ok: true,
        qc_fail: true,
        expected_hold: "QC_STERILITY_FAIL"
      });
    }
    for (i = 0; i < 8; i += 1) {
      cap = CYCLE[i % CYCLE.length];
      rows.push({
        row_id: "R" + pad(113 + i, 3),
        submission_id: "SHP-DB" + pad(i + 1, 2),
        component_id: rows[i].component_id,
        batch_id: rows[i].batch_id,
        line: cap[0],
        format: cap[1],
        method: cap[2],
        method_version: cap[3],
        isolator_slot: "ISO-DB-" + pad(i + 1, 2),
        lyo_shelf: "LYO-DB-" + pad(i + 1, 2),
        weight_ok: true,
        qc_fail: false,
        expected_hold: "DUPLICATE_COMPONENT_BATCH"
      });
    }
    return rows;
  }

  function classify(row, seen, slots, shelves) {
    var submissionId = text(row.submission_id);
    var component = text(row.component_id);
    var batch = text(row.batch_id);
    var method = text(row.method);
    var version = text(row.method_version);
    var pair = component + "|" + batch;
    if (!method || !version || !KNOWN_METHODS[method] || !(METHOD_VERSIONS[method] && METHOD_VERSIONS[method][version])) {
      return { ok: false, code: "MISSING_METHOD_VERSION", intake: true, submission_id: submissionId || null };
    }
    if (!component || !batch || seen[pair]) {
      return { ok: false, code: "DUPLICATE_COMPONENT_BATCH", intake: true, submission_id: submissionId };
    }
    if (!CAPABLE[keyOf(row.line, row.format, row.method, row.method_version)]) {
      return { ok: false, code: "FORMAT_LINE_MISMATCH", intake: true, submission_id: submissionId };
    }
    if (slots[text(row.isolator_slot)] || shelves[text(row.lyo_shelf)] || row.weight_ok === false) {
      return { ok: false, code: "WEIGHT_SLOT_CONFLICT", intake: false, submission_id: submissionId };
    }
    if (row.qc_fail) return { ok: false, code: "QC_STERILITY_FAIL", intake: false, submission_id: submissionId };
    return { ok: true, submission_id: submissionId, line: text(row.line), pair: pair };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var jobs = {};
    var holds = [];
    var seen = {};
    var slots = {};
    var shelves = {};
    inbound.forEach(function (row) {
      var verdict = classify(row, seen, slots, shelves);
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
          seen[text(row.component_id) + "|" + text(row.batch_id)] = true;
          slots[text(row.isolator_slot)] = true;
          shelves[text(row.lyo_shelf)] = true;
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
      seen[verdict.pair] = true;
      slots[text(row.isolator_slot)] = true;
      shelves[text(row.lyo_shelf)] = true;
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
      released_packs: 0,
      staged_packs: accessioned.filter(function (item) { return item.staged; }).length,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      compliance_decision: false,
      gmp_decision: false,
      production_writes: 0,
      pre_sale_transport: "NONE",
      official_binary: "python3 test_sharp_rtu_vial_isolator_lineage.py"
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
    if (result.gmp_decision !== false) failures.push("gmp_decision");
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
