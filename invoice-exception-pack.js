(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.InvoiceExceptionPack = api;
  if (root.document) root.addEventListener("DOMContentLoaded", function () { api.mount(root.document); });
}(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  var STORAGE_KEY = "commons-invoice-exception-pack-v1";
  var REQUIRED = [
    "invoice_id", "invoice_vendor", "invoice_amount", "invoice_currency",
    "po_id", "po_vendor", "po_amount", "po_currency"
  ];

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function createMemoryStorage() {
    var data = {};
    return {
      getItem: function (key) { return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null; },
      setItem: function (key, value) { data[key] = String(value); },
      removeItem: function (key) { delete data[key]; }
    };
  }

  function load(storage) {
    var raw = storage.getItem(STORAGE_KEY);
    if (!raw) return { schema_version: "commons-invoice-exception-ledger/v1", records: {} };
    try {
      var parsed = JSON.parse(raw);
      if (!parsed || !parsed.records) throw new Error("bad ledger");
      return parsed;
    } catch (_) {
      return { schema_version: "commons-invoice-exception-ledger/v1", records: {} };
    }
  }

  function save(storage, ledger) { storage.setItem(STORAGE_KEY, JSON.stringify(ledger)); }
  function clean(value) { return String(value == null ? "" : value).trim(); }

  function cents(value) {
    var text = clean(value);
    if (!/^\d+(?:\.\d{1,2})?$/.test(text)) return null;
    var parts = text.split(".");
    return (parseInt(parts[0], 10) * 100) + parseInt((parts[1] || "").padEnd(2, "0"), 10);
  }

  function normalize(input) {
    var out = {};
    Object.keys(input || {}).forEach(function (key) { out[key] = clean(input[key]); });
    out.invoice_currency = (out.invoice_currency || "").toUpperCase();
    out.po_currency = (out.po_currency || "").toUpperCase();
    return out;
  }

  function keyFor(input) {
    return [input.invoice_id || "MISSING_INVOICE", input.po_id || "MISSING_PO"]
      .map(encodeURIComponent).join("::");
  }

  function evaluate(raw) {
    var input = normalize(raw || {});
    var missing = REQUIRED.filter(function (field) { return !input[field]; });
    var invoiceCents = cents(input.invoice_amount);
    var poCents = cents(input.po_amount);
    if (input.invoice_amount && invoiceCents === null) missing.push("invoice_amount_valid_decimal");
    if (input.po_amount && poCents === null) missing.push("po_amount_valid_decimal");
    if (missing.length) {
      return { status: "MISSING_DATA", queue: "AP_INCOMPLETE", missing_fields: missing, exceptions: [], input: input };
    }
    var exceptions = [];
    if (input.invoice_vendor.toLowerCase() !== input.po_vendor.toLowerCase()) exceptions.push("VENDOR_MISMATCH");
    if (input.invoice_currency !== input.po_currency) exceptions.push("CURRENCY_MISMATCH");
    if (invoiceCents !== poCents) exceptions.push("AMOUNT_MISMATCH");
    return {
      status: exceptions.length ? "EXCEPTION" : "MATCH",
      queue: exceptions.length ? "AP_EXCEPTION_REVIEW" : "CONTROLLER_APPROVAL",
      missing_fields: [],
      exceptions: exceptions,
      amount_cents: invoiceCents,
      input: input
    };
  }

  function timestamp(options) { return options && options.now ? String(options.now) : new Date().toISOString(); }

  function receipt(record, replayed) {
    return {
      schema_version: "commons-invoice-exception-receipt/v1",
      idempotency_key: record.idempotency_key,
      state: record.state,
      decision: clone(record.decision),
      approval_request_count: record.approval_request_count,
      approval_request: record.approval_request || null,
      replayed: !!replayed,
      created_at: record.created_at,
      updated_at: record.updated_at,
      audit: clone(record.audit),
      synthetic_demo: true,
      moves_money: false,
      cash_claim: false
    };
  }

  function processInvoice(storage, raw, options) {
    options = options || {};
    var decision = evaluate(raw);
    var key = keyFor(decision.input);
    var ledger = load(storage);
    var existing = ledger.records[key];

    if (existing) {
      if (existing.state === "INTENT_RECORDED" && !options.forceCrashAfterIntent) {
        existing.state = "COMPLETED";
        existing.approval_request_count = 1;
        existing.approval_request = {
          effect_id: "APR-" + key,
          kind: "SYNTHETIC_APPROVAL_REQUEST",
          queue: "CONTROLLER_APPROVAL"
        };
        existing.updated_at = timestamp(options);
        existing.audit.push({ at: existing.updated_at, event: "RETRY_COMPLETED_EXISTING_INTENT" });
        save(storage, ledger);
        return receipt(existing, true);
      }
      return receipt(existing, true);
    }

    var now = timestamp(options);
    var record = {
      idempotency_key: key,
      state: decision.status === "MATCH" ? "INTENT_RECORDED" : "BLOCKED",
      decision: decision,
      approval_request_count: 0,
      approval_request: null,
      created_at: now,
      updated_at: now,
      audit: [{ at: now, event: decision.status === "MATCH" ? "INTENT_RECORDED" : "BLOCKED_BEFORE_EFFECT" }]
    };
    ledger.records[key] = record;
    save(storage, ledger);

    if (record.state === "BLOCKED") return receipt(record, false);
    if (options.forceCrashAfterIntent) {
      var error = new Error("SIMULATED_CRASH_AFTER_DURABLE_INTENT");
      error.code = "SIMULATED_CRASH_AFTER_DURABLE_INTENT";
      error.receipt = receipt(record, false);
      throw error;
    }

    record.state = "COMPLETED";
    record.approval_request_count = 1;
    record.approval_request = {
      effect_id: "APR-" + key,
      kind: "SYNTHETIC_APPROVAL_REQUEST",
      queue: "CONTROLLER_APPROVAL"
    };
    record.audit.push({ at: now, event: "APPROVAL_REQUEST_CREATED_ONCE" });
    save(storage, ledger);
    return receipt(record, false);
  }

  function rollback(storage, key, options) {
    var ledger = load(storage);
    var record = ledger.records[key];
    if (!record) return null;
    var now = timestamp(options || {});
    if (record.state === "INTENT_RECORDED") {
      record.state = "ROLLED_BACK";
      record.updated_at = now;
      record.audit.push({ at: now, event: "ROLLED_BACK_BEFORE_EFFECT" });
    } else if (record.state === "COMPLETED") {
      record.state = "ROLLBACK_REQUIRES_HUMAN";
      record.updated_at = now;
      record.audit.push({ at: now, event: "EFFECT_ALREADY_RECORDED_NO_FALSE_UNDO" });
    }
    save(storage, ledger);
    return receipt(record, false);
  }

  function markdown(data) {
    return [
      "# Invoice exception receipt", "",
      "- state: " + data.state,
      "- decision: " + data.decision.status,
      "- queue: " + data.decision.queue,
      "- idempotency key: " + data.idempotency_key,
      "- approval requests: " + data.approval_request_count,
      "- replayed: " + data.replayed,
      "- synthetic demo: true",
      "- moves money: false", "",
      "## Exceptions", "",
      (data.decision.exceptions.length ? data.decision.exceptions : ["none"]).map(function (x) { return "- " + x; }).join("\n"), "",
      "## Missing fields", "",
      (data.decision.missing_fields.length ? data.decision.missing_fields : ["none"]).map(function (x) { return "- " + x; }).join("\n"), "",
      "## Audit", "",
      data.audit.map(function (x) { return "- " + x.at + " — " + x.event; }).join("\n"), ""
    ].join("\n");
  }

  function mount(doc) {
    var form = doc.getElementById("invoice-demo");
    if (!form) return;
    var storage;
    try { storage = root.localStorage; storage.getItem(STORAGE_KEY); }
    catch (_) { storage = createMemoryStorage(); }
    var output = doc.getElementById("invoice-receipt");
    var md = doc.getElementById("invoice-receipt-md");
    var status = doc.getElementById("demo-status");
    var lastKey = "";

    function input() {
      var data = {};
      REQUIRED.forEach(function (field) {
        var node = doc.getElementById(field);
        data[field] = node ? node.value : "";
      });
      return data;
    }

    function render(data, note) {
      if (!data) return;
      lastKey = data.idempotency_key;
      output.value = JSON.stringify(data, null, 2);
      md.value = markdown(data);
      status.textContent = note || (data.state + " · " + data.decision.status + " · approval requests " + data.approval_request_count);
    }

    function processCurrentInput(options, note) {
      var raw = input();
      var current = normalize(raw);
      var existing = load(storage).records[keyFor(current)];
      if (existing) {
        var saved = normalize(existing.decision.input);
        var changed = REQUIRED.filter(function (field) { return clean(current[field]) !== clean(saved[field]); });
        if (changed.length) {
          render(receipt(existing, true), "Input differs from saved invoice/PO fields: " + changed.join(", ") + ". Showing the saved receipt; no ledger change. Restore saved values, use new IDs, or reset local demo for a new scenario.");
          return;
        }
      }
      render(processInvoice(storage, raw, options), note);
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      processCurrentInput({});
    });
    doc.getElementById("force-crash").addEventListener("click", function () {
      try { processCurrentInput({ forceCrashAfterIntent: true }); }
      catch (error) { render(error.receipt, "Forced crash landed after durable intent. Retry or roll back."); }
    });
    doc.getElementById("retry-run").addEventListener("click", function () {
      processCurrentInput({}, "Retry reconciled the existing intent; no duplicate request.");
    });
    doc.getElementById("duplicate-run").addEventListener("click", function () {
      processCurrentInput({}, "Duplicate replay returned the existing receipt.");
    });
    doc.getElementById("rollback-run").addEventListener("click", function () {
      render(rollback(storage, lastKey || keyFor(normalize(input()))), "Rollback recorded without inventing an undo.");
    });
    doc.getElementById("reset-run").addEventListener("click", function () {
      storage.removeItem(STORAGE_KEY);
      output.value = "";
      md.value = "";
      lastKey = "";
      status.textContent = "Local synthetic ledger reset.";
    });
    doc.getElementById("copy-receipt").addEventListener("click", function () {
      if (root.navigator && root.navigator.clipboard) root.navigator.clipboard.writeText(output.value || "");
    });
  }

  return {
    STORAGE_KEY: STORAGE_KEY,
    createMemoryStorage: createMemoryStorage,
    evaluate: evaluate,
    keyFor: function (input) { return keyFor(normalize(input || {})); },
    processInvoice: processInvoice,
    rollback: rollback,
    markdown: markdown,
    mount: mount
  };
}));