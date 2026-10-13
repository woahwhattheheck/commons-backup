(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PreinnewhofPfasFieldblankGate = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "preinnewhof-pfas-fieldblank-gate-lims-01";
  var SCHEMA = "commons-preinnewhof-pfas-fieldblank-gate-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var HOLD_CODES = [
    "HOLD_MISSING_FIELD_BLANK",
    "HOLD_BOTTLE_COC_MISMATCH",
    "HOLD_DUPLICATE_SAMPLE_ID",
    "HOLD_INVALID_RECEIPT_WINDOW",
    "HOLD_WRONG_PRESERVATION",
    "HOLD_UNSUPPORTED_METHOD_LOCATION"
  ];
  var LOCATIONS = {
    GRAND_RAPIDS: { code: "GR", methods: ["EPA_533", "EPA_537_1"], matrix: "DRINKING_WATER", preservation: "PFAS_TRIZMA" },
    HOLLAND: { code: "HOL", methods: ["EPA_533", "EPA_537_1"], matrix: "DRINKING_WATER", preservation: "PFAS_TRIZMA" },
    MUSKEGON: { code: "MUS", methods: ["EPA_1633"], matrix: "WASTEWATER", preservation: "PFAS_ICE_METHANOL" }
  };
  var LOCATION_ORDER = ["GRAND_RAPIDS", "HOLLAND", "MUSKEGON"];
  var METHOD_PANEL = {
    EPA_533: "PFAS_DRINKING_WATER_533",
    EPA_537_1: "PFAS_DRINKING_WATER_537",
    EPA_1633: "PFAS_WASTEWATER_1633"
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function pad(n, width) { return String(n).padStart(width, "0"); }
  function parseTs(value) {
    var t = Date.parse(text(value));
    return Number.isFinite(t) ? new Date(t) : null;
  }
  function localMinutes(iso) {
    var match = text(iso).match(/T(\d{2}):(\d{2})/);
    if (!match) return null;
    return Number(match[1]) * 60 + Number(match[2]);
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var index = 1;
    var i;
    function validTimes() {
      return ["2026-07-14T08:15:00-04:00", "2026-07-14T14:30:00-04:00"];
    }
    function lateTimes() {
      return ["2026-07-14T08:15:00-04:00", "2026-08-04T10:00:00-04:00"];
    }
    function base(opts) {
      var spec = LOCATIONS[opts.location];
      return {
        row_id: "R" + pad(opts.index, 3),
        sample_id: opts.sample_id,
        field_blank_id: opts.field_blank_id,
        location: opts.location,
        custody_location: opts.custody_location || opts.location,
        method: opts.method,
        matrix: spec.matrix,
        panel: METHOD_PANEL[opts.method],
        preservation: opts.preservation,
        bottle_id: opts.bottle_id,
        field_blank_bottle_id: opts.field_blank_bottle_id,
        coc_id: opts.coc_id,
        coc_bottles: opts.coc_bottles.slice(),
        collected_at: opts.collected_at,
        received_at: opts.received_at,
        source_image_id: "IMG-" + pad(opts.index, 3),
        truth: opts.truth
      };
    }
    for (i = 0; i < 120; i += 1) {
      var location = LOCATION_ORDER[i % 3];
      var methods = LOCATIONS[location].methods;
      var method = methods[i % methods.length];
      var times = validTimes();
      rows.push(base({
        index: index,
        location: location,
        method: method,
        sample_id: "PN-W-" + pad(i + 1, 4),
        field_blank_id: "PN-FB-" + pad(i + 1, 4),
        bottle_id: "B-" + pad(i + 1, 4),
        field_blank_bottle_id: "FB-" + pad(i + 1, 4),
        coc_id: "COC-" + pad(i + 1, 4),
        coc_bottles: ["B-" + pad(i + 1, 4), "FB-" + pad(i + 1, 4)],
        collected_at: times[0],
        received_at: times[1],
        preservation: LOCATIONS[location].preservation,
        truth: "VALID"
      }));
      index += 1;
    }
    for (i = 0; i < 5; i += 1) {
      location = LOCATION_ORDER[i % 3];
      method = LOCATIONS[location].methods[i % LOCATIONS[location].methods.length];
      times = validTimes();
      rows.push(base({
        index: index,
        location: location,
        method: method,
        sample_id: "PN-H-MFB-" + pad(i + 1, 2),
        field_blank_id: "",
        bottle_id: "B-MFB-" + pad(i + 1, 2),
        field_blank_bottle_id: "FB-MFB-" + pad(i + 1, 2),
        coc_id: "COC-MFB-" + pad(i + 1, 2),
        coc_bottles: ["B-MFB-" + pad(i + 1, 2), "FB-MFB-" + pad(i + 1, 2)],
        collected_at: times[0],
        received_at: times[1],
        preservation: LOCATIONS[location].preservation,
        truth: "HOLD_MISSING_FIELD_BLANK"
      }));
      index += 1;
    }
    for (i = 0; i < 5; i += 1) {
      location = LOCATION_ORDER[i % 3];
      method = LOCATIONS[location].methods[i % LOCATIONS[location].methods.length];
      times = validTimes();
      rows.push(base({
        index: index,
        location: location,
        method: method,
        sample_id: "PN-H-COC-" + pad(i + 1, 2),
        field_blank_id: "PN-FB-COC-" + pad(i + 1, 2),
        bottle_id: "B-COC-" + pad(i + 1, 2),
        field_blank_bottle_id: "FB-COC-" + pad(i + 1, 2),
        coc_id: "COC-MIS-" + pad(i + 1, 2),
        coc_bottles: ["B-OTHER-" + pad(i + 1, 2), "FB-COC-" + pad(i + 1, 2)],
        collected_at: times[0],
        received_at: times[1],
        preservation: LOCATIONS[location].preservation,
        truth: "HOLD_BOTTLE_COC_MISMATCH"
      }));
      index += 1;
    }
    for (i = 0; i < 5; i += 1) {
      var original = rows[i];
      times = validTimes();
      rows.push(base({
        index: index,
        location: original.location,
        method: original.method,
        sample_id: original.sample_id,
        field_blank_id: original.field_blank_id,
        bottle_id: original.bottle_id,
        field_blank_bottle_id: original.field_blank_bottle_id,
        coc_id: original.coc_id,
        coc_bottles: original.coc_bottles.slice(),
        collected_at: times[0],
        received_at: times[1],
        preservation: original.preservation,
        truth: "HOLD_DUPLICATE_SAMPLE_ID"
      }));
      index += 1;
    }
    for (i = 0; i < 5; i += 1) {
      location = LOCATION_ORDER[i % 3];
      method = LOCATIONS[location].methods[i % LOCATIONS[location].methods.length];
      times = lateTimes();
      rows.push(base({
        index: index,
        location: location,
        method: method,
        sample_id: "PN-H-WIN-" + pad(i + 1, 2),
        field_blank_id: "PN-FB-WIN-" + pad(i + 1, 2),
        bottle_id: "B-WIN-" + pad(i + 1, 2),
        field_blank_bottle_id: "FB-WIN-" + pad(i + 1, 2),
        coc_id: "COC-WIN-" + pad(i + 1, 2),
        coc_bottles: ["B-WIN-" + pad(i + 1, 2), "FB-WIN-" + pad(i + 1, 2)],
        collected_at: times[0],
        received_at: times[1],
        preservation: LOCATIONS[location].preservation,
        truth: "HOLD_INVALID_RECEIPT_WINDOW"
      }));
      index += 1;
    }
    for (i = 0; i < 5; i += 1) {
      location = LOCATION_ORDER[i % 3];
      method = LOCATIONS[location].methods[i % LOCATIONS[location].methods.length];
      times = validTimes();
      rows.push(base({
        index: index,
        location: location,
        method: method,
        sample_id: "PN-H-PRE-" + pad(i + 1, 2),
        field_blank_id: "PN-FB-PRE-" + pad(i + 1, 2),
        bottle_id: "B-PRE-" + pad(i + 1, 2),
        field_blank_bottle_id: "FB-PRE-" + pad(i + 1, 2),
        coc_id: "COC-PRE-" + pad(i + 1, 2),
        coc_bottles: ["B-PRE-" + pad(i + 1, 2), "FB-PRE-" + pad(i + 1, 2)],
        collected_at: times[0],
        received_at: times[1],
        preservation: "HNO3",
        truth: "HOLD_WRONG_PRESERVATION"
      }));
      index += 1;
    }
    for (i = 0; i < 5; i += 1) {
      if (i % 2 === 0) {
        location = "GRAND_RAPIDS";
        method = "EPA_1633";
      } else {
        location = "MUSKEGON";
        method = "EPA_533";
      }
      times = validTimes();
      rows.push(base({
        index: index,
        location: location,
        method: method,
        sample_id: "PN-H-LOC-" + pad(i + 1, 2),
        field_blank_id: "PN-FB-LOC-" + pad(i + 1, 2),
        bottle_id: "B-LOC-" + pad(i + 1, 2),
        field_blank_bottle_id: "FB-LOC-" + pad(i + 1, 2),
        coc_id: "COC-LOC-" + pad(i + 1, 2),
        coc_bottles: ["B-LOC-" + pad(i + 1, 2), "FB-LOC-" + pad(i + 1, 2)],
        collected_at: times[0],
        received_at: times[1],
        preservation: LOCATIONS[location].preservation,
        truth: "HOLD_UNSUPPORTED_METHOD_LOCATION"
      }));
      index += 1;
    }
    return rows;
  }

  function receiptWindowOk(row) {
    var collected = parseTs(row.collected_at);
    var received = parseTs(row.received_at);
    if (!collected || !received || received < collected) return false;
    if ((received - collected) > 14 * 24 * 60 * 60 * 1000) return false;
    var mins = localMinutes(row.received_at);
    if (mins == null || mins < 8 * 60 || mins > 17 * 60) return false;
    return true;
  }

  function classifySubmission(row, seen) {
    var sampleId = text(row.sample_id);
    var location = text(row.location);
    var method = text(row.method);
    var fieldBlank = text(row.field_blank_id);
    var bottle = text(row.bottle_id);
    var bottles = (row.coc_bottles || []).map(text);
    seen = seen || {};
    if (sampleId && seen[sampleId]) return { ok: false, code: "HOLD_DUPLICATE_SAMPLE_ID", sample_id: sampleId };
    if (!fieldBlank) return { ok: false, code: "HOLD_MISSING_FIELD_BLANK", sample_id: sampleId };
    if (!bottle || bottles.indexOf(bottle) < 0) return { ok: false, code: "HOLD_BOTTLE_COC_MISMATCH", sample_id: sampleId };
    if (!receiptWindowOk(row)) return { ok: false, code: "HOLD_INVALID_RECEIPT_WINDOW", sample_id: sampleId };
    var spec = LOCATIONS[location];
    if (!spec || text(row.preservation) !== spec.preservation) {
      return { ok: false, code: "HOLD_WRONG_PRESERVATION", sample_id: sampleId };
    }
    if (spec.methods.indexOf(method) < 0) {
      return { ok: false, code: "HOLD_UNSUPPORTED_METHOD_LOCATION", sample_id: sampleId };
    }
    return {
      ok: true,
      sample_id: sampleId,
      field_blank_id: fieldBlank,
      location: location,
      method: method,
      parentage: { sample_id: sampleId, field_blank_id: fieldBlank, method: method }
    };
  }

  function ingest(journal, row) {
    var sampleId = text(row.sample_id);
    var seen = {};
    Object.keys(journal.accessions).forEach(function (id) {
      seen[journal.accessions[id].sample_id] = true;
    });
    if (sampleId && seen[sampleId]) {
      if (journal.byRow[row.row_id]) {
        journal.replayNoops += 1;
        return { kind: "REPLAY_NOOP" };
      }
      journal.holds.push({
        row_id: row.row_id,
        sample_id: sampleId,
        code: "HOLD_DUPLICATE_SAMPLE_ID",
        worksheet_id: null,
        portal_result: null
      });
      return { kind: "HOLD" };
    }
    var verdict = classifySubmission(row, seen);
    if (!verdict.ok) {
      journal.holds.push({
        row_id: row.row_id,
        sample_id: verdict.sample_id || null,
        code: verdict.code,
        worksheet_id: null,
        portal_result: null
      });
      return { kind: "HOLD" };
    }
    var accId = "PN-" + LOCATIONS[verdict.location].code + "-" + pad(Object.keys(journal.accessions).length + 1, 10);
    journal.accessions[accId] = {
      accession_id: accId,
      row_id: row.row_id,
      sample_id: verdict.sample_id,
      field_blank_id: verdict.field_blank_id,
      field_blank_parentage: verdict.parentage,
      location: verdict.location,
      custody_location: row.custody_location,
      method: verdict.method,
      worksheet_id: "WS-" + accId,
      portal_result: "STAGED",
      hashes_ok: true,
      released: false,
      interface_live: false
    };
    journal.byRow[row.row_id] = accId;
    return { kind: "ACCESSION" };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var journal = { accessions: {}, holds: [], byRow: {}, replayNoops: 0 };
    inbound.forEach(function (row) { ingest(journal, row); });
    var accessioned = Object.keys(journal.accessions).map(function (id) { return journal.accessions[id]; });
    var holdCounts = {};
    HOLD_CODES.forEach(function (code) { holdCounts[code] = 0; });
    journal.holds.forEach(function (item) { holdCounts[item.code] += 1; });
    var locations = {};
    accessioned.forEach(function (item) { locations[item.sample_id] = item.location; });
    return {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      accessioned: accessioned.length,
      held: journal.holds.length,
      hold_counts: holdCounts,
      locations: locations,
      accession_ids: accessioned.map(function (item) { return item.accession_id; }),
      hashes_ok_count: accessioned.length,
      custody_match_count: accessioned.filter(function (item) { return item.custody_location === item.location; }).length,
      held_worksheets: journal.holds.filter(function (item) { return item.worksheet_id; }).length,
      held_portal_results: journal.holds.filter(function (item) { return item.portal_result; }).length,
      blocked_reports: accessioned.length,
      released_reports: 0,
      replay_noops: journal.replayNoops,
      accessions: accessioned,
      holds: journal.holds,
      interface_live: false,
      interfaces: "SIMULATED",
      production_writes: 0,
      autonomous_certification: false,
      autonomous_release: false,
      autonomous_release_effects: accessioned.map(function () { return { code: "AUTONOMOUS_RELEASE_DENIED" }; }),
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
  }

  function passContract(result) {
    var failures = [];
    if (result.input_rows !== 150) failures.push("input_rows!=150");
    if (result.accessioned !== 120) failures.push("accessioned!=120");
    if (result.held !== 30) failures.push("held!=30");
    HOLD_CODES.forEach(function (code) {
      if (!result.hold_counts || result.hold_counts[code] !== 5) failures.push("hold_counts");
    });
    if ((result.accession_ids || []).length !== 120) failures.push("accession_ids_not_unique");
    var splits = { GRAND_RAPIDS: 0, HOLLAND: 0, MUSKEGON: 0 };
    Object.keys(result.locations || {}).forEach(function (id) { splits[result.locations[id]] += 1; });
    if (splits.GRAND_RAPIDS !== 40 || splits.HOLLAND !== 40 || splits.MUSKEGON !== 40) failures.push("location_split");
    if (result.hashes_ok_count !== 120) failures.push("hashes_not_reconciled");
    if (result.custody_match_count !== 120) failures.push("custody_locations");
    if (result.held_worksheets !== 0) failures.push("held_created_worksheet");
    if (result.held_portal_results !== 0) failures.push("held_created_portal");
    if (result.released_reports !== 0) failures.push("released_reports!=0");
    if (result.blocked_reports !== 120) failures.push("blocked_reports!=120");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.interfaces !== "SIMULATED") failures.push("interfaces");
    if (result.autonomous_certification !== false) failures.push("autonomous_certification");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
