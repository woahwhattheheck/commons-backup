(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.RoseCityOlccMetrcSampling = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "rosecity-olcc-metrc-sampling-lims-01";
  var SCHEMA = "commons-rosecity-olcc-metrc-sampling-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var BUYER = "Rose City Laboratories / Chris Griffey";
  var DUP_PACKAGE_ID = "1A4FF0000000000000DUP1";

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function flag(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    return /^(1|true|yes|y)$/i.test(String(value).trim());
  }
  function asInt(value, fallback) {
    var n = parseInt(value, 10);
    return Number.isFinite(n) ? n : (fallback || 0);
  }
  function packageIds(value) {
    if (value == null) return [];
    if (typeof value === "string") return text(value) ? [text(value)] : [];
    var out = [];
    for (var i = 0; i < value.length; i += 1) {
      var item = text(value[i]);
      if (item) out.push(item);
    }
    return out;
  }
  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }
  function pkg(tag, n) {
    return "1A4FF00000000000" + tag + pad(n, 4);
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
  function idFor(kind, requestId, extra) {
    var body = { demand_id: DEMAND_ID, kind: kind, request_id: requestId };
    if (extra) Object.keys(extra).forEach(function (key) { body[key] = extra[key]; });
    var prefix = kind === "dispatch" ? "DSP-" : kind === "custody" ? "CUS-" : kind === "pickup" ? "PCK-" : "ACC-";
    return prefix + sha256HexSync(body).slice(0, 12);
  }

  function row(n, spec) {
    var requestId = "RCL-" + pad(n, 3);
    var email = "results+" + pad(n, 3) + "@rosecity.example.test";
    var webPackages = spec.package_ids.slice();
    var metrcPackages = spec.package_ids.slice();
    if (spec.defect === "BATCH_COUNT_MISMATCH") {
      metrcPackages = webPackages.slice(0, 1);
    }
    var record = {
      row_id: "R" + pad(n, 3),
      request_id: requestId,
      web_request: {
        submitted_at: "2026-08-31T12:" + pad(n % 60, 2) + ":00Z",
        client_license: "060-100" + pad(n, 4),
        batch_count: spec.request_batch,
        package_ids: webPackages,
        result_email: email
      },
      appointment: {
        confirmed: spec.confirmed,
        scheduled_at: "2026-08-31T14:" + pad(n % 60, 2) + ":00Z",
        batch_count: spec.request_batch
      },
      metrc_transfer: null,
      defect: spec.defect || null
    };
    if (spec.metrc) {
      record.metrc_transfer = {
        transfer_id: "TR-" + pad(n, 3),
        package_ids: metrcPackages,
        batch_count: spec.metrc_batch,
        adapter: "READ_ONLY"
      };
    }
    return record;
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var n;
    for (n = 1; n <= 75; n += 1) {
      var batch = n % 5 === 0 ? 2 : 1;
      var packages = [pkg("C", n)];
      if (batch === 2) packages.push(pkg("D", n));
      rows.push(row(n, {
        confirmed: true,
        metrc: true,
        request_batch: batch,
        metrc_batch: batch,
        package_ids: packages,
        defect: null
      }));
    }
    for (n = 76; n <= 83; n += 1) {
      rows.push(row(n, {
        confirmed: true,
        metrc: false,
        request_batch: 1,
        metrc_batch: null,
        package_ids: [pkg("M", n)],
        defect: "MISSING_METRC_TRANSFER"
      }));
    }
    for (n = 84; n <= 90; n += 1) {
      rows.push(row(n, {
        confirmed: true,
        metrc: true,
        request_batch: 2,
        metrc_batch: 1,
        package_ids: [pkg("B", n), pkg("E", n)],
        defect: "BATCH_COUNT_MISMATCH"
      }));
    }
    for (n = 91; n <= 95; n += 1) {
      rows.push(row(n, {
        confirmed: true,
        metrc: true,
        request_batch: 1,
        metrc_batch: 1,
        package_ids: [DUP_PACKAGE_ID],
        defect: "DUPLICATE_PACKAGE_ID"
      }));
    }
    for (n = 96; n <= 100; n += 1) {
      rows.push(row(n, {
        confirmed: true === false,
        metrc: true,
        request_batch: 1,
        metrc_batch: 1,
        package_ids: [pkg("U", n)],
        defect: "UNCONFIRMED_APPOINTMENT"
      }));
    }
    return rows;
  }

  function packageFrequency(rows) {
    var counts = {};
    rows.forEach(function (item) {
      var packages = packageIds((item.web_request || {}).package_ids);
      var seen = {};
      packages.forEach(function (pkgId) {
        if (seen[pkgId]) counts[pkgId] = (counts[pkgId] || 0) + 1;
        seen[pkgId] = true;
      });
      Object.keys(seen).forEach(function (pkgId) {
        counts[pkgId] = (counts[pkgId] || 0) + 1;
      });
    });
    return counts;
  }

  function classifyRequest(item, packageCounts) {
    var requestId = text(item.request_id);
    var web = item.web_request || {};
    var appointment = item.appointment || {};
    var transfer = item.metrc_transfer;
    var packages = packageIds(web.package_ids);
    var requestBatch = asInt(web.batch_count);
    var apptBatch = asInt(appointment.batch_count, requestBatch);
    var confirmed = flag(appointment.confirmed);
    var email = text(web.result_email);
    var base = {
      request_id: requestId,
      package_ids: packages,
      request_batch_count: requestBatch,
      appointment_batch_count: apptBatch,
      appointment_confirmed: confirmed,
      result_email: email || null,
      metrc_transfer_id: transfer ? (text(transfer.transfer_id) || null) : null
    };
    if (!confirmed) return Object.assign({ ok: false, status: "HOLD", code: "UNCONFIRMED_APPOINTMENT" }, base);
    if (!transfer) return Object.assign({ ok: false, status: "HOLD", code: "MISSING_METRC_TRANSFER" }, base);
    var metrcBatch = asInt(transfer.batch_count);
    if (requestBatch !== metrcBatch || apptBatch !== metrcBatch) {
      return Object.assign({ ok: false, status: "HOLD", code: "BATCH_COUNT_MISMATCH", metrc_batch_count: metrcBatch }, base);
    }
    var counts = packageCounts || {};
    var dup = packages.length !== Object.keys(packages.reduce(function (acc, pkgId) { acc[pkgId] = true; return acc; }, {})).length;
    if (dup || packages.some(function (pkgId) { return (counts[pkgId] || 1) > 1; })) {
      return Object.assign({ ok: false, status: "HOLD", code: "DUPLICATE_PACKAGE_ID" }, base);
    }
    return Object.assign({ ok: true, status: "DISPATCH_READY", code: null, metrc_batch_count: metrcBatch }, base);
  }

  function custodyLink(seq, kind, ref, payload, prev) {
    var body = { kind: kind, payload: payload, prev: prev, ref: ref, seq: seq };
    return Object.assign({}, body, { hash: sha256HexSync(body) });
  }

  function buildCustodyChain(item, verdict) {
    var requestId = verdict.request_id;
    var packages = verdict.package_ids.slice();
    var accId = idFor("accession", requestId, { package_ids: packages });
    var pckId = idFor("pickup", requestId);
    var cusId = idFor("custody", requestId);
    var transfer = item.metrc_transfer || {};
    var web = item.web_request || {};
    var appointment = item.appointment || {};
    var steps = [
      ["WEB_REQUEST", requestId, { batch_count: asInt(web.batch_count), package_ids: packages, submitted_at: text(web.submitted_at) }],
      ["APPOINTMENT", requestId + ":appt", { batch_count: asInt(appointment.batch_count), confirmed: true, scheduled_at: text(appointment.scheduled_at) }],
      ["METRC_TRANSFER", text(transfer.transfer_id), { batch_count: asInt(transfer.batch_count), package_ids: packageIds(transfer.package_ids), transfer_id: text(transfer.transfer_id) }],
      ["FIELD_PICKUP", pckId, { package_ids: packages, pickup_id: pckId }],
      ["ACCESSION", accId, { accession_id: accId, package_ids: packages }]
    ];
    var links = [];
    var prev = null;
    steps.forEach(function (step, idx) {
      var link = custodyLink(idx + 1, step[0], step[1], step[2], prev);
      links.push(link);
      prev = link.hash;
    });
    return {
      accession_id: accId,
      chain_hash: sha256HexSync({ custody_id: cusId, links: links }),
      custody_id: cusId,
      immutable: true,
      links: links,
      pickup_id: pckId,
      request_id: requestId,
      sealed: true
    };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var counts = packageFrequency(inbound);
    var verdicts = {};
    var dispatches = {};
    var custodyChains = {};
    var accessions = {};
    var holds = [];
    inbound.forEach(function (item) {
      var requestId = text(item.request_id);
      if (verdicts[requestId]) return;
      var verdict = classifyRequest(item, counts);
      var destination = verdict.result_email;
      if (!verdict.ok) {
        var hold = {
          request_id: requestId,
          code: verdict.code,
          status: "HOLD",
          dispatch_id: null,
          custody_id: null,
          accession_id: null,
          result_email: destination,
          email_linked: !!destination,
          email_sent: false,
          coa_released: false
        };
        verdicts[requestId] = hold;
        holds.push(hold);
        return;
      }
      var chain = buildCustodyChain(item, verdict);
      var dspId = idFor("dispatch", requestId);
      var accId = chain.accession_id;
      var cusId = chain.custody_id;
      var dispatch = {
        accession_id: accId,
        coa_released: false,
        custody_id: cusId,
        dispatch_id: dspId,
        email_destination: destination,
        email_linked: !!destination,
        email_sent: false,
        package_ids: verdict.package_ids.slice(),
        pickup_id: chain.pickup_id,
        request_id: requestId,
        status: "DISPATCH_READY",
        auto_release: false
      };
      verdicts[requestId] = {
        accession_id: accId,
        code: null,
        coa_released: false,
        custody_id: cusId,
        dispatch_id: dspId,
        email_linked: !!destination,
        email_sent: false,
        result_email: destination,
        request_id: requestId,
        status: "DISPATCH_READY"
      };
      dispatches[dspId] = dispatch;
      custodyChains[cusId] = chain;
      accessions[accId] = {
        accession_id: accId,
        custody_id: cusId,
        dispatch_id: dspId,
        package_ids: verdict.package_ids.slice(),
        request_id: requestId,
        state: "ACCESSIONED"
      };
    });
    var ready = Object.keys(verdicts).map(function (id) { return verdicts[id]; })
      .filter(function (item) { return item.status === "DISPATCH_READY"; });
    var holdRows = Object.keys(verdicts).map(function (id) { return verdicts[id]; })
      .filter(function (item) { return item.status === "HOLD"; });
    var holdCodeCounts = {
      MISSING_METRC_TRANSFER: 0,
      BATCH_COUNT_MISMATCH: 0,
      DUPLICATE_PACKAGE_ID: 0,
      UNCONFIRMED_APPOINTMENT: 0
    };
    holds.forEach(function (item) { holdCodeCounts[item.code] = (holdCodeCounts[item.code] || 0) + 1; });
    var dispatchList = Object.keys(dispatches).map(function (id) { return dispatches[id]; })
      .sort(function (a, b) { return a.request_id < b.request_id ? -1 : 1; });
    var custodyList = Object.keys(custodyChains).map(function (id) { return custodyChains[id]; })
      .sort(function (a, b) { return a.request_id < b.request_id ? -1 : 1; });
    var accessionList = Object.keys(accessions).map(function (id) { return accessions[id]; })
      .sort(function (a, b) { return a.request_id < b.request_id ? -1 : 1; });
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      buyer: BUYER,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      dispatch_ready: ready.length,
      hold: holdRows.length,
      hold_code_counts: holdCodeCounts,
      dispatch_count: dispatchList.length,
      hold_dispatch_count: holdRows.filter(function (item) { return item.dispatch_id; }).length,
      custody_count: custodyList.length,
      accession_count: accessionList.length,
      email_linked: dispatchList.filter(function (item) { return item.email_linked; }).length,
      emails_sent: dispatchList.filter(function (item) { return item.email_sent; }).length,
      coa_released: dispatchList.filter(function (item) { return item.coa_released; }).length,
      email_send_denied: ready.length,
      auto_release_denied: ready.length,
      metrc_write_denied: true,
      custody_immutable: custodyList.every(function (chain) {
        return chain.immutable && chain.sealed && chain.links.length === 5;
      }),
      dispatches: dispatchList,
      holds: holds,
      custody_chains: custodyList,
      accessions: accessionList,
      interface_live: false,
      interfaces: "READ_ONLY_SYNTHETIC",
      metrc_write: false,
      state_write: false,
      automatic_release: false,
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
    if (result.dispatch_ready !== 75) failures.push("dispatch_ready!=75");
    if (result.hold !== 25) failures.push("hold!=25");
    if (result.dispatch_count !== 75) failures.push("dispatch_count!=75");
    if (result.hold_dispatch_count !== 0) failures.push("hold_produced_dispatch");
    if (result.custody_count !== 75) failures.push("custody_count!=75");
    if (result.accession_count !== 75) failures.push("accession_count!=75");
    var expected = {
      MISSING_METRC_TRANSFER: 8,
      BATCH_COUNT_MISMATCH: 7,
      DUPLICATE_PACKAGE_ID: 5,
      UNCONFIRMED_APPOINTMENT: 5
    };
    if (JSON.stringify(result.hold_code_counts) !== JSON.stringify(expected)) failures.push("hold_code_counts");
    if (result.email_linked !== 75) failures.push("email_linked!=75");
    if (result.emails_sent !== 0) failures.push("emails_sent!=0");
    if (result.coa_released !== 0) failures.push("coa_released!=0");
    if (result.metrc_write !== false) failures.push("metrc_write");
    if (result.automatic_release !== false) failures.push("automatic_release");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.custody_immutable !== true) failures.push("custody_not_immutable");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    classifyRequest: classifyRequest,
    packageFrequency: packageFrequency,
    runGate: runGate,
    passContract: passContract,
    sha256HexSync: sha256HexSync
  };
});
