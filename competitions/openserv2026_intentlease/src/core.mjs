import { createHash, randomBytes } from 'node:crypto'

export const RECEIPT_SCHEMA = 'intentlease.receipt.v1'
export const STATE_SCHEMA = 'intentlease.state.v1'
export const AUTHORITY = Object.freeze({
  send: false,
  contact: false,
  pay: false,
  deploy: false,
  sign: false,
  post: false
})

const ACTION_KINDS = new Set([
  'email',
  'form_submit',
  'provider_mutation',
  'payment_request',
  'deploy',
  'sign',
  'social_post',
  'other_consequential'
])
const OPAQUE_REF = /^[A-Za-z0-9][A-Za-z0-9:_./-]{2,127}$/
const KEY = /^[A-Za-z0-9][A-Za-z0-9:_./-]{1,95}$/

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false
  const proto = Object.getPrototypeOf(value)
  return proto === Object.prototype || proto === null
}

export function canonicalJson(value) {
  const walk = current => {
    if (current === null || typeof current === 'string' || typeof current === 'boolean') return current
    if (typeof current === 'number') {
      if (!Number.isFinite(current)) throw new TypeError('non-finite numbers are not canonical JSON')
      if (Object.is(current, -0)) return 0
      return current
    }
    if (Array.isArray(current)) {
      if (Object.keys(current).some(k => !/^\d+$/.test(k))) throw new TypeError('arrays may not have named properties')
      return current.map(walk)
    }
    if (!isPlainObject(current)) throw new TypeError('only plain JSON objects are supported')
    const out = Object.create(null)
    for (const key of Object.keys(current).sort()) {
      if (current[key] === undefined) throw new TypeError(`undefined is not canonical JSON: ${key}`)
      out[key] = walk(current[key])
    }
    return out
  }
  return JSON.stringify(walk(value))
}

export function sha256(value) {
  const bytes = typeof value === 'string' ? value : canonicalJson(value)
  return createHash('sha256').update(bytes).digest('hex')
}

function requireString(value, name, pattern = KEY) {
  if (typeof value !== 'string' || !pattern.test(value)) throw new TypeError(`invalid ${name}`)
  return value
}

export function validateNormalizedIntent(intent) {
  if (!isPlainObject(intent)) throw new TypeError('normalized intent must be a plain object')
  const keys = Object.keys(intent).sort()
  const expected = ['actionKind', 'generation', 'purposeKey', 'sourceHash', 'targetRef']
  if (canonicalJson(keys) !== canonicalJson(expected)) throw new TypeError('normalized intent has unknown or missing fields')
  if (!ACTION_KINDS.has(intent.actionKind)) throw new TypeError('unsupported actionKind')
  requireString(intent.targetRef, 'targetRef', OPAQUE_REF)
  if (intent.targetRef.includes('@') || /^https?:/i.test(intent.targetRef)) throw new TypeError('targetRef must be opaque, not direct contact/provider data')
  requireString(intent.purposeKey, 'purposeKey', KEY)
  requireString(intent.generation, 'generation', KEY)
  if (typeof intent.sourceHash !== 'string' || !/^[a-f0-9]{64}$/.test(intent.sourceHash)) throw new TypeError('invalid sourceHash')
  return Object.freeze({ ...intent })
}

export function intentIdentity(intent) {
  const n = validateNormalizedIntent(intent)
  return `intent:${sha256({ actionKind: n.actionKind, targetRef: n.targetRef, purposeKey: n.purposeKey, generation: n.generation })}`
}

export function emptyState() {
  return { schema: STATE_SCHEMA, generation: 0, leases: {}, requests: {} }
}

function cloneState(state) {
  if (!isPlainObject(state) || state.schema !== STATE_SCHEMA) throw new TypeError('invalid state schema')
  return JSON.parse(canonicalJson(state))
}

function receipt(body) {
  const withoutHash = { schema: RECEIPT_SCHEMA, authority: AUTHORITY, ...body }
  return { ...withoutHash, receiptHash: sha256(withoutHash) }
}

export function verifyReceipt(candidate) {
  if (!isPlainObject(candidate) || candidate.schema !== RECEIPT_SCHEMA) return false
  const { receiptHash, ...withoutHash } = candidate
  return typeof receiptHash === 'string' && /^[a-f0-9]{64}$/.test(receiptHash) && sha256(withoutHash) === receiptHash && canonicalJson(candidate.authority) === canonicalJson(AUTHORITY)
}

export class IntentLeaseRegistry {
  constructor({ state = emptyState(), tokenFactory } = {}) {
    this.state = cloneState(state)
    this.tokenFactory = tokenFactory ?? (() => randomBytes(24).toString('hex'))
  }

