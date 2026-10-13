(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PlantDowntimeHandoff = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var VERSION = "plant-downtime-handoff-v1";
  var SLUG = "plant-downtime-handoff";

  var CLASSES = {
    overtemp: {
      label: "Kiln / thermal overtemp",
      techLane: "TECH_KILN_THERMAL",
      partsKit: "PARTS_THERMAL_KIT",
      required: ["plantId", "assetId", "faultCode", "severity", "observedAt", "windowId"]
    },
    vibration: {
      label: "Rotating vibration",
      techLane: "TECH_ROTATING",
      partsKit: "PARTS_BEARING_KIT",
      required: ["plantId", "assetId", "faultCode", "severity", "observedAt", "windowId"]
    },
    "pressure-drop": {
      label: "Process pressure drop",
      techLane: "TECH_PROCESS",
      partsKit: "PARTS_SEAL_KIT",
      required: ["plantId", "assetId", "faultCode", "severity", "observedAt", "windowId"]
    },
    estop: {
      label: "Synthetic e-stop report",
      techLane: "TECH_SAFETY",
      partsKit: "PARTS_NONE",
      required: ["plantId", "assetId", "faultCode", "severity", "observedAt", "windowId"]
    }
  };

  var ENUMS = {
    faultCode: ["OVERTEMP", "VIBRATION", "PRESSURE_DROP", "ESTOP"],
    severity: ["LOW", "MEDIUM", "HIGH", "UNKNOWN"],
    partsNeeded: ["YES", "NO", "UNKNOWN"],
    source: ["SENSOR_PING", "FAULT_REPORT"]
  };

  var HOLD_VALUES = {
    severity: "UNKNOWN",
    partsNeeded: "UNKNOWN"
  };

  var FORBIDDEN_KEYS = [
    "phone", "email", "ssn", "address", "operator", "operatorname", "operatorname",
    "employeename", "employee", "firstname", "lastname", "name",
    "pii", "patient", "patientname", "mrn", "dob"
  ];

  var FAULT_RE = /^FAULT-SYN-[A-Z0-9][A-Z0-9-]{0,30}$/;
  var PLANT_RE = /^PLANT-[A-Z0-9][A-Z0-9-]{0,24}-DEMO$/;
  var ASSET_RE = /^ASSET-[A-Z0-9][A-Z0-9-]{0,24}-DEMO$/;
  var EVENT_RE = /^(SENSOR|RPT)-SYN-[A-Z0-9][A-Z0-9-]{0,30}$/;
  var PHONE_RE = /\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b/;
  var SSN_RE = /\b\d{3}-\d{2}-\d{4}\b/;
  var EMAIL_RE = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i;

  function text(value) { return String(value == null ? "" : value).trim(); }
  function upper(value) { return text(value).toUpperCase(); }
  function present(value) { return text(value) !== ""; }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function canonical(value) {
    if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
    if (value && typeof value === "object") {
      return "{" + Object.keys(value).sort().map(function (key) {
        return JSON.stringify(key) + ":" + canonical(value[key]);
      }).join(",") + "}";
    }
    return JSON.stringify(value);
  }

  function hash(value) {
    var s = canonical(value);
    var h = 5381;
    for (var i = 0; i < s.length; i += 1) {
      h = ((h << 5) + h) ^ s.charCodeAt(i);
    }
    return ("00000000" + ((h >>> 0).toString(16))).slice(-8);
  }

  function keyLooksForbidden(key) {
    var compact = String(key || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    if (!compact) return false;
    if (FORBIDDEN_KEYS.indexOf(compact) !== -1) return true;
    return /phone|email|ssn|address|employee|operator|pii|patient/.test(String(key || "").toLowerCase());
  }

  function valueLooksPii(value) {
    var raw = text(value);
    if (!raw) return false;
    return PHONE_RE.test(raw) || SSN_RE.test(raw) || EMAIL_RE.test(raw);
  }

  function collectPiiHits(raw) {
    var hits = [];
    var source = raw || {};
    Object.keys(source).forEach(function (key) {
      if (key === "fields") return;
      if (keyLooksForbidden(key) || valueLooksPii(source[key])) hits.push(key);
    });
    var fields = source.fields || {};
    Object.keys(fields).forEach(function (key) {
      if (keyLooksForbidden(key) || valueLooksPii(fields[key])) hits.push("fields." + key);
    });
    return hits.sort();
  }

  function normalize(raw) {
    var source = raw || {};
    var fieldsIn = source.fields || {};
    var fields = {};
    Object.keys(fieldsIn).sort().forEach(function (key) {
      var name = text(key);
      if (!name) return;
      fields[name] = text(fieldsIn[key]);
      if (ENUMS[name]) fields[name] = upper(fields[name]);
    });
    ["plantId", "assetId", "faultCode", "severity", "observedAt", "windowId", "partsNeeded"].forEach(function (key) {
      if (source[key] != null && fields[key] == null) {
        fields[key] = ENUMS[key] ? upper(source[key]) : text(source[key]);
      }
    });
    if (!fields.partsNeeded) fields.partsNeeded = "YES";
    return {
      faultId: upper(source.faultId),
      faultClass: text(source.faultClass).toLowerCase(),
      source: upper(source.source || "FAULT_REPORT"),
      eventId: upper(source.eventId),
      submittedAt: text(source.submittedAt),
      fields: fields
    };
  }

  function identityKey(input) {
    return input.faultId;
  }

  function identityPayload(input) {
    return {
      faultId: input.faultId,
      faultClass: input.faultClass,
      plantId: input.fields.plantId,
      assetId: input.fields.assetId,
      faultCode: input.fields.faultCode,
      severity: input.fields.severity,
      observedAt: input.fields.observedAt,
      windowId: input.fields.windowId,
      partsNeeded: input.fields.partsNeeded
    };
  }

  function identityFingerprint(input) {
    return hash(identityPayload(input));
  }

  function createStore() {
    return { version: VERSION, workerGeneration: 0, faults: {} };
  }

  function snapshotStore(store) {
    return clone(store || createStore());
  }

  function createWorker(existingStore) {
    var store = existingStore ? snapshotStore(existingStore) : createStore();
    store.workerGeneration = (store.workerGeneration || 0) + 1;
    return {
      generation: store.workerGeneration,
      store: store,
      processFault: function (raw, options) {
        return processFault(raw, store, options);
      },
      rollback: function (faultId, options) {
        return rollback(faultId, store, options);
      },
      snapshot: function () {
        return snapshotStore(store);
      }
    };
  }

  function effectCounts(state) {
    var tech = state && state.effects.technicianHandoff ? 1 : 0;
    var parts = state && state.effects.partsRequest ? 1 : 0;
    return {
      classifications: state && state.effects.classification ? 1 : 0,
      technicianHandoffs: tech,
      partsRequests: parts,
      statusReceipts: state && state.effects.statusReceipt ? 1 : 0,
      progressReceipts: state && state.effects.progressReceipt ? 1 : 0,
      dispatches: tech
    };
  }

  function plantZero() {
    return {
      livePlantControl: 0,
      cmmsWrites: 0,
      purchasingOrders: 0,
      safetyDecisions: 0,
      piiEmitted: 0,
      externalMessagesSent: 0,
      outreach: 0,
      cashUsd: 0
    };
  }

  function result(state, status, extras) {
    var packet = Object.assign({
      receiptVersion: 1,
      slug: SLUG,
      faultId: state.input.faultId,
      idempotencyKey: state.idempotencyKey,
      fingerprint: state.fingerprint,
      status: status || state.status,
      storedStatus: state.status,
      attempts: state.attempts,
      replayCount: state.replayCount,
      rollbackCount: state.rollbackCount,
      workerGeneration: state.lastWorkerGeneration || 0,
      faultClass: state.input.faultClass,
      events: clone(state.events),
      classification: clone(state.effects.classification),
      technicianHandoff: clone(state.effects.technicianHandoff),
      partsRequest: clone(state.effects.partsRequest),
      statusReceipt: clone(state.effects.statusReceipt),
      progressReceipt: clone(state.effects.progressReceipt),
      effectCounts: effectCounts(state),
      lastProcessedAt: state.lastProcessedAt,
      invariant: "AT_MOST_ONE_DISPATCH_PER_FAULT_IDENTITY"
    }, plantZero(), extras || {});
    return packet;
  }

  function emptyEffects() {
    return {
      classification: null,
      technicianHandoff: null,
      partsRequest: null,
      statusReceipt: null,
      progressReceipt: null
    };
  }

  function newState(input, fingerprint, now) {
    return {
      input: clone(input),
      idempotencyKey: identityKey(input),
      fingerprint: fingerprint,
      status: "NEW",
      attempts: 0,
      replayCount: 0,
      rollbackCount: 0,
      lastWorkerGeneration: 0,
      events: [],
      effects: emptyEffects(),
      lastProcessedAt: now
    };
  }

  function recordEvent(state, input, now) {
    if (!input.eventId) return;
    var exists = state.events.some(function (row) {
      return row.eventId === input.eventId;
    });
    if (exists) return;
    state.events.push({
      source: input.source,
      eventId: input.eventId,
      receivedAt: now
    });
  }

  function stampProgress(state, now, status) {
    state.effects.progressReceipt = {
      id: (state.input.faultId || "UNKEYED") + ":progress",
      kind: "PROGRESS_RECEIPT",
      status: status || state.status,
      attempt: state.attempts,
      createdAt: now
    };
  }

  function terminal(status) {
    return status === "DISPATCHED" ||
      status === "HELD_INCOMPLETE" ||
      status === "FAULT_EXCEPTION" ||
      status === "PII_REFUSED";
  }

  function processFault(raw, store, options) {
    options = options || {};
    store = store || createStore();
    if (!store.faults) store.faults = {};
    var now = text(options.now) || new Date().toISOString();
    var workerGeneration = store.workerGeneration || 1;
    var piiHits = collectPiiHits(raw);
    var input = normalize(raw);
    var fingerprint = identityFingerprint(input);
    var key = identityKey(input);
    var existing = key ? store.faults[key] : null;

    if (piiHits.length) {
      var refusalInput = {
        faultId: FAULT_RE.test(input.faultId) && piiHits.indexOf("faultId") === -1 ? input.faultId : "",
        faultClass: Object.prototype.hasOwnProperty.call(CLASSES, input.faultClass) ? input.faultClass : "",
        fields: {}
      };
      var refusalState = existing ? clone(existing) : newState(refusalInput, fingerprint, now);
      refusalState.input = refusalInput;
      refusalState.idempotencyKey = refusalInput.faultId;
      refusalState.status = "PII_REFUSED";
      refusalState.attempts += 1;
      refusalState.lastProcessedAt = now;
      refusalState.lastWorkerGeneration = workerGeneration;
      refusalState.effects.statusReceipt = {
        id: (refusalInput.faultId || "UNKEYED") + ":status",
        kind: "HANDOFF_REFUSAL_RECEIPT",
        reason: "PII_OR_LIVE_IDENTIFIER",
        hits: piiHits,
        createdAt: now
      };
      stampProgress(refusalState, now, refusalState.status);
      return result(refusalState, null, { storedStatus: existing ? existing.status : null });
    }

    if (existing && (existing.fingerprint !== fingerprint ||
        canonical(identityPayload(existing.input)) !== canonical(identityPayload(input)))) {
      return Object.assign({
        receiptVersion: 1,
        slug: SLUG,
        faultId: input.faultId,
        idempotencyKey: key,
        fingerprint: fingerprint,
        storedFingerprint: existing.fingerprint,
        status: "FAULT_CONFLICT",
        effectCounts: effectCounts(existing),
        technicianHandoff: clone(existing.effects.technicianHandoff),
        lastProcessedAt: existing.lastProcessedAt,
        invariant: "SAME_ID_DIFFERENT_BYTES_KEEPS_ORIGINAL_DISPATCH"
      }, plantZero());
    }

    var state = existing || newState(input, fingerprint, now);
    if (!existing && key) store.faults[key] = state;
    state.attempts += 1;
    state.lastProcessedAt = now;
    state.lastWorkerGeneration = workerGeneration;
    recordEvent(state, input, now);

    if (terminal(state.status)) {
      state.replayCount += 1;
      stampProgress(state, now, "REPLAY_NOOP");
      return result(state, "REPLAY_NOOP");
    }
    if (state.status === "ROLLED_BACK") {
      state.status = "NEW";
      state.effects = emptyEffects();
    }

    if (!input.faultId || !FAULT_RE.test(input.faultId)) {
      state.status = "FAULT_EXCEPTION";
      state.effects.statusReceipt = state.effects.statusReceipt || {
        id: "UNKEYED:status",
        kind: "HANDOFF_EXCEPTION_RECEIPT",
        missing: ["syntheticFaultId"],
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    if (input.eventId && !EVENT_RE.test(input.eventId)) {
      state.status = "FAULT_EXCEPTION";
      state.effects.statusReceipt = state.effects.statusReceipt || {
        id: input.faultId + ":status",
        kind: "HANDOFF_EXCEPTION_RECEIPT",
        missing: ["syntheticEventId"],
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    var rule = Object.prototype.hasOwnProperty.call(CLASSES, input.faultClass) ? CLASSES[input.faultClass] : null;
    if (!rule) {
      state.status = "FAULT_EXCEPTION";
      state.effects.statusReceipt = state.effects.statusReceipt || {
        id: input.faultId + ":status",
        kind: "HANDOFF_EXCEPTION_RECEIPT",
        missing: ["recognizedFaultClass"],
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    var checks = rule.required.map(function (field) {
      var value = input.fields[field];
      var ok = present(value);
      var enumOk = !ENUMS[field] || ENUMS[field].indexOf(value) !== -1;
      if (field === "plantId") enumOk = PLANT_RE.test(value);
      if (field === "assetId") enumOk = ASSET_RE.test(value);
      return {
        item: field,
        present: ok,
        valid: ok && enumOk,
        valueClass: ok ? (enumOk ? "SYNTHETIC_OK" : "INVALID") : "ABSENT"
      };
    });
    var missing = checks.filter(function (row) { return !row.present; }).map(function (row) { return row.item; });
    var invalid = checks.filter(function (row) { return row.present && !row.valid; }).map(function (row) { return row.item; });
    var hold = [];
    if (input.fields.severity === HOLD_VALUES.severity) hold.push("severity");
    if (input.fields.partsNeeded === HOLD_VALUES.partsNeeded) hold.push("partsNeeded");

    state.effects.classification = state.effects.classification || {
      id: input.faultId + ":classify",
      kind: "FAULT_CLASSIFICATION",
      faultClass: input.faultClass,
      idempotencyKey: state.idempotencyKey,
      checks: checks,
      missing: missing,
      invalid: invalid,
      operationalHold: hold,
      createdAt: now
    };

    if (options.crashAt === "after_classify" && (state.status === "NEW" || state.status === "ROLLED_BACK")) {
      state.status = "CRASHED_AFTER_CLASSIFY";
      stampProgress(state, now, state.status);
      return result(state);
    }

    var complete = missing.length === 0 && invalid.length === 0 && hold.length === 0;
    if (!complete) {
      state.effects.statusReceipt = state.effects.statusReceipt || {
        id: input.faultId + ":status",
        kind: "HANDOFF_HOLD_RECEIPT",
        completeness: "INCOMPLETE",
        missing: missing,
        invalid: invalid,
        operationalHold: hold,
        createdAt: now
      };
      state.status = "HELD_INCOMPLETE";
      stampProgress(state, now, state.status);
      return result(state);
    }

    state.effects.technicianHandoff = state.effects.technicianHandoff || {
      id: input.faultId + ":tech",
      kind: "TECHNICIAN_HANDOFF",
      lane: rule.techLane,
      crewSlot: "CREW-SYN-" + rule.techLane.replace(/^TECH_/, ""),
      createdAt: now
    };

    if (options.crashAt === "after_tech" && String(state.status).indexOf("CRASHED_AFTER_PARTS") !== 0) {
      if (state.status === "NEW" || state.status === "CRASHED_AFTER_CLASSIFY" || state.status === "ROLLED_BACK") {
        state.status = "CRASHED_AFTER_TECH";
        stampProgress(state, now, state.status);
        return result(state);
      }
    }

    var wantsParts = input.fields.partsNeeded === "YES" && rule.partsKit !== "PARTS_NONE";
    if (wantsParts) {
      state.effects.partsRequest = state.effects.partsRequest || {
        id: input.faultId + ":parts",
        kind: "PARTS_REQUEST_INTENT",
        kit: rule.partsKit,
        technicianHandoffId: state.effects.technicianHandoff.id,
        createdAt: now
      };
    } else {
      state.effects.partsRequest = state.effects.partsRequest || {
        id: input.faultId + ":parts",
        kind: "PARTS_NONE_INTENT",
        kit: "PARTS_NONE",
        technicianHandoffId: state.effects.technicianHandoff.id,
        createdAt: now
      };
    }

    if (options.crashAt === "after_parts" && (state.status === "NEW" || state.status === "CRASHED_AFTER_CLASSIFY" || state.status === "CRASHED_AFTER_TECH")) {
      state.status = "CRASHED_AFTER_PARTS";
      stampProgress(state, now, state.status);
      return result(state);
    }

    state.effects.statusReceipt = state.effects.statusReceipt || {
      id: input.faultId + ":status",
      kind: "HANDOFF_STATUS_RECEIPT",
      technicianHandoffId: state.effects.technicianHandoff.id,
      partsRequestId: state.effects.partsRequest.id,
      lane: state.effects.technicianHandoff.lane,
      completeness: "COMPLETE",
      createdAt: now
    };
    state.status = "DISPATCHED";
    stampProgress(state, now, state.status);
    return result(state);
  }

  function rollback(faultId, store, options) {
    options = options || {};
    store = store || createStore();
    var id = upper(faultId);
    var state = store.faults && store.faults[id];
    if (!state) {
      return Object.assign({ status: "NOT_FOUND", faultId: id }, plantZero());
    }
    if (String(state.status).indexOf("CRASHED_") !== 0) {
      return result(state, "NOT_ROLLBACKABLE");
    }
    var now = text(options.now) || new Date().toISOString();
    state.effects = emptyEffects();
    state.status = "ROLLED_BACK";
    state.rollbackCount += 1;
    state.lastProcessedAt = now;
    stampProgress(state, now, state.status);
    return result(state);
  }

  return {
    VERSION: VERSION,
    SLUG: SLUG,
    CLASSES: clone(CLASSES),
    ENUMS: clone(ENUMS),
    createStore: createStore,
    createJournal: createStore,
    snapshotStore: snapshotStore,
    createWorker: createWorker,
    processFault: processFault,
    rollback: rollback,
    hash: hash,
    collectPiiHits: collectPiiHits,
    identityFingerprint: identityFingerprint
  };
});
