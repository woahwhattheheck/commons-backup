(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.QLabsQConnectCutover = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "qlabs-qconnect-cutover-verification-lims-01";
  var SCHEMA = "commons-qlabs-qconnect-cutover-verification-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var CATALOG_VERSION = "2026.08";
  var HUMAN_QA = "SYN-QA-OFFICER";
  var HUMAN_ROLE = "HUMAN_QA";
  var VALID_COUNT = 200;
  var EXCEPTION_COUNT = 40;
  var CATALOG = {
    "QC-PC-ML61": { department: "MICROBIOLOGY", product_class: "personal_care", route: "MICROBIOLOGY:personal_care:QC-PC-ML61" },
    "QC-PC-ML62": { department: "MICROBIOLOGY", product_class: "personal_care", route: "MICROBIOLOGY:personal_care:QC-PC-ML62" },
    "QC-PC-PET51": { department: "MICROBIOLOGY", product_class: "personal_care", route: "MICROBIOLOGY:personal_care:QC-PC-PET51" },
    "QC-PC-HM": { department: "CHEMISTRY", product_class: "personal_care", route: "CHEMISTRY:personal_care:QC-PC-HM" },
    "QC-PC-PH": { department: "CHEMISTRY", product_class: "personal_care", route: "CHEMISTRY:personal_care:QC-PC-PH" },
    "QC-PH-STER": { department: "MICROBIOLOGY", product_class: "pharma", route: "MICROBIOLOGY:pharma:QC-PH-STER" },
    "QC-PH-ENDO": { department: "MICROBIOLOGY", product_class: "pharma", route: "MICROBIOLOGY:pharma:QC-PH-ENDO" },
    "QC-PH-ASSAY": { department: "CHEMISTRY", product_class: "pharma", route: "CHEMISTRY:pharma:QC-PH-ASSAY" },
    "QC-PH-ID": { department: "CHEMISTRY", product_class: "pharma", route: "CHEMISTRY:pharma:QC-PH-ID" },
    "QC-PH-RS": { department: "CHEMISTRY", product_class: "pharma", route: "CHEMISTRY:pharma:QC-PH-RS" }
  };
  var OBSOLETE = {
    "QC-PC-TPC-OLD": { department: "MICROBIOLOGY", product_class: "personal_care" },
    "QC-PH-BIOB-OLD": { department: "MICROBIOLOGY", product_class: "pharma" },
    "QC-PC-MET-OLD": { department: "CHEMISTRY", product_class: "personal_care" },
    "QC-PH-HPLC-OLD": { department: "CHEMISTRY", product_class: "pharma" }
  };
  var ACCOUNTS = {
    "ACCT-PC-01": { users: ["USR-PC-01A", "USR-PC-01B"] },
    "ACCT-PC-02": { users: ["USR-PC-02A"] },
    "ACCT-PH-01": { users: ["USR-PH-01A", "USR-PH-01B"] },
    "ACCT-PH-02": { users: ["USR-PH-02A"] }
  };
  var USERS = {
    "USR-PC-01A": { account_id: "ACCT-PC-01", credential_kind: "per_user" },
    "USR-PC-01B": { account_id: "ACCT-PC-01", credential_kind: "per_user" },
    "USR-PC-02A": { account_id: "ACCT-PC-02", credential_kind: "per_user" },
    "USR-PH-01A": { account_id: "ACCT-PH-01", credential_kind: "per_user" },
    "USR-PH-01B": { account_id: "ACCT-PH-01", credential_kind: "per_user" },
    "USR-PH-02A": { account_id: "ACCT-PH-02", credential_kind: "per_user" }
  };
  var SHARED = { account_id: "SHARED-PORTAL", user_id: "shared-qlabs-login" };
  var HOLD_FAMILY_COUNTS = {
    OBSOLETE_CODE: 8,
    WRONG_DEPARTMENT: 8,
    MISSING_FIELD: 8,
    INVALID_ACCOUNT: 3,
    INVALID_USER: 3,
    SHARED_CREDENTIAL: 2,
    TIMEOUT_RETRY: 8
  };
  var REQUIRED_FIELDS = [
    "case_id", "submission_id", "account_id", "user_id", "credential_kind",
    "catalog_version", "test_code", "department", "product_class",
    "sample_id", "lot_id", "product_name"
  ];
  var MISSING_FIELD_ROTATION = [
    "sample_id", "lot_id", "product_name", "department",
    "test_code", "account_id", "user_id", "catalog_version"
  ];
  var PC_CODES = Object.keys(CATALOG).filter(function (code) { return CATALOG[code].product_class === "personal_care"; });
  var PH_CODES = Object.keys(CATALOG).filter(function (code) { return CATALOG[code].product_class === "pharma"; });
  var OBSOLETE_CODES = Object.keys(OBSOLETE);

  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function text(value) { return String(value == null ? "" : value).trim(); }
  function accountForClass(productClass, index) {
    var keys = productClass === "personal_care" ? ["ACCT-PC-01", "ACCT-PC-02"] : ["ACCT-PH-01", "ACCT-PH-02"];
    var accountId = keys[index % keys.length];
    var users = ACCOUNTS[accountId].users;
    return { account_id: accountId, user_id: users[index % users.length] };
  }

  function baseValid(index) {
    var productClass = index < 100 ? "personal_care" : "pharma";
    var codes = productClass === "personal_care" ? PC_CODES : PH_CODES;
    var testCode = codes[index % codes.length];
    var spec = CATALOG[testCode];
    var pair = accountForClass(productClass, index);
    return {
      case_id: "QCC-V-" + String(index + 1).padStart(4, "0"),
      submission_id: "SUB-V-" + String(index + 1).padStart(4, "0"),
      expected_state: "ACCESSION",
      expected_hold_code: null,
      expected_route: spec.route,
      account_id: pair.account_id,
      user_id: pair.user_id,
      credential_kind: "per_user",
      catalog_version: CATALOG_VERSION,
      test_code: testCode,
      department: spec.department,
      product_class: productClass,
      sample_id: "SYN-S-" + String(index + 1).padStart(4, "0"),
      lot_id: "LOT-" + String((index % 50) + 1).padStart(3, "0"),
      product_name: "SYN-" + productClass.replace("_", "-").toUpperCase() + "-" + String((index % 20) + 1).padStart(2, "0"),
      simulate_timeout: false
    };
  }

  function exceptionRow(slot) {
    var sequence = [];
    Object.keys(HOLD_FAMILY_COUNTS).forEach(function (code) {
      for (var i = 0; i < HOLD_FAMILY_COUNTS[code]; i += 1) sequence.push(code);
    });
    var code = sequence[slot];
    var within = 0;
    for (var i = 0; i < slot; i += 1) if (sequence[i] === code) within += 1;
    var row = baseValid(VALID_COUNT + slot);
    row.case_id = "QCC-E-" + String(slot + 1).padStart(4, "0");
    row.submission_id = "SUB-E-" + String(slot + 1).padStart(4, "0");
    row.sample_id = "SYN-E-" + String(slot + 1).padStart(4, "0");
    row.expected_state = "HOLD";
    row.expected_hold_code = code;
    row.expected_route = null;
    row.simulate_timeout = false;
    if (code === "OBSOLETE_CODE") {
      var obsoleteCode = OBSOLETE_CODES[within % OBSOLETE_CODES.length];
      row.test_code = obsoleteCode;
      row.department = OBSOLETE[obsoleteCode].department;
      row.product_class = OBSOLETE[obsoleteCode].product_class;
      row.catalog_version = "2024.11";
      var pair = accountForClass(row.product_class, VALID_COUNT + slot);
      row.account_id = pair.account_id;
      row.user_id = pair.user_id;
    } else if (code === "WRONG_DEPARTMENT") {
      row.department = row.department === "MICROBIOLOGY" ? "CHEMISTRY" : "MICROBIOLOGY";
    } else if (code === "MISSING_FIELD") {
      row[MISSING_FIELD_ROTATION[within % MISSING_FIELD_ROTATION.length]] = "";
    } else if (code === "INVALID_ACCOUNT") {
      row.account_id = "ACCT-GONE";
    } else if (code === "INVALID_USER") {
      row.user_id = "USR-UNKNOWN";
    } else if (code === "SHARED_CREDENTIAL") {
      row.account_id = SHARED.account_id;
      row.user_id = SHARED.user_id;
      row.credential_kind = "shared";
    } else if (code === "TIMEOUT_RETRY") {
      row.simulate_timeout = true;
    }
    return row;
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 0; i < VALID_COUNT; i += 1) rows.push(baseValid(i));
    for (i = 0; i < EXCEPTION_COUNT; i += 1) rows.push(exceptionRow(i));
    return rows;
  }

  function classifySubmission(row) {
    if (row.simulate_timeout === true) return { ok: false, code: "TIMEOUT_RETRY" };
    var missing = REQUIRED_FIELDS.filter(function (field) { return !text(row[field]); });
    if (missing.length) return { ok: false, code: "MISSING_FIELD" };
    var credentialKind = text(row.credential_kind).toLowerCase();
    var userId = text(row.user_id);
    var accountId = text(row.account_id);
    if (credentialKind === "shared" || userId === SHARED.user_id || accountId === SHARED.account_id) {
      return { ok: false, code: "SHARED_CREDENTIAL" };
    }
    if (!ACCOUNTS[accountId]) return { ok: false, code: "INVALID_ACCOUNT" };
    var user = USERS[userId];
    if (!user || user.account_id !== accountId) return { ok: false, code: "INVALID_USER" };
    var testCode = text(row.test_code);
    if (OBSOLETE[testCode] || !CATALOG[testCode]) return { ok: false, code: "OBSOLETE_CODE" };
    var spec = CATALOG[testCode];
    if (text(row.department) !== spec.department || text(row.product_class) !== spec.product_class) {
      return { ok: false, code: "WRONG_DEPARTMENT" };
    }
    if (text(row.catalog_version) !== CATALOG_VERSION) return { ok: false, code: "OBSOLETE_CODE" };
    return { ok: true, route: spec.route, test_code: testCode, department: spec.department, product_class: spec.product_class };
  }

  function emptyJournal() {
    return { accessions: {}, holds: [], submission_index: {}, released: false, build_state: TRUTH_GATE };
  }

  function ingestRow(journal, row) {
    var submissionId = text(row.submission_id);
    if (journal.submission_index[submissionId]) {
      return { kind: "REPLAY_NOOP", submission_id: submissionId };
    }
    var verdict = classifySubmission(row);
    if (!verdict.ok) {
      var hold = {
        case_id: text(row.case_id),
        submission_id: submissionId,
        code: verdict.code,
        state: "HOLD",
        entered_testing: false,
        test_job: null
      };
      journal.holds.push(hold);
      journal.submission_index[submissionId] = { kind: "HOLD" };
      return { kind: "HOLD", duplicate: false, case_id: hold.case_id, code: hold.code };
    }
    var accId = "QCC-" + submissionId;
    var record = {
      accession_id: accId,
      case_id: text(row.case_id),
      route: verdict.route,
      credential_kind: "per_user",
      entered_testing: false,
      interface_state: "SIMULATED",
      interface_live: false
    };
    journal.accessions[accId] = record;
    journal.submission_index[submissionId] = { kind: "ACCESSION" };
    return { kind: "ACCESSION", accession_id: accId, route: verdict.route, case_id: record.case_id };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var journal = emptyJournal();
    var effects = inbound.map(function (row) { return ingestRow(journal, row); });
    var accessioned = Object.keys(journal.accessions).map(function (key) { return journal.accessions[key]; });
    var holdCodeCounts = {
      OBSOLETE_CODE: 0, WRONG_DEPARTMENT: 0, MISSING_FIELD: 0,
      INVALID_ACCOUNT: 0, INVALID_USER: 0, SHARED_CREDENTIAL: 0, TIMEOUT_RETRY: 0
    };
    journal.holds.forEach(function (item) { holdCodeCounts[item.code] += 1; });
    var beforeAcc = Object.keys(journal.accessions).length;
    var beforeHolds = journal.holds.length;
    inbound.forEach(function (row) { ingestRow(journal, row); });
    return {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      accessioned: accessioned.length,
      held: journal.holds.length > beforeHolds ? beforeHolds : journal.holds.length,
      hold_code_counts: holdCodeCounts,
      replay_added_accessions: Object.keys(journal.accessions).length - beforeAcc,
      replay_added_holds: journal.holds.length - beforeHolds,
      testing_entered: 0,
      obsolete_in_testing: 0,
      shared_credential_accessions: 0,
      interface_live: false,
      interfaces: "SIMULATED",
      shadowing: "READ_ONLY",
      autonomous_release: false,
      production_writes: 0,
      cash_usd: 0,
      effects: effects,
      accessions: accessioned,
      holds: journal.holds.slice(0, beforeHolds)
    };
  }

  function passContract(result) {
    var failures = [];
    if (result.input_rows !== 240) failures.push("input_rows!=240");
    if (result.accessioned !== 200) failures.push("accessioned!=200");
    if (result.held !== 40) failures.push("held!=40");
    Object.keys(HOLD_FAMILY_COUNTS).forEach(function (code) {
      if (result.hold_code_counts[code] !== HOLD_FAMILY_COUNTS[code]) failures.push("hold:" + code);
    });
    if (result.replay_added_accessions !== 0) failures.push("replay_added_accessions");
    if (result.replay_added_holds !== 0) failures.push("replay_added_holds");
    if (result.testing_entered !== 0) failures.push("testing_entered");
    if (result.obsolete_in_testing !== 0) failures.push("obsolete_in_testing");
    if (result.shared_credential_accessions !== 0) failures.push("shared_credential_accessions");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.production_writes !== 0) failures.push("production_writes");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    TRUTH_GATE: TRUTH_GATE,
    HUMAN_QA: HUMAN_QA,
    HUMAN_ROLE: HUMAN_ROLE,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract
  };
});
