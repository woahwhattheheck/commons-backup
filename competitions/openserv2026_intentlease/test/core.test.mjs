import test from 'node:test'
import assert from 'node:assert/strict'
import { AUTHORITY, IntentLeaseRegistry, canonicalJson, emptyState, intentIdentity, sha256, validateNormalizedIntent, verifyReceipt } from '../src/core.mjs'

const baseIntent = Object.freeze({
  actionKind: 'email',
  targetRef: 'crm:lead-2048',
  purposeKey: 'proposal-followup',
  generation: 'proposal-v3',
  sourceHash: sha256('follow up on the accepted discovery proposal')
})
const fixedRegistry = () => new IntentLeaseRegistry({ tokenFactory: () => '0123456789abcdef0123456789abcdef0123456789abcdef' })

test('canonical JSON is key-order independent', () => {
  assert.equal(canonicalJson({ b: 2, a: 1 }), canonicalJson({ a: 1, b: 2 }))
})

test('canonical JSON rejects non-finite numbers and custom prototypes', () => {
  assert.throws(() => canonicalJson({ x: NaN }))
  assert.throws(() => canonicalJson(new Date()))
})

test('normalized intent rejects direct email contact data', () => {
  assert.throws(() => validateNormalizedIntent({ ...baseIntent, targetRef: 'lead@example.com' }))
})

test('normalized intent rejects unknown fields', () => {
  assert.throws(() => validateNormalizedIntent({ ...baseIntent, execute: true }))
})

test('identity is stable for exact semantic candidate', () => {
  assert.equal(intentIdentity(baseIntent), intentIdentity({ ...baseIntent }))
})

test('first writer obtains the only live lease', () => {
  const r = fixedRegistry()
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  const b = r.acquire({ writerId: 'agent-b', requestId: 'req-2', intent: baseIntent }, 1001)
  assert.equal(a.status, 'LEASED')
  assert.equal(b.status, 'COLLISION')
  assert.equal(b.conflict.ownerWriterId, 'agent-a')
})

test('exact request replay is idempotent and does not advance state', () => {
  const r = fixedRegistry()
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  const before = r.snapshot()
  const replay = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 2000)
  assert.equal(replay.status, a.status)
  assert.equal(replay.replay, true)
  assert.deepEqual(r.snapshot(), before)
})

test('requestId replay with changed material is rejected', () => {
  const r = fixedRegistry()
  r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  assert.throws(() => r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: { ...baseIntent, generation: 'proposal-v4' } }, 1001))
})

test('expired lease can be reclaimed by a new writer', () => {
  const r = fixedRegistry()
  r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent, leaseMs: 1000 }, 1000)
  const b = r.acquire({ writerId: 'agent-b', requestId: 'req-2', intent: baseIntent, leaseMs: 1000 }, 2001)
  assert.equal(b.status, 'RECLAIMED_AFTER_EXPIRY')
  assert.equal(b.writerId, 'agent-b')
})

test('different generation does not inherit stale lease', () => {
  const r = fixedRegistry()
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  const b = r.acquire({ writerId: 'agent-b', requestId: 'req-2', intent: { ...baseIntent, generation: 'proposal-v4' } }, 1001)
  assert.equal(a.status, 'LEASED')
  assert.equal(b.status, 'LEASED')
  assert.notEqual(a.identity, b.identity)
})

test('same target but different purpose may coexist', () => {
  const r = fixedRegistry()
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  const b = r.acquire({ writerId: 'agent-b', requestId: 'req-2', intent: { ...baseIntent, purposeKey: 'technical-question' } }, 1001)
  assert.equal(a.status, 'LEASED')
  assert.equal(b.status, 'LEASED')
})

test('release requires exact writer and lease token', () => {
  const r = fixedRegistry()
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  assert.equal(r.release({ writerId: 'agent-b', requestId: 'rel-1', intent: baseIntent, leaseToken: a.lease.leaseToken }, 1001).status, 'REJECTED')
  assert.equal(r.release({ writerId: 'agent-a', requestId: 'rel-2', intent: baseIntent, leaseToken: 'wrong-wrong-wrong-wrong' }, 1001).status, 'REJECTED')
  assert.equal(r.release({ writerId: 'agent-a', requestId: 'rel-3', intent: baseIntent, leaseToken: a.lease.leaseToken }, 1001).status, 'RELEASED')
})

test('transfer preserves exactly one owner and invalidates old owner mutation', () => {
  const r = fixedRegistry()
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  const moved = r.transfer({ writerId: 'agent-a', requestId: 'xfer-1', newWriterId: 'agent-b', intent: baseIntent, leaseToken: a.lease.leaseToken }, 1001)
  assert.equal(moved.status, 'TRANSFERRED')
  assert.equal(moved.lease.writerId, 'agent-b')
  assert.equal(r.release({ writerId: 'agent-a', requestId: 'rel-old', intent: baseIntent, leaseToken: a.lease.leaseToken }, 1002).status, 'REJECTED')
  assert.equal(r.release({ writerId: 'agent-b', requestId: 'rel-new', intent: baseIntent, leaseToken: a.lease.leaseToken }, 1002).status, 'RELEASED')
})

test('all receipts hard-deny side-effect authority', () => {
  const r = fixedRegistry()
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  assert.deepEqual(a.authority, AUTHORITY)
  assert.equal(Object.values(a.authority).some(Boolean), false)
})

test('receipt verification rejects tampering', () => {
  const r = fixedRegistry()
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  assert.equal(verifyReceipt(a), true)
  assert.equal(verifyReceipt({ ...a, status: 'PAY_NOW' }), false)
})

test('50-way race admits exactly one writer', async () => {
  let counter = 0
  const r = new IntentLeaseRegistry({ tokenFactory: () => `race-token-${String(++counter).padStart(32, '0')}` })
  const contenders = Array.from({ length: 50 }, (_, i) => `agent-${String(i).padStart(2, '0')}`)
  const receipts = await Promise.all(contenders.map((writerId, i) => Promise.resolve().then(() => r.acquire({ writerId, requestId: `req-${i}`, intent: baseIntent }, 1000))))
  assert.equal(receipts.filter(x => x.status === 'LEASED').length, 1)
  assert.equal(receipts.filter(x => x.status === 'COLLISION').length, 49)
})

test('two natural-language phrasings normalized to same candidate collide', () => {
  const r = fixedRegistry()
  const normalizedA = { ...baseIntent, sourceHash: sha256('please follow up on the proposal with this lead') }
  const normalizedB = { ...baseIntent, sourceHash: sha256('send the lead our proposal follow-up') }
  const a = r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: normalizedA }, 1000)
  const b = r.acquire({ writerId: 'agent-b', requestId: 'req-2', intent: normalizedB }, 1001)
  assert.equal(a.identity, b.identity)
  assert.equal(b.status, 'COLLISION')
})

test('state snapshots are plain serializable evidence', () => {
  const r = fixedRegistry()
  r.acquire({ writerId: 'agent-a', requestId: 'req-1', intent: baseIntent }, 1000)
  assert.equal(JSON.parse(JSON.stringify(r.snapshot())).schema, emptyState().schema)
})
