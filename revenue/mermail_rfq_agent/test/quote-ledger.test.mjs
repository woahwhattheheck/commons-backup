import assert from 'node:assert/strict';
import test from 'node:test';
import { RFQError, RFQLedger } from '../src/quote-ledger.mjs';

const ledger = () => new RFQLedger({
  rfqId: 'rfq-demo-01',
  requirements: { item: 'precision gasket', material: 'FKM-75', quantity: 1000 },
  requestedQuantity: 1000,
  createdAt: '2026-09-13T08:30:00Z',
});
const vendor = (l, id = 'alpha', email = 'quotes@alpha.example', threadId = 'thread-alpha', solicitedAt = '2026-09-13T08:31:00Z') =>
  l.registerVendor({ vendorId: id, email, threadId, solicitedAt });
const quote = (overrides = {}) => ({
  vendorId: 'alpha', senderEmail: 'quotes@alpha.example', threadId: 'thread-alpha', quoteId: 'q-alpha-v1', version: 1,
  currency: 'USD', unitPrice: 4.25, totalPrice: 4250, minimumOrderQuantity: 500, leadTimeDays: 14,
  validUntil: '2026-10-01T00:00:00Z', shippingIncluded: false, incoterm: 'FOB', taxIncluded: false,
  warranty: '12 months', receivedAt: '2026-09-13T09:00:00Z', sourceEmailId: 'email-alpha-v1', ...overrides,
});

const rejects = (fn, code) => assert.throws(fn, (error) => error instanceof RFQError && error.code === code);

test('freezes a deterministic requirements digest', () => {
  const l = ledger();
  assert.match(l.round.requirementsDigest, /^[a-f0-9]{64}$/);
  assert.equal(l.round.rfqId, 'rfq-demo-01');
});

test('hashes nested requirements independent of object key order', () => {
  const a = new RFQLedger({ rfqId: 'x', requirements: { spec: { b: 2, a: 1 }, qty: 4 }, createdAt: '2026-09-13T00:00:00Z' });
  const b = new RFQLedger({ rfqId: 'x', requirements: { qty: 4, spec: { a: 1, b: 2 } }, createdAt: '2026-09-13T00:00:00Z' });
  assert.equal(a.round.requirementsDigest, b.round.requirementsDigest);
});

test('rejects requirement values that JSON would silently erase or coerce', () => {
  const cyclic = { item: 'gasket' };
  cyclic.self = cyclic;
  const sparse = [];
  sparse.length = 1;
  const invalid = [
    { item: undefined },
    { item: NaN },
    { item: Infinity },
    { item: new Date('2026-09-13T00:00:00Z') },
    { item: sparse },
    cyclic,
  ];
  for (const requirements of invalid) {
    rejects(
      () => new RFQLedger({ rfqId: 'strict-json', requirements, createdAt: '2026-09-13T00:00:00Z' }),
      'invalid_requirements',
    );
  }
});

test('keeps distinct supported JSON requirements on distinct digests', () => {
  const a = new RFQLedger({ rfqId: 'x', requirements: { spec: null }, createdAt: '2026-09-13T00:00:00Z' });
  const b = new RFQLedger({ rfqId: 'x', requirements: { spec: 'null' }, createdAt: '2026-09-13T00:00:00Z' });
  assert.notEqual(a.round.requirementsDigest, b.round.requirementsDigest);
});

test('rejects vendor solicitation before RFQ round creation', () => {
  const l = ledger();
  rejects(() => vendor(l, 'alpha', 'quotes@alpha.example', 'thread-alpha', '2026-09-13T08:29:59Z'), 'solicitation_before_round');
});

test('rejects string booleans instead of coercing commercial terms', () => {
  const l = ledger(); vendor(l);
  rejects(() => l.recordQuote(quote({ shippingIncluded: 'false' })), 'invalid_boolean');
});

test('requires one isolated thread per vendor', () => {
  const l = ledger(); vendor(l);
  rejects(() => vendor(l, 'beta', 'quotes@beta.example', 'thread-alpha'), 'duplicate_thread');
});

test('rejects spoofed sender identity', () => {
  const l = ledger(); vendor(l);
  rejects(() => l.recordQuote(quote({ senderEmail: 'attacker@example.net' })), 'sender_mismatch');
});

test('rejects thread drift even from the expected email', () => {
  const l = ledger(); vendor(l);
  rejects(() => l.recordQuote(quote({ threadId: 'thread-other' })), 'thread_mismatch');
});

test('rejects quote evidence timestamped before solicitation', () => {
  const l = ledger(); vendor(l);
  rejects(() => l.recordQuote(quote({ receivedAt: '2026-09-13T08:30:59Z' })), 'quote_before_solicitation');
});

test('accepts quote evidence exactly at the solicitation timestamp', () => {
  const l = ledger(); vendor(l);
  const accepted = l.recordQuote(quote({ receivedAt: '2026-09-13T08:31:00Z' }));
  assert.equal(accepted.receivedAt, '2026-09-13T08:31:00.000Z');
});

test('never infers a missing price', () => {
  const l = ledger(); vendor(l);
  rejects(() => l.recordQuote(quote({ unitPrice: null, totalPrice: null })), 'missing_price');
});

test('idempotently accepts an exact quote replay', () => {
  const l = ledger(); vendor(l);
  const a = l.recordQuote(quote());
  const b = l.recordQuote(quote());
  assert.deepEqual(a, b);
  assert.equal(l.snapshot().quotes.length, 1);
});

test('rejects quote id reuse with changed terms', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote());
  rejects(() => l.recordQuote(quote({ unitPrice: 3.99 })), 'quote_id_conflict');
});

