import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { BidBridgeError, compileBidBridge, formatMinutes, moneyLabel } from './bidbridge.js';

const here = dirname(fileURLToPath(import.meta.url));
const demo = JSON.parse(readFileSync(join(here, 'demo-opportunity.json'), 'utf8'));
const clone = x => structuredClone(x);
const AS_OF = '2026-09-13T14:00:00.000Z';
const D = c => c.repeat(64);
const expectCode = (fn, code) => assert.throws(fn, error => error instanceof BidBridgeError && error.code === code);

function readyInput() {
  const x = clone(demo);
  for (const row of x.evidence) {
    row.status = 'SATISFIED';
    row.naAuthorityDigest = null;
  }
  x.teaming = [];
  return x;
}

test('checked-in synthetic demo produces recoverable gap review', () => {
  const result = compileBidBridge(demo, { asOf: AS_OF });
  assert.equal(result.evaluation.state, 'READY_FOR_GAP_REVIEW');
  assert.equal(result.evaluation.remainingEffortHours, 12);
  assert.equal(result.evaluation.usablePrepHours, 22);
  assert.equal(result.opportunity.referenceAmountCents, 18000000);
  assert.equal(result.authorities.bidSubmission, false);
  assert.equal(result.authorities.partnerContact, false);
  assert.deepEqual(result.queue.slice(0, 2).map(x => x.type), ['EXTERNAL_DEPENDENCY', 'PARTIAL_GAP']);
});

test('all mandatory evidence satisfied produces owner bid decision review', () => {
  const result = compileBidBridge(readyInput(), { asOf: AS_OF });
  assert.equal(result.evaluation.state, 'READY_FOR_BID_DECISION');
  assert.equal(result.evaluation.remainingEffortHours, 0);
});

test('pre-open opportunity is not open when evidence itself is current', () => {
  const x = readyInput();
  x.opportunity.capturedAt = '2026-09-12T08:00:00.000Z';
  x.opportunity.opensAt = '2026-09-14T08:00:00.000Z';
  x.evidence.forEach(row => { row.observedAt = '2026-09-12T10:00:00.000Z'; });
  assert.equal(compileBidBridge(x, { asOf: AS_OF }).evaluation.state, 'NOT_OPEN');
});

test('exact submission deadline boundary is no-bid review required', () => {
  const x = readyInput();
  x.capacityPolicy.maxEvidenceAgeMinutes = 10000;
  const result = compileBidBridge(x, { asOf: x.opportunity.submissionDueAt });
  assert.equal(result.evaluation.minutesToSubmission, 0);
  assert.equal(result.evaluation.state, 'NO_BID_REVIEW_REQUIRED');
});

test('non-teamable missing mandatory row is a hard blocker', () => {
  const x = readyInput();
  x.evidence.find(row => row.requirementId === 'req-certification').status = 'MISSING';
  const result = compileBidBridge(x, { asOf: AS_OF });
  assert.equal(result.evaluation.state, 'NO_BID_REVIEW_REQUIRED');
  assert.equal(result.queue[0].type, 'HARD_BLOCKER');
});

test('teamable missing row remains an explicit recoverable gap', () => {
  const x = readyInput();
  x.evidence.find(row => row.requirementId === 'req-field-capacity').status = 'MISSING';
  const result = compileBidBridge(x, { asOf: AS_OF });
  assert.equal(result.evaluation.state, 'READY_FOR_GAP_REVIEW');
  assert.ok(result.queue.some(item => item.type === 'EXTERNAL_DEPENDENCY'));
});

test('explicit N/A requires an authority digest', () => {
  const x = readyInput();
  const row = x.evidence[0];
  row.status = 'NOT_APPLICABLE_CONFIRMED';
  row.naAuthorityDigest = D('f');
  assert.equal(compileBidBridge(x, { asOf: AS_OF }).evaluation.state, 'READY_FOR_BID_DECISION');
  row.naAuthorityDigest = null;
  const held = compileBidBridge(x, { asOf: AS_OF });
  assert.equal(held.evaluation.state, 'HOLD');
  assert.ok(held.holds.some(item => item.reason === 'NA_AUTHORITY_MISSING'));
});

test('missing and conflicting requirement evidence HOLD instead of guessing', () => {
  const missing = readyInput();
  missing.evidence.pop();
  assert.equal(compileBidBridge(missing, { asOf: AS_OF }).evaluation.state, 'HOLD');

  const conflict = readyInput();
  const row = clone(conflict.evidence[0]);
  row.eventId = 'ev-conflict-2';
  row.status = 'MISSING';
  conflict.evidence.push(row);
  const result = compileBidBridge(conflict, { asOf: AS_OF });
  assert.equal(result.evaluation.state, 'HOLD');
  assert.ok(result.holds.some(item => item.reason === 'CONFLICTING_REQUIREMENT_EVIDENCE'));
});

test('changed bytes under the same evidence event id HOLD', () => {
  const x = readyInput();
  const row = clone(x.evidence[0]);
  row.status = 'MISSING';
  x.evidence.push(row);
  const result = compileBidBridge(x, { asOf: AS_OF });
  assert.equal(result.evaluation.state, 'HOLD');
  assert.ok(result.holds.some(item => item.reason === 'CONFLICTING_EVENT_ID'));
});

