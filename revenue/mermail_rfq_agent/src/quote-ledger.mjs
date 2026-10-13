import { createHash } from 'node:crypto';

export class RFQError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'RFQError';
    this.code = code;
  }
}

const clone = (value) => structuredClone(value);
const canonicalEmail = (value) => {
  if (typeof value !== 'string') throw new RFQError('invalid_email', 'email must be text');
  const email = value.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new RFQError('invalid_email', 'email must be syntactically valid');
  return email;
};
const text = (value, field) => {
  if (typeof value !== 'string' || !value.trim()) throw new RFQError('invalid_text', `${field} must be non-empty text`);
  return value.trim();
};
const isoInstant = (value, field) => {
  const raw = text(value, field);
  const ms = Date.parse(raw);
  if (!Number.isFinite(ms)) throw new RFQError('invalid_time', `${field} must be ISO-8601 compatible`);
  return new Date(ms).toISOString();
};
const optionalInstant = (value, field) => value == null ? null : isoInstant(value, field);
const nullableText = (value, field) => value == null ? null : text(value, field);
const positiveInteger = (value, field, { nullable = true } = {}) => {
  if (value == null && nullable) return null;
  if (!Number.isInteger(value) || value <= 0) throw new RFQError('invalid_integer', `${field} must be a positive integer`);
  return value;
};
const nonNegativeInteger = (value, field) => {
  if (value == null) return null;
  if (!Number.isInteger(value) || value < 0) throw new RFQError('invalid_integer', `${field} must be a non-negative integer`);
  return value;
};
const positiveMoney = (value, field) => {
  if (value == null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    throw new RFQError('invalid_money', `${field} must be a positive finite number`);
  }
  return value;
};
const currency = (value) => {
  const code = text(value, 'currency').toUpperCase();
  if (!/^[A-Z]{3}$/.test(code)) throw new RFQError('invalid_currency', 'currency must be an explicit ISO-style 3-letter code');
  return code;
};

const strictJsonClone = (value, field = 'value', seen = new Set()) => {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new RFQError('invalid_requirements', `${field} must contain only finite JSON numbers`);
    return Object.is(value, -0) ? 0 : value;
  }
  if (typeof value !== 'object') {
    throw new RFQError('invalid_requirements', `${field} contains a value that JSON would erase or coerce`);
  }
  if (seen.has(value)) throw new RFQError('invalid_requirements', `${field} must not contain cycles`);
  seen.add(value);
  try {
    const descriptors = Object.getOwnPropertyDescriptors(value);
    if (Array.isArray(value)) {
      for (const key of Reflect.ownKeys(descriptors)) {
        if (typeof key !== 'string') throw new RFQError('invalid_requirements', `${field} must not contain symbol properties`);
        if (key === 'length') continue;
        if (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= value.length) {
          throw new RFQError('invalid_requirements', `${field} arrays must not contain extra properties`);
        }
        const descriptor = descriptors[key];
        if (!descriptor.enumerable || !Object.hasOwn(descriptor, 'value')) {
          throw new RFQError('invalid_requirements', `${field}[${key}] must be an enumerable data value`);
        }
      }
      const result = [];
      for (let index = 0; index < value.length; index += 1) {
        const descriptor = descriptors[String(index)];
        if (!descriptor || !descriptor.enumerable || !Object.hasOwn(descriptor, 'value')) {
          throw new RFQError('invalid_requirements', `${field} arrays must not be sparse`);
        }
        result.push(strictJsonClone(descriptor.value, `${field}[${index}]`, seen));
      }
      return result;
    }

    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new RFQError('invalid_requirements', `${field} must contain only plain JSON objects`);
    }
    const keys = Reflect.ownKeys(descriptors);
    if (keys.some((key) => typeof key !== 'string')) {
      throw new RFQError('invalid_requirements', `${field} must not contain symbol properties`);
    }
    const entries = [];
    for (const key of keys.sort()) {
      const descriptor = descriptors[key];
      if (!descriptor.enumerable || !Object.hasOwn(descriptor, 'value')) {
        throw new RFQError('invalid_requirements', `${field}.${key} must be an enumerable data value`);
      }
      entries.push([key, strictJsonClone(descriptor.value, `${field}.${key}`, seen)]);
    }
    return Object.fromEntries(entries);
  } finally {
    seen.delete(value);
  }
};
const canonicalJson = (value) => JSON.stringify(strictJsonClone(value));
const digest = (value) => createHash('sha256').update(canonicalJson(value)).digest('hex');
const nullableBoolean = (value, field) => {
  if (value == null) return null;
  if (typeof value !== 'boolean') throw new RFQError('invalid_boolean', `${field} must be true, false, or null`);
  return value;
};

