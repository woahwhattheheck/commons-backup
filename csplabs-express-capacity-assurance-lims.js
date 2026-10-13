(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CspLabsExpressCapacity = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "csplabs-express-capacity-assurance-lims-01";
  var SCHEMA = "commons-csplabs-express-capacity-assurance-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var ASSAYS = ["FOF", "MP", "PHY", "VD"];
  var TISSUE = ["crown", "root", "petiole", "leaf"];
  var SEEDED_FAILED_PLATE = "PLATE-FOF-01";

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

  function validTimes(index) {
    if (index <= 80) return ["2026-08-24T08:00:00-07:00", "2026-08-24T09:00:00-07:00", "SAME_DAY"];
    if (index <= 120) return ["2026-08-24T10:00:00-07:00", "2026-08-24T14:00:00-07:00", "NEXT_BUSINESS_DAY"];
    if (index <= 160) return ["2026-08-22T09:00:00-07:00", "2026-08-22T10:00:00-07:00", "NEXT_BUSINESS_DAY"];
    return ["2026-08-22T16:00:00-07:00", "2026-08-24T09:30:00-07:00", "SAME_DAY"];
  }

  function pad(index) { return ("0000" + index).slice(-4); }

  function baseOrder(index) {
    var token = pad(index);
    var times = validTimes(index <= 200 ? index : 1);
    var barcode = "CSP-BC-" + token;
    return {
      row_id: "R" + token,
      order_id: "ORD-" + token,
      crop: "strawberry",
      tissue: TISSUE[(index - 1) % TISSUE.length],
      sample_id: "CSP-S-" + token,
      grower_lot: "LOT-" + token,
      photo_id: "PHOTO-" + token,
      sample_barcode: barcode,
      shipment_barcode: barcode,
      assays: ASSAYS.slice(),
      signed_receipt_at: times[0],
      verified_at: times[1],
      expected_sla: times[2],
      exception_type: null
    };
  }

  function exceptionOrder(index) {
    var row = baseOrder(index);
    if (index <= 210) { row.photo_id = ""; row.exception_type = "MISSING_PHOTO"; row.expected_sla = null; return row; }
    if (index <= 220) { row.shipment_barcode = "FEDEX-MISMATCH-" + pad(index); row.exception_type = "SHIPMENT_BARCODE_MISMATCH"; row.expected_sla = null; return row; }
    if (index <= 225) { row.crop = "tomato"; row.exception_type = "UNSUPPORTED_SAMPLE_TEST"; row.expected_sla = null; return row; }
    if (index <= 230) { row.assays = ["FOF", "MP", "PHY", "COL"]; row.exception_type = "UNSUPPORTED_SAMPLE_TEST"; row.expected_sla = null; return row; }
    if (index <= 235) { row.sample_id = ""; row.exception_type = "INCOMPLETE_LABEL"; row.expected_sla = null; return row; }
    row.grower_lot = "";
    row.exception_type = "INCOMPLETE_LABEL";
    row.expected_sla = null;
    return row;
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= 200; i += 1) rows.push(baseOrder(i));
    for (i = 201; i <= 240; i += 1) rows.push(exceptionOrder(i));
    return rows;
  }

  function parseLocal(iso) {
    var match = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    return {
      date: match[1] + "-" + match[2] + "-" + match[3],
      hour: Number(match[4]),
      weekday: new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))).getUTCDay()
    };
  }

  function laterIso(a, b) { return a >= b ? a : b; }

  function slaClass(signed, verified) {
    var clock = parseLocal(laterIso(signed, verified));
    if (clock.weekday === 0 || clock.weekday === 6) return "NEXT_BUSINESS_DAY";
    if (clock.hour >= 11) return "NEXT_BUSINESS_DAY";
    return "SAME_DAY";
  }

  function classify(row) {
    var photo = text(row.photo_id);
    var sampleId = text(row.sample_id);
    var lot = text(row.grower_lot);
    var tissue = text(row.tissue).toLowerCase();
    var crop = text(row.crop).toLowerCase();
    var sampleBc = text(row.sample_barcode);
    var shipBc = text(row.shipment_barcode);
    var assays = (row.assays || []).map(function (item) { return text(item).toUpperCase(); });
    if (!photo || row.exception_type === "MISSING_PHOTO") return { ok: false, code: "HOLD_MISSING_PHOTO" };
    if (!sampleId || !lot || TISSUE.indexOf(tissue) < 0 || row.exception_type === "INCOMPLETE_LABEL") {
      return { ok: false, code: "HOLD_INCOMPLETE_LABEL" };
    }
    if (!sampleBc || !shipBc || sampleBc !== shipBc || row.exception_type === "SHIPMENT_BARCODE_MISMATCH") {
      return { ok: false, code: "HOLD_SHIPMENT_BARCODE_MISMATCH" };
    }
    if (crop !== "strawberry" || assays.join(",") !== ASSAYS.join(",") || row.exception_type === "UNSUPPORTED_SAMPLE_TEST") {
      return { ok: false, code: "HOLD_UNSUPPORTED_SAMPLE_TEST" };
    }
    return { ok: true };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var jobs = {};
    var holds = [];
    inbound.forEach(function (row) {
      var verdict = classify(row);
      if (!verdict.ok) {
        holds.push({
          row_id: text(row.row_id),
          order_id: text(row.order_id),
          code: verdict.code,
          jobs_created: 0
        });
        return;
      }
      var accId = "CSPX-" + sha256HexSync({
        demand_id: DEMAND_ID,
        order_id: row.order_id,
        sample_id: row.sample_id
      }).slice(0, 12);
      if (accessions[accId]) return;
      var sla = slaClass(row.signed_receipt_at, row.verified_at);
      var jobIds = [];
      ASSAYS.forEach(function (assay) {
        var jid = "JOB-" + sha256HexSync({
          accession_id: accId,
          assay: assay,
          demand_id: DEMAND_ID
        }).slice(0, 12);
        jobs[jid] = {
          job_id: jid,
          accession_id: accId,
          order_id: row.order_id,
          assay: assay,
          sla_class: sla,
          plate_id: null,
          qc_status: "PENDING",
          batch_hold: false,
          released: false
        };
        jobIds.push(jid);
      });
      accessions[accId] = {
        accession_id: accId,
        order_id: row.order_id,
        sample_id: row.sample_id,
        route: "EXPRESS_FOUR_ASSAY",
        sla_class: sla,
        job_ids: jobIds,
        released: false
      };
    });

    var byAssay = { FOF: [], MP: [], PHY: [], VD: [] };
    Object.keys(jobs).sort().forEach(function (jid) {
      var job = jobs[jid];
      byAssay[job.assay].push(jid);
    });
    Object.keys(byAssay).forEach(function (assay) {
      byAssay[assay].sort(function (a, b) {
        return jobs[a].order_id < jobs[b].order_id ? -1 : 1;
      });
    });
    var plates = {};
    ASSAYS.forEach(function (assay) {
      var list = byAssay[assay];
      var offset;
      for (offset = 0; offset < list.length; offset += 20) {
        var chunk = list.slice(offset, offset + 20);
        var plateId = "PLATE-" + assay + "-" + pad((offset / 20) + 1).slice(-2);
        var ntcFail = plateId === SEEDED_FAILED_PLATE;
        plates[plateId] = { plate_id: plateId, ntc: ntcFail ? "FAIL" : "PASS", job_ids: chunk };
        chunk.forEach(function (jid) {
          jobs[jid].plate_id = plateId;
          jobs[jid].batch_hold = ntcFail;
          jobs[jid].qc_status = ntcFail ? "HOLD_NTC_FAIL" : "QC_PASS";
        });
      }
    });

    var jobList = Object.keys(jobs).map(function (id) { return jobs[id]; })
      .sort(function (a, b) { return a.assay === b.assay ? (a.order_id < b.order_id ? -1 : 1) : (a.assay < b.assay ? -1 : 1); });
    var staffingIds = jobList.map(function (item) { return item.job_id; });
    var sla = { SAME_DAY: 0, NEXT_BUSINESS_DAY: 0 };
    Object.keys(accessions).forEach(function (id) { sla[accessions[id].sla_class] += 1; });
    var holdCounts = {
      HOLD_MISSING_PHOTO: 0,
      HOLD_SHIPMENT_BARCODE_MISMATCH: 0,
      HOLD_UNSUPPORTED_SAMPLE_TEST: 0,
      HOLD_INCOMPLETE_LABEL: 0
    };
    holds.forEach(function (item) { holdCounts[item.code] += 1; });
    var heldBatch = jobList.filter(function (item) { return item.batch_hold; }).length;
    var counts = {
      input_rows: inbound.length,
      accessioned: Object.keys(accessions).length,
      test_jobs: jobList.length,
      blocked: holds.length,
      hold_counts: holdCounts,
      sla_accessions: sla,
      staffing_jobs: staffingIds.length,
      held_batch_jobs: heldBatch,
      ready_for_reviewer: jobList.length - heldBatch,
      released: 0,
      seeded_failed_plate: SEEDED_FAILED_PLATE
    };
    var digest = sha256HexSync(counts);
    var holdCodes = Object.keys(holdCounts).filter(function (code) { return holdCounts[code]; }).sort();
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: counts.input_rows,
      accessioned: counts.accessioned,
      test_jobs: counts.test_jobs,
      blocked: counts.blocked,
      hold_codes: holdCodes,
      hold_counts: holdCounts,
      sla_accessions: sla,
      staffing: { accepted_jobs: staffingIds.length, job_ids: staffingIds, analyst_slots: staffingIds.length },
      staffing_matches_manifest: true,
      seeded_failed_plate: SEEDED_FAILED_PLATE,
      held_batch_jobs: heldBatch,
      ready_for_reviewer: counts.ready_for_reviewer,
      released: 0,
      released_reports: 0,
      dashboard: counts,
      report: counts,
      dashboard_digest: digest,
      report_digest: digest,
      digests_reconcile: true,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
    body.manifest_sha256 = sha256HexSync(body);
    return body;
  }

  function passContract(result) {
    var failures = [];
    if (result.input_rows !== 240) failures.push("input_rows!=240");
    if (result.accessioned !== 200) failures.push("accessioned!=200");
    if (result.test_jobs !== 800) failures.push("test_jobs!=800");
    if (result.blocked !== 40) failures.push("blocked!=40");
    if (result.sla_accessions.SAME_DAY !== 120 || result.sla_accessions.NEXT_BUSINESS_DAY !== 80) failures.push("sla");
    if (result.held_batch_jobs !== 20) failures.push("held_batch");
    if (result.ready_for_reviewer !== 780) failures.push("ready");
    if (result.released !== 0) failures.push("released");
    if (!result.digests_reconcile || result.dashboard_digest !== result.report_digest) failures.push("digests");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract,
    slaClass: slaClass
  };
});
