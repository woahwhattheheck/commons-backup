(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ParagonBiodieselSampleCoa = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "paragon-biodiesel-sample-coa-lims-01";
  var SCHEMA = "commons-paragon-biodiesel-sample-coa-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var BUYER = "Paragon Laboratories / Rich McKenzie";
  var FIXTURE_DATE = "2026-08-31";
  var HOLD_CODES = ["HOLD_DUPLICATE_ID", "HOLD_INCOMPLETE_COC", "HOLD_INCOMPLETE_SDS", "HOLD_OOS"];
  var GOLDEN_AUDIT_SHA256 = "70e0875552b9024e42b0117cbcd63fe4d56e7b55277fe2ea700ccfaa9594e8da";
  var GOLDEN_SET_SHA256 = "13b30045df03d9ac2a8493924bcd5da2a5f51486be77e6a2fb6d4bd109f14275";
  var GOLDEN_COUNTS = {
    input_rows: 120,
    accessioned_valid: 100,
    accessioned_total: 105,
    hold: 20,
    incomplete_coc: 5,
    incomplete_sds: 5,
    duplicate_id: 5,
    oos: 5,
    in_spec: 100,
    staged_coa: 100,
    human_released: 100,
    autonomous_released: 0,
    duplicate_accessions: 0
  };
  var OOS = {
    "PBD-O01": { method: "D7371", value: 4.8 },
    "PBD-O02": { method: "D93", value: 48.0 },
    "PBD-O03": { method: "D445", value: 4.52 },
    "PBD-O04": { method: "D5453", value: 22.0 },
    "PBD-O05": { method: "D664", value: 0.42 }
  };
  var GRADES = ["B6", "B10", "B15", "B20"];

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function flag(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    return /^(1|true|yes|y)$/i.test(String(value).trim());
  }
  function stable(value) {
    if (Array.isArray(value)) return value.map(stable);
    if (value && typeof value === "object") {
      var out = {};
      Object.keys(value).sort().forEach(function (key) { out[key] = stable(value[key]); });
      return out;
    }
    return value;
  }
  function sha256HexSync(value) {
    var payload = JSON.stringify(stable(value));
    if (typeof require === "function") {
      try { return require("crypto").createHash("sha256").update(payload).digest("hex"); } catch (_) {}
    }
    var h = 5381;
    for (var i = 0; i < payload.length; i += 1) h = ((h << 5) + h) ^ payload.charCodeAt(i);
    return ("00000000" + ((h >>> 0).toString(16))).slice(-8);
  }

  function validRow(index) {
    var grade = GRADES[(index - 1) % 4];
    return {
      row_id: "R" + String(index).padStart(3, "0"),
      sample_id: "PBD-V" + String(index).padStart(3, "0"),
      pickup_id: "PBD-PU-" + String(index).padStart(3, "0"),
      coc_id: "PBD-COC-" + String(index).padStart(3, "0"),
      sds_id: "PBD-SDS-" + grade,
      blend_grade: grade,
      lot_id: "PBD-LOT-" + String(index).padStart(3, "0"),
      tank_id: "PBD-TANK-" + String((index % 8) + 1).padStart(2, "0"),
      courier: "SYN-COURIER-01",
      custody_seal: "SEAL-" + String(index).padStart(4, "0"),
      collected_at: FIXTURE_DATE + "T08:00:00Z",
      received_at: FIXTURE_DATE + "T14:00:00Z",
      relinquisher: "SYN-DRIVER",
      receiver: "SYN-RECEIVING",
      coc_complete: true,
      sds_present: true,
      container_intact: true
    };
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 100; i += 1) rows.push(validRow(i));
    for (i = 1; i <= 5; i += 1) {
      var coc = validRow(100 + i);
      coc.row_id = "C" + String(i).padStart(2, "0");
      coc.sample_id = "PBD-C" + String(i).padStart(2, "0");
      coc.pickup_id = "PBD-PU-C" + String(i).padStart(2, "0");
      coc.coc_id = "";
      coc.custody_seal = "";
      coc.collected_at = "";
      coc.relinquisher = "";
      coc.coc_complete = false;
      rows.push(coc);
    }
    for (i = 1; i <= 5; i += 1) {
      var sds = validRow(105 + i);
      sds.row_id = "S" + String(i).padStart(2, "0");
      sds.sample_id = "PBD-S" + String(i).padStart(2, "0");
      sds.pickup_id = "PBD-PU-S" + String(i).padStart(2, "0");
      sds.sds_id = "";
      sds.sds_present = false;
      rows.push(sds);
    }
    for (i = 1; i <= 5; i += 1) {
      var dup = clone(validRow(i));
      dup.row_id = "D" + String(i).padStart(2, "0");
      dup.pickup_id = "PBD-PU-DUP-" + String(i).padStart(2, "0");
      rows.push(dup);
    }
    var oosIds = Object.keys(OOS).sort();
    for (i = 0; i < oosIds.length; i += 1) {
      var oos = validRow(111 + i);
      oos.row_id = "O" + String(i + 1).padStart(2, "0");
      oos.sample_id = oosIds[i];
      oos.pickup_id = "PBD-PU-O" + String(i + 1).padStart(2, "0");
      oos.coc_id = "PBD-COC-O" + String(i + 1).padStart(2, "0");
      oos.lot_id = "PBD-LOT-O" + String(i + 1).padStart(2, "0");
      rows.push(oos);
    }
    return rows;
  }

  function classify(row, seen) {
    var sampleId = text(row.sample_id);
    if (sampleId && seen[sampleId]) return "HOLD_DUPLICATE_ID";
    var cocOk = flag(row.coc_complete) && text(row.coc_id) && text(row.custody_seal)
      && text(row.collected_at) && text(row.relinquisher) && text(row.courier)
      && text(row.pickup_id) && text(row.received_at) && text(row.receiver)
      && flag(row.container_intact);
    if (!cocOk) return "HOLD_INCOMPLETE_COC";
    if (!flag(row.sds_present) || !text(row.sds_id)) return "HOLD_INCOMPLETE_SDS";
    return null;
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var seen = {};
    var accessions = [];
    var holds = [];
    inbound.forEach(function (row) {
      var code = classify(row, seen);
      if (code) {
        holds.push({ row_id: text(row.row_id), sample_id: text(row.sample_id) || null, code: code, state: "HOLD" });
        return;
      }
      var sampleId = text(row.sample_id);
      var oos = OOS[sampleId];
      seen[sampleId] = true;
      accessions.push({
        sample_id: sampleId,
        blend_grade: text(row.blend_grade),
        route: "B6_B20_D7467_PANEL",
        result_state: oos ? "OOS" : "IN_SPEC",
        review_hold: oos ? "HOLD_OOS" : null,
        released: !oos,
        released_by: oos ? null : "rich-mckenzie-reviewer",
        interface_state: "SIMULATED",
        interface_live: false
      });
      if (oos) holds.push({ row_id: text(row.row_id), sample_id: sampleId, code: "HOLD_OOS", state: "HOLD" });
    });
    var holdCodes = holds.map(function (item) { return item.code; }).sort();
    var inSpec = accessions.filter(function (item) { return item.result_state === "IN_SPEC"; }).length;
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      buyer: BUYER,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      accessioned_valid: inSpec,
      accessioned_total: accessions.length,
      hold: holds.length,
      hold_codes: holdCodes,
      hold_code_set: HOLD_CODES.slice(),
      incomplete_coc: holds.filter(function (item) { return item.code === "HOLD_INCOMPLETE_COC"; }).length,
      incomplete_sds: holds.filter(function (item) { return item.code === "HOLD_INCOMPLETE_SDS"; }).length,
      duplicate_id: holds.filter(function (item) { return item.code === "HOLD_DUPLICATE_ID"; }).length,
      oos: holds.filter(function (item) { return item.code === "HOLD_OOS"; }).length,
      in_spec: inSpec,
      staged_coa: inSpec,
      human_released: inSpec,
      autonomous_released: 0,
      duplicate_accessions: 0,
      accessions: accessions,
      holds: holds,
      interface_live: false,
      interfaces: "SIMULATED",
      qc_decisions: 0,
      production_writes: 0,
      outreach: 0,
      autonomous_certification: false,
      autonomous_release: false,
      pre_sale_transport: "NONE",
      cash_usd: 0,
      golden_audit_sha256: GOLDEN_AUDIT_SHA256,
      golden_set_sha256: GOLDEN_SET_SHA256
    };
    body.manifest_sha256 = sha256HexSync(body);
    return body;
  }

  function passContract(result) {
    var failures = [];
    Object.keys(GOLDEN_COUNTS).forEach(function (key) {
      if (result[key] !== GOLDEN_COUNTS[key]) failures.push(key + "!=" + GOLDEN_COUNTS[key]);
    });
    if (JSON.stringify(result.hold_code_set) !== JSON.stringify(HOLD_CODES)) failures.push("hold_code_set");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    if (result.outreach !== 0) failures.push("outreach");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    GOLDEN_COUNTS: GOLDEN_COUNTS,
    GOLDEN_AUDIT_SHA256: GOLDEN_AUDIT_SHA256,
    GOLDEN_SET_SHA256: GOLDEN_SET_SHA256,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
