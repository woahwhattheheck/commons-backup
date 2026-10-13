(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LuvakSsaLabAnalyticsCutover = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "luvak-ssa-lab-analytics-cutover-lims-01";
  var SCHEMA = "commons-luvak-ssa-lab-analytics-cutover-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var MATERIALS = [
    ["Ti-6Al-4V", "titanium_alloy"],
    ["316L", "stainless"],
    ["Inconel 718", "nickel_superalloy"],
    ["Zr-2.5Nb", "zirconium_alloy"],
    ["17-4PH", "stainless"],
    ["Al 7075", "aluminum_alloy"],
    ["CP-Ti Grade 2", "titanium"],
    ["Haynes 282", "nickel_superalloy"]
  ];
  var METHODS = {
    INTERSTITIAL_GAS: { revision: "IGA-2026.1", analytes: ["oxygen", "nitrogen", "hydrogen"], family: "interstitial_gas" },
    CARBON_SULFUR: { revision: "CS-2026.1", analytes: ["carbon", "sulfur"], family: "carbon_sulfur" },
    METALS: { revision: "MET-2026.1", analytes: ["iron", "nickel", "chromium", "molybdenum"], family: "metals" },
    WET_CHEMISTRY: { revision: "WC-2026.1", analytes: ["acid_soluble"], family: "wet_chemistry" }
  };
  var METHOD_NAMES = ["INTERSTITIAL_GAS", "CARBON_SULFUR", "METALS", "WET_CHEMISTRY"];
  var HOLD_CODES = [
    "MISSING_ACCEPTED_QUOTE",
    "DUPLICATE_SAMPLE_ID",
    "FORM_PACKAGE_MISMATCH",
    "METHOD_REVISION_MISMATCH"
  ];

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function flag(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    return /^(1|true|yes|y|accepted)$/i.test(String(value).trim());
  }
  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
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
  function methodName(index) { return METHOD_NAMES[(index - 1) % METHOD_NAMES.length]; }
  function material(index) { return MATERIALS[(index - 1) % MATERIALS.length]; }

  function validRow(index) {
    var method = methodName(index);
    var spec = METHODS[method];
    var mat = material(index);
    var sampleId = "LVK-" + pad(index, 4);
    var row = {
      row_id: "R" + pad(index, 3),
      sample_id: sampleId,
      quote_id: "Q-" + pad(index, 4),
      quote_accepted: true,
      form_id: "F-" + pad(index, 4),
      package_id: "P-" + pad(index, 4),
      form_sample_id: sampleId,
      package_sample_id: sampleId,
      material: mat[0],
      material_family: mat[1],
      method: method,
      quote_method_revision: spec.revision,
      form_method_revision: spec.revision,
      mass_g: 4.0,
      cutover_lane: index % 2 === 0 ? "SSA_LAB_ANALYTICS" : "LUVAK_LEGACY",
      coc: null
    };
    if (index % 3 === 0) row.coc = { coc_id: "COC-" + pad(index, 4), sample_id: sampleId };
    return row;
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 80; i += 1) rows.push(validRow(i));
    for (i = 81; i <= 88; i += 1) {
      var missing = validRow(i);
      missing.quote_id = "";
      missing.quote_accepted = false;
      rows.push(missing);
    }
    for (i = 89; i <= 92; i += 1) {
      var dup = validRow(i - 88);
      dup.row_id = "R" + pad(i, 3);
      dup.quote_id = "Q-" + pad(i, 4);
      dup.form_id = "F-" + pad(i, 4);
      dup.package_id = "P-" + pad(i, 4);
      rows.push(dup);
    }
    for (i = 93; i <= 96; i += 1) {
      var mismatch = validRow(i);
      mismatch.package_sample_id = mismatch.sample_id + "-PKG";
      rows.push(mismatch);
    }
    for (i = 97; i <= 100; i += 1) {
      var revision = validRow(i);
      revision.form_method_revision = "IGA-2025.9";
      rows.push(revision);
    }
    return rows;
  }

  function classifyShipment(row, seen) {
    var sampleId = text(row.sample_id);
    var quoteId = text(row.quote_id);
    var accepted = flag(row.quote_accepted);
    var formSample = text(row.form_sample_id) || sampleId;
    var packageSample = text(row.package_sample_id) || sampleId;
    var quoteRev = text(row.quote_method_revision);
    var formRev = text(row.form_method_revision);
    var method = text(row.method);
    if (!quoteId || !accepted) {
      return { ok: false, code: "MISSING_ACCEPTED_QUOTE", sample_id: sampleId || null, row_id: text(row.row_id) };
    }
    if (sampleId && seen[sampleId]) {
      return { ok: false, code: "DUPLICATE_SAMPLE_ID", sample_id: sampleId, row_id: text(row.row_id) };
    }
    if (formSample !== packageSample) {
      return { ok: false, code: "FORM_PACKAGE_MISMATCH", sample_id: sampleId || null, row_id: text(row.row_id) };
    }
    if (!quoteRev || !formRev || quoteRev !== formRev) {
      return { ok: false, code: "METHOD_REVISION_MISMATCH", sample_id: sampleId || null, row_id: text(row.row_id) };
    }
    if (!sampleId || !METHODS[method]) {
      return { ok: false, code: "MISSING_ACCEPTED_QUOTE", sample_id: sampleId || null, row_id: text(row.row_id) };
    }
    return { ok: true, sample_id: sampleId, method: method, row_id: text(row.row_id), cutover_lane: text(row.cutover_lane) || "LUVAK_LEGACY", coc: row.coc || null };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var ready = {};
    var holds = [];
    inbound.forEach(function (row) {
      var verdict = classifyShipment(row, ready);
      if (!verdict.ok) {
        holds.push({
          row_id: verdict.row_id,
          sample_id: verdict.sample_id,
          state: "HOLD",
          hold_code: verdict.code,
          test_stage: null,
          report_stage: null,
          result_hash: null,
          report_hash: null
        });
        return;
      }
      if (ready[verdict.sample_id]) return;
      var spec = METHODS[verdict.method];
      ready[verdict.sample_id] = {
        accession_id: "LVK-" + sha256HexSync({ demand_id: DEMAND_ID, sample_id: verdict.sample_id, method: verdict.method }).slice(0, 12),
        sample_id: verdict.sample_id,
        method: verdict.method,
        state: "READY",
        cutover_lane: verdict.cutover_lane,
        quote_hash: sha256HexSync({ quote_id: text(row.quote_id), sample_id: verdict.sample_id, method: verdict.method }),
        form_hash: sha256HexSync({ form_id: text(row.form_id), sample_id: verdict.sample_id, method: verdict.method }),
        coc_hash: verdict.coc ? sha256HexSync(verdict.coc) : null,
        method_hash: sha256HexSync({ method: verdict.method, revision: spec.revision }),
        result_hash: sha256HexSync({ sample_id: verdict.sample_id, method: verdict.method, analytes: spec.analytes }),
        report_hash: sha256HexSync({ sample_id: verdict.sample_id, stage: "STAGED", cutover_lane: verdict.cutover_lane }),
        test_stage: "HASHED",
        report_stage: "STAGED",
        released: false,
        qualification_decision: null
      };
    });
    var records = Object.keys(ready).map(function (id) { return ready[id]; })
      .sort(function (a, b) { return a.sample_id < b.sample_id ? -1 : 1; });
    var holdCounts = {};
    HOLD_CODES.forEach(function (code) { holdCounts[code] = 0; });
    holds.forEach(function (item) { holdCounts[item.hold_code] += 1; });
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      ready: records.length,
      hold: holds.length,
      hold_counts: holdCounts,
      ready_ids: records.map(function (item) { return item.sample_id; }),
      accession_ids: records.map(function (item) { return item.accession_id; }),
      released_reports: 0,
      staged_reports: records.length,
      records: records,
      holds: holds,
      interface_live: false,
      interfaces: "SIMULATED",
      adapters: "SYNTHETIC_READ_ONLY",
      autonomous_certification: false,
      autonomous_release: false,
      qualification_decision: null,
      materials_quality_evidence_only: true,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
    body.manifest_sha256 = sha256HexSync(Object.keys(body).reduce(function (acc, key) {
      if (key !== "manifest_sha256") acc[key] = body[key];
      return acc;
    }, {}));
    return body;
  }

  function passContract(result) {
    var failures = [];
    if (result.input_rows !== 100) failures.push("input_rows!=100");
    if (result.ready !== 80) failures.push("ready!=80");
    if (result.hold !== 20) failures.push("hold!=20");
    var expected = {
      MISSING_ACCEPTED_QUOTE: 8,
      DUPLICATE_SAMPLE_ID: 4,
      FORM_PACKAGE_MISMATCH: 4,
      METHOD_REVISION_MISMATCH: 4
    };
    if (JSON.stringify(result.hold_counts) !== JSON.stringify(expected)) failures.push("hold_counts");
    if ((result.ready_ids || []).length !== 80) failures.push("ready_ids");
    if (result.released_reports !== 0) failures.push("released_reports!=0");
    if (result.staged_reports !== 80) failures.push("staged_reports!=80");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    (result.holds || []).forEach(function (hold) {
      if (hold.test_stage != null || hold.report_stage != null) failures.push("hold_opened_stage");
    });
    return failures.filter(function (item, idx, arr) { return arr.indexOf(item) === idx; });
  }

  return {
    DEMAND_ID: DEMAND_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract,
    sha256HexSync: sha256HexSync
  };
});
