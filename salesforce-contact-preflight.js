(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.SalesforceContactPreflight = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const OPS = new Set(["create", "update", "merge"]);
  const ID_FIELDS = ["external_id", "email", "phone"];

  function canonical(value) {
    if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
    if (value && typeof value === "object") {
      return "{" + Object.keys(value).sort().map(k => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
    }
    return JSON.stringify(value);
  }

  function hash(value) {
    const text = canonical(value);
    let h = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return ("00000000" + (h >>> 0).toString(16)).slice(-8);
  }

  function clean(value) {
    return String(value == null ? "" : value).trim().toLowerCase();
  }

  function identity(fields) {
    for (const field of ID_FIELDS) {
      const value = clean(fields[field]);
      if (value) return field + ":" + value;
    }
    return "";
  }

  function receipt(event, index, status, reason, contactId, detail) {
    const core = {
      index,
      event_id: event && event.event_id ? String(event.event_id) : "",
      operation: event && event.operation ? String(event.operation) : "",
      status,
      reason,
      contact_id: contactId || "",
      detail: detail || {}
    };
    return Object.assign(core, { receipt_hash: hash(core) });
  }

  function run(events) {
    if (!Array.isArray(events)) throw new TypeError("events must be an array");
    const contacts = new Map();
    const aliases = new Map();
    const seen = new Map();
    const receipts = [];

    function lookup(key) {
      const normalized = clean(key);
      const contactId = aliases.get(normalized) || normalized;
      return contacts.has(contactId) ? contactId : "";
    }

    events.forEach((event, index) => {
      if (!event || typeof event !== "object" || Array.isArray(event)) {
        receipts.push(receipt({}, index, "REJECTED", "INVALID_EVENT", "", {}));
        return;
      }
      const eventId = clean(event.event_id);
      const eventHash = hash(event);
      if (!eventId) {
        receipts.push(receipt(event, index, "REJECTED", "MISSING_EVENT_ID", "", {}));
        return;
      }
      if (seen.has(eventId)) {
        const prior = seen.get(eventId);
        receipts.push(prior.hash === eventHash
          ? receipt(event, index, "REPLAYED", "EXACT_REPLAY", prior.receipt.contact_id, { original_receipt_hash: prior.receipt.receipt_hash })
          : receipt(event, index, "REJECTED", "EVENT_ID_CONFLICT", "", { prior_hash: prior.hash, supplied_hash: eventHash }));
        return;
      }
      const op = clean(event.operation);
      if (!OPS.has(op)) {
        const out = receipt(event, index, "REJECTED", "INVALID_OPERATION", "", { operation: op });
        seen.set(eventId, { hash: eventHash, receipt: out });
        receipts.push(out);
        return;
      }

      let out;
      if (op === "create") {
        const fields = event.fields && typeof event.fields === "object" && !Array.isArray(event.fields) ? Object.assign({}, event.fields) : {};
        const key = identity(fields);
        if (!key) {
          out = receipt(event, index, "REJECTED", "MISSING_MATCH_KEY", "", {});
        } else {
          const existingId = aliases.get(key);
          if (!existingId) {
            const contactId = "contact-" + hash({ key });
            contacts.set(contactId, { id: contactId, fields, active: true });
            ID_FIELDS.forEach(f => { const v = clean(fields[f]); if (v) aliases.set(f + ":" + v, contactId); });
            out = receipt(event, index, "ACCEPTED", "CREATED", contactId, {});
          } else {
            const existing = contacts.get(existingId);
            const conflict = Object.keys(fields).sort().find(f => clean(existing.fields[f]) && clean(fields[f]) && clean(existing.fields[f]) !== clean(fields[f]));
            out = conflict
              ? receipt(event, index, "REJECTED", "DUPLICATE_CONFLICT", existingId, { field: conflict })
              : receipt(event, index, "ACCEPTED", "CREATE_NOOP", existingId, {});
          }
        }
      } else if (op === "update") {
        const suppliedKey = event.match_key || identity(event.fields || {});
        const key = clean(suppliedKey);
        const contactId = lookup(suppliedKey);
        if (!contactId || !contacts.get(contactId)?.active) {
          out = receipt(event, index, "REJECTED", "CONTACT_NOT_FOUND", "", { match_key: key });
        } else {
          const contact = contacts.get(contactId);
          const patch = event.fields && typeof event.fields === "object" && !Array.isArray(event.fields) ? event.fields : {};
          let collision = "";
          for (const f of ID_FIELDS) {
            const v = clean(patch[f]);
            const mapped = v ? aliases.get(f + ":" + v) : "";
            if (mapped && mapped !== contactId) { collision = f; break; }
          }
          if (collision) {
            out = receipt(event, index, "REJECTED", "MATCH_KEY_CONFLICT", contactId, { field: collision });
          } else {
            contact.fields = Object.assign({}, contact.fields, patch);
            ID_FIELDS.forEach(f => { const v = clean(contact.fields[f]); if (v) aliases.set(f + ":" + v, contactId); });
            out = receipt(event, index, "ACCEPTED", "UPDATED", contactId, { changed_fields: Object.keys(patch).sort() });
          }
        }
      } else {
        const sourceId = lookup(event.source_key);
        const targetId = lookup(event.target_key);
        if (!sourceId || !targetId || sourceId === targetId || !contacts.get(sourceId)?.active || !contacts.get(targetId)?.active) {
          out = receipt(event, index, "REJECTED", "INVALID_MERGE", "", { source_key: clean(event.source_key), target_key: clean(event.target_key) });
        } else {
          const source = contacts.get(sourceId);
          const target = contacts.get(targetId);
          const conflict = Object.keys(source.fields).sort().find(f => clean(source.fields[f]) && clean(target.fields[f]) && clean(source.fields[f]) !== clean(target.fields[f]) && !ID_FIELDS.includes(f));
          if (conflict) {
            out = receipt(event, index, "REJECTED", "FIELD_CONFLICT", targetId, { field: conflict });
          } else {
            target.fields = Object.assign({}, source.fields, target.fields);
            source.active = false;
            for (const [alias, mapped] of aliases.entries()) if (mapped === sourceId) aliases.set(alias, targetId);
            out = receipt(event, index, "ACCEPTED", "MERGED", targetId, { source_contact_id: sourceId });
          }
        }
      }
      seen.set(eventId, { hash: eventHash, receipt: out });
      receipts.push(out);
    });

    const active = Array.from(contacts.values()).filter(c => c.active).sort((a, b) => a.id.localeCompare(b.id));
    const departments = {};
    active.forEach(c => {
      const department = clean(c.fields.department) || "unassigned";
      departments[department] = (departments[department] || 0) + 1;
    });
    const accepted = receipts.filter(r => r.status === "ACCEPTED").length;
    const rejected = receipts.filter(r => r.status === "REJECTED").length;
    const replayed = receipts.filter(r => r.status === "REPLAYED").length;
    const result = {
      contacts: active,
      receipts,
      dashboard: {
        canonical_contacts: active.length,
        department_counts: departments,
        reconciles: Object.values(departments).reduce((a, b) => a + b, 0) === active.length
      },
      totals: { submitted: events.length, accepted, rejected, replayed }
    };
    return Object.assign(result, { run_hash: hash(result) });
  }

  return { run, canonical, hash };
});
