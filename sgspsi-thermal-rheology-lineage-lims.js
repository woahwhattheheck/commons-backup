(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SgsPsiThermalRheologyLineage = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "sgspsi-high-throughput-thermal-rheology-lineage-lims-01";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var DSC_METHODS = ["ASTM-D3418", "ISO-11357-2"];
  var HR_METHODS = ["ASTM-D4440", "ISO-6721-10"];
  var MISMATCH_PAIRS = [
    ["DSC-250", "ASTM-D4440"],
    ["DSC-250", "ISO-6721-10"],
    ["DSC-250", "ASTM-D4440"],
    ["HR-20", "ASTM-D3418"],
    ["HR-20", "ISO-11357-2"],
    ["HR-20", "ASTM-D3418"]
  ];
  var GOLDEN_COUNTS = {
    input_rows: 120,
    ready: 90,
    held: 30,
    reserved_slots_occupied: 90,
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
  function instrumentFor(index) { return index % 2 === 1 ? "DSC-250" : "HR-20"; }
  function methodFor(instrument, index) {
    var names = instrument === "DSC-250" ? DSC_METHODS : HR_METHODS;
    return names[(index - 1) % names.length];
  }
  function reservedSlot(index) {
    var prefix = instrumentFor(index) === "DSC-250" ? "DSC" : "HR";
    return prefix + "-" + pad(Math.floor((index + 1) / 2), 2);
  }
  function methodOk(instrument, method) {
    if (instrument === "DSC-250") return DSC_METHODS.indexOf(method) !== -1;
    if (instrument === "HR-20") return HR_METHODS.indexOf(method) !== -1;
    return false;
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 90; i += 1) {
      var instrument = instrumentFor(i);
      rows.push({
        row_id: "R" + pad(i, 3),
        request_id: "SGS-V" + pad(i, 3),
        container_id: "CTR-V" + pad(i, 3),
        requirement_id: "REQ-SGS-V" + pad(i, 3),
        form_id: "FORM-SGS-V" + pad(i, 3),
        payment_id: "PAY-SGS-V" + pad(i, 3),
        instrument: instrument,
        method: methodFor(instrument, i),
        slot: reservedSlot(i),
        qc_ok: true,
        expected_hold: null
      });
    }
    var missing = ["requirement_id", "form_id", "payment_id", "requirement_id", "form_id", "payment_id", "requirement_id", "form_id"];
    for (i = 0; i < 8; i += 1) {
      var row = {
        row_id: "R" + pad(91 + i, 3),
        request_id: "SGS-HLINK" + pad(i + 1, 2),
        container_id: "CTR-HLINK" + pad(i + 1, 2),
        requirement_id: "REQ-HLINK" + pad(i + 1, 2),
        form_id: "FORM-HLINK" + pad(i + 1, 2),
        payment_id: "PAY-HLINK" + pad(i + 1, 2),
        instrument: "DSC-250",
        method: "ASTM-D3418",
        slot: "DSC-" + pad(51 + i, 2),
        qc_ok: true,
        expected_hold: "MISSING_LINKAGE"
      };
      row[missing[i]] = "";
      rows.push(row);
    }
    for (i = 0; i < 6; i += 1) {
      rows.push({
        row_id: "R" + pad(99 + i, 3),
        request_id: "SGS-HDUP" + pad(i + 1, 2),
        container_id: "CTR-V" + pad(i + 1, 3),
        requirement_id: "REQ-HDUP",
        form_id: "FORM-HDUP",
        payment_id: "PAY-HDUP",
        instrument: instrumentFor(i + 1),
        method: methodFor(instrumentFor(i + 1), i + 1),
        slot: "DSC-" + pad(60 + i, 2),
        qc_ok: true,
        expected_hold: "DUPLICATE_CONTAINER"
      });
    }
    for (i = 0; i < 6; i += 1) {
      rows.push({
        row_id: "R" + pad(105 + i, 3),
        request_id: "SGS-HMIS" + pad(i + 1, 2),
        container_id: "CTR-HMIS" + pad(i + 1, 2),
        requirement_id: "REQ-HMIS",
        form_id: "FORM-HMIS",
        payment_id: "PAY-HMIS",
        instrument: MISMATCH_PAIRS[i][0],
        method: MISMATCH_PAIRS[i][1],
        slot: (MISMATCH_PAIRS[i][0] === "HR-20" ? "HR" : "DSC") + "-" + pad(70 + i, 2),
        qc_ok: true,
        expected_hold: "METHOD_INSTRUMENT_MISMATCH"
      });
    }
    for (i = 0; i < 5; i += 1) {
      rows.push({
        row_id: "R" + pad(111 + i, 3),
        request_id: "SGS-HSLOT" + pad(i + 1, 2),
        container_id: "CTR-HSLOT" + pad(i + 1, 2),
        requirement_id: "REQ-HSLOT",
        form_id: "FORM-HSLOT",
        payment_id: "PAY-HSLOT",
        instrument: instrumentFor(i + 1),
        method: methodFor(instrumentFor(i + 1), i + 1),
        slot: reservedSlot(i + 1),
        qc_ok: true,
        expected_hold: "SLOT_COLLISION"
      });
    }
    for (i = 0; i < 5; i += 1) {
      var qcInstrument = instrumentFor(91 + i);
      rows.push({
        row_id: "R" + pad(116 + i, 3),
        request_id: "SGS-HQC" + pad(i + 1, 2),
        container_id: "CTR-HQC" + pad(i + 1, 2),
        requirement_id: "REQ-HQC",
        form_id: "FORM-HQC",
        payment_id: "PAY-HQC",
        instrument: qcInstrument,
        method: methodFor(qcInstrument, 91 + i),
        slot: (qcInstrument === "DSC-250" ? "DSC" : "HR") + "-" + pad(46 + i, 2),
        qc_ok: false,
        expected_hold: "QC_FAILURE"
      });
    }
    return rows;
  }

  function classify(row, seenContainers, seenSlots) {
    var requestId = text(row.request_id);
    var containerId = text(row.container_id);
    var requirementId = text(row.requirement_id);
    var formId = text(row.form_id);
    var paymentId = text(row.payment_id);
    var instrument = text(row.instrument);
    var method = text(row.method);
    var slot = text(row.slot);
    if (!requestId || !containerId || !requirementId || !formId || !paymentId) {
      return { ok: false, code: "MISSING_LINKAGE", request_id: requestId || null };
    }
    if (seenContainers[containerId]) return { ok: false, code: "DUPLICATE_CONTAINER", request_id: requestId };
    if (!methodOk(instrument, method)) return { ok: false, code: "METHOD_INSTRUMENT_MISMATCH", request_id: requestId };
    if (seenSlots[slot]) return { ok: false, code: "SLOT_COLLISION", request_id: requestId };
    if (row.qc_ok === false) return { ok: false, code: "QC_FAILURE", request_id: requestId };
    return { ok: true, request_id: requestId, container_id: containerId, slot: slot };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var holds = [];
    var slots = {};
    inbound.forEach(function (row) {
      var seenContainers = {};
      Object.keys(accessions).forEach(function (key) { seenContainers[accessions[key].container_id] = true; });
      var verdict = classify(row, seenContainers, slots);
      if (!verdict.ok) {
        holds.push({ request_id: verdict.request_id, code: verdict.code, state: "HOLD" });
        return;
      }
      accessions[verdict.request_id] = {
        request_id: verdict.request_id,
        container_id: verdict.container_id,
        slot: verdict.slot,
        state: "READY",
        released: false
      };
      slots[verdict.slot] = verdict.request_id;
    });
    var ready = Object.keys(accessions).sort().map(function (key) { return accessions[key]; });
    return {
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      ready: ready.length,
      held: holds.length,
      hold_codes: holds.map(function (item) { return item.code; }),
      reserved_slots_occupied: Object.keys(slots).length,
      released_reports: 0,
      staged_reports: ready.length,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      production_writes: 0,
      pre_sale_transport: "NONE",
      official_binary: "python3 test_sgspsi_thermal_rheology_lineage.py"
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
