(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.DealerServiceLeadRescue = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var VERSION = "dealer-service-lead-rescue-v1";
  var SLUG = "dealer-service-lead-rescue";

  var CLASSES = {
    "oil-change": {
      label: "Express oil change",
      followUpLane: "FOLLOWUP_EXPRESS",
      appointmentLane: "APPT_QUICK_LANE",
      required: ["dealerId", "vehicleSlot", "concernCode", "preferredWindow", "mileageBand"]
    },
    "brake-service": {
      label: "Brake inspection / service",
      followUpLane: "FOLLOWUP_ADVISOR",
      appointmentLane: "APPT_SHOP_BAY",
      required: ["dealerId", "vehicleSlot", "concernCode", "preferredWindow", "mileageBand"]
    },
    "recall-campaign": {
      label: "OEM recall campaign",
      followUpLane: "FOLLOWUP_RECALL",
      appointmentLane: "APPT_RECALL_LANE",
      required: ["dealerId", "vehicleSlot", "concernCode", "preferredWindow", "mileageBand"]
    },
    "check-engine": {
      label: "Check-engine diagnostic",
      followUpLane: "FOLLOWUP_DIAG",
      appointmentLane: "APPT_DIAG_BAY",
      required: ["dealerId", "vehicleSlot", "concernCode", "preferredWindow", "mileageBand"]
    }
  };

  var ENUMS = {
    concernCode: ["OIL_CHANGE", "BRAKE_SERVICE", "RECALL", "CHECK_ENGINE"],
    mileageBand: ["UNDER_5K", "5K_15K", "OVER_15K", "UNKNOWN"],
    preferredWindow: ["AM", "PM", "UNKNOWN"],
    source: ["WEB_FORM", "AFTER_HOURS"]
  };

  var HOLD_VALUES = {
    mileageBand: "UNKNOWN",
    preferredWindow: "UNKNOWN"
  };

  var FORBIDDEN_KEYS = [
    "phone", "email", "ssn", "address", "vin", "fullname", "firstname",
    "lastname", "customer", "customername", "ownername", "name", "pii",
    "driver", "driverlicense", "licenseplate"
  ];

  var LEAD_RE = /^LEAD-SYN-[A-Z0-9][A-Z0-9-]{0,30}$/;
  var DEALER_RE = /^DEALER-[A-Z0-9][A-Z0-9-]{0,24}-DEMO$/;
  var VEHICLE_RE = /^VEH-SYN-[A-Z0-9][A-Z0-9-]{0,24}-DEMO$/;
  var INQUIRY_RE = /^(FORM|AFT)-SYN-[A-Z0-9][A-Z0-9-]{0,30}$/;
  var PHONE_RE = /\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b/;
  var SSN_RE = /\b\d{3}-\d{2}-\d{4}\b/;
  var EMAIL_RE = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i;
  var VIN_RE = /\b[A-HJ-NPR-Z0-9]{17}\b/;

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
    return /phone|email|ssn|address|vin|customer|pii|license/.test(String(key || "").toLowerCase());
  }

  function valueLooksPii(value) {
    var raw = text(value);
    if (!raw) return false;
    return PHONE_RE.test(raw) || SSN_RE.test(raw) || EMAIL_RE.test(raw) || VIN_RE.test(raw);
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
    ["dealerId", "vehicleSlot", "concernCode", "preferredWindow", "mileageBand"].forEach(function (key) {
      if (source[key] != null && fields[key] == null) {
        fields[key] = ENUMS[key] ? upper(source[key]) : text(source[key]);
      }
    });
    return {
      leadId: upper(source.leadId),
      leadClass: text(source.leadClass).toLowerCase(),
      source: upper(source.source || "WEB_FORM"),
      inquiryId: upper(source.inquiryId),
      submittedAt: text(source.submittedAt),
      fields: fields
    };
  }

  function identityKey(input) {
    return input.leadId;
  }

  function identityPayload(input) {
    return {
      leadId: input.leadId,
      leadClass: input.leadClass,
      dealerId: input.fields.dealerId,
      vehicleSlot: input.fields.vehicleSlot,
      concernCode: input.fields.concernCode,
      preferredWindow: input.fields.preferredWindow,
      mileageBand: input.fields.mileageBand
    };
  }

  function identityFingerprint(input) {
    return hash(identityPayload(input));
  }

  function createStore() {
    return { version: VERSION, workerGeneration: 0, leads: {} };
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
      processLead: function (raw, options) {
        return processLead(raw, store, options);
      },
      rollback: function (leadId, options) {
        return rollback(leadId, store, options);
      },
      snapshot: function () {
        return snapshotStore(store);
      }
    };
  }

  function effectCounts(state) {
    var follow = state && state.effects.followUp ? 1 : 0;
    var appt = state && state.effects.appointment ? 1 : 0;
    return {
      classifications: state && state.effects.classification ? 1 : 0,
      followUps: follow,
      appointments: appt,
      crmRecords: appt,
      statusReceipts: state && state.effects.statusReceipt ? 1 : 0,
      progressReceipts: state && state.effects.progressReceipt ? 1 : 0,
      dispatches: appt
    };
  }

  function dealerZero() {
    return {
      liveCrmWrites: 0,
      realDealerships: 0,
      outreach: 0,
      externalMessagesSent: 0,
      piiEmitted: 0,
      paymentsProcessed: 0,
      cashUsd: 0
    };
  }

  function result(state, status, extras) {
    var packet = Object.assign({
      receiptVersion: 1,
      slug: SLUG,
      leadId: state.input.leadId,
      idempotencyKey: state.idempotencyKey,
      fingerprint: state.fingerprint,
      status: status || state.status,
      storedStatus: state.status,
      attempts: state.attempts,
      replayCount: state.replayCount,
      rollbackCount: state.rollbackCount,
      workerGeneration: state.lastWorkerGeneration || 0,
      leadClass: state.input.leadClass,
      inquiries: clone(state.inquiries),
      classification: clone(state.effects.classification),
      followUp: clone(state.effects.followUp),
      appointment: clone(state.effects.appointment),
      statusReceipt: clone(state.effects.statusReceipt),
      progressReceipt: clone(state.effects.progressReceipt),
      effectCounts: effectCounts(state),
      lastProcessedAt: state.lastProcessedAt,
      invariant: "AT_MOST_ONE_APPOINTMENT_PER_LEAD_IDENTITY"
    }, dealerZero(), extras || {});
    return packet;
  }

  function emptyEffects() {
    return {
      classification: null,
      followUp: null,
      appointment: null,
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
      inquiries: [],
      effects: emptyEffects(),
      lastProcessedAt: now
    };
  }

  function recordInquiry(state, input, now) {
    if (!input.inquiryId) return;
    var exists = state.inquiries.some(function (row) {
      return row.inquiryId === input.inquiryId;
    });
    if (exists) return;
    state.inquiries.push({
      source: input.source,
      inquiryId: input.inquiryId,
      receivedAt: now
    });
  }

  function stampProgress(state, now, status) {
    state.effects.progressReceipt = {
      id: (state.input.leadId || "UNKEYED") + ":progress",
      kind: "PROGRESS_RECEIPT",
      status: status || state.status,
      attempt: state.attempts,
      createdAt: now
    };
  }

  function terminal(status) {
    return status === "RESCUED" ||
      status === "HELD_INCOMPLETE" ||
      status === "LEAD_EXCEPTION" ||
      status === "PII_REFUSED";
  }

  function processLead(raw, store, options) {
    options = options || {};
    store = store || createStore();
    if (!store.leads) store.leads = {};
    var now = text(options.now) || new Date().toISOString();
    var workerGeneration = store.workerGeneration || 1;
    var piiHits = collectPiiHits(raw);
    var input = normalize(raw);
    var fingerprint = identityFingerprint(input);
    var key = identityKey(input);
    var existing = key ? store.leads[key] : null;

    if (piiHits.length) {
      var refusalInput = {
        leadId: LEAD_RE.test(input.leadId) && piiHits.indexOf("leadId") === -1 ? input.leadId : "",
        leadClass: Object.prototype.hasOwnProperty.call(CLASSES, input.leadClass) ? input.leadClass : "",
        fields: {}
      };
      var refusalState = existing ? clone(existing) : newState(refusalInput, fingerprint, now);
      refusalState.input = refusalInput;
      refusalState.idempotencyKey = refusalInput.leadId;
      refusalState.status = "PII_REFUSED";
      refusalState.attempts += 1;
      refusalState.lastProcessedAt = now;
      refusalState.lastWorkerGeneration = workerGeneration;
      refusalState.effects.statusReceipt = {
        id: (refusalInput.leadId || "UNKEYED") + ":status",
        kind: "RESCUE_REFUSAL_RECEIPT",
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
        leadId: input.leadId,
        idempotencyKey: key,
        fingerprint: fingerprint,
        storedFingerprint: existing.fingerprint,
        status: "LEAD_CONFLICT",
        effectCounts: effectCounts(existing),
        appointment: clone(existing.effects.appointment),
        followUp: clone(existing.effects.followUp),
        lastProcessedAt: existing.lastProcessedAt,
        invariant: "SAME_ID_DIFFERENT_BYTES_KEEPS_ORIGINAL_RESCUE"
      }, dealerZero());
    }

    var state = existing || newState(input, fingerprint, now);
    if (!existing && key) store.leads[key] = state;
    state.attempts += 1;
    state.lastProcessedAt = now;
    state.lastWorkerGeneration = workerGeneration;
    recordInquiry(state, input, now);

    if (terminal(state.status)) {
      state.replayCount += 1;
      stampProgress(state, now, "REPLAY_NOOP");
      return result(state, "REPLAY_NOOP");
    }
    if (state.status === "ROLLED_BACK") {
      state.status = "NEW";
      state.effects = emptyEffects();
    }

    if (!input.leadId || !LEAD_RE.test(input.leadId)) {
      state.status = "LEAD_EXCEPTION";
      state.effects.statusReceipt = state.effects.statusReceipt || {
        id: "UNKEYED:status",
        kind: "RESCUE_EXCEPTION_RECEIPT",
        missing: ["syntheticLeadId"],
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    if (input.inquiryId && !INQUIRY_RE.test(input.inquiryId)) {
      state.status = "LEAD_EXCEPTION";
      state.effects.statusReceipt = state.effects.statusReceipt || {
        id: input.leadId + ":status",
        kind: "RESCUE_EXCEPTION_RECEIPT",
        missing: ["syntheticInquiryId"],
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    var rule = Object.prototype.hasOwnProperty.call(CLASSES, input.leadClass) ? CLASSES[input.leadClass] : null;
    if (!rule) {
      state.status = "LEAD_EXCEPTION";
      state.effects.statusReceipt = state.effects.statusReceipt || {
        id: input.leadId + ":status",
        kind: "RESCUE_EXCEPTION_RECEIPT",
        missing: ["recognizedLeadClass"],
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    var checks = rule.required.map(function (field) {
      var value = input.fields[field];
      var ok = present(value);
      var enumOk = !ENUMS[field] || ENUMS[field].indexOf(value) !== -1;
      if (field === "dealerId") enumOk = DEALER_RE.test(value);
      if (field === "vehicleSlot") enumOk = VEHICLE_RE.test(value);
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
    if (input.fields.preferredWindow === HOLD_VALUES.preferredWindow) hold.push("preferredWindow");
    if (input.fields.mileageBand === HOLD_VALUES.mileageBand) hold.push("mileageBand");

    state.effects.classification = state.effects.classification || {
      id: input.leadId + ":classify",
      kind: "LEAD_CLASSIFICATION",
      leadClass: input.leadClass,
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
        id: input.leadId + ":status",
        kind: "RESCUE_HOLD_RECEIPT",
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

    state.effects.followUp = state.effects.followUp || {
      id: input.leadId + ":followup",
      kind: "CUSTOMER_FOLLOWUP",
      lane: rule.followUpLane,
      advisorSlot: "BDC-SYN-" + rule.followUpLane.replace(/^FOLLOWUP_/, ""),
      createdAt: now
    };

    if (options.crashAt === "after_followup") {
      if (state.status === "NEW" || state.status === "CRASHED_AFTER_CLASSIFY" || state.status === "ROLLED_BACK") {
        state.status = "CRASHED_AFTER_FOLLOWUP";
        stampProgress(state, now, state.status);
        return result(state);
      }
    }

    state.effects.appointment = state.effects.appointment || {
      id: input.leadId + ":appt",
      kind: "BOOKED_SERVICE_CRM_RECORD",
      lane: rule.appointmentLane,
      followUpId: state.effects.followUp.id,
      createdAt: now
    };

    if (options.crashAt === "after_appointment" && (state.status === "NEW" || state.status === "CRASHED_AFTER_CLASSIFY" || state.status === "CRASHED_AFTER_FOLLOWUP")) {
      state.status = "CRASHED_AFTER_APPOINTMENT";
      stampProgress(state, now, state.status);
      return result(state);
    }

    state.effects.statusReceipt = state.effects.statusReceipt || {
      id: input.leadId + ":status",
      kind: "RESCUE_STATUS_RECEIPT",
      followUpId: state.effects.followUp.id,
      appointmentId: state.effects.appointment.id,
      lane: state.effects.appointment.lane,
      completeness: "COMPLETE",
      createdAt: now
    };
    state.status = "RESCUED";
    stampProgress(state, now, state.status);
    return result(state);
  }

  function rollback(leadId, store, options) {
    options = options || {};
    store = store || createStore();
    var id = upper(leadId);
    var state = store.leads && store.leads[id];
    if (!state) {
      return Object.assign({ status: "NOT_FOUND", leadId: id }, dealerZero());
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
    processLead: processLead,
    rollback: rollback,
    hash: hash,
    collectPiiHits: collectPiiHits,
    identityFingerprint: identityFingerprint
  };
});
