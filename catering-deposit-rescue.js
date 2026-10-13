(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CateringDepositRescue = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var CATALOG = {
    "boxed-lunch": { label: "Boxed lunch", centsPerGuest: 1800, minimumGuests: 10 },
    "buffet": { label: "Buffet", centsPerGuest: 2600, minimumGuests: 20 },
    "plated": { label: "Plated service", centsPerGuest: 4200, minimumGuests: 25 }
  };
  var SERVICE_FEE_CENTS = 7500;
  var DEPOSIT_RATE = 0.25;

  function text(value) { return String(value == null ? "" : value).trim(); }
  function integer(value) {
    var n = Number(value);
    return Number.isInteger(n) ? n : NaN;
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
    var input = canonical(value);
    var h = 2166136261;
    for (var i = 0; i < input.length; i += 1) {
      h ^= input.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return ("00000000" + (h >>> 0).toString(16)).slice(-8);
  }
  function normalize(raw) {
    return {
      eventId: text(raw && raw.eventId),
      customer: text(raw && raw.customer),
      eventDate: text(raw && raw.eventDate),
      menu: text(raw && raw.menu),
      guests: integer(raw && raw.guests),
      budgetCents: raw && text(raw.budgetCents) !== "" ? integer(raw.budgetCents) : 0,
      notes: text(raw && raw.notes)
    };
  }
  function validate(input) {
    if (!input.eventId) return "MISSING_EVENT_ID";
    if (!input.customer) return "MISSING_CUSTOMER";
    if (!input.eventDate) return "MISSING_EVENT_DATE";
    if (!Number.isInteger(input.guests) || input.guests < 1 || input.guests > 500) return "INVALID_GUEST_COUNT";
    if (!CATALOG[input.menu]) return "UNKNOWN_MENU_RULE";
    if (input.guests < CATALOG[input.menu].minimumGuests) return "BELOW_MENU_MINIMUM";
    if (!Number.isInteger(input.budgetCents) || input.budgetCents < 0) return "INVALID_BUDGET";
    return "";
  }
  function quoteFor(input) {
    var rule = CATALOG[input.menu];
    var subtotal = rule.centsPerGuest * input.guests;
    var total = subtotal + SERVICE_FEE_CENTS;
    return {
      currency: "USD",
      menu: input.menu,
      menuLabel: rule.label,
      guests: input.guests,
      centsPerGuest: rule.centsPerGuest,
      subtotalCents: subtotal,
      serviceFeeCents: SERVICE_FEE_CENTS,
      totalCents: total,
      depositRate: DEPOSIT_RATE,
      depositCents: Math.round(total * DEPOSIT_RATE),
      source: "PUBLIC_FIXED_RULES_V1"
    };
  }
  function createJournal() { return { version: 1, events: {} }; }
  function counts(state) {
    return {
      followups: state && state.effects.followup ? 1 : 0,
      depositIntents: state && state.effects.depositIntent ? 1 : 0,
      staffExceptions: state && state.effects.staffException ? 1 : 0
    };
  }
  function receipt(state, resultStatus) {
    return {
      receiptVersion: 1,
      slug: "catering-deposit-rescue",
      eventId: state.input.eventId,
      fingerprint: state.fingerprint,
      status: resultStatus || state.status,
      storedStatus: state.status,
      attempts: state.attempts,
      replayCount: state.replayCount,
      rollbackCount: state.rollbackCount,
      quote: clone(state.quote),
      effects: clone(state.effects),
      effectCounts: counts(state),
      lastProcessedAt: state.lastProcessedAt,
      invariant: "RULES_PRICED_QUOTE_AND_AT_MOST_ONE_FOLLOWUP_AND_ONE_DEPOSIT_INTENT",
      externalMessagesSent: 0,
      paymentsProcessed: 0,
      cashUsd: 0
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
      quote: null,
      effects: { followup: null, depositIntent: null, staffException: null },
      lastProcessedAt: now
    };
  }
  function staffException(state, reason, now) {
    if (!state.effects.staffException) {
      state.effects.staffException = {
        id: state.input.eventId + ":staff-exception",
        kind: "STAFF_EXCEPTION",
        reason: reason,
        createdAt: now
      };
    }
    state.status = "STAFF_EXCEPTION";
    state.lastProcessedAt = now;
    return receipt(state);
  }
  function processInquiry(raw, journal, options) {
    options = options || {};
    journal = journal || createJournal();
    if (!journal.events) journal.events = {};
    var now = text(options.now) || new Date().toISOString();
    var input = normalize(raw || {});
    var fingerprint = hash(input);
    var existing = input.eventId ? journal.events[input.eventId] : null;

    if (existing && existing.fingerprint !== fingerprint) {
      return {
        receiptVersion: 1,
        slug: "catering-deposit-rescue",
        eventId: input.eventId,
        fingerprint: fingerprint,
        status: "EVENT_CONFLICT",
        storedFingerprint: existing.fingerprint,
        effectCounts: counts(existing),
        invariant: "SAME_EVENT_ID_DIFFERENT_BYTES_REJECTED",
        externalMessagesSent: 0,
        paymentsProcessed: 0,
        cashUsd: 0
      };
    }

    var state = existing || newState(input, fingerprint, now);
    if (!existing && input.eventId) journal.events[input.eventId] = state;
    state.attempts += 1;
    state.lastProcessedAt = now;

    if (state.status === "READY" || state.status === "STAFF_EXCEPTION") {
      state.replayCount += 1;
      return receipt(state, "REPLAY_NOOP");
    }
    if (state.status === "ROLLED_BACK") {
      state.status = "NEW";
      state.quote = null;
      state.effects = { followup: null, depositIntent: null, staffException: null };
    }

    var invalid = validate(input);
    if (invalid) return staffException(state, invalid, now);

    state.quote = state.quote || quoteFor(input);
    if (input.budgetCents && input.budgetCents < state.quote.totalCents) {
      return staffException(state, "BUDGET_BELOW_RULES_TOTAL", now);
    }

    if (options.crashAt === "after_quote" && state.status === "NEW") {
      state.status = "CRASHED_AFTER_QUOTE";
      return receipt(state);
    }

    if (!state.effects.followup) {
      state.effects.followup = {
        id: input.eventId + ":followup",
        kind: "LOCAL_FOLLOWUP_PACKET",
        customer: input.customer,
        quoteTotalCents: state.quote.totalCents,
        createdAt: now
      };
    }

    if (options.crashAt === "after_followup" && state.status !== "CRASHED_AFTER_FOLLOWUP") {
      state.status = "CRASHED_AFTER_FOLLOWUP";
      return receipt(state);
    }

    if (!state.effects.depositIntent) {
      state.effects.depositIntent = {
        id: input.eventId + ":deposit-intent",
        kind: "INERT_DEPOSIT_INTENT",
        amountCents: state.quote.depositCents,
        reference: "deposit-intent://" + input.eventId + "/" + fingerprint,
        createdAt: now,
        paymentProcessed: false
      };
    }
    state.status = "READY";
    return receipt(state);
  }
  function rollback(eventId, journal, options) {
    options = options || {};
    journal = journal || createJournal();
    var state = journal.events && journal.events[text(eventId)];
    if (!state) return { status: "NOT_FOUND", eventId: text(eventId), paymentsProcessed: 0 };
    if (state.status.indexOf("CRASHED_") !== 0) return receipt(state, "NOT_ROLLBACKABLE");
    state.quote = null;
    state.effects.followup = null;
    state.effects.depositIntent = null;
    state.status = "ROLLED_BACK";
    state.rollbackCount += 1;
    state.lastProcessedAt = text(options.now) || new Date().toISOString();
    return receipt(state);
  }

  return {
    CATALOG: clone(CATALOG),
    SERVICE_FEE_CENTS: SERVICE_FEE_CENTS,
    DEPOSIT_RATE: DEPOSIT_RATE,
    createJournal: createJournal,
    processInquiry: processInquiry,
    rollback: rollback,
    hash: hash
  };
});