test('reserves one source email to one immutable quote evidence identity', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote());
  rejects(
    () => l.recordQuote(quote({
      quoteId: 'q-alpha-v2',
      version: 2,
      unitPrice: 0.01,
      totalPrice: 10,
      receivedAt: '2026-09-13T10:00:00Z',
      sourceEmailId: 'email-alpha-v1',
    })),
    'source_email_conflict',
  );
  const report = l.comparison({ at: '2026-09-13T11:00:00Z' });
  assert.equal(report.rows[0].quoteId, 'q-alpha-v1');
  assert.equal(report.rows[0].unitPrice, 4.25);
});

test('source email reservation is global across vendors', () => {
  const l = ledger();
  vendor(l);
  vendor(l, 'beta', 'quotes@beta.example', 'thread-beta');
  l.recordQuote(quote());
  rejects(
    () => l.recordQuote(quote({
      vendorId: 'beta',
      senderEmail: 'quotes@beta.example',
      threadId: 'thread-beta',
      quoteId: 'q-beta-v1',
      version: 1,
      sourceEmailId: 'email-alpha-v1',
    })),
    'source_email_conflict',
  );
});

test('requires strictly increasing amendment versions', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote());
  rejects(() => l.recordQuote(quote({ quoteId: 'q-alpha-other', version: 1, sourceEmailId: 'email-alpha-other' })), 'version_regression');
});

test('accepts a same-thread higher-version amendment and supersedes it for comparison', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote());
  l.recordQuote(quote({ quoteId: 'q-alpha-v2', version: 2, unitPrice: 4.10, totalPrice: 4100, receivedAt: '2026-09-13T10:00:00Z', sourceEmailId: 'email-alpha-v2' }));
  const report = l.comparison({ at: '2026-09-14T00:00:00Z' });
  assert.equal(report.rows[0].version, 2);
  assert.equal(report.rows[0].unitPrice, 4.10);
});

test('does not leak a future quote into a backdated comparison', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote({ receivedAt: '2026-09-13T10:00:00Z' }));
  const report = l.comparison({ at: '2026-09-13T09:59:59Z' });
  assert.equal(report.rows[0].status, 'no_quote');
  assert.equal('quoteId' in report.rows[0], false);
  assert.deepEqual(report.ranking, []);
});

test('later amendment becomes visible only at its receivedAt boundary', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote());
  l.recordQuote(quote({ quoteId: 'q-alpha-v2', version: 2, unitPrice: 4.10, totalPrice: 4100, receivedAt: '2026-09-13T10:00:00Z', sourceEmailId: 'email-alpha-v2' }));
  const before = l.comparison({ at: '2026-09-13T09:59:59Z' });
  const atBoundary = l.comparison({ at: '2026-09-13T10:00:00Z' });
  assert.equal(before.rows[0].version, 1);
  assert.equal(before.rows[0].quoteId, 'q-alpha-v1');
  assert.equal(atBoundary.rows[0].version, 2);
  assert.equal(atBoundary.rows[0].quoteId, 'q-alpha-v2');
});

test('marks expired quotes instead of ranking them', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote({ validUntil: '2026-09-13T09:30:00Z' }));
  const report = l.comparison({ at: '2026-09-14T00:00:00Z' });
  assert.equal(report.rows[0].status, 'expired');
  assert.deepEqual(report.ranking, []);
});

test('does not rank cross-currency quotes', () => {
  const l = ledger(); vendor(l); vendor(l, 'beta', 'quotes@beta.example', 'thread-beta');
  l.recordQuote(quote());
  l.recordQuote(quote({ vendorId: 'beta', senderEmail: 'quotes@beta.example', threadId: 'thread-beta', quoteId: 'q-beta-v1', currency: 'EUR', unitPrice: 3.8, totalPrice: 3800, sourceEmailId: 'email-beta-v1' }));
  const report = l.comparison({ at: '2026-09-14T00:00:00Z' });
  assert.equal(report.rankingBasis, 'not_rankable_without_same_currency_explicit_unit_prices');
  assert.deepEqual(report.ranking, []);
});

test('ranks same-currency explicit unit prices without authorizing an award', () => {
  const l = ledger(); vendor(l); vendor(l, 'beta', 'quotes@beta.example', 'thread-beta');
  l.recordQuote(quote());
  l.recordQuote(quote({ vendorId: 'beta', senderEmail: 'quotes@beta.example', threadId: 'thread-beta', quoteId: 'q-beta-v1', unitPrice: 4.05, totalPrice: 4050, sourceEmailId: 'email-beta-v1' }));
  const report = l.comparison({ at: '2026-09-14T00:00:00Z' });
  assert.deepEqual(report.ranking.map((x) => x.vendorId), ['beta', 'alpha']);
  assert.equal(report.awardAuthorized, false);
  assert.equal(report.paymentAuthorized, false);
});

test('flags MOQ above requested quantity instead of silently changing quantity', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote({ minimumOrderQuantity: 2500 }));
  const report = l.comparison({ at: '2026-09-14T00:00:00Z' });
  assert.equal(report.rows[0].status, 'quantity_mismatch');
});

test('preserves unknown terms as explicit missing fields', () => {
  const l = ledger(); vendor(l); l.recordQuote(quote({ leadTimeDays: null, shippingIncluded: null, taxIncluded: null, validUntil: null }));
  const report = l.comparison({ at: '2026-09-14T00:00:00Z' });
  assert.deepEqual(report.rows[0].missingTerms.sort(), ['leadTimeDays', 'shippingIncluded', 'taxIncluded', 'validUntil'].sort());
});

test('snapshot never contains award or payment authority', () => {
  const l = ledger();
  assert.deepEqual(l.snapshot().authority, { awardAuthorized: false, paymentAuthorized: false });
});