test('future, stale, and prior-revision evidence HOLD', () => {
  const future = readyInput();
  future.evidence[0].observedAt = '2026-09-13T14:01:00.000Z';
  assert.equal(compileBidBridge(future, { asOf: AS_OF }).evaluation.state, 'HOLD');

  const stale = readyInput();
  stale.capacityPolicy.maxEvidenceAgeMinutes = 30;
  assert.equal(compileBidBridge(stale, { asOf: AS_OF }).evaluation.state, 'HOLD');

  const oldRevision = readyInput();
  oldRevision.evidence[0].opportunityRevision = 2;
  assert.equal(compileBidBridge(oldRevision, { asOf: AS_OF }).evaluation.state, 'HOLD');
});

test('question deadline warning appears inside owner warning window', () => {
  const x = readyInput();
  x.opportunity.questionsDueAt = '2026-09-13T16:00:00.000Z';
  x.capacityPolicy.questionWarningMinutes = 120;
  const result = compileBidBridge(x, { asOf: AS_OF });
  assert.ok(result.queue.some(item => item.type === 'QUESTION_DEADLINE_WARNING'));
});

test('capacity threshold is exact and one-hour shortfall blocks pursuit review', () => {
  const x = readyInput();
  x.evidence.find(row => row.requirementId === 'req-technical-plan').status = 'PARTIAL';
  x.capacityPolicy.availablePrepHours = 13;
  x.capacityPolicy.reserveHours = 6;
  assert.equal(compileBidBridge(x, { asOf: AS_OF }).evaluation.state, 'READY_FOR_GAP_REVIEW');
  x.capacityPolicy.availablePrepHours = 12;
  assert.equal(compileBidBridge(x, { asOf: AS_OF }).evaluation.state, 'NO_BID_REVIEW_REQUIRED');
});

test('partner evidence never becomes partner-contact authority', () => {
  const result = compileBidBridge(demo, { asOf: AS_OF });
  const teamReq = result.requirements.find(row => row.requirementId === 'req-field-capacity');
  assert.equal(teamReq.teamState, 'IDENTIFIED');
  assert.equal(result.authorities.partnerContact, false);
  assert.equal(result.authorities.teamingCommitment, false);
});

test('teaming row on non-teamable requirement HOLDs', () => {
  const x = readyInput();
  x.teaming = [{
    requirementId: 'req-certification', partnerCandidateId: 'candidate-02', state: 'IDENTIFIED',
    observedAt: '2026-09-13T12:30:00.000Z', evidenceDigest: D('f'),
  }];
  const result = compileBidBridge(x, { asOf: AS_OF });
  assert.equal(result.evaluation.state, 'HOLD');
  assert.ok(result.holds.some(item => item.reason === 'TEAMING_NOT_ALLOWED'));
});

test('input ordering cannot change the deterministic review result', () => {
  const a = readyInput();
  const b = readyInput();
  b.opportunity.requirements.reverse();
  b.evidence.reverse();
  assert.deepEqual(compileBidBridge(a, { asOf: AS_OF }), compileBidBridge(b, { asOf: AS_OF }));
});

test('PII and secret-shaped durable refs are rejected', () => {
  const pii = readyInput();
  pii.evidence[0].evidenceRef = 'owner@example.com';
  expectCode(() => compileBidBridge(pii, { asOf: AS_OF }), 'SENSITIVE_TEXT');
  const secret = readyInput();
  secret.opportunity.sourceRef = 'secret/token';
  expectCode(() => compileBidBridge(secret, { asOf: AS_OF }), 'SENSITIVE_TEXT');
});

test('bool-as-int and unsafe money are rejected', () => {
  const boolAlias = readyInput();
  boolAlias.capacityPolicy.availablePrepHours = true;
  expectCode(() => compileBidBridge(boolAlias, { asOf: AS_OF }), 'INVALID_INTEGER');
  const unsafe = readyInput();
  unsafe.opportunity.referenceAmountCents = Number.MAX_SAFE_INTEGER + 1;
  expectCode(() => compileBidBridge(unsafe, { asOf: AS_OF }), 'INVALID_INTEGER');
});

test('noncanonical timestamps fail closed', () => {
  const x = readyInput();
  x.opportunity.capturedAt = '2026-09-13T12:00:00Z';
  expectCode(() => compileBidBridge(x, { asOf: AS_OF }), 'NONCANONICAL_TIMESTAMP');
});

test('presentation helpers preserve truth labels', () => {
  assert.equal(formatMinutes(3000), '2d 2h');
  assert.equal(formatMinutes(-5), '5 min past deadline');
  assert.equal(moneyLabel('USD', 12345), 'USD 123.45 source reference');
  assert.equal(moneyLabel(null, null), 'Not supplied');
});

test('browser shell never uses innerHTML or embeds executable candidate strings', () => {
  const html = readFileSync(join(here, 'index.html'), 'utf8');
  const js = readFileSync(join(here, 'bidbridge.js'), 'utf8');
  assert.doesNotMatch(html, /innerHTML/i);
  assert.doesNotMatch(js, /innerHTML/i);
  assert.match(js, /textContent/);
});