  snapshot() {
    return cloneState(this.state)
  }

  acquire({ writerId, requestId, intent, leaseMs = 10 * 60_000 }, nowMs = Date.now()) {
    requireString(writerId, 'writerId', KEY)
    requireString(requestId, 'requestId', KEY)
    if (!Number.isSafeInteger(nowMs) || nowMs < 0) throw new TypeError('invalid nowMs')
    if (!Number.isSafeInteger(leaseMs) || leaseMs < 1_000 || leaseMs > 24 * 60 * 60_000) throw new TypeError('invalid leaseMs')
    const normalized = validateNormalizedIntent(intent)
    const identity = intentIdentity(normalized)
    const requestKey = `${writerId}:${requestId}`
    const requestHash = sha256({ writerId, requestId, intent: normalized, leaseMs })
    const before = cloneState(this.state)
    const beforeHash = sha256(before)
    const replay = before.requests[requestKey]
    if (replay) {
      if (replay.requestHash !== requestHash) throw new Error('requestId replay changed request material')
      return receipt({ operation: 'acquire', status: replay.status, replay: true, identity, writerId, requestId, lease: replay.lease ?? null, conflict: replay.conflict ?? null, stateBeforeHash: beforeHash, stateAfterHash: beforeHash })
    }

    const live = before.leases[identity]
    const next = cloneState(before)
    let status
    let lease = null
    let conflict = null
    if (live && live.expiresAtMs > nowMs) {
      status = 'COLLISION'
      conflict = { identity, ownerWriterId: live.writerId, expiresAtMs: live.expiresAtMs, leaseTokenHash: live.leaseTokenHash }
    } else {
      status = live ? 'RECLAIMED_AFTER_EXPIRY' : 'LEASED'
      const leaseToken = this.tokenFactory()
      if (typeof leaseToken !== 'string' || leaseToken.length < 16) throw new TypeError('tokenFactory returned weak/invalid token')
      lease = { identity, writerId, acquiredAtMs: nowMs, expiresAtMs: nowMs + leaseMs, leaseToken, leaseTokenHash: sha256(leaseToken), normalizedIntentHash: sha256(normalized) }
      next.leases[identity] = { ...lease, leaseToken: undefined }
      delete next.leases[identity].leaseToken
    }
    next.requests[requestKey] = { requestHash, status, lease: lease ? { ...lease } : null, conflict }
    next.generation += 1
    const afterHash = sha256(next)
    this.state = next
    return receipt({ operation: 'acquire', status, replay: false, identity, writerId, requestId, lease, conflict, stateBeforeHash: beforeHash, stateAfterHash: afterHash })
  }

  release({ writerId, requestId, intent, leaseToken }, nowMs = Date.now()) {
    return this.#mutateLease('release', { writerId, requestId, intent, leaseToken }, nowMs)
  }

  transfer({ writerId, requestId, intent, leaseToken, newWriterId }, nowMs = Date.now()) {
    requireString(newWriterId, 'newWriterId', KEY)
    return this.#mutateLease('transfer', { writerId, requestId, intent, leaseToken, newWriterId }, nowMs)
  }

  #mutateLease(operation, args, nowMs) {
    const { writerId, requestId, intent, leaseToken, newWriterId } = args
    requireString(writerId, 'writerId', KEY)
    requireString(requestId, 'requestId', KEY)
    if (typeof leaseToken !== 'string' || leaseToken.length < 16) throw new TypeError('invalid leaseToken')
    if (!Number.isSafeInteger(nowMs) || nowMs < 0) throw new TypeError('invalid nowMs')
    const normalized = validateNormalizedIntent(intent)
    const identity = intentIdentity(normalized)
    const before = cloneState(this.state)
    const beforeHash = sha256(before)
    const current = before.leases[identity]
    let status = 'REJECTED'
    const next = cloneState(before)
    let lease = null
    if (current && current.expiresAtMs > nowMs && current.writerId === writerId && current.leaseTokenHash === sha256(leaseToken)) {
      if (operation === 'release') {
        delete next.leases[identity]
        status = 'RELEASED'
      } else {
        next.leases[identity] = { ...current, writerId: newWriterId }
        status = 'TRANSFERRED'
        lease = { ...next.leases[identity] }
      }
      next.generation += 1
      this.state = next
    }
    const afterHash = sha256(this.state)
    return receipt({ operation, status, replay: false, identity, writerId, newWriterId: newWriterId ?? null, requestId, lease, stateBeforeHash: beforeHash, stateAfterHash: afterHash })
  }
}
