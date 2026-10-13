(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PermitIntakeReceipt = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var RULES = {
    "residential-remodel": {
      label: "Residential remodel",
      queue: "RESIDENTIAL_BUILDING_REVIEW",
      required: ["applicant", "parcelId", "siteAddress", "scope", "estimatedCost", "ownerConsent"]
    },
    "commercial-tenant": {
      label: "Commercial tenant improvement",
      queue: "COMMERCIAL_PLAN_REVIEW",
      required: ["applicant", "parcelId", "siteAddress", "scope", "estimatedCost", "planSet", "occupancyType", "contractorLicense"]
    },
    "sign": {
      label: "Sign permit",
      queue: "ZONING_SIGN_REVIEW",
      required: ["applicant", "parcelId", "siteAddress", "signDimensions", "sitePlan", "ownerConsent"]
    },
    "demolition": {
      label: "Demolition",
      queue: "SAFETY_DEMOLITION_REVIEW",
      required: ["applicant", "parcelId", "siteAddress", "scope", "utilityDisconnects", "asbestosSurvey"]
    }
  };

  function text(value) { return String(value == null ? "" : value).trim(); }
  function present(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    return text(value) !== "";
  }
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
    var s = canonical(value), h = 2166136261;
    for (var i = 0; i < s.length; i += 1) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return ("00000000" + (h >>> 0).toString(16)).slice(-8);
  }
  function normalize(raw) {
    var source = raw || {}, items = source.items || {};
    var cleanItems = {};
    Object.keys(items).sort().forEach(function (key) {
      cleanItems[text(key)] = typeof items[key] === "boolean" ? items[key] : text(items[key]);
    });
    return {
      applicationId: text(source.applicationId),
      permitType: text(source.permitType),
      submittedAt: text(source.submittedAt),
      items: cleanItems
    };
  }
  function createJournal() { return { version: 1, applications: {} }; }
  function effectCounts(state) {
    return {
      checklists: state && state.effects.checklist ? 1 : 0,
      missingNotices: state && state.effects.missingNotice ? 1 : 0,
      queueRoutes: state && state.effects.queueRoute ? 1 : 0,
      applicantReceipts: state && state.effects.applicantReceipt ? 1 : 0
    };
  }
  function result(state, status) {
    return {
      receiptVersion: 1,
      slug: "permit-intake-receipt",
      applicationId: state.input.applicationId,
      fingerprint: state.fingerprint,
      status: status || state.status,
      storedStatus: state.status,
      attempts: state.attempts,
      replayCount: state.replayCount,
      rollbackCount: state.rollbackCount,
      permitType: state.input.permitType,
      checklist: clone(state.effects.checklist),
      missingItemNotice: clone(state.effects.missingNotice),
      queueRoute: clone(state.effects.queueRoute),
      applicantReceipt: clone(state.effects.applicantReceipt),
      effectCounts: effectCounts(state),
      decision: "NONE_INTAKE_ONLY",
      approvals: 0,
      denials: 0,
      externalMessagesSent: 0,
      lastProcessedAt: state.lastProcessedAt,
      invariant: "DETERMINISTIC_COMPLETENESS_AND_AT_MOST_ONE_NOTICE_ROUTE_AND_RECEIPT"
    };
  }
  function newState(input, fingerprint, now) {
    return {
      input: clone(input),
      fingerprint: fingerprint,
      status: "NEW",
      attempts: 0,
      replayCount: 0,
      rollbackCount: 0,
      effects: { checklist: null, missingNotice: null, queueRoute: null, applicantReceipt: null },
      lastProcessedAt: now
    };
  }
  function processApplication(raw, journal, options) {
    options = options || {};
    journal = journal || createJournal();
    if (!journal.applications) journal.applications = {};
    var now = text(options.now) || new Date().toISOString();
    var input = normalize(raw);
    var fingerprint = hash(input);
    var existing = input.applicationId ? journal.applications[input.applicationId] : null;

    if (existing && existing.fingerprint !== fingerprint) {
      return {
        receiptVersion: 1,
        slug: "permit-intake-receipt",
        applicationId: input.applicationId,
        fingerprint: fingerprint,
        storedFingerprint: existing.fingerprint,
        status: "APPLICATION_CONFLICT",
        effectCounts: effectCounts(existing),
        decision: "NONE_INTAKE_ONLY",
        approvals: 0,
        denials: 0,
        externalMessagesSent: 0
      };
    }

    var state = existing || newState(input, fingerprint, now);
    if (!existing && input.applicationId) journal.applications[input.applicationId] = state;
    state.attempts += 1;
    state.lastProcessedAt = now;

    if (state.status === "ROUTED_FOR_REVIEW" || state.status === "MISSING_ITEMS" || state.status === "INTAKE_EXCEPTION") {
      state.replayCount += 1;
      return result(state, "REPLAY_NOOP");
    }
    if (state.status === "ROLLED_BACK") {
      state.status = "NEW";
      state.effects = { checklist: null, missingNotice: null, queueRoute: null, applicantReceipt: null };
    }

    if (!input.applicationId) {
      state.input.applicationId = "UNKEYED";
      state.effects.missingNotice = {
        id: "UNKEYED:missing-notice",
        kind: "MISSING_ITEM_NOTICE",
        missing: ["applicationId"],
        createdAt: now
      };
      state.status = "INTAKE_EXCEPTION";
      return result(state);
    }

    var rule = RULES[input.permitType];
    if (!rule) {
      state.effects.missingNotice = state.effects.missingNotice || {
        id: input.applicationId + ":missing-notice",
        kind: "INTAKE_EXCEPTION",
        missing: ["recognizedPermitType"],
        createdAt: now
      };
      state.effects.applicantReceipt = state.effects.applicantReceipt || {
        id: input.applicationId + ":applicant-receipt",
        kind: "APPLICANT_INTAKE_RECEIPT",
        status: "INTAKE_EXCEPTION",
        createdAt: now
      };
      state.status = "INTAKE_EXCEPTION";
      return result(state);
    }

    var checks = rule.required.map(function (key) {
      return { item: key, present: present(input.items[key]) };
    });
    var missing = checks.filter(function (x) { return !x.present; }).map(function (x) { return x.item; });
    state.effects.checklist = state.effects.checklist || {
      id: input.applicationId + ":checklist",
      kind: "COMPLETENESS_CHECKLIST",
      rule: input.permitType,
      checks: checks,
      createdAt: now
    };

    if (options.crashAt === "after_checklist" && state.status === "NEW") {
      state.status = "CRASHED_AFTER_CHECKLIST";
      return result(state);
    }

    if (missing.length && !state.effects.missingNotice) {
      state.effects.missingNotice = {
        id: input.applicationId + ":missing-notice",
        kind: "MISSING_ITEM_NOTICE",
        missing: missing,
        createdAt: now
      };
    }

    if (options.crashAt === "after_notice" && missing.length && state.status !== "CRASHED_AFTER_NOTICE") {
      state.status = "CRASHED_AFTER_NOTICE";
      return result(state);
    }

    state.effects.queueRoute = state.effects.queueRoute || {
      id: input.applicationId + ":queue-route",
      kind: "REVIEW_QUEUE_ROUTE",
      queue: rule.queue,
      completeness: missing.length ? "INCOMPLETE" : "COMPLETE",
      createdAt: now
    };
    state.effects.applicantReceipt = state.effects.applicantReceipt || {
      id: input.applicationId + ":applicant-receipt",
      kind: "APPLICANT_INTAKE_RECEIPT",
      checklistId: state.effects.checklist.id,
      noticeId: state.effects.missingNotice ? state.effects.missingNotice.id : null,
      queueRouteId: state.effects.queueRoute.id,
      status: missing.length ? "MISSING_ITEMS" : "ROUTED_FOR_REVIEW",
      createdAt: now
    };
    state.status = missing.length ? "MISSING_ITEMS" : "ROUTED_FOR_REVIEW";
    return result(state);
  }
  function rollback(applicationId, journal, options) {
    options = options || {};
    journal = journal || createJournal();
    var state = journal.applications && journal.applications[text(applicationId)];
    if (!state) return { status: "NOT_FOUND", applicationId: text(applicationId), approvals: 0, denials: 0 };
    if (state.status.indexOf("CRASHED_") !== 0) return result(state, "NOT_ROLLBACKABLE");
    state.effects = { checklist: null, missingNotice: null, queueRoute: null, applicantReceipt: null };
    state.status = "ROLLED_BACK";
    state.rollbackCount += 1;
    state.lastProcessedAt = text(options.now) || new Date().toISOString();
    return result(state);
  }

  return { RULES: clone(RULES), createJournal: createJournal, processApplication: processApplication, rollback: rollback, hash: hash };
});
