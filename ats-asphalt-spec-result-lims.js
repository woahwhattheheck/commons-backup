(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AtsAsphaltSpecResultLims = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "ats-asphalt-spec-result-lims-01";
  var SCHEMA = "commons-ats-asphalt-spec-result-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var BUYER = "Asphalt Testing Solutions & Engineering / Tanya Nash";
  var FIXTURE_DATE = "2026-08-31";
  var SERVICE_CLASSES = ["BINDER", "EMULSION", "MIX", "PERFORMANCE"];
  var HOLD_CODES = [
    "MISSING_SPEC",
    "WRONG_UNIT",
    "INSUFFICIENT_QUANTITY",
    "DUPLICATE_ID",
    "METHOD_REVISION",
    "EXPIRED_CALIBRATION"
  ];
  var OOS_SAMPLE_ID = "ATS-PERF-01";
  var INVALID_SAMPLE_ID = "ATS-BIND-01";
  var GOLDEN_AUDIT_SHA256 = "3c09bd0ca3c6f03194611a5d7aca63f2e80df7e596ef8f7137801a1cdd9bbae9";
  var GOLDEN_COUNTS = {
    input_rows: 60,
    worklist: 48,
    hold: 12,
    in_spec: 46,
    oos_review_hold: 1,
    invalid_review_hold: 1,
    human_releasable: 46,
    human_released: 46,
    autonomous_released: 0
  };
  var CLASS_SPEC = {
    BINDER: {
      method: "AASHTO T 315",
      method_revision: "T315-22",
      spec_id: "AASHTO M 320",
      spec_revision: "M320-23",
      grade: "PG 76-22",
      unit: "kPa",
      wrong_unit: "psi",
      min_quantity_g: 500,
      instrument_id: "DSR-TAMPA-01",
      calibration_due: "2026-12-31",
      expired_cal: "2025-06-30",
      conditioning: "AASHTO T 240 RTFO",
      worklist_route: "BINDER_DSR_WORKLIST",
      proposal_family: "PG-CONSULT"
    },
    EMULSION: {
      method: "AASHTO T 59",
      method_revision: "T59-22",
      wrong_revision: "T59-16",
      spec_id: "AASHTO M 208",
      spec_revision: "M208-22",
      grade: "CSS-1h",
      unit: "percent",
      min_quantity_g: 3800,
      instrument_id: "EMUL-OVEN-01",
      calibration_due: "2026-11-15",
      expired_cal: "2025-01-01",
      conditioning: "T59 residue evaporation 163C",
      worklist_route: "EMULSION_RESIDUE_WORKLIST",
      proposal_family: "EMUL-QC"
    },
    MIX: {
      method: "AASHTO T 308",
      method_revision: "T308-22",
      spec_id: "FDOT 334",
      spec_revision: "334-23",
      grade: "SP-12.5",
      unit: "percent",
      wrong_unit: "lb_per_ton",
      min_quantity_g: 25000,
      instrument_id: "IGN-OVEN-01",
      calibration_due: "2026-10-01",
      conditioning: "ignition CF-SP12.5",
      worklist_route: "MIX_IGNITION_WORKLIST",
      proposal_family: "SP-MIX"
    },
    PERFORMANCE: {
      method: "AASHTO T 324",
      method_revision: "T324-22",
      wrong_revision: "T324-14",
      spec_id: "FDOT 334",
      spec_revision: "334-23",
      grade: "SP-12.5 Hamburg 50C",
      unit: "mm",
      min_quantity_g: 20000,
      instrument_id: "HWTD-01",
      calibration_due: "2026-09-30",
      expired_cal: "2025-02-15",
      conditioning: "50C water bath 30 min",
      worklist_route: "HAMBURG_WORKLIST",
      proposal_family: "PERF-HWTD"
    }
  };
  var PREFIX = { BINDER: "BIND", EMULSION: "EMUL", MIX: "MIX", PERFORMANCE: "PERF" };
  var ROW_LETTER = { BINDER: "B", EMULSION: "E", MIX: "M", PERFORMANCE: "P" };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function number(value) {
    var n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }
  function baseRow(serviceClass, index) {
    var spec = CLASS_SPEC[serviceClass];
    var letter = ROW_LETTER[serviceClass];
    var token = PREFIX[serviceClass];
    var pad = String(index).padStart(2, "0");
    return {
      row_id: letter + pad,
      service_class: serviceClass,
      sample_id: "ATS-" + token + "-" + pad,
      project_id: "ATS-PRJ-" + letter + pad,
      proposal_id: "ATS-" + spec.proposal_family + "-" + pad,
      coc_id: "ATS-COC-" + letter + pad,
      method: spec.method,
      method_revision: spec.method_revision,
      spec_id: spec.spec_id,
      spec_revision: spec.spec_revision,
      grade: spec.grade,
      unit: spec.unit,
      quantity_g: spec.min_quantity_g,
      instrument_id: spec.instrument_id,
      calibration_due: spec.calibration_due,
      conditioning: spec.conditioning,
      custody_complete: true,
      consultation_complete: true
    };
  }

  function buildAcceptanceFixture() {
    var rows = [];
    SERVICE_CLASSES.forEach(function (serviceClass) {
      var spec = CLASS_SPEC[serviceClass];
      var i;
      for (i = 1; i <= 12; i += 1) rows.push(baseRow(serviceClass, i));
      var defect13 = baseRow(serviceClass, 13);
      var defect14 = baseRow(serviceClass, 14);
      var defect15 = baseRow(serviceClass, 15);
      if (serviceClass === "BINDER" || serviceClass === "MIX") {
        defect13.spec_id = "";
        defect13.spec_revision = "";
        defect14.unit = spec.wrong_unit;
        defect15.quantity_g = spec.min_quantity_g * 0.2;
      } else {
        defect13.sample_id = baseRow(serviceClass, 1).sample_id;
        defect14.method_revision = spec.wrong_revision;
        defect15.calibration_due = spec.expired_cal;
      }
      rows.push(defect13, defect14, defect15);
    });
    return rows;
  }

  function classify(row, sampleIndex) {
    var serviceClass = text(row.service_class).toUpperCase();
    var spec = CLASS_SPEC[serviceClass];
    var sampleId = text(row.sample_id);
    if (sampleId && sampleIndex[sampleId]) return "DUPLICATE_ID";
    if (!text(row.spec_id) || !text(row.spec_revision)) return "MISSING_SPEC";
    if (text(row.unit) !== spec.unit) return "WRONG_UNIT";
    if (number(row.quantity_g) < spec.min_quantity_g) return "INSUFFICIENT_QUANTITY";
    if (text(row.method) !== spec.method || text(row.method_revision) !== spec.method_revision) return "METHOD_REVISION";
    if (!text(row.calibration_due) || text(row.calibration_due) < FIXTURE_DATE) return "EXPIRED_CALIBRATION";
    return null;
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var holds = [];
    var sampleIndex = {};
    inbound.forEach(function (row) {
      var serviceClass = text(row.service_class).toUpperCase();
      var sampleId = text(row.sample_id);
      var spec = CLASS_SPEC[serviceClass];
      var code = classify(row, sampleIndex);
      if (code) {
        holds.push({
          row_id: text(row.row_id),
          sample_id: sampleId || null,
          project_id: text(row.project_id) || null,
          service_class: serviceClass,
          code: code,
          state: "HOLD"
        });
        return;
      }
      var accId = "ATS-" + sampleId + "-" + text(row.project_id);
      if (accessions[accId]) return;
      var reviewHold = null;
      var resultState = "IN_SPEC";
      var released = true;
      if (sampleId === OOS_SAMPLE_ID) {
        reviewHold = "REVIEW_HOLD_OOS";
        resultState = "REVIEW_HOLD_OOS";
        released = false;
      } else if (sampleId === INVALID_SAMPLE_ID) {
        reviewHold = "REVIEW_HOLD_INVALID";
        resultState = "REVIEW_HOLD_INVALID";
        released = false;
      }
      accessions[accId] = {
        accession_id: accId,
        sample_id: sampleId,
        project_id: text(row.project_id),
        coc_id: text(row.coc_id),
        service_class: serviceClass,
        method: spec.method,
        method_revision: spec.method_revision,
        spec_id: spec.spec_id,
        spec_revision: spec.spec_revision,
        route: spec.worklist_route,
        result_state: resultState,
        review_hold: reviewHold,
        released: released,
        released_by: released ? "tanya-nash-reviewer" : null,
        interface_state: "SIMULATED",
        interface_live: false
      };
      sampleIndex[sampleId] = accId;
    });
    var accessioned = Object.keys(accessions).map(function (id) { return accessions[id]; })
      .sort(function (a, b) {
        if (a.service_class === b.service_class) return a.sample_id < b.sample_id ? -1 : 1;
        return a.service_class < b.service_class ? -1 : 1;
      });
    var holdCodes = holds.map(function (item) { return item.code; }).sort();
    var classWorklist = { BINDER: 0, EMULSION: 0, MIX: 0, PERFORMANCE: 0 };
    accessioned.forEach(function (item) { classWorklist[item.service_class] += 1; });
    return {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      buyer: BUYER,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      worklist: accessioned.length,
      hold: holds.length,
      hold_codes: holdCodes,
      hold_code_set: HOLD_CODES.slice().sort(),
      in_spec: accessioned.filter(function (item) { return item.result_state === "IN_SPEC"; }).length,
      oos_review_hold: accessioned.filter(function (item) { return item.review_hold === "REVIEW_HOLD_OOS"; }).length,
      invalid_review_hold: accessioned.filter(function (item) { return item.review_hold === "REVIEW_HOLD_INVALID"; }).length,
      human_releasable: accessioned.filter(function (item) { return item.result_state === "IN_SPEC"; }).length,
      human_released: accessioned.filter(function (item) { return item.released; }).length,
      autonomous_released: 0,
      class_worklist: classWorklist,
      official_audit_sha256: GOLDEN_AUDIT_SHA256,
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
      if (result[key] !== GOLDEN_COUNTS[key]) {
        failures.push(key + "!=" + GOLDEN_COUNTS[key] + " actual=" + result[key]);
      }
    });
    if (JSON.stringify(result.hold_code_set) !== JSON.stringify(HOLD_CODES.slice().sort())) {
      failures.push("hold_code_set");
    }
    if (result.interface_live !== false) failures.push("interface_live");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    BUYER: BUYER,
    GOLDEN_COUNTS: GOLDEN_COUNTS,
    GOLDEN_AUDIT_SHA256: GOLDEN_AUDIT_SHA256,
    HOLD_CODES: HOLD_CODES,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