export class RFQLedger {
  #round;
  #vendors = new Map();
  #quotes = new Map();
  #quoteIds = new Map();
  #sourceEmailIds = new Map();

  constructor({ rfqId, requirements, requestedQuantity = null, createdAt }) {
    const cleanRequirements = strictJsonClone(requirements, 'requirements');
    if (!cleanRequirements || typeof cleanRequirements !== 'object' || Array.isArray(cleanRequirements)) {
      throw new RFQError('invalid_requirements', 'requirements must be a plain JSON object');
    }
    this.#round = Object.freeze({
      rfqId: text(rfqId, 'rfqId'),
      requirements: cleanRequirements,
      requirementsDigest: digest(cleanRequirements),
      requestedQuantity: positiveInteger(requestedQuantity, 'requestedQuantity'),
      createdAt: isoInstant(createdAt, 'createdAt'),
    });
  }

  get round() { return clone(this.#round); }

  registerVendor({ vendorId, email, threadId, displayName = null, solicitedAt }) {
    const id = text(vendorId, 'vendorId');
    if (this.#vendors.has(id)) throw new RFQError('duplicate_vendor', `vendor ${id} already exists`);
    const record = Object.freeze({
      vendorId: id,
      email: canonicalEmail(email),
      threadId: text(threadId, 'threadId'),
      displayName: nullableText(displayName, 'displayName'),
      solicitedAt: isoInstant(solicitedAt, 'solicitedAt'),
    });
    if (Date.parse(record.solicitedAt) < Date.parse(this.#round.createdAt)) {
      throw new RFQError('solicitation_before_round', 'vendor solicitation cannot predate RFQ round creation');
    }
    for (const existing of this.#vendors.values()) {
      if (existing.threadId === record.threadId) throw new RFQError('duplicate_thread', 'each vendor must have an isolated Mermail thread');
    }
    this.#vendors.set(id, record);
    this.#quotes.set(id, []);
    return clone(record);
  }

  recordQuote(input) {
    const vendorId = text(input.vendorId, 'vendorId');
    const vendor = this.#vendors.get(vendorId);
    if (!vendor) throw new RFQError('unknown_vendor', `vendor ${vendorId} is not registered`);
    if (canonicalEmail(input.senderEmail) !== vendor.email) throw new RFQError('sender_mismatch', 'quote sender does not match the solicited vendor identity');
    if (text(input.threadId, 'threadId') !== vendor.threadId) throw new RFQError('thread_mismatch', 'quote arrived on a different thread than the solicitation');

    const quote = Object.freeze({
      vendorId,
      senderEmail: vendor.email,
      threadId: vendor.threadId,
      quoteId: text(input.quoteId, 'quoteId'),
      version: positiveInteger(input.version, 'version', { nullable: false }),
      currency: currency(input.currency),
      unitPrice: positiveMoney(input.unitPrice, 'unitPrice'),
      totalPrice: positiveMoney(input.totalPrice, 'totalPrice'),
      minimumOrderQuantity: positiveInteger(input.minimumOrderQuantity, 'minimumOrderQuantity'),
      leadTimeDays: nonNegativeInteger(input.leadTimeDays, 'leadTimeDays'),
      validUntil: optionalInstant(input.validUntil, 'validUntil'),
      shippingIncluded: nullableBoolean(input.shippingIncluded, 'shippingIncluded'),
      incoterm: nullableText(input.incoterm, 'incoterm'),
      taxIncluded: nullableBoolean(input.taxIncluded, 'taxIncluded'),
      warranty: nullableText(input.warranty, 'warranty'),
      receivedAt: isoInstant(input.receivedAt, 'receivedAt'),
      sourceEmailId: text(input.sourceEmailId, 'sourceEmailId'),
    });
    if (quote.unitPrice == null && quote.totalPrice == null) {
      throw new RFQError('missing_price', 'a quote must state unitPrice or totalPrice; never infer a price');
    }
    if (Date.parse(quote.receivedAt) < Date.parse(vendor.solicitedAt)) {
      throw new RFQError('quote_before_solicitation', 'quote cannot predate the vendor solicitation');
    }

    const fingerprint = digest(quote);
    const existingId = this.#quoteIds.get(quote.quoteId);
    if (existingId) {
      if (existingId.fingerprint !== fingerprint) throw new RFQError('quote_id_conflict', 'quoteId was reused with different commercial facts');
      return clone(existingId.quote);
    }
    const existingSource = this.#sourceEmailIds.get(quote.sourceEmailId);
    if (existingSource) {
      throw new RFQError(
        'source_email_conflict',
        `sourceEmailId ${quote.sourceEmailId} is already bound to quote ${existingSource.quoteId}`,
      );
    }

    const vendorQuotes = this.#quotes.get(vendorId);
    const latest = vendorQuotes.at(-1);
    if (latest && quote.version <= latest.version) {
      throw new RFQError('version_regression', 'quote amendments must have a strictly increasing explicit version');
    }
    if (latest && Date.parse(quote.receivedAt) < Date.parse(latest.receivedAt)) {
      throw new RFQError('time_regression', 'a later quote version cannot predate the current version');
    }

    vendorQuotes.push(quote);
    this.#quoteIds.set(quote.quoteId, { fingerprint, quote });
    this.#sourceEmailIds.set(quote.sourceEmailId, { quoteId: quote.quoteId, fingerprint });
    return clone(quote);
  }

  comparison({ at }) {
    const now = Date.parse(isoInstant(at, 'at'));
    const rows = [];
    for (const [vendorId, vendor] of this.#vendors.entries()) {
      const vendorQuotes = this.#quotes.get(vendorId);
      let quote = null;
      for (let index = vendorQuotes.length - 1; index >= 0; index -= 1) {
        if (Date.parse(vendorQuotes[index].receivedAt) <= now) {
          quote = vendorQuotes[index];
          break;
        }
      }
      if (!quote) {
        rows.push({ vendorId, vendorEmail: vendor.email, status: 'no_quote', missingTerms: ['quote'] });
        continue;
      }
      const expired = quote.validUntil != null && Date.parse(quote.validUntil) < now;
      const missingTerms = [
        ['minimumOrderQuantity', quote.minimumOrderQuantity],
        ['leadTimeDays', quote.leadTimeDays],
        ['shippingIncluded', quote.shippingIncluded],
        ['taxIncluded', quote.taxIncluded],
        ['validUntil', quote.validUntil],
      ].filter(([, value]) => value == null).map(([field]) => field);
      const quantityConflict = this.#round.requestedQuantity != null && quote.minimumOrderQuantity != null
        && quote.minimumOrderQuantity > this.#round.requestedQuantity;
      rows.push({
        vendorId,
        vendorEmail: vendor.email,
        quoteId: quote.quoteId,
        version: quote.version,
        currency: quote.currency,
        unitPrice: quote.unitPrice,
        totalPrice: quote.totalPrice,
        minimumOrderQuantity: quote.minimumOrderQuantity,
        leadTimeDays: quote.leadTimeDays,
        validUntil: quote.validUntil,
        shippingIncluded: quote.shippingIncluded,
        incoterm: quote.incoterm,
        taxIncluded: quote.taxIncluded,
        warranty: quote.warranty,
        sourceEmailId: quote.sourceEmailId,
        status: expired ? 'expired' : quantityConflict ? 'quantity_mismatch' : 'active',
        missingTerms,
      });
    }

    const active = rows.filter((row) => row.status === 'active');
    const currencies = [...new Set(active.map((row) => row.currency))];
    const rankable = currencies.length === 1 && active.length > 0 && active.every((row) => row.unitPrice != null);
    const ranking = rankable
      ? active.map((row) => ({ vendorId: row.vendorId, unitPrice: row.unitPrice, currency: row.currency }))
          .sort((a, b) => a.unitPrice - b.unitPrice || a.vendorId.localeCompare(b.vendorId))
      : [];

    return {
      rfqId: this.#round.rfqId,
      requirementsDigest: this.#round.requirementsDigest,
      comparedAt: new Date(now).toISOString(),
      rows,
      ranking,
      rankingBasis: rankable ? 'explicit_unit_price_same_currency_only' : 'not_rankable_without_same_currency_explicit_unit_prices',
      awardAuthorized: false,
      paymentAuthorized: false,
    };
  }

  snapshot() {
    return {
      round: this.round,
      vendors: [...this.#vendors.values()].map(clone),
      quotes: [...this.#quotes.entries()].flatMap(([, quotes]) => quotes.map(clone)),
      authority: { awardAuthorized: false, paymentAuthorized: false },
    };
  }
}
