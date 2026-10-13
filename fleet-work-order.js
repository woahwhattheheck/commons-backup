(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.FleetWorkOrder = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const VERSION = "fleet-work-order-v1";

  function stableString(value) {
    if (Array.isArray(value)) return "[" + value.map(stableString).join(",") + "]";
    if (value && typeof value === "object") {
      return "{" + Object.keys(value).sort().map(function (key) {
        return JSON.stringify(key) + ":" + stableString(value[key]);
      }).join(",") + "}";
    }
    return JSON.stringify(value);
  }

  function hash32(text) {
    let hash = 0x811c9dc5;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, "0");
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function emptyLedger() {
    return { version: VERSION, events: {}, work_orders: {}, escalations: {}, receipts: {} };
  }

  function memoryStore(initial) {
    let ledger = clone(initial || emptyLedger());
    return {
      load: function () { return clone(ledger); },
      save: function (next) { ledger = clone(next); },
      clear: function () { ledger = emptyLedger(); }
    };
  }

  function localStore(storage, key) {
    const storageKey = key || "commons:fleet-work-order:v1";
    return {
      load: function () {
        const raw = storage.getItem(storageKey);
        return raw ? JSON.parse(raw) : emptyLedger();
      },
      save: function (next) { storage.setItem(storageKey, JSON.stringify(next)); },
      clear: function () { storage.removeItem(storageKey); }
    };
  }

  function normalize(input) {
    const event = {
      event_id: String(input.event_id || "").trim(),
      vehicle_id: String(input.vehicle_id || "").trim(),
      fault_code: String(input.fault_code || "").trim().toUpperCase(),
      severity: String(input.severity || "").trim().toUpperCase(),
      reported_at: String(input.reported_at || "").trim(),
      note: String(input.note || "").trim()
    };
    const missing = ["event_id", "vehicle_id", "fault_code", "severity", "reported_at"]
      .filter(function (key) { return !event[key]; });
    if (missing.length) return { ok: false, reason: "MISSING:" + missing.join(","), event: event };
    if (!["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(event.severity)) {
      return { ok: false, reason: "INVALID:severity", event: event };
    }
    if (Number.isNaN(Date.parse(event.reported_at))) {
      return { ok: false, reason: "INVALID:reported_at", event: event };
    }
    return { ok: true, event: event };
  }

  function result(kind, eventId, ledger, extra) {
    return Object.assign({ kind: kind, event_id: eventId, ledger: clone(ledger) }, extra || {});
  }

  function process(store, input, options) {
    const opts = options || {};
    const checked = normalize(input || {});
    let ledger = store.load();
    if (!checked.ok) return result("REJECTED", checked.event.event_id, ledger, { reason: checked.reason });

    const event = checked.event;
    const fingerprint = hash32(stableString(event));
    const current = ledger.events[event.event_id];
    if (current && current.fingerprint !== fingerprint) {
      return result("CONFLICT", event.event_id, ledger, { reason: "EVENT_ID_REUSED_WITH_DIFFERENT_BYTES" });
    }
    if (current && current.status === "COMMITTED") {
      return result("REPLAY_NOOP", event.event_id, ledger, { receipt: clone(ledger.receipts[event.event_id]) });
    }
    if (current && current.status === "ROLLED_BACK") {
      return result("ROLLED_BACK", event.event_id, ledger, { receipt: clone(ledger.receipts[event.event_id]) });
    }

    const workOrderId = "WO-" + hash32(event.event_id + ":work-order");
    const escalationId = "ESC-" + hash32(event.event_id + ":escalation");
    if (!current) {
      ledger.events[event.event_id] = {
        status: "PREPARED",
        fingerprint: fingerprint,
        event: event,
        work_order_id: workOrderId,
        escalation_id: escalationId
      };
      store.save(ledger);
      if (opts.fail_at === "after_prepare") throw new Error("SIMULATED_CRASH:after_prepare");
    }

    ledger = store.load();
    if (!ledger.work_orders[workOrderId]) {
      ledger.work_orders[workOrderId] = {
        id: workOrderId,
        source_event_id: event.event_id,
        vehicle_id: event.vehicle_id,
        fault_code: event.fault_code,
        status: "OPEN"
      };
    }
    if (!ledger.escalations[escalationId]) {
      ledger.escalations[escalationId] = {
        id: escalationId,
        source_event_id: event.event_id,
        severity: event.severity,
        route: event.severity === "CRITICAL" ? "IMMEDIATE" : "PLANNED"
      };
    }
    store.save(ledger);
    if (opts.fail_at === "after_effects") throw new Error("SIMULATED_CRASH:after_effects");

    ledger = store.load();
    const receipt = {
      state: "COMMITTED",
      event_id: event.event_id,
      fingerprint: fingerprint,
      work_order_id: workOrderId,
      escalation_id: escalationId,
      effects: 2,
      invariant: "one source event -> one work order + one escalation"
    };
    ledger.events[event.event_id].status = "COMMITTED";
    ledger.receipts[event.event_id] = receipt;
    store.save(ledger);
    return result("COMMITTED", event.event_id, ledger, { receipt: clone(receipt) });
  }

  function rollback(store, eventId) {
    const ledger = store.load();
    const current = ledger.events[eventId];
    if (!current) return result("NOT_FOUND", eventId, ledger);
    if (current.status === "COMMITTED") return result("ROLLBACK_REFUSED", eventId, ledger, { reason: "COMMITTED_EFFECTS_REQUIRE_OPERATOR_CLOSEOUT" });
    delete ledger.work_orders[current.work_order_id];
    delete ledger.escalations[current.escalation_id];
    current.status = "ROLLED_BACK";
    ledger.receipts[eventId] = {
      state: "ROLLED_BACK",
      event_id: eventId,
      work_order_id: current.work_order_id,
      escalation_id: current.escalation_id,
      effects_remaining: 0
    };
    store.save(ledger);
    return result("ROLLED_BACK", eventId, ledger, { receipt: clone(ledger.receipts[eventId]) });
  }

  return {
    VERSION: VERSION,
    emptyLedger: emptyLedger,
    memoryStore: memoryStore,
    localStore: localStore,
    normalize: normalize,
    process: process,
    rollback: rollback
  };
});
