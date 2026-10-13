(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.OregonBrewlabSampleReport = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "oregon-brewlab-sample-report-reconciliation-lims-01";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var UNOPENED = { unopened_bottle: true, unopened_can: true, unopened_crowler: true };
  var SEALED = {
    unopened_bottle: true,
    unopened_can: true,
    unopened_crowler: true,
    sealed_jar: true,
    mason_jar: true,
    nalgene: true,
    approved_container: true
  };
  var ANALYSES = {
    ABV: { min: 4, cold: false, pack: false, family: "chemistry", route: "ASBC_BEER_4G" },
    IBU: { min: 4, cold: false, pack: false, family: "chemistry", route: "ASBC_BEER_23A" },
    PH: { min: 4, cold: false, pack: false, family: "chemistry", route: "ASBC_BEER_9" },
    SRM: { min: 4, cold: false, pack: false, family: "chemistry", route: "ASBC_BEER_10A" },
    VDK: { min: 12, cold: true, pack: true, family: "vdk", route: "ASBC_BEER_25B" },
    FCR: { min: 12, cold: false, pack: true, family: "foam", route: "ASBC_BEER_22A" },
    MICRO_UBA: { min: 4, cold: true, pack: true, family: "micro", route: "ASBC_MICRO_2B" },
    MICRO_COMBO: { min: 4, cold: true, pack: true, family: "micro", route: "ASBC_MICRO_COMBO" },
    KOMBUCHA_ABV: { min: 4, cold: true, pack: false, family: "kombucha", route: "ASBC_BEER_4G_KOMBUCHA" }
  };
  var VALID_PLAN = [
    ["ABV", 16, "STANDARD"],
    ["IBU", 12, "STANDARD"],
    ["PH", 12, "STANDARD"],
    ["SRM", 12, "STANDARD"],
    ["VDK", 12, "STANDARD"],
    ["MICRO_UBA", 12, "STANDARD"],
    ["MICRO_COMBO", 8, "STANDARD"],
    ["FCR", 6, "STANDARD"],
    ["KOMBUCHA_ABV", 4, "STANDARD"],
    ["ABV", 2, "TTB"]
  ];
  var GOLDEN_COUNTS = {
    input_rows: 120,
    ready: 96,
    held: 24,
    duplicate_jobs: 0,
    staged_reports: 96,
    released_reports: 0
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
  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }
  function defaultContainer(analysis) {
    var spec = ANALYSES[analysis] || ANALYSES.ABV;
    if (spec.pack) {
      if (spec.family === "micro") return "unopened_can";
      if (analysis === "FCR") return "unopened_crowler";
      return "unopened_bottle";
    }
    return "sealed_jar";
  }
  function containerAllowed(analysis, container) {
    var spec = ANALYSES[analysis];
    if (!spec) return false;
    return spec.pack ? !!UNOPENED[container] : !!SEALED[container];
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var index = 0;
    var i;
    VALID_PLAN.forEach(function (plan) {
      for (i = 0; i < plan[1]; i += 1) {
        index += 1;
        var analysis = plan[0];
        var spec = ANALYSES[analysis];
        var sampleId = "OBL-V-" + pad(index, 3);
        rows.push({
          row_id: "R" + pad(index, 3),
          sample_id: sampleId,
          analysis: analysis,
          volume_oz: spec.min,
          additional_testing: false,
          form_present: true,
          form_sample_name: sampleId,
          container_label: sampleId,
          container_type: defaultContainer(analysis),
          ice_pack: spec.cold,
          overnight: spec.cold,
          report_class: plan[2],
          expected_hold: null
        });
      }
    });
    var mismatch = [
      { analysis: "ABV", form_present: false, form_sample_name: "" },
      { analysis: "ABV", form_sample_name: "FORM-OTHER", container_label: "OBL-M-02" },
      { analysis: "MICRO_UBA", container_type: "mason_jar" },
      { analysis: "MICRO_UBA", container_type: "falcon_tube" },
      { analysis: "VDK", container_type: "nalgene", volume_oz: 12, ice_pack: true, overnight: true },
      { analysis: "MICRO_UBA", container_type: "whirlpack" },
      { analysis: "MICRO_UBA", container_type: "reused_water_bottle" },
      { analysis: "ABV", form_sample_name: "", container_label: "OBL-M-08" }
    ];
    mismatch.forEach(function (extra, offset) {
      var sampleId = "OBL-M-" + pad(offset + 1, 2);
      var spec = ANALYSES[extra.analysis];
      rows.push({
        row_id: "R" + pad(97 + offset, 3),
        sample_id: sampleId,
        analysis: extra.analysis,
        volume_oz: extra.volume_oz == null ? spec.min : extra.volume_oz,
        additional_testing: false,
        form_present: extra.form_present !== false,
        form_sample_name: extra.form_sample_name == null ? sampleId : extra.form_sample_name,
        container_label: extra.container_label == null ? sampleId : extra.container_label,
        container_type: extra.container_type || defaultContainer(extra.analysis),
        ice_pack: extra.ice_pack == null ? spec.cold : extra.ice_pack,
        overnight: extra.overnight == null ? spec.cold : extra.overnight,
        report_class: "STANDARD",
        expected_hold: "FORM_CONTAINER_MISMATCH"
      });
    });
    for (i = 0; i < 6; i += 1) {
      var original = rows[i];
      rows.push({
        row_id: "R" + pad(105 + i, 3),
        sample_id: original.sample_id,
        analysis: original.analysis,
        volume_oz: original.volume_oz,
        additional_testing: false,
        form_present: true,
        form_sample_name: original.sample_id,
        container_label: original.sample_id,
        container_type: original.container_type,
        ice_pack: original.ice_pack,
        overnight: original.overnight,
        report_class: original.report_class,
        expected_hold: "DUPLICATE_ID"
      });
    }
    var warm = [
      { analysis: "VDK", ice_pack: false, overnight: true, volume_oz: 12 },
      { analysis: "VDK", ice_pack: true, overnight: false, volume_oz: 12 },
      { analysis: "MICRO_UBA", ice_pack: false, overnight: true },
      { analysis: "MICRO_UBA", ice_pack: true, overnight: false },
      { analysis: "MICRO_COMBO", ice_pack: false, overnight: false }
    ];
    warm.forEach(function (extra, offset) {
      var sampleId = "OBL-W-" + pad(offset + 1, 2);
      var spec = ANALYSES[extra.analysis];
      rows.push({
        row_id: "R" + pad(111 + offset, 3),
        sample_id: sampleId,
        analysis: extra.analysis,
        volume_oz: extra.volume_oz == null ? spec.min : extra.volume_oz,
        additional_testing: false,
        form_present: true,
        form_sample_name: sampleId,
        container_label: sampleId,
        container_type: defaultContainer(extra.analysis),
        ice_pack: extra.ice_pack,
        overnight: extra.overnight,
        report_class: "STANDARD",
        expected_hold: "WARM_MICRO_VDK"
      });
    });
    var under = [
      { analysis: "ABV", volume_oz: 2 },
      { analysis: "IBU", volume_oz: 3 },
      { analysis: "VDK", volume_oz: 4, ice_pack: true, overnight: true },
      { analysis: "FCR", volume_oz: 8 },
      { analysis: "VDK", volume_oz: 12, additional_testing: true, ice_pack: true, overnight: true }
    ];
    under.forEach(function (extra, offset) {
      var sampleId = "OBL-U-" + pad(offset + 1, 2);
      var spec = ANALYSES[extra.analysis];
      rows.push({
        row_id: "R" + pad(116 + offset, 3),
        sample_id: sampleId,
        analysis: extra.analysis,
        volume_oz: extra.volume_oz,
        additional_testing: !!extra.additional_testing,
        form_present: true,
        form_sample_name: sampleId,
        container_label: sampleId,
        container_type: defaultContainer(extra.analysis),
        ice_pack: extra.ice_pack == null ? spec.cold : extra.ice_pack,
        overnight: extra.overnight == null ? spec.cold : extra.overnight,
        report_class: "STANDARD",
        expected_hold: "INSUFFICIENT_VOLUME"
      });
    });
    return rows;
  }

  function classify(row, seen) {
    var sampleId = text(row.sample_id);
    var analysis = text(row.analysis).toUpperCase();
    var spec = ANALYSES[analysis];
    var vol = volume(row.volume_oz);
    var additional = flag(row.additional_testing);
    var ice = flag(row.ice_pack);
    var overnight = flag(row.overnight);
    var formPresent = flag(row.form_present);
    var formName = text(row.form_sample_name);
    var label = text(row.container_label);
    var container = text(row.container_type);
    if (sampleId && seen[sampleId]) return { ok: false, code: "DUPLICATE_ID", sample_id: sampleId };
    if (!sampleId || !spec || !formPresent || !formName || !label || formName !== label || !containerAllowed(analysis, container)) {
      return { ok: false, code: "FORM_CONTAINER_MISMATCH", sample_id: sampleId || null };
    }
    var minimum = spec.min * (additional ? 2 : 1);
    if (vol < minimum) return { ok: false, code: "INSUFFICIENT_VOLUME", sample_id: sampleId };
    if (spec.cold && (spec.family === "micro" || spec.family === "vdk" || spec.family === "kombucha") && (!ice || !overnight)) {
      return { ok: false, code: "WARM_MICRO_VDK", sample_id: sampleId };
    }
    return { ok: true, sample_id: sampleId, analysis: analysis, route: spec.route };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var jobs = {};
    var holds = [];
    var seen = {};
    inbound.forEach(function (row) {
      var verdict = classify(row, seen);
      if (!verdict.ok) {
        holds.push({
          row_id: text(row.row_id),
          sample_id: verdict.sample_id,
          code: verdict.code,
          ready: false
        });
        return;
      }
      seen[verdict.sample_id] = true;
      jobs[verdict.sample_id] = {
        sample_id: verdict.sample_id,
        analysis: verdict.analysis,
        route: verdict.route,
        state: "READY",
        report_status: "STAGED",
        released: false,
        interface_live: false
      };
    });
    var jobList = Object.keys(jobs).sort().map(function (id) { return jobs[id]; });
    var holdCodes = holds.map(function (item) { return item.code; });
    var routes = {};
    jobList.forEach(function (item) { routes[item.sample_id] = item.route; });
    return {
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      ready: jobList.length,
      held: holds.length,
      hold_codes: holdCodes,
      hold_code_set: Object.keys(holdCodes.reduce(function (acc, code) { acc[code] = true; return acc; }, {})).sort(),
      duplicate_jobs: 0,
      staged_reports: jobList.length,
      released_reports: 0,
      jobs: jobList,
      holds: holds,
      routes: routes,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      production_writes: 0,
      official_binary: "python3 test_oregon_brewlab_sample_report.py",
      pre_sale_transport: "NONE"
    };
  }

  function passContract(result) {
    var failures = [];
    if (result.input_rows !== GOLDEN_COUNTS.input_rows) failures.push("input_rows");
    if (result.ready !== GOLDEN_COUNTS.ready) failures.push("ready");
    if (result.held !== GOLDEN_COUNTS.held) failures.push("held");
    if (result.duplicate_jobs !== 0) failures.push("duplicate_jobs");
    if (result.staged_reports !== GOLDEN_COUNTS.staged_reports) failures.push("staged_reports");
    if (result.released_reports !== 0) failures.push("released_reports");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    var counts = result.hold_codes.reduce(function (acc, code) {
      acc[code] = (acc[code] || 0) + 1;
      return acc;
    }, {});
    if (counts.FORM_CONTAINER_MISMATCH !== 8) failures.push("form_container");
    if (counts.DUPLICATE_ID !== 6) failures.push("duplicate_id");
    if (counts.WARM_MICRO_VDK !== 5) failures.push("warm_micro_vdk");
    if (counts.INSUFFICIENT_VOLUME !== 5) failures.push("insufficient_volume");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
