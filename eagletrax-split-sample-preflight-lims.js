(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.EagleTraxSplitSamplePreflight = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "eagletrax-split-sample-preflight-lims-01";
  var SCHEMA = "commons-eagletrax-split-sample-preflight-lims/v1";
  var TRUTH_GATE = "HOLD / BUILD-AND-VERIFY";
  var STALE_BEFORE = "2026-03-01";
  var MIN_VOLUME_ML = { CHEM: 5, MICRO: 5 };
  var VALID_COUNT = 200;
  var HOLD_COUNT = 40;
  var INPUT_COUNT = 240;
  var DISCIPLINES = ["CHEM", "MICRO"];
  var MATRICES = ["cream", "suspension", "solution", "capsule", "sterile_injectable"];
  var PREPARATIONS = [
    "progesterone_cream",
    "thyroid_suspension",
    "estradiol_solution",
    "liothyronine_capsule",
    "sterile_injectable_b12"
  ];
  var HOLD_CODE_COUNTS = {
    ABSENT_WORKBOOK: 8,
    INSUFFICIENT_CONTAINER: 8,
    UNSPLIT_CONTAINER: 8,
    MISSING_HANDLING: 8,
    STALE_CLIENT: 4,
    FORM_CONTAINER_MISMATCH: 4
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
  function pad(n) { return String(n).padStart(3, "0"); }
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
  function testsOf(row) {
    var out = [];
    (row.tests || []).forEach(function (item) {
      var token = text(item).toUpperCase();
      if (DISCIPLINES.indexOf(token) >= 0 && out.indexOf(token) < 0) out.push(token);
    });
    return out;
  }
  function workbookPresent(workbook) {
    return !!(workbook && flag(workbook.present) && text(workbook.formula_id) && text(workbook.batch_record_id));
  }
  function handlingPresent(handling) {
    return !!(handling && flag(handling.present) && text(handling.temperature) && text(handling.special_requirements));
  }
  function isStale(last) {
    var day = text(last).slice(0, 10);
    return !day || day < STALE_BEFORE;
  }
  function containersOf(row) {
    return Array.isArray(row.containers) ? row.containers.filter(function (item) { return item && typeof item === "object"; }) : [];
  }
  function formContainerMismatch(row) {
    var requestId = text(row.request_id);
    var sampleId = text(row.sample_id);
    var matrix = text(row.matrix);
    var tests = testsOf(row);
    var containers = containersOf(row);
    if (!containers.length) return true;
    return containers.some(function (container) {
      return text(container.request_id) !== requestId
        || text(container.sample_id) !== sampleId
        || text(container.matrix) !== matrix
        || tests.indexOf(text(container.discipline).toUpperCase()) < 0;
    });
  }
  function splitOk(row) {
    var tests = testsOf(row);
    if (tests.indexOf("CHEM") < 0 || tests.indexOf("MICRO") < 0) return true;
    var chem = {};
    var micro = {};
    containersOf(row).forEach(function (container) {
      var id = text(container.container_id);
      var disc = text(container.discipline).toUpperCase();
      if (disc === "CHEM" && id) chem[id] = true;
      if (disc === "MICRO" && id) micro[id] = true;
    });
    var chemIds = Object.keys(chem);
    var microIds = Object.keys(micro);
    return chemIds.length === 1 && microIds.length === 1 && chemIds[0] !== microIds[0];
  }
  function insufficient(row) {
    var tests = testsOf(row);
    var volumes = { CHEM: 0, MICRO: 0 };
    containersOf(row).forEach(function (container) {
      var disc = text(container.discipline).toUpperCase();
      if (volumes[disc] != null) volumes[disc] += volume(container.volume_ml);
    });
    return tests.some(function (disc) { return volumes[disc] < MIN_VOLUME_ML[disc]; });
  }
  function parentId(requestId) {
    return "ETX-P-" + sha256HexSync({ demand_id: DEMAND_ID, request_id: requestId, kind: "parent" }).slice(0, 12);
  }
  function childId(requestId, discipline) {
    var prefix = discipline === "CHEM" ? "ETX-C-" : "ETX-M-";
    return prefix + sha256HexSync({
      demand_id: DEMAND_ID,
      request_id: requestId,
      kind: "aliquot",
      discipline: discipline
    }).slice(0, 12);
  }
  function kindForIndex(index) {
    var rem = index % 5;
    if (rem === 0 || rem === 1) return "CHEM_AND_MICRO";
    if (rem === 2 || rem === 3) return "CHEM_ONLY";
    return "MICRO_ONLY";
  }
  function testsForKind(kind) {
    if (kind === "CHEM_AND_MICRO") return ["CHEM", "MICRO"];
    if (kind === "CHEM_ONLY") return ["CHEM"];
    return ["MICRO"];
  }
  function baseRow(index, kind) {
    var tests = testsForKind(kind);
    var requestId = "ETX-REQ-" + pad(index);
    var sampleId = "ETX-S-" + pad(index);
    var matrix = MATRICES[(index - 1) % MATRICES.length];
    var containers = tests.map(function (discipline) {
      return {
        container_id: requestId + "-" + discipline,
        request_id: requestId,
        sample_id: sampleId,
        matrix: matrix,
        discipline: discipline,
        volume_ml: 10,
        dispensing_container: discipline === "MICRO" && matrix === "sterile_injectable"
      };
    });
    return {
      row_id: "R" + pad(index),
      request_id: requestId,
      sample_id: sampleId,
      client_id: "ETX-CL-" + pad((index % 40) + 1),
      matrix: matrix,
      preparation: PREPARATIONS[(index - 1) % PREPARATIONS.length],
      kind: kind,
      tests: tests,
      last_submission_at: "2026-06-15",
      containers: containers,
      workbook: {
        present: tests.indexOf("CHEM") >= 0,
        formula_id: tests.indexOf("CHEM") >= 0 ? "WB-" + pad(index) : "",
        batch_record_id: tests.indexOf("CHEM") >= 0 ? "MBR-" + pad(index) : ""
      },
      handling: {
        present: true,
        temperature: (matrix === "suspension" || matrix === "sterile_injectable") ? "cool_pack" : "ambient",
        special_requirements: index % 2 ? "protect_from_light" : "upright_only"
      },
      expected_state: "ACCESSION",
      expected_hold_code: null,
      expected_children: tests.slice()
    };
  }
  function heldRow(offset, code, kind) {
    var index = VALID_COUNT + offset;
    var row = baseRow(index, kind);
    row.expected_state = "HOLD";
    row.expected_hold_code = code;
    row.expected_children = [];
    if (code === "STALE_CLIENT") row.last_submission_at = "2025-08-01";
    if (code === "FORM_CONTAINER_MISMATCH") row.containers[0].sample_id = "ETX-S-MISMATCH-" + pad(index);
    if (code === "ABSENT_WORKBOOK") row.workbook = { present: false, formula_id: "", batch_record_id: "" };
    if (code === "MISSING_HANDLING") row.handling = { present: false, temperature: "", special_requirements: "" };
    if (code === "UNSPLIT_CONTAINER") {
      var shared = row.request_id + "-SHARED";
      row.containers = ["CHEM", "MICRO"].map(function (discipline) {
        return {
          container_id: shared,
          request_id: row.request_id,
          sample_id: row.sample_id,
          matrix: row.matrix,
          discipline: discipline,
          volume_ml: 10
        };
      });
    }
    if (code === "INSUFFICIENT_CONTAINER") {
      row.containers.forEach(function (container) { container.volume_ml = 1; });
    }
    return row;
  }
  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    for (i = 1; i <= VALID_COUNT; i += 1) rows.push(baseRow(i, kindForIndex(i)));
    var cursor = 1;
    function add(count, code, kind) {
      var n;
      for (n = 0; n < count; n += 1) {
        rows.push(heldRow(cursor, code, kind));
        cursor += 1;
      }
    }
    add(8, "ABSENT_WORKBOOK", "CHEM_ONLY");
    add(8, "INSUFFICIENT_CONTAINER", "CHEM_AND_MICRO");
    add(8, "UNSPLIT_CONTAINER", "CHEM_AND_MICRO");
    add(8, "MISSING_HANDLING", "MICRO_ONLY");
    add(4, "STALE_CLIENT", "CHEM_ONLY");
    add(4, "FORM_CONTAINER_MISMATCH", "CHEM_AND_MICRO");
    return rows;
  }
  function classifySubmission(row) {
    var tests = testsOf(row);
    function hold(code) {
      return {
        ok: false,
        state: "HOLD",
        code: code,
        request_id: text(row.request_id),
        sample_id: text(row.sample_id),
        tests: tests
      };
    }
    if (isStale(row.last_submission_at)) return hold("STALE_CLIENT");
    if (formContainerMismatch(row)) return hold("FORM_CONTAINER_MISMATCH");
    if (tests.indexOf("CHEM") >= 0 && !workbookPresent(row.workbook)) return hold("ABSENT_WORKBOOK");
    if (!handlingPresent(row.handling)) return hold("MISSING_HANDLING");
    if (!splitOk(row)) return hold("UNSPLIT_CONTAINER");
    if (insufficient(row)) return hold("INSUFFICIENT_CONTAINER");
    var children = DISCIPLINES.filter(function (name) { return tests.indexOf(name) >= 0; });
    var childIds = {};
    children.forEach(function (name) { childIds[name] = childId(text(row.request_id), name); });
    return {
      ok: true,
      state: "ACCESSION",
      request_id: text(row.request_id),
      sample_id: text(row.sample_id),
      kind: text(row.kind),
      tests: tests,
      children: children,
      parent_id: parentId(text(row.request_id)),
      child_ids: childIds
    };
  }
  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var accessions = {};
    var children = {};
    var holds = [];
    inbound.forEach(function (row) {
      var verdict = classifySubmission(row);
      if (!verdict.ok) {
        if (holds.some(function (item) { return item.request_id === verdict.request_id; })) return;
        holds.push({
          request_id: verdict.request_id,
          sample_id: verdict.sample_id || null,
          code: verdict.code,
          state: "HOLD"
        });
        return;
      }
      if (accessions[verdict.parent_id]) return;
      accessions[verdict.parent_id] = {
        parent_id: verdict.parent_id,
        request_id: verdict.request_id,
        sample_id: verdict.sample_id,
        kind: verdict.kind,
        tests: verdict.children.slice(),
        expected_children: verdict.children.slice(),
        child_ids: verdict.child_ids,
        report_status: "BLOCKED_MISSING_RESULT",
        released: false,
        interface_state: "SIMULATED",
        interface_live: false
      };
      verdict.children.forEach(function (discipline) {
        var id = verdict.child_ids[discipline];
        children[id] = {
          child_id: id,
          parent_id: verdict.parent_id,
          aliquot_of: verdict.parent_id,
          request_id: verdict.request_id,
          discipline: discipline
        };
      });
    });
    var parents = Object.keys(accessions).map(function (id) { return accessions[id]; })
      .sort(function (a, b) { return a.request_id < b.request_id ? -1 : 1; });
    var childList = Object.keys(children).map(function (id) { return children[id]; })
      .sort(function (a, b) { return a.request_id === b.request_id ? (a.discipline < b.discipline ? -1 : 1) : (a.request_id < b.request_id ? -1 : 1); });
    var parentChildren = {};
    parents.forEach(function (item) { parentChildren[item.request_id] = item.expected_children.slice(); });
    var holdCodeCounts = {};
    Object.keys(HOLD_CODE_COUNTS).forEach(function (code) {
      holdCodeCounts[code] = holds.filter(function (item) { return item.code === code; }).length;
    });
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      truth_gate: TRUTH_GATE,
      input_rows: inbound.length,
      accessioned_parents: parents.length,
      accessioned_children: childList.length,
      held: holds.length,
      hold_code_counts: holdCodeCounts,
      parent_children: parentChildren,
      parent_ids: parents.map(function (item) { return item.parent_id; }),
      child_ids: childList.map(function (item) { return item.child_id; }),
      blocked_reports: parents.length,
      released_reports: 0,
      wrong_child_attached: 0,
      accessions: parents,
      children: childList,
      holds: holds,
      interface_live: false,
      interfaces: "SIMULATED",
      autonomous_release: false,
      production_writes: 0,
      pre_sale_transport: "NONE",
      cash_usd: 0
    };
    body.audit_sha256 = sha256HexSync({
      demand_id: body.demand_id,
      input_rows: body.input_rows,
      accessioned_parents: body.accessioned_parents,
      accessioned_children: body.accessioned_children,
      held: body.held,
      hold_code_counts: body.hold_code_counts
    });
    return body;
  }
  function passContract(result) {
    var failures = [];
    var rows = buildAcceptanceFixture();
    var expectedChildren = rows.reduce(function (sum, row) { return sum + (row.expected_children || []).length; }, 0);
    if (result.input_rows !== INPUT_COUNT) failures.push("input_rows!=240");
    if (result.accessioned_parents !== VALID_COUNT) failures.push("parents!=200");
    if (result.accessioned_children !== expectedChildren) failures.push("children");
    if (result.held !== HOLD_COUNT) failures.push("held!=40");
    if (JSON.stringify(result.hold_code_counts) !== JSON.stringify(HOLD_CODE_COUNTS)) failures.push("hold_code_counts");
    if (result.released_reports !== 0) failures.push("released_reports!=0");
    if (result.blocked_reports !== VALID_COUNT) failures.push("blocked_reports!=200");
    if (result.wrong_child_attached !== 0) failures.push("wrong_child_attached");
    if (result.interface_live !== false) failures.push("interface_live");
    if (result.production_writes !== 0) failures.push("production_writes");
    var expectedMap = {};
    rows.forEach(function (row) {
      if (row.expected_state === "ACCESSION") expectedMap[row.request_id] = row.expected_children.slice();
    });
    if (JSON.stringify(result.parent_children) !== JSON.stringify(expectedMap)) failures.push("parent_children");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    HOLD_CODE_COUNTS: HOLD_CODE_COUNTS,
    buildAcceptanceFixture: buildAcceptanceFixture,
    classifySubmission: classifySubmission,
    runGate: runGate,
    passContract: passContract,
    sha256HexSync: sha256HexSync
  };
});
