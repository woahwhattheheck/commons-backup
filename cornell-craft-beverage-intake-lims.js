(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CornellCraftBeverageIntake = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "cornell-craft-beverage-intake-lims-01";
  var SCHEMA = "commons-cornell-craft-beverage-intake-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var PANELS = {
    WINE_MULTI: { matrix: "grape_wine", analyses: ["so2", "ethanol", "ph", "ta"], min_volume_ml: 750 },
    WINE_SINGLE: { matrix: "grape_wine", analyses: ["ethanol"], min_volume_ml: 375 },
    CIDER_SINGLE: { matrix: "cider", analyses: ["ethanol"], min_volume_ml: 375 },
    SPIRITS_ABV: { matrix: "distillate", analyses: ["ethanol"], min_volume_ml: 100 },
    KOMBUCHA_ABV: { matrix: "kombucha", analyses: ["ethanol"], min_volume_ml: 100 },
    JUICE_PANEL: { matrix: "juice", analyses: ["brix", "ta", "ph", "yeast_assimilable_n"], min_volume_ml: 750 }
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function flag(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    return /^(1|true|yes|y)$/i.test(String(value).trim());
  }
  function volume(value) {
    var n = Number(value);
    return Number.isFinite(n) ? n : 0;
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
  function accessionId(sampleId, panel, matrix) {
    return "CCB-" + sha256HexSync({
      demand_id: DEMAND_ID,
      sample_id: sampleId,
      panel: panel,
      matrix: matrix
    }).slice(0, 12);
  }

  function buildAcceptanceFixture() {
    return [
      { row_id: "R01", sample_id: "CCB-W01", matrix: "grape_wine", panel: "WINE_MULTI", volume_ml: 750, frozen: false, next_day: false, container_full: true },
      { row_id: "R02", sample_id: "CCB-W02", matrix: "grape_wine", panel: "WINE_SINGLE", volume_ml: 375, frozen: false, next_day: false, container_full: true },
      { row_id: "R03", sample_id: "CCB-S01", matrix: "distillate", panel: "SPIRITS_ABV", volume_ml: 100, frozen: false, next_day: false, sealed: true },
      { row_id: "R04", sample_id: "CCB-K01", matrix: "kombucha", panel: "KOMBUCHA_ABV", volume_ml: 100, frozen: false, next_day: false, chilled: true },
      { row_id: "R05", sample_id: "CCB-J01", matrix: "juice", panel: "JUICE_PANEL", volume_ml: 750, frozen: true, next_day: true },
      { row_id: "R06", sample_id: "CCB-C01", matrix: "cider", panel: "CIDER_SINGLE", volume_ml: 375, frozen: false, next_day: false, container_full: true },
      { row_id: "R07", sample_id: "CCB-W03", matrix: "grape_wine", panel: "WINE_MULTI", volume_ml: 200, frozen: false, next_day: false, container_full: true },
      { row_id: "R08", sample_id: "", matrix: "grape_wine", panel: "WINE_SINGLE", volume_ml: 375, frozen: false, next_day: false, container_full: true }
    ];
  }

  function classifySubmission(row) {
    var sampleId = text(row.sample_id);
    var matrix = text(row.matrix);
    var panel = text(row.panel);
    var volumeMl = volume(row.volume_ml);
    var spec = PANELS[panel];
    if (!sampleId) {
      return { ok: false, code: "MISSING_SAMPLE_ID", sample_id: sampleId, matrix: matrix, panel: panel, volume_ml: volumeMl };
    }
    if (!spec || spec.matrix !== matrix || volumeMl < spec.min_volume_ml) {
      return { ok: false, code: "UNDER_VOLUME", sample_id: sampleId, matrix: matrix, panel: panel, volume_ml: volumeMl };
    }
    return {
      ok: true,
      sample_id: sampleId,
      matrix: matrix,
      panel: panel,
      analyses: spec.analyses.slice(),
      volume_ml: volumeMl,
      frozen: flag(row.frozen),
      next_day: flag(row.next_day),
      accession_id: accessionId(sampleId, panel, matrix),
      route: panel
    };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var rejects = [];
    inbound.forEach(function (row) {
      var verdict = classifySubmission(row);
      if (!verdict.ok) {
        rejects.push({
          row_id: text(row.row_id),
          sample_id: verdict.sample_id || null,
          code: verdict.code,
          matrix: verdict.matrix,
          panel: verdict.panel,
          volume_ml: verdict.volume_ml
        });
        return;
      }
      if (accessions[verdict.accession_id]) return;
      var received = verdict.matrix !== "juice" || (verdict.frozen && verdict.next_day);
      accessions[verdict.accession_id] = {
        accession_id: verdict.accession_id,
        sample_id: verdict.sample_id,
        matrix: verdict.matrix,
        panel: verdict.panel,
        route: verdict.route,
        analyses: verdict.analyses,
        volume_ml: verdict.volume_ml,
        frozen: verdict.frozen,
        next_day: verdict.next_day,
        state: received ? "RECEIVED" : "ACCESSIONED",
        analyst_result: null,
        qc_signoff: false,
        released: false,
        report_status: "BLOCKED_MISSING_RESULT",
        interface_state: "SIMULATED",
        interface_live: false
      };
    });
    var accessioned = Object.keys(accessions).map(function (id) { return accessions[id]; })
      .sort(function (a, b) { return a.sample_id < b.sample_id ? -1 : 1; });
    var routes = {};
    accessioned.forEach(function (item) { routes[item.sample_id] = item.route; });
    var rejectCodes = rejects.map(function (item) { return item.code; }).sort();
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      accessioned: accessioned.length,
      rejected: rejects.length,
      reject_codes: rejectCodes,
      routes: routes,
      accession_ids: accessioned.map(function (item) { return item.accession_id; }),
      received: accessioned.filter(function (item) { return item.state === "RECEIVED"; }).map(function (item) { return item.accession_id; }).sort(),
      received_count: accessioned.filter(function (item) { return item.state === "RECEIVED"; }).length,
      blocked_reports: accessioned.length,
      released_reports: 0,
      accessions: accessioned,
      rejects: rejects,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_certification: false,
      autonomous_release: false,
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
    if (result.input_rows !== 8) failures.push("input_rows!=8");
    if (result.accessioned !== 6) failures.push("accessioned!=6");
    if (result.rejected !== 2) failures.push("rejected!=2");
    if (JSON.stringify(result.reject_codes) !== JSON.stringify(["MISSING_SAMPLE_ID", "UNDER_VOLUME"])) failures.push("reject_codes");
    var expected = {
      "CCB-C01": "CIDER_SINGLE",
      "CCB-J01": "JUICE_PANEL",
      "CCB-K01": "KOMBUCHA_ABV",
      "CCB-S01": "SPIRITS_ABV",
      "CCB-W01": "WINE_MULTI",
      "CCB-W02": "WINE_SINGLE"
    };
    if (JSON.stringify(result.routes) !== JSON.stringify(expected)) failures.push("routes");
    if ((result.accession_ids || []).length !== 6) failures.push("accession_ids");
    if (result.released_reports !== 0) failures.push("released_reports!=0");
    if (result.blocked_reports !== 6) failures.push("blocked_reports!=6");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    var juice = (result.accessions || []).filter(function (item) { return item.sample_id === "CCB-J01"; })[0];
    if (!juice || juice.state !== "RECEIVED") failures.push("juice_not_received");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract,
    sha256HexSync: sha256HexSync
  };
});
