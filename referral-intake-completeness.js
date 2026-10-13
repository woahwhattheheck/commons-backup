(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ReferralIntakeCompleteness = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var VERSION = "referral-intake-completeness-v1";
  var SLUG = "referral-intake-completeness";

  var CLASSES = {
    "imaging-slot": {
      label: "Imaging slot packet",
      completeLane: "IMAGING_SCHEDULING",
      required: ["referringClinicId", "destinationClinicId", "laterality", "insuranceAuthFlag", "preferredWindow"]
    },
    "specialist-consult": {
      label: "Specialist consult packet",
      completeLane: "SPECIALIST_INTAKE",
      required: ["referringClinicId", "destinationClinicId", "reasonCategory", "insuranceAuthFlag", "recordsSetFlag"]
    },
    "procedure-slot": {
      label: "Procedure slot packet",
      completeLane: "PROCEDURE_SCHEDULING",
      required: ["referringClinicId", "destinationClinicId", "laterality", "procedureClass", "insuranceAuthFlag"]
    },
    "records-transfer": {
      label: "Records transfer packet",
      completeLane: "RECORDS_INTAKE",
      required: ["referringClinicId", "destinationClinicId", "recordsSetFlag", "releaseAttestation"]
    }
  };

  var ENUMS = {
    laterality: ["LEFT", "RIGHT", "NA"],
    reasonCategory: ["FOLLOW_UP_SLOT", "SECOND_OPINION_SLOT", "TRANSFER_PACKET", "IMAGING_SLOT"],
    procedureClass: ["SLOT-A", "SLOT-B", "SLOT-C"],
    insuranceAuthFlag: ["ATTACHED", "MISSING", "NA"],
    recordsSetFlag: ["PACKET-INDEX-ONLY", "NONE"],
    releaseAttestation: ["SYNTHETIC-ATTESTED", "MISSING"]
  };

  var HOLD_VALUES = {
    insuranceAuthFlag: "MISSING",
    recordsSetFlag: "NONE",
    releaseAttestation: "MISSING"
  };

  var FORBIDDEN_KEYS = [
    "patient", "patientname", "patient_name", "firstname", "lastname", "name",
    "mrn", "ssn", "dob", "dateofbirth", "date_of_birth",
    "diagnosis", "diagnoses", "icd", "icd10", "icd9",
    "treatment", "treatmentplan", "medication", "medications",
    "phi", "phone", "email", "address", "insurancememberid", "memberid"
  ];

  var REFERRAL_RE = /^REF-SYN-[A-Z0-9][A-Z0-9-]{0,30}$/;
  var CLINIC_RE = /^CLINIC-[A-Z0-9][A-Z0-9-]{0,24}-DEMO$/;
  var SSN_RE = /\b\d{3}-\d{2}-\d{4}\b/;
  var MRN_RE = /\bMRN[:\s-]?\d{5,}\b/i;
  var PHI_SCAN_MAX_DEPTH = 8;
  var PHI_SCAN_MAX_NODES = 256;

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
    return /patient|diagnos|treatment|medication|ssn|mrn|\bdob\b/.test(String(key || "").toLowerCase());
  }

  function valueLooksPhi(value) {
    if (value && typeof value === "object") return false;
    var raw = text(value);
    if (!raw) return false;
    return SSN_RE.test(raw) || MRN_RE.test(raw);
  }

  function collectPhiHits(raw) {
    var hits = [];
    var seen = {};
    var nodes = 0;

    function add(path) {
      var key = path || "$packet";
      if (!seen[key]) {
        seen[key] = true;
        hits.push(key);
      }
    }

    function walk(value, path, depth) {
      nodes += 1;
      if (nodes > PHI_SCAN_MAX_NODES) {
        add("$structure.node_limit");
        return;
      }
      if (depth > PHI_SCAN_MAX_DEPTH) {
        add("$structure.depth_limit");
        return;
      }
      if (value && typeof value === "object") {
        if (Array.isArray(value)) {
          add((path || "$packet") + ".$array");
        } else if (path !== "" && path !== "fields") {
          add(path + ".$nested");
        }
        Object.keys(value).sort().forEach(function (key) {
          var child = path ? path + "." + key : key;
          if (keyLooksForbidden(key)) add(child);
          walk(value[key], child, depth + 1);
        });
        return;
      }
      if (valueLooksPhi(value)) add(path || "$value");
    }

    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      add("$packet.invalid_shape");
      return hits.sort();
    }
    walk(raw, "", 0);
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
    ["laterality", "reasonCategory", "procedureClass", "insuranceAuthFlag", "recordsSetFlag", "releaseAttestation", "preferredWindow", "referringClinicId", "destinationClinicId"].forEach(function (key) {
      if (source[key] != null && fields[key] == null) {
        fields[key] = ENUMS[key] ? upper(source[key]) : text(source[key]);
      }
    });
    return {
      referralId: upper(source.referralId),
      referralClass: text(source.referralClass).toLowerCase(),
      submittedAt: text(source.submittedAt),
      fields: fields
    };
  }

  function createJournal() {
    return { version: VERSION, referrals: {} };
  }

  function effectCounts(state) {
    return {
      checklists: state && state.effects.checklist ? 1 : 0,
      queueEntries: state && state.effects.queueEntry ? 1 : 0,
      intakeReceipts: state && state.effects.intakeReceipt ? 1 : 0,
      progressReceipts: state && state.effects.progressReceipt ? 1 : 0
    };
  }

  function clinicalZero() {
    return {
      clinicalDecision: "NONE_INTAKE_ONLY",
      diagnoses: 0,
      careApprovals: 0,
      careDenials: 0,
      treatmentAdvice: 0,
      phiEmitted: 0,
      externalMessagesSent: 0,
      cashUsd: 0
    };
  }

  function result(state, status) {
    return Object.assign({
      receiptVersion: 1,
      slug: SLUG,
      referralId: state.input.referralId,
      fingerprint: state.fingerprint,
      status: status || state.status,
      storedStatus: state.status,
      attempts: state.attempts,
      replayCount: state.replayCount,
      rollbackCount: state.rollbackCount,
      referralClass: state.input.referralClass,
      checklist: clone(state.effects.checklist),
      queueEntry: clone(state.effects.queueEntry),
      intakeReceipt: clone(state.effects.intakeReceipt),
      progressReceipt: clone(state.effects.progressReceipt),
      effectCounts: effectCounts(state),
      lastProcessedAt: state.lastProcessedAt,
      invariant: "NO_CLINICAL_DECISION_NO_PHI_AT_MOST_ONE_QUEUE_ENTRY"
    }, clinicalZero());
  }

  function newState(input, fingerprint, now) {
    return {
      input: clone(input),
      fingerprint: fingerprint,
      status: "NEW",
      attempts: 0,
      replayCount: 0,
      rollbackCount: 0,
      effects: { checklist: null, queueEntry: null, intakeReceipt: null, progressReceipt: null },
      lastProcessedAt: now
    };
  }

  function stampProgress(state, now, status) {
    state.effects.progressReceipt = {
      id: (state.input.referralId || "UNKEYED") + ":progress",
      kind: "PROGRESS_RECEIPT",
      status: status || state.status,
      attempt: state.attempts,
      createdAt: now
    };
  }

  function processReferral(raw, journal, options) {
    options = options || {};
    journal = journal || createJournal();
    if (!journal.referrals) journal.referrals = {};
    var now = text(options.now) || new Date().toISOString();
    var phiHits = collectPhiHits(raw);
    var input = normalize(raw);
    var fingerprint = hash(input);
    var existing = input.referralId ? journal.referrals[input.referralId] : null;

    if (existing && (existing.fingerprint !== fingerprint || canonical(existing.input) !== canonical(input))) {
      return Object.assign({
        receiptVersion: 1,
        slug: SLUG,
        referralId: input.referralId,
        fingerprint: fingerprint,
        storedFingerprint: existing.fingerprint,
        status: "REFERRAL_CONFLICT",
        effectCounts: effectCounts(existing),
        lastProcessedAt: existing.lastProcessedAt,
        invariant: "SAME_ID_DIFFERENT_BYTES_KEEPS_ORIGINAL_QUEUE"
      }, clinicalZero());
    }

    var state = existing || newState(input, fingerprint, now);
    if (!existing && input.referralId) journal.referrals[input.referralId] = state;
    state.attempts += 1;
    state.lastProcessedAt = now;

    if (state.status === "QUEUED_COMPLETE" || state.status === "QUEUED_INCOMPLETE" || state.status === "INTAKE_EXCEPTION" || state.status === "PHI_REFUSED") {
      state.replayCount += 1;
      stampProgress(state, now, "REPLAY_NOOP");
      return result(state, "REPLAY_NOOP");
    }
    if (state.status === "ROLLED_BACK") {
      state.status = "NEW";
      state.effects = { checklist: null, queueEntry: null, intakeReceipt: null, progressReceipt: null };
    }

    if (phiHits.length) {
      state.status = "PHI_REFUSED";
      state.effects.intakeReceipt = state.effects.intakeReceipt || {
        id: (input.referralId || "UNKEYED") + ":intake-receipt",
        kind: "INTAKE_REFUSAL_RECEIPT",
        reason: "PHI_OR_CLINICAL_FIELD",
        hits: phiHits,
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    if (!input.referralId || !REFERRAL_RE.test(input.referralId)) {
      state.status = "INTAKE_EXCEPTION";
      state.effects.intakeReceipt = state.effects.intakeReceipt || {
        id: "UNKEYED:intake-receipt",
        kind: "INTAKE_EXCEPTION_RECEIPT",
        missing: ["syntheticReferralId"],
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    var rule = Object.prototype.hasOwnProperty.call(CLASSES, input.referralClass) ? CLASSES[input.referralClass] : null;
    if (!rule) {
      state.status = "INTAKE_EXCEPTION";
      state.effects.intakeReceipt = state.effects.intakeReceipt || {
        id: input.referralId + ":intake-receipt",
        kind: "INTAKE_EXCEPTION_RECEIPT",
        missing: ["recognizedReferralClass"],
        createdAt: now
      };
      stampProgress(state, now, state.status);
      return result(state);
    }

    var checks = rule.required.map(function (key) {
      var value = input.fields[key];
      var ok = present(value);
      var enumOk = !ENUMS[key] || ENUMS[key].indexOf(value) !== -1;
      if (key === "referringClinicId" || key === "destinationClinicId") {
        enumOk = CLINIC_RE.test(value);
      }
      return { item: key, present: ok, valid: ok && enumOk, valueClass: ok ? (enumOk ? "SYNTHETIC_OK" : "INVALID") : "ABSENT" };
    });
    var missing = checks.filter(function (row) { return !row.present; }).map(function (row) { return row.item; });
    var invalid = checks.filter(function (row) { return row.present && !row.valid; }).map(function (row) { return row.item; });
    var hold = checks.filter(function (row) {
      return row.valid && HOLD_VALUES[row.item] && input.fields[row.item] === HOLD_VALUES[row.item];
    }).map(function (row) { return row.item; });

    state.effects.checklist = state.effects.checklist || {
      id: input.referralId + ":checklist",
      kind: "REQUIRED_FIELD_CHECKLIST",
      referralClass: input.referralClass,
      checks: checks,
      missing: missing,
      invalid: invalid,
      operationalHold: hold,
      createdAt: now
    };

    if (options.crashAt === "after_checklist" && state.status === "NEW") {
      state.status = "CRASHED_AFTER_CHECKLIST";
      stampProgress(state, now, state.status);
      return result(state);
    }

    var complete = missing.length === 0 && invalid.length === 0 && hold.length === 0;
    var lane = complete ? rule.completeLane : "INCOMPLETE_INTAKE";
    state.effects.queueEntry = state.effects.queueEntry || {
      id: input.referralId + ":queue",
      kind: "INTAKE_QUEUE_ENTRY",
      lane: lane,
      completeness: complete ? "COMPLETE" : "INCOMPLETE",
      createdAt: now
    };

    if (options.crashAt === "after_queue" && (state.status === "NEW" || state.status === "CRASHED_AFTER_CHECKLIST")) {
      state.status = "CRASHED_AFTER_QUEUE";
      stampProgress(state, now, state.status);
      return result(state);
    }

    state.effects.intakeReceipt = state.effects.intakeReceipt || {
      id: input.referralId + ":intake-receipt",
      kind: "REFERRAL_INTAKE_RECEIPT",
      checklistId: state.effects.checklist.id,
      queueEntryId: state.effects.queueEntry.id,
      lane: state.effects.queueEntry.lane,
      completeness: state.effects.queueEntry.completeness,
      missing: missing,
      invalid: invalid,
      operationalHold: hold,
      createdAt: now
    };
    state.status = complete ? "QUEUED_COMPLETE" : "QUEUED_INCOMPLETE";
    stampProgress(state, now, state.status);
    return result(state);
  }

  function rollback(referralId, journal, options) {
    options = options || {};
    journal = journal || createJournal();
    var id = upper(referralId);
    var state = journal.referrals && journal.referrals[id];
    if (!state) {
      return Object.assign({ status: "NOT_FOUND", referralId: id }, clinicalZero());
    }
    if (String(state.status).indexOf("CRASHED_") !== 0) {
      return result(state, "NOT_ROLLBACKABLE");
    }
    var now = text(options.now) || new Date().toISOString();
    state.effects = { checklist: null, queueEntry: null, intakeReceipt: null, progressReceipt: null };
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
    createJournal: createJournal,
    processReferral: processReferral,
    rollback: rollback,
    hash: hash,
    collectPhiHits: collectPhiHits
  };
});
