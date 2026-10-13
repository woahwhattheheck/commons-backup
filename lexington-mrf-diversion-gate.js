(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LexingtonMrfDiversionGate = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var DEMAND_ID = "lexington-mrf-diversion-gate-01";
  var SCHEMA = "commons-lexington-mrf-diversion-gate/v1";
  var OCCUPANCY_CAP_TONS = 100;
  var CITY_DIVERT = { CITY_DIVERT: 1, SHUTDOWN: 1, ZERO_STORAGE: 1, WET_MECHANICAL: 1 };
  var HAULER_HOLD = { HAULER_HOLD: 1, SHUTDOWN: 1, WET_MECHANICAL: 1 };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function text(value) {
    return String(value == null ? "" : value).trim();
  }

  function canonical(value) {
    return JSON.stringify(value, Object.keys(value && typeof value === "object" ? value : {}).sort ? undefined : undefined);
  }

  function stable(value) {
    if (Array.isArray(value)) return value.map(stable);
    if (value && typeof value === "object") {
      var out = {};
      Object.keys(value).sort().forEach(function (key) {
        out[key] = stable(value[key]);
      });
      return out;
    }
    return value;
  }

  function sha256HexSync(value) {
    var payload = JSON.stringify(stable(value));
    if (typeof require === "function") {
      try {
        return require("crypto").createHash("sha256").update(payload).digest("hex");
      } catch (_) {}
    }
    var h = 5381;
    for (var i = 0; i < payload.length; i += 1) h = ((h << 5) + h) ^ payload.charCodeAt(i);
    return ("00000000" + ((h >>> 0).toString(16))).slice(-8);
  }

  function load(loadId, source, tons, currentWindow, material, observedAt, staleNotice) {
    return {
      row_id: loadId,
      kind: "LOAD",
      load_id: loadId,
      source: source,
      tons: tons,
      material: material,
      observed_at: observedAt,
      current_window: currentWindow,
      stale_notice: staleNotice || null
    };
  }

  function buildAcceptanceFixture() {
    var rows = [];
    var i;
    var windowName;
    for (i = 1; i <= 10; i += 1) {
      windowName = i <= 5 ? "CITY_DIVERT" : i <= 8 ? "SHUTDOWN" : "WET_MECHANICAL";
      rows.push(load("L" + String(i).padStart(3, "0"), "CITY", 4, windowName, "CURBSIDE", "2026-08-31T08:" + String(i).padStart(2, "0") + ":00Z", null));
    }
    for (i = 11; i <= 20; i += 1) {
      windowName = i <= 15 ? "HAULER_HOLD" : i <= 18 ? "SHUTDOWN" : "WET_MECHANICAL";
      rows.push(load("L" + String(i).padStart(3, "0"), "HAULER", 4, windowName, "OUTSIDE", "2026-08-31T09:" + String(i - 10).padStart(2, "0") + ":00Z", null));
    }
    for (i = 21; i <= 35; i += 1) {
      var stale = i <= 28;
      var notice = stale ? (i <= 24 ? "SHUTDOWN" : "WET_MECHANICAL") : null;
      rows.push(load("L" + String(i).padStart(3, "0"), i % 2 === 0 ? "CITY" : "HAULER", 6, "OPEN", "DRY", "2026-08-31T10:" + String(i - 20).padStart(2, "0") + ":00Z", notice));
    }
    for (i = 36; i <= 40; i += 1) {
      rows.push(load("L" + String(i).padStart(3, "0"), "CITY", 12, "OPEN", "DRY", "2026-08-31T11:" + String(i - 35).padStart(2, "0") + ":00Z", null));
    }
    var dupeIds = ["L001", "L002", "L011", "L012", "L021", "L022", "L023", "L036", "L037", "L038"];
    var originals = {};
    rows.forEach(function (row) { originals[row.load_id] = row; });
    dupeIds.forEach(function (id, index) {
      var copy = clone(originals[id]);
      copy.row_id = "DUP" + String(index + 1).padStart(2, "0");
      rows.push(copy);
    });
    return rows;
  }

  function collapseDuplicates(rows) {
    var seen = {};
    var unique = [];
    var collapsed = 0;
    rows.forEach(function (row) {
      var id = text(row.load_id);
      if (!id) return;
      if (seen[id]) {
        collapsed += 1;
        return;
      }
      seen[id] = 1;
      unique.push(clone(row));
    });
    unique.sort(function (a, b) {
      var left = text(a.observed_at) + "\0" + text(a.load_id);
      var right = text(b.observed_at) + "\0" + text(b.load_id);
      return left < right ? -1 : left > right ? 1 : 0;
    });
    return { unique: unique, collapsed: collapsed };
  }

  function classifyLoad(row, occupancyTons) {
    var source = text(row.source).toUpperCase();
    var windowName = text(row.current_window).toUpperCase();
    var tons = Number(row.tons);
    if (!(tons >= 0)) tons = 0;
    var disposition;
    var reason;
    var occupy = 0;
    if (source === "CITY" && CITY_DIVERT[windowName]) {
      disposition = "LANDFILL_CITY";
      reason = "city_load_in_divert_window";
    } else if (source === "HAULER" && HAULER_HOLD[windowName]) {
      disposition = "HOLD_HAULER";
      reason = "outside_hauler_in_hold_window";
    } else if (occupancyTons + tons > OCCUPANCY_CAP_TONS) {
      disposition = "HOLD_CAPACITY";
      reason = "occupancy_would_exceed_100t";
    } else {
      disposition = "ACCEPT";
      reason = "open_window_within_capacity";
      occupy = tons;
    }
    return {
      load_id: text(row.load_id),
      source: source,
      tons: tons,
      current_window: windowName,
      stale_notice_ignored: text(row.stale_notice).toUpperCase() || null,
      disposition: disposition,
      reason: reason,
      occupancy_before_t: occupancyTons,
      occupancy_delta_t: occupy,
      actions: []
    };
  }

  function runGate(rows) {
    var inbound = clone(rows || buildAcceptanceFixture());
    var collapsed = collapseDuplicates(inbound);
    var occupancy = 0;
    var receipts = [];
    var ignoredStale = 0;
    collapsed.unique.forEach(function (row) {
      if (text(row.stale_notice)) ignoredStale += 1;
      var receipt = classifyLoad(row, occupancy);
      occupancy += Number(receipt.occupancy_delta_t);
      receipts.push(receipt);
    });
    var counts = { LANDFILL_CITY: 0, HOLD_HAULER: 0, ACCEPT: 0, HOLD_CAPACITY: 0 };
    receipts.forEach(function (receipt) { counts[receipt.disposition] += 1; });
    var body = {
      schema: SCHEMA,
      demand_id: DEMAND_ID,
      input_rows: inbound.length,
      unique_loads: collapsed.unique.length,
      collapsed_duplicates: collapsed.collapsed,
      ignored_stale_states: ignoredStale,
      occupancy_cap_t: OCCUPANCY_CAP_TONS,
      occupancy_accepted_t: occupancy,
      counts: counts,
      receipts: receipts,
      actions: [],
      equipment_control: false,
      autonomous_safety_decision: false,
      pre_sale_transport: "NONE"
    };
    body.manifest_sha256 = sha256HexSync(
      Object.keys(body).reduce(function (acc, key) {
        if (key !== "manifest_sha256") acc[key] = body[key];
        return acc;
      }, {})
    );
    return body;
  }

  function passContract(result) {
    var failures = [];
    if (result.input_rows !== 50) failures.push("input_rows!=50");
    if (result.collapsed_duplicates !== 10) failures.push("collapsed_duplicates!=10");
    if (result.ignored_stale_states !== 8) failures.push("ignored_stale_states!=8");
    var expected = { LANDFILL_CITY: 10, HOLD_HAULER: 10, ACCEPT: 15, HOLD_CAPACITY: 5 };
    Object.keys(expected).forEach(function (name) {
      if (!result.counts || result.counts[name] !== expected[name]) failures.push("counts." + name);
    });
    if (Number(result.occupancy_accepted_t) > OCCUPANCY_CAP_TONS) failures.push("occupancy>100t");
    if (result.actions && result.actions.length) failures.push("actions_not_empty");
    if (result.equipment_control !== false) failures.push("equipment_control");
    if (result.autonomous_safety_decision !== false) failures.push("autonomous_safety_decision");
    return failures;
  }

  return {
    DEMAND_ID: DEMAND_ID,
    buildAcceptanceFixture: buildAcceptanceFixture,
    runGate: runGate,
    passContract: passContract,
    sha256HexSync: sha256HexSync,
    canonical: canonical
  };
});
