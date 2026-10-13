(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AitMnMetrcCapacityGate = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "ait-mn-metrc-capacity-gate-lims-01";
  var SCHEMA = "commons-ait-mn-metrc-capacity-gate-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var ADAPTER_MODE = "READ_ONLY";
  var VALID_COMPLIANCE = 80;
  var VALID_RND = 20;
  var INVALID_LICENSE = 8;
  var DUPLICATE_IDS = 6;
  var DESIGNATION_MISMATCH = 6;
  var HOLD_CODES = ["INVALID_OR_MISSING_LICENSE", "DUPLICATE_PACKAGE_OR_SAMPLE", "DESIGNATION_MISMATCH"];

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
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
  function pkg(prefix, n) { return "1A40MNSYN" + prefix + pad(n, 7); }
  function sample(prefix, n) { return "AIT-S-" + prefix + "-" + pad(n, 4); }
  function order(prefix, n) { return "QB-" + prefix + "-" + pad(n, 4); }
  function phys(prefix, n) { return "AIT-A-" + prefix + "-" + pad(n, 4); }
  function validLicense(n) { return "MN-LIC-" + pad(n, 4); }

  function row(rowId, kind, designation, n, prefix, license, extras) {
    extras = extras || {};
    var packageId = extras.package_id || pkg(prefix, n);
    var sampleId = extras.sample_id || sample(prefix, n);
    return {
      row_id: rowId,
      kind: kind,
      qbench: {
        order_id: order(prefix, n),
        sample_id: sampleId,
        package_id: packageId,
        designation: extras.qbench_designation || designation,
        license_number: license,
        lab: "AIT-MN-SYN"
      },
      metrc: {
        package_id: packageId,
        sample_id: sampleId,
        designation: extras.metrc_designation || designation,
        license_number: license,
        state: "MN",
        monitoring: "STATE_READ_ONLY"
      },
      physical: {
        accession_id: phys(prefix, n),
        sample_id: sampleId,
        package_id: packageId,
        designation: extras.physical_designation || designation,
        received: true
      }
    };
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= VALID_COMPLIANCE; i += 1) {
      rows.push(row("C" + pad(i, 3), "VALID_COMPLIANCE", "COMPLIANCE", i, "C", validLicense(i)));
    }
    for (i = 1; i <= VALID_RND; i += 1) {
      rows.push(row("R" + pad(i, 3), "VALID_RND", "R_AND_D", i, "R", ""));
    }
    for (i = 1; i <= 4; i += 1) {
      rows.push(row("L" + pad(i, 3), "MISSING_LICENSE", "COMPLIANCE", i, "L", ""));
    }
    for (i = 5; i <= INVALID_LICENSE; i += 1) {
      rows.push(row("L" + pad(i, 3), "INVALID_LICENSE", "COMPLIANCE", i, "L", "XX-VOID-" + pad(i, 4)));
    }
    for (i = 1; i <= DUPLICATE_IDS; i += 1) {
      rows.push(row("D" + pad(i, 3), "DUPLICATE", "COMPLIANCE", 900 + i, "D", validLicense(i), {
        package_id: rows[i - 1].metrc.package_id,
        sample_id: rows[i - 1].physical.sample_id
      }));
    }
    for (i = 1; i <= DESIGNATION_MISMATCH; i += 1) {
      rows.push(row("M" + pad(i, 3), "DESIGNATION_MISMATCH", "COMPLIANCE", i, "M", validLicense(i), {
        qbench_designation: "COMPLIANCE",
        metrc_designation: i % 2 ? "R_AND_D" : "COMPLIANCE",
        physical_designation: i % 2 ? "COMPLIANCE" : "R_AND_D"
      }));
    }
    return rows;
  }

  function pointersOf(row) {
    return {
      qbench: { id: row.qbench.order_id, sha256: sha256HexSync(row.qbench), adapter: "qbench", mode: ADAPTER_MODE },
      metrc: { id: row.metrc.package_id, sha256: sha256HexSync(row.metrc), adapter: "metrc", mode: ADAPTER_MODE },
      physical: { id: row.physical.accession_id, sha256: sha256HexSync(row.physical), adapter: "physical", mode: ADAPTER_MODE }
    };
  }

  function licenseOk(number, designation) {
    if (designation === "R_AND_D") return true;
    return /^MN-LIC-(000[1-9]|00[1-7][0-9]|0080)$/.test(number);
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var holds = [];
    var seenPkg = {};
    var seenSample = {};
    var complianceIds = [];
    var rndIds = [];
    inbound.forEach(function (item) {
      var qb = item.qbench;
      var mt = item.metrc;
      var ph = item.physical;
      var designations = {};
      designations[qb.designation] = true;
      designations[mt.designation] = true;
      designations[ph.designation] = true;
      var keys = Object.keys(designations);
      var pointers = pointersOf(item);
      var provenance = sha256HexSync(pointers);
      var packageId = text(mt.package_id || qb.package_id);
      var sampleId = text(ph.sample_id || qb.sample_id);
      var license = text(qb.license_number || mt.license_number);
      var holdBase = {
        row_id: text(item.row_id),
        package_id: packageId,
        sample_id: sampleId,
        license_number: license || null,
        source_pointers: pointers,
        provenance_sha256: provenance,
        queue: "hold",
        state: "HOLD"
      };
      if (keys.length !== 1 || (keys[0] !== "COMPLIANCE" && keys[0] !== "R_AND_D")) {
        holds.push(Object.assign({ code: "DESIGNATION_MISMATCH", designation: null }, holdBase));
        return;
      }
      var designation = keys[0];
      if (!licenseOk(license, designation)) {
        holds.push(Object.assign({ code: "INVALID_OR_MISSING_LICENSE", designation: designation }, holdBase));
        return;
      }
      if (seenPkg[packageId] || seenSample[sampleId]) {
        holds.push(Object.assign({ code: "DUPLICATE_PACKAGE_OR_SAMPLE", designation: designation }, holdBase));
        return;
      }
      var accId = "AIT-" + sha256HexSync({
        demand_id: DEMAND_ID,
        package_id: packageId,
        sample_id: sampleId,
        designation: designation
      }).slice(0, 12);
      if (accessions[accId]) return;
      var queue = designation === "R_AND_D" ? "rnd" : "compliance";
      accessions[accId] = {
        accession_id: accId,
        row_id: text(item.row_id),
        package_id: packageId,
        sample_id: sampleId,
        designation: designation,
        queue: queue,
        state: "ACCESSIONED",
        staged: false,
        released: false,
        released_by: null,
        coa_released: false,
        source_pointers: pointers,
        provenance_sha256: provenance,
        interface_state: ADAPTER_MODE,
        interface_live: false
      };
      seenPkg[packageId] = true;
      seenSample[sampleId] = true;
      if (queue === "rnd") rndIds.push(accId);
      else complianceIds.push(accId);
    });
    var accessioned = Object.keys(accessions).map(function (id) { return accessions[id]; })
      .sort(function (a, b) { return a.row_id < b.row_id ? -1 : 1; });
    var holdCounts = {};
    HOLD_CODES.forEach(function (code) { holdCounts[code] = 0; });
    holds.forEach(function (item) { holdCounts[item.code] += 1; });
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      accessioned: accessioned.length,
      held: holds.length,
      hold_codes: HOLD_CODES.filter(function (code) { return holdCounts[code] > 0; }),
      hold_code_counts: holdCounts,
      compliance_queue: complianceIds.length,
      rnd_queue: rndIds.length,
      compliance_release_queue: 0,
      rnd_in_compliance_release: 0,
      accession_ids: accessioned.map(function (item) { return item.accession_id; }),
      released_coas: 0,
      accessions: accessioned,
      holds: holds,
      compliance_ids: complianceIds,
      rnd_ids: rndIds,
      interface_live: false,
      interfaces: ADAPTER_MODE,
      metrc_write: false,
      state_write: false,
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
    if (result.input_rows !== 120) failures.push("input_rows!=120");
    if (result.accessioned !== 100) failures.push("accessioned!=100");
    if (result.held !== 20) failures.push("held!=20");
    var counts = result.hold_code_counts || {};
    if (counts.INVALID_OR_MISSING_LICENSE !== 8) failures.push("license_holds!=8");
    if (counts.DUPLICATE_PACKAGE_OR_SAMPLE !== 6) failures.push("duplicate_holds!=6");
    if (counts.DESIGNATION_MISMATCH !== 6) failures.push("mismatch_holds!=6");
    if (result.compliance_queue !== 80) failures.push("compliance_queue!=80");
    if (result.rnd_queue !== 20) failures.push("rnd_queue!=20");
    if (result.compliance_release_queue !== 0) failures.push("compliance_release_queue!=0");
    if (result.rnd_in_compliance_release !== 0) failures.push("rnd_leaked_into_compliance_release");
    if ((result.accession_ids || []).length !== 100) failures.push("accession_ids");
    if (result.released_coas !== 0) failures.push("released_coas!=0");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.metrc_write !== false) failures.push("metrc_write");
    if (result.autonomous_release !== false) failures.push("autonomous_release");
    var rnd = (result.accessions || []).filter(function (item) { return item.designation === "R_AND_D"; });
    if (rnd.length !== 20 || rnd.some(function (item) { return item.queue !== "rnd"; })) failures.push("rnd_not_segregated");
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
