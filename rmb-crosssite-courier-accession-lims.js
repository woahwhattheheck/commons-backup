(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.RmbCrosssiteCourierAccession = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "rmb-crosssite-courier-accession-lims-01";
  var SCHEMA = "commons-rmb-crosssite-courier-accession-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var HOLD_CODES = [
    "HOLD_RECEIPT_OVER_48H",
    "HOLD_MISSED_COURIER_CUTOFF",
    "HOLD_DUPLICATE_SAMPLE_ID",
    "HOLD_BROKEN_COOLER_CUSTODY",
    "HOLD_FACILITY_METHOD_SCOPE_MISMATCH",
    "HOLD_LEGACY_SITE_MAPPING"
  ];
  var FACILITIES = {
    RMB_DETROIT_LAKES: {
      code: "RMB",
      offset: "-05:00",
      cert_scopes: ["SM_9223B", "SM_4500P", "SM_2540D", "SM_10200H", "SM_5210B", "EPA_2008"]
    },
    BECKTON_PONCE: {
      code: "BECKTON",
      offset: "-04:00",
      cert_scopes: ["SM_9223B", "SM_4500P", "SM_2540D", "EPA_2008"]
    }
  };
  var METHOD_SCOPE = {
    SM_9223B: "MICRO_COLIFORM",
    SM_4500P: "NUTRIENTS",
    SM_2540D: "TSS",
    SM_10200H: "CHL_A",
    SM_5210B: "BOD",
    EPA_2008: "METALS"
  };
  var RMB_METHODS = FACILITIES.RMB_DETROIT_LAKES.cert_scopes;
  var BECKTON_METHODS = FACILITIES.BECKTON_PONCE.cert_scopes;
  var LAKE_ONLY = { SM_10200H: true, SM_5210B: true };
  var RMB_LEGACY = ["RMB", "RMB-HQ", "DL", "DETROIT-LAKES"];
  var BECKTON_LEGACY = ["BEC", "BECKTON", "BECKTON-OLD", "PONCE"];
  var LEGACY_MAP = {
    BEC: "BECKTON_PONCE",
    BECKTON: "BECKTON_PONCE",
    "BECKTON-OLD": "BECKTON_PONCE",
    PONCE: "BECKTON_PONCE",
    RMB: "RMB_DETROIT_LAKES",
    "RMB-HQ": "RMB_DETROIT_LAKES",
    DL: "RMB_DETROIT_LAKES",
    "DETROIT-LAKES": "RMB_DETROIT_LAKES"
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function flag(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    return /^(1|true|yes|y)$/i.test(String(value).trim());
  }
  function temp(value) {
    var n = Number(value);
    return Number.isFinite(n) ? n : 99;
  }
  function parseTs(value) {
    var t = Date.parse(text(value));
    return Number.isFinite(t) ? new Date(t) : null;
  }
  function localTime(iso) {
    var match = text(iso).match(/T(\d{2}):(\d{2})/);
    if (!match) return null;
    return Number(match[1]) * 60 + Number(match[2]);
  }

  function stamp(row) {
    row.signed_manifest = {
      courier_id: row.courier_id,
      pickup_ts: row.pickup_ts,
      receipt_ts: row.receipt_ts,
      facility: row.facility,
      method: row.method,
      cert_scope: row.cert_scope,
      seal_id: row.manifest_seal_id,
      signature: "SIG-" + row.row_id
    };
    return row;
  }

  function baseRow(opts) {
    var seal = opts.cooler_seal_id || ("SEAL-" + String(opts.index).padStart(4, "0"));
    return stamp({
      row_id: "R" + String(opts.index).padStart(3, "0"),
      sample_id: opts.sample_id,
      client_id: opts.client_id,
      site_id: opts.site_id,
      matrix: opts.matrix,
      method: opts.method,
      cert_scope: METHOD_SCOPE[opts.method],
      facility: opts.facility,
      legacy_site_code: opts.legacy_site_code,
      collection_ts: opts.collection_ts,
      pickup_ts: opts.pickup_ts,
      receipt_ts: opts.receipt_ts,
      courier_id: opts.facility === "RMB_DETROIT_LAKES" ? "PARTNER-NORTH" : "PARTNER-CARIB",
      cooler_seal_id: seal,
      manifest_seal_id: opts.manifest_seal_id || seal,
      cooler_intact: opts.cooler_intact !== false,
      temp_c: opts.temp_c == null ? 3.2 : opts.temp_c,
      truth: opts.truth
    });
  }

  function validTimes(facility) {
    var offset = FACILITIES[facility].offset;
    return ["2026-06-08T08:00:00" + offset, "2026-06-08T10:30:00" + offset, "2026-06-08T14:00:00" + offset];
  }
  function over48Times(facility) {
    var offset = FACILITIES[facility].offset;
    return ["2026-06-08T08:00:00" + offset, "2026-06-08T10:30:00" + offset, "2026-06-10T10:30:00" + offset];
  }
  function lateTimes(facility) {
    var offset = FACILITIES[facility].offset;
    return ["2026-06-08T08:00:00" + offset, "2026-06-08T16:15:00" + offset, "2026-06-08T17:30:00" + offset];
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var index = 1;
    var i;
    var times;
    var method;
    var facility;
    for (i = 0; i < 120; i += 1) {
      method = RMB_METHODS[i % RMB_METHODS.length];
      times = validTimes("RMB_DETROIT_LAKES");
      rows.push(baseRow({
        index: index,
        facility: "RMB_DETROIT_LAKES",
        method: method,
        matrix: LAKE_ONLY[method] ? "lake" : "water",
        sample_id: "RMB-W-" + String(i + 1).padStart(4, "0"),
        client_id: "CLIENT-RMB-" + String((i % 24) + 1).padStart(2, "0"),
        site_id: "SITE-RMB-" + String((i % 40) + 1).padStart(2, "0"),
        legacy_site_code: RMB_LEGACY[i % RMB_LEGACY.length],
        collection_ts: times[0],
        pickup_ts: times[1],
        receipt_ts: times[2],
        truth: "VALID"
      }));
      index += 1;
    }
    for (i = 0; i < 120; i += 1) {
      method = BECKTON_METHODS[i % BECKTON_METHODS.length];
      times = validTimes("BECKTON_PONCE");
      rows.push(baseRow({
        index: index,
        facility: "BECKTON_PONCE",
        method: method,
        matrix: "water",
        sample_id: "BEC-W-" + String(i + 1).padStart(4, "0"),
        client_id: "CLIENT-BEC-" + String((i % 24) + 1).padStart(2, "0"),
        site_id: "SITE-BEC-" + String((i % 40) + 1).padStart(2, "0"),
        legacy_site_code: BECKTON_LEGACY[i % BECKTON_LEGACY.length],
        collection_ts: times[0],
        pickup_ts: times[1],
        receipt_ts: times[2],
        truth: "VALID"
      }));
      index += 1;
    }
    for (i = 0; i < 10; i += 1) {
      facility = i % 2 === 0 ? "RMB_DETROIT_LAKES" : "BECKTON_PONCE";
      method = facility === "RMB_DETROIT_LAKES" ? RMB_METHODS[i % RMB_METHODS.length] : BECKTON_METHODS[i % BECKTON_METHODS.length];
      times = over48Times(facility);
      rows.push(baseRow({
        index: index,
        facility: facility,
        method: method,
        matrix: LAKE_ONLY[method] ? "lake" : "water",
        sample_id: (facility === "RMB_DETROIT_LAKES" ? "RMB" : "BEC") + "-H48-" + String(i + 1).padStart(2, "0"),
        client_id: "CLIENT-H48-" + String(i + 1).padStart(2, "0"),
        site_id: "SITE-H48-" + String(i + 1).padStart(2, "0"),
        legacy_site_code: facility === "RMB_DETROIT_LAKES" ? RMB_LEGACY[i % RMB_LEGACY.length] : BECKTON_LEGACY[i % BECKTON_LEGACY.length],
        collection_ts: times[0],
        pickup_ts: times[1],
        receipt_ts: times[2],
        truth: "HOLD_RECEIPT_OVER_48H"
      }));
      index += 1;
    }
    for (i = 0; i < 10; i += 1) {
      facility = i % 2 === 0 ? "RMB_DETROIT_LAKES" : "BECKTON_PONCE";
      method = facility === "RMB_DETROIT_LAKES" ? RMB_METHODS[i % RMB_METHODS.length] : BECKTON_METHODS[i % BECKTON_METHODS.length];
      times = lateTimes(facility);
      rows.push(baseRow({
        index: index,
        facility: facility,
        method: method,
        matrix: LAKE_ONLY[method] ? "lake" : "water",
        sample_id: (facility === "RMB_DETROIT_LAKES" ? "RMB" : "BEC") + "-CUT-" + String(i + 1).padStart(2, "0"),
        client_id: "CLIENT-CUT-" + String(i + 1).padStart(2, "0"),
        site_id: "SITE-CUT-" + String(i + 1).padStart(2, "0"),
        legacy_site_code: facility === "RMB_DETROIT_LAKES" ? RMB_LEGACY[i % RMB_LEGACY.length] : BECKTON_LEGACY[i % BECKTON_LEGACY.length],
        collection_ts: times[0],
        pickup_ts: times[1],
        receipt_ts: times[2],
        truth: "HOLD_MISSED_COURIER_CUTOFF"
      }));
      index += 1;
    }
    for (i = 0; i < 10; i += 1) {
      var original = rows[i];
      times = validTimes(original.facility);
      rows.push(baseRow({
        index: index,
        facility: original.facility,
        method: original.method,
        matrix: original.matrix,
        sample_id: original.sample_id,
        client_id: original.client_id,
        site_id: original.site_id,
        legacy_site_code: original.legacy_site_code,
        collection_ts: times[0],
        pickup_ts: times[1],
        receipt_ts: times[2],
        truth: "HOLD_DUPLICATE_SAMPLE_ID"
      }));
      index += 1;
    }
    for (i = 0; i < 10; i += 1) {
      facility = i % 2 === 0 ? "RMB_DETROIT_LAKES" : "BECKTON_PONCE";
      method = facility === "RMB_DETROIT_LAKES" ? RMB_METHODS[i % RMB_METHODS.length] : BECKTON_METHODS[i % BECKTON_METHODS.length];
      times = validTimes(facility);
      var coolerIntact = true;
      var tempC = 3.2;
      var coolerSeal = "SEAL-" + String(index).padStart(4, "0");
      var manifestSeal = coolerSeal;
      if (i < 4) coolerIntact = false;
      else if (i < 7) manifestSeal = "SEAL-BROKEN-" + String(i).padStart(2, "0");
      else tempC = 12.4;
      rows.push(baseRow({
        index: index,
        facility: facility,
        method: method,
        matrix: LAKE_ONLY[method] ? "lake" : "water",
        sample_id: (facility === "RMB_DETROIT_LAKES" ? "RMB" : "BEC") + "-COOL-" + String(i + 1).padStart(2, "0"),
        client_id: "CLIENT-COOL-" + String(i + 1).padStart(2, "0"),
        site_id: "SITE-COOL-" + String(i + 1).padStart(2, "0"),
        legacy_site_code: facility === "RMB_DETROIT_LAKES" ? RMB_LEGACY[i % RMB_LEGACY.length] : BECKTON_LEGACY[i % BECKTON_LEGACY.length],
        collection_ts: times[0],
        pickup_ts: times[1],
        receipt_ts: times[2],
        truth: "HOLD_BROKEN_COOLER_CUSTODY",
        cooler_intact: coolerIntact,
        temp_c: tempC,
        cooler_seal_id: coolerSeal,
        manifest_seal_id: manifestSeal
      }));
      index += 1;
    }
    for (i = 0; i < 10; i += 1) {
      method = i % 2 === 0 ? "SM_10200H" : "SM_5210B";
      times = validTimes("BECKTON_PONCE");
      rows.push(baseRow({
        index: index,
        facility: "BECKTON_PONCE",
        method: method,
        matrix: "lake",
        sample_id: "BEC-SCOPE-" + String(i + 1).padStart(2, "0"),
        client_id: "CLIENT-SCOPE-" + String(i + 1).padStart(2, "0"),
        site_id: "SITE-SCOPE-" + String(i + 1).padStart(2, "0"),
        legacy_site_code: BECKTON_LEGACY[i % BECKTON_LEGACY.length],
        collection_ts: times[0],
        pickup_ts: times[1],
        receipt_ts: times[2],
        truth: "HOLD_FACILITY_METHOD_SCOPE_MISMATCH"
      }));
      index += 1;
    }
    for (i = 0; i < 10; i += 1) {
      facility = i % 2 === 0 ? "RMB_DETROIT_LAKES" : "BECKTON_PONCE";
      times = validTimes(facility);
      rows.push(baseRow({
        index: index,
        facility: facility,
        method: "SM_9223B",
        matrix: "water",
        sample_id: (facility === "RMB_DETROIT_LAKES" ? "RMB" : "BEC") + "-MAP-" + String(i + 1).padStart(2, "0"),
        client_id: "CLIENT-MAP-" + String(i + 1).padStart(2, "0"),
        site_id: "SITE-MAP-" + String(i + 1).padStart(2, "0"),
        legacy_site_code: facility === "RMB_DETROIT_LAKES" ? BECKTON_LEGACY[i % BECKTON_LEGACY.length] : RMB_LEGACY[i % RMB_LEGACY.length],
        collection_ts: times[0],
        pickup_ts: times[1],
        receipt_ts: times[2],
        truth: "HOLD_LEGACY_SITE_MAPPING"
      }));
      index += 1;
    }
    if (rows.length !== 300) throw new Error("fixture must be 300 rows");
    return rows;
  }

  function classify(row, seen) {
    var sampleId = text(row.sample_id);
    var facility = text(row.facility);
    var method = text(row.method);
    var legacy = text(row.legacy_site_code).toUpperCase();
    if (sampleId && seen && seen[sampleId] && seen[sampleId] !== text(row.row_id)) {
      return { ok: false, code: "HOLD_DUPLICATE_SAMPLE_ID", sample_id: sampleId };
    }
    var mapped = LEGACY_MAP[legacy];
    if (!mapped || mapped !== facility) {
      return { ok: false, code: "HOLD_LEGACY_SITE_MAPPING", sample_id: sampleId };
    }
    var scopes = (FACILITIES[facility] || {}).cert_scopes || [];
    if (scopes.indexOf(method) < 0) {
      return { ok: false, code: "HOLD_FACILITY_METHOD_SCOPE_MISMATCH", sample_id: sampleId };
    }
    var intact = flag(row.cooler_intact);
    var sealOk = text(row.cooler_seal_id) && text(row.cooler_seal_id) === text(row.manifest_seal_id);
    if (!intact || !sealOk || temp(row.temp_c) > 6) {
      return { ok: false, code: "HOLD_BROKEN_COOLER_CUSTODY", sample_id: sampleId };
    }
    if (localTime(row.pickup_ts) == null || localTime(row.pickup_ts) > 15 * 60) {
      return { ok: false, code: "HOLD_MISSED_COURIER_CUTOFF", sample_id: sampleId };
    }
    var collected = parseTs(row.collection_ts);
    var received = parseTs(row.receipt_ts);
    if (!collected || !received || (received - collected) > 48 * 3600 * 1000) {
      return { ok: false, code: "HOLD_RECEIPT_OVER_48H", sample_id: sampleId };
    }
    return {
      ok: true,
      sample_id: sampleId,
      client_id: text(row.client_id),
      site_id: text(row.site_id),
      facility: facility,
      method: method,
      cert_scope: text(row.cert_scope) || METHOD_SCOPE[method],
      pickup_ts: text(row.pickup_ts),
      receipt_ts: text(row.receipt_ts)
    };
  }

  function manifestMatches(row, verdict) {
    var manifest = row.signed_manifest || {};
    return text(manifest.pickup_ts) === verdict.pickup_ts
      && text(manifest.receipt_ts) === verdict.receipt_ts
      && text(manifest.facility) === verdict.facility
      && text(manifest.method) === verdict.method
      && text(manifest.cert_scope) === verdict.cert_scope;
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var bySample = {};
    var holds = [];
    inbound.forEach(function (row) {
      var sampleId = text(row.sample_id);
      var rowId = text(row.row_id);
      if (sampleId && bySample[sampleId] && bySample[sampleId].row_id === rowId) return;
      var seen = {};
      Object.keys(bySample).forEach(function (id) { seen[id] = bySample[id].row_id; });
      var verdict = classify(row, seen);
      if (!verdict.ok) {
        holds.push({ row_id: rowId, sample_id: verdict.sample_id || null, code: verdict.code });
        return;
      }
      var accId = verdict.facility + ":" + verdict.sample_id;
      accessions[accId] = {
        incumbent_accession_id: accId,
        row_id: rowId,
        sample_id: verdict.sample_id,
        client_id: verdict.client_id,
        site_id: verdict.site_id,
        facility: verdict.facility,
        method: verdict.method,
        cert_scope: verdict.cert_scope,
        pickup_ts: verdict.pickup_ts,
        receipt_ts: verdict.receipt_ts,
        hashes_ok: manifestMatches(row, verdict),
        report_status: "STAGED_BLOCKED_MISSING_RESULT",
        released: false,
        interface_state: "READ_ONLY_SHADOW",
        interface_live: false
      };
      bySample[verdict.sample_id] = accessions[accId];
    });
    var accessioned = Object.keys(accessions).map(function (id) { return accessions[id]; });
    var holdCounts = {};
    HOLD_CODES.forEach(function (code) { holdCounts[code] = 0; });
    holds.forEach(function (item) { holdCounts[item.code] = (holdCounts[item.code] || 0) + 1; });
    var rmb = accessioned.filter(function (item) { return item.facility === "RMB_DETROIT_LAKES"; }).length;
    var beckton = accessioned.filter(function (item) { return item.facility === "BECKTON_PONCE"; }).length;
    return {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      accessioned: accessioned.length,
      held: holds.length,
      hold_counts: holdCounts,
      rmb_facility: rmb,
      beckton_facility: beckton,
      hashes_ok_count: accessioned.filter(function (item) { return item.hashes_ok; }).length,
      blocked_reports: accessioned.length,
      released_reports: 0,
      interface_live: false,
      interfaces: "READ_ONLY_SHADOW",
      incumbent_writes: 0,
      production_writes: 0,
      shadow_only: true,
      autonomous_release: false,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
  }

  function passContract(result) {
    var failures = [];
    if (result.input_rows !== 300) failures.push("input_rows!=300");
    if (result.accessioned !== 240) failures.push("accessioned!=240");
    if (result.held !== 60) failures.push("held!=60");
    HOLD_CODES.forEach(function (code) {
      if ((result.hold_counts || {})[code] !== 10) failures.push(code);
    });
    if (result.rmb_facility !== 120) failures.push("rmb_facility");
    if (result.beckton_facility !== 120) failures.push("beckton_facility");
    if (result.hashes_ok_count !== 240) failures.push("hashes");
    if (result.released_reports !== 0) failures.push("released");
    if (result.incumbent_writes !== 0) failures.push("incumbent_writes");
    if (result.production_writes !== 0) failures.push("production_writes");
    if (result.interface_live !== false) failures.push("interface_live");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
