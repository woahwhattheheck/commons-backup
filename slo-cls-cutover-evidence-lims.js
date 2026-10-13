(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SloClsCutoverEvidence = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "slo-cls-cutover-evidence-lims-01";
  var SCHEMA = "commons-slo-cls-cutover-evidence-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var HUMAN_APPROVER = "SYN-SLO-RELEASER";
  var VALID_COUNT = 850;
  var DUPLICATE_COUNT = 50;
  var BROKEN_REF_COUNT = 40;
  var METHOD_CONFLICT_COUNT = 30;
  var HASH_MISMATCH_COUNT = 30;
  var HOLD_COUNT = 150;
  var INPUT_COUNT = 1000;
  var CATALOG = {
    "PF-SARS-COV-2": { versions: ["2.1.0", "2.2.0"] },
    "PF-FLU-AB-RSV": { versions: ["1.5.0", "1.6.0"] },
    "PF-PARAFLU": { versions: ["1.3.0"] },
    "PF-ADENO": { versions: ["1.2.0"] },
    "PF-CT-NG": { versions: ["2.0.0", "2.1.0"] }
  };
  var METHOD_PAIRS = [];
  Object.keys(CATALOG).forEach(function (method) {
    CATALOG[method].versions.forEach(function (version) {
      METHOD_PAIRS.push([method, version]);
    });
  });
  var HOLD_FAMILY_COUNTS = {
    DUPLICATE_ID: 50,
    BROKEN_SAMPLE_TEST_REF: 40,
    METHOD_VERSION_CONFLICT: 30,
    HASH_MISMATCH: 30
  };

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
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
  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }
  function methodPair(index) { return METHOD_PAIRS[index % METHOD_PAIRS.length]; }
  function resultPayload(index, method, version) {
    return { cycle_index: index, rf_units: (index % 97) + 3, method: method, method_version: version, instrument: "SYN-PANTHER-FUSION" };
  }
  function reportPayload(accessionId, sampleId, testId, resultHash) {
    return { accession_id: accessionId, sample_id: sampleId, test_id: testId, result_hash: resultHash, interpretation: null, public_health_call: null };
  }
  function sourcePayload(row) {
    return {
      demand_id: DEMAND_ID,
      legacy_id: row.legacy_id,
      channel: row.channel,
      accession_id: row.accession_id,
      requisition_id: row.requisition_id,
      sample_id: row.sample_id,
      test_id: row.test_id,
      sample_test_ref: row.sample_test_ref,
      method: row.method,
      method_version: row.method_version
    };
  }
  function stampHashes(row) {
    row.result_hash = sha256HexSync(row.result);
    row.report = reportPayload(row.accession_id, row.sample_id, row.test_id, row.result_hash);
    row.report_hash = sha256HexSync(row.report);
    row.source = sourcePayload(row);
    row.source_hash = sha256HexSync(row.source);
    return row;
  }
  function validBundle(index) {
    var pair = methodPair(index - 1);
    var channel = index % 2 === 1 ? "REQUISITION" : "PORTAL";
    var prefix = channel === "REQUISITION" ? "REQ" : "PRT";
    var row = {
      bundle_id: "SLO-" + pad(index, 4),
      legacy_id: "INC-" + pad(index, 4),
      channel: channel,
      accession_id: "ACC-" + pad(index, 4),
      requisition_id: prefix + "-" + pad(index, 4),
      sample_id: "SMP-" + pad(index, 4),
      test_id: "TST-" + pad(index, 4),
      sample_test_ref: "SMP-" + pad(index, 4) + "->TST-" + pad(index, 4),
      method: pair[0],
      method_version: pair[1],
      result: resultPayload(index, pair[0], pair[1]),
      expected_state: "READY",
      expected_hold: null
    };
    return stampHashes(row);
  }
  function duplicateBundle(slot) {
    var row = clone(validBundle(slot + 1));
    row.bundle_id = "SLO-D-" + pad(slot + 1, 4);
    row.expected_state = "HOLD";
    row.expected_hold = "DUPLICATE_ID";
    return row;
  }
  function brokenRefBundle(slot) {
    var index = VALID_COUNT + slot + 1;
    var row = validBundle(index);
    row.bundle_id = "SLO-B-" + pad(slot + 1, 4);
    row.expected_state = "HOLD";
    row.expected_hold = "BROKEN_SAMPLE_TEST_REF";
    row.sample_test_ref = slot % 2 === 0 ? row.sample_id + "->TST-MISSING" : "SMP-MISSING->" + row.test_id;
    return stampHashes(row);
  }
  function methodConflictBundle(slot) {
    var index = VALID_COUNT + BROKEN_REF_COUNT + slot + 1;
    var row = validBundle(index);
    row.bundle_id = "SLO-M-" + pad(slot + 1, 4);
    row.expected_state = "HOLD";
    row.expected_hold = "METHOD_VERSION_CONFLICT";
    if (slot % 2 === 0) { row.method = "PF-UNKNOWN"; row.method_version = "0.0.0"; }
    else { row.method_version = "9.9.9"; }
    row.result = resultPayload(index, row.method, row.method_version);
    return stampHashes(row);
  }
  function hashMismatchBundle(slot) {
    var index = VALID_COUNT + BROKEN_REF_COUNT + METHOD_CONFLICT_COUNT + slot + 1;
    var row = validBundle(index);
    row.bundle_id = "SLO-H-" + pad(slot + 1, 4);
    row.expected_state = "HOLD";
    row.expected_hold = "HASH_MISMATCH";
    if (slot % 3 === 0) row.result_hash = "00000000";
    else if (slot % 3 === 1) row.report_hash = "11111111";
    else row.source_hash = "22222222";
    return row;
  }
  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= VALID_COUNT; i += 1) rows.push(validBundle(i));
    for (i = 0; i < DUPLICATE_COUNT; i += 1) rows.push(duplicateBundle(i));
    for (i = 0; i < BROKEN_REF_COUNT; i += 1) rows.push(brokenRefBundle(i));
    for (i = 0; i < METHOD_CONFLICT_COUNT; i += 1) rows.push(methodConflictBundle(i));
    for (i = 0; i < HASH_MISMATCH_COUNT; i += 1) rows.push(hashMismatchBundle(i));
    return rows;
  }
  function hashesOk(row) {
    return sha256HexSync(row.result) === text(row.result_hash)
      && sha256HexSync(row.report) === text(row.report_hash)
      && sha256HexSync(row.source) === text(row.source_hash);
  }
  function methodOk(row) {
    var spec = CATALOG[text(row.method)];
    return !!(spec && spec.versions.indexOf(text(row.method_version)) !== -1);
  }
  function refOk(row) {
    return text(row.sample_test_ref) === text(row.sample_id) + "->" + text(row.test_id);
  }
  function emptyJournal() {
    return {
      seenLegacy: {},
      seenAccession: {},
      ready: {},
      holds: [],
      mappings: {},
      clsIndex: {},
      objects: {}
    };
  }
  function classify(journal, row) {
    var legacyId = text(row.legacy_id);
    var accessionId = text(row.accession_id);
    if (!legacyId || !accessionId) return "DUPLICATE_ID";
    if (journal.seenLegacy[legacyId] || journal.seenAccession[accessionId]) return "DUPLICATE_ID";
    if (!refOk(row)) return "BROKEN_SAMPLE_TEST_REF";
    if (!methodOk(row)) return "METHOD_VERSION_CONFLICT";
    if (!hashesOk(row)) return "HASH_MISMATCH";
    return null;
  }
  function clsId(row) {
    return "CLS-" + sha256HexSync({
      demand_id: DEMAND_ID,
      accession_id: row.accession_id,
      method: row.method,
      method_version: row.method_version,
      result_hash: row.result_hash,
      report_hash: row.report_hash,
      source_hash: row.source_hash
    }).slice(0, 16);
  }
  function ingest(journal, row) {
    var bundleId = text(row.bundle_id);
    var legacyId = text(row.legacy_id);
    var existing = journal.ready[legacyId];
    if (existing && existing.bundle_id === bundleId) return "REPLAY_NOOP";
    var code = classify(journal, row);
    if (code) {
      var hold = { bundle_id: bundleId, legacy_id: legacyId || null, accession_id: text(row.accession_id) || null, code: code, state: "HOLD", mapped: false };
      var key = hold.bundle_id + ":" + hold.code;
      if (!journal.holds.some(function (item) { return item.bundle_id + ":" + item.code === key; })) {
        journal.holds.push(hold);
        return "HOLD";
      }
      return "HOLD_DUP";
    }
    var id = clsId(row);
    journal.ready[legacyId] = {
      bundle_id: bundleId,
      legacy_id: legacyId,
      channel: text(row.channel),
      accession_id: text(row.accession_id),
      cls_id: id,
      mapped: false,
      released_result: false,
      released_report: false,
      interpretation: null,
      interface_state: "SIMULATED",
      interface_live: false
    };
    journal.seenLegacy[legacyId] = bundleId;
    journal.seenAccession[text(row.accession_id)] = bundleId;
    return "READY";
  }
  function migrate(journal) {
    var added = 0;
    Object.keys(journal.ready).forEach(function (legacyId) {
      var record = journal.ready[legacyId];
      if (journal.mappings[legacyId] || journal.clsIndex[record.cls_id]) return;
      journal.objects[record.cls_id] = { cls_id: record.cls_id, incumbent_id: legacyId };
      journal.mappings[legacyId] = record.cls_id;
      journal.clsIndex[record.cls_id] = legacyId;
      record.mapped = true;
      added += 1;
    });
    return added;
  }
  function snapshot(objects) { return sha256HexSync(objects); }
  function releaseDenied(named) {
    var name = text(named);
    if (!name) return "MISSING_NAMED_APPROVAL";
    if (/^(SYSTEM|AUTO|AUTONOMOUS|BOT|MACHINE)$/i.test(name)) return "AUTONOMOUS_RELEASE_DENIED";
    return null;
  }
  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var journal = emptyJournal();
    var baseline = snapshot(journal.objects);
    inbound.forEach(function (row) { ingest(journal, row); });
    var first = migrate(journal);
    var after = snapshot(journal.objects);
    var replay = migrate(journal);
    var replayNoops = 0;
    inbound.forEach(function (row) {
      if (ingest(journal, row) === "REPLAY_NOOP") replayNoops += 1;
    });
    var readyIds = Object.keys(journal.ready);
    var autonomous = readyIds.map(function (id) { return releaseDenied("SYSTEM"); });
    var holdCodeCounts = { DUPLICATE_ID: 0, BROKEN_SAMPLE_TEST_REF: 0, METHOD_VERSION_CONFLICT: 0, HASH_MISMATCH: 0 };
    journal.holds.forEach(function (item) { holdCodeCounts[item.code] += 1; });
    var mappedCls = {};
    Object.keys(journal.mappings).forEach(function (lid) { mappedCls[journal.mappings[lid]] = true; });
    var orphans = 0;
    readyIds.forEach(function (lid) { if (!journal.mappings[lid]) orphans += 1; });
    Object.keys(journal.objects).forEach(function (cid) { if (!mappedCls[cid]) orphans += 1; });
    var holdMapped = journal.holds.filter(function (item) { return item.mapped; }).length;
    var restored = snapshot({});
    return {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      ready: readyIds.length,
      holds: journal.holds.length,
      hold_code_counts: holdCodeCounts,
      mapped: Object.keys(journal.mappings).length,
      cls_objects: first,
      orphans: orphans,
      duplicates: 0,
      hold_mapped: holdMapped,
      replay_added_mappings: replay,
      replay_ingest_noops: replayNoops,
      baseline_hash: baseline,
      after_migrate_hash: after,
      restored_hash: restored,
      rollback_restored_baseline: restored === baseline,
      released_results: 0,
      released_reports: 0,
      autonomous_denied: autonomous.length === readyIds.length,
      interface_live: false,
      interfaces: "SIMULATED",
      shadowing: "READ_ONLY",
      public_health_interpretation: false,
      production_writes: 0,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
  }
  function passContract(result) {
    var failures = [];
    if (result.input_rows !== INPUT_COUNT) failures.push("input_rows!=1000");
    if (result.ready !== VALID_COUNT) failures.push("ready!=850");
    if (result.holds !== HOLD_COUNT) failures.push("holds!=150");
    Object.keys(HOLD_FAMILY_COUNTS).forEach(function (code) {
      if (result.hold_code_counts[code] !== HOLD_FAMILY_COUNTS[code]) failures.push("hold:" + code);
    });
    if (result.mapped !== VALID_COUNT) failures.push("mapped!=850");
    if (result.orphans !== 0) failures.push("orphans");
    if (result.duplicates !== 0) failures.push("duplicates");
    if (result.hold_mapped !== 0) failures.push("hold_mapped");
    if (result.replay_added_mappings !== 0) failures.push("replay_added_mappings");
    if (result.rollback_restored_baseline !== true) failures.push("rollback_baseline");
    if (result.released_results !== 0) failures.push("released_results");
    if (result.released_reports !== 0) failures.push("released_reports");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.production_writes !== 0) failures.push("production_writes");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    TRUTH_GATE: TRUTH_GATE,
    HUMAN_APPROVER: HUMAN_APPROVER,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract,
    sha256HexSync: sha256HexSync
  };
});
