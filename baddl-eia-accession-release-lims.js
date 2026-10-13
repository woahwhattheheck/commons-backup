(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BaddlEiaAccessionRelease = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "baddl-eia-accession-release-lims-01";
  var SCHEMA = "commons-baddl-eia-accession-release-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var BUYER = "Florida BADDL / Y. Reddy Bommineni";
  var WORKLIST_ROUTE = "EIA_WORKLIST";
  var CURRENT_PAPER_VERSION = "VS10-11-CURRENT";
  var REPORT_ROUTES = {
    PAPER_VS1011: "SIM_PAPER_REPORT",
    VSPS: "SIM_VSPS_PORTAL",
    GVL: "SIM_GVL_PORTAL"
  };
  var SIMULATED_RESULTS = {
    "SYN-EIA-G05": "POSITIVE",
    "SYN-EIA-G06": "POSITIVE",
    "SYN-EIA-G07": "INVALID"
  };
  var GOLDEN_COUNTS = {
    input_rows: 24,
    worklist: 22,
    hold: 2,
    negative: 19,
    positive: 2,
    invalid: 1,
    human_releasable: 21,
    human_released: 21,
    invalid_hold: 1,
    autonomous_released: 0
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function flag(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    return /^(1|true|yes|y)$/i.test(String(value).trim());
  }
  function row(rowId, source, index, opts) {
    opts = opts || {};
    var prefix = { PAPER_VS1011: "P", VSPS: "V", GVL: "G" }[source];
    var token = "SYN-EIA-" + prefix + String(index).padStart(2, "0");
    return {
      row_id: rowId,
      source: source,
      form_version: source === "PAPER_VS1011" ? CURRENT_PAPER_VERSION : source + "-CURRENT",
      form_id: "SYN-FORM-" + prefix + String(index).padStart(2, "0"),
      sample_id: opts.sample_id || token,
      tube_id: opts.tube_id || token,
      owner_ref: "SYN-OWN-" + prefix + String(index).padStart(2, "0"),
      animal_ref: "SYN-EQ-" + prefix + String(index).padStart(2, "0"),
      species: "equine",
      vet_ref: "SYN-VET-" + prefix + String(index).padStart(2, "0"),
      vet_accredited: true,
      signature_present: opts.signature_present !== false,
      complete: true,
      assay: "EIA"
    };
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 8; i += 1) {
      rows.push(row("P" + String(i).padStart(2, "0"), "PAPER_VS1011", i, { signature_present: i !== 8 }));
    }
    for (i = 1; i <= 8; i += 1) rows.push(row("V" + String(i).padStart(2, "0"), "VSPS", i));
    for (i = 1; i <= 8; i += 1) {
      if (i === 8) {
        rows.push(row("G08", "GVL", 8, { tube_id: "SYN-EIA-G07", sample_id: "SYN-EIA-G08" }));
      } else {
        rows.push(row("G" + String(i).padStart(2, "0"), "GVL", i));
      }
    }
    return rows;
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var holds = [];
    var tubeIndex = {};
    inbound.forEach(function (item) {
      var source = text(item.source).toUpperCase();
      var sampleId = text(item.sample_id);
      var tubeId = text(item.tube_id);
      if (source === "PAPER_VS1011" && !flag(item.signature_present)) {
        holds.push({ row_id: text(item.row_id), sample_id: sampleId, tube_id: tubeId, source: source, code: "HOLD_UNSIGNED_FORM", state: "HOLD" });
        return;
      }
      if (tubeId && tubeIndex[tubeId]) {
        holds.push({ row_id: text(item.row_id), sample_id: sampleId, tube_id: tubeId, source: source, code: "HOLD_DUPLICATE_TUBE_ID", state: "HOLD" });
        return;
      }
      if (!sampleId || sampleId !== tubeId) {
        holds.push({ row_id: text(item.row_id), sample_id: sampleId || null, tube_id: tubeId || null, source: source, code: "HOLD_SAMPLE_TUBE_MISMATCH", state: "HOLD" });
        return;
      }
      var accId = "BADDL-EIA-" + sampleId + "-" + source;
      if (accessions[accId]) return;
      var result = SIMULATED_RESULTS[sampleId] || "NEGATIVE";
      var released = result !== "INVALID";
      accessions[accId] = {
        accession_id: accId,
        sample_id: sampleId,
        tube_id: tubeId,
        source: source,
        route: WORKLIST_ROUTE,
        simulated_result: result,
        released: released,
        report_route: released ? REPORT_ROUTES[source] : null,
        report_status: released ? "RELEASED" : "HOLD_INVALID_RESULT",
        interface_state: "SIMULATED",
        interface_live: false,
        animal_status: null
      };
      tubeIndex[tubeId] = accId;
    });
    var accessioned = Object.keys(accessions).map(function (id) { return accessions[id]; })
      .sort(function (a, b) { return a.sample_id < b.sample_id ? -1 : 1; });
    var resultCounts = { NEGATIVE: 0, POSITIVE: 0, INVALID: 0 };
    accessioned.forEach(function (item) { resultCounts[item.simulated_result] += 1; });
    var released = accessioned.filter(function (item) { return item.released; });
    var holdCodes = holds.map(function (item) { return item.code; }).sort();
    return {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      buyer: BUYER,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      worklist: accessioned.length,
      hold: holds.length,
      hold_codes: holdCodes,
      negative: resultCounts.NEGATIVE,
      positive: resultCounts.POSITIVE,
      invalid: resultCounts.INVALID,
      human_releasable: resultCounts.NEGATIVE + resultCounts.POSITIVE,
      human_released: released.length,
      invalid_hold: accessioned.filter(function (item) { return item.simulated_result === "INVALID" && !item.released; }).length,
      autonomous_released: 0,
      accessions: accessioned,
      holds: holds,
      interface_live: false,
      interfaces: "SIMULATED",
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
  }

  function passContract(result) {
    var failures = [];
    Object.keys(GOLDEN_COUNTS).forEach(function (key) {
      if (result[key] !== GOLDEN_COUNTS[key]) failures.push(key + "!=" + GOLDEN_COUNTS[key] + " actual=" + result[key]);
    });
    if (JSON.stringify(result.hold_codes) !== JSON.stringify(["HOLD_DUPLICATE_TUBE_ID", "HOLD_UNSIGNED_FORM"])) {
      failures.push("hold_codes");
    }
    if (result.interface_live !== false) failures.push("interface_live");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    BUYER: BUYER,
    GOLDEN_COUNTS: GOLDEN_COUNTS,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
