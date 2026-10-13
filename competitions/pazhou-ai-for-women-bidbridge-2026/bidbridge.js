export const SCHEMA = 'bidbridge.review-input/v1';

const STATUS = new Set([
  'SATISFIED',
  'PARTIAL',
  'MISSING',
  'NOT_APPLICABLE_CONFIRMED',
  'NEEDS_EXTERNAL_PARTNER',
]);
const TEAM_STATE = new Set(['IDENTIFIED', 'CONTACT_PENDING', 'EVIDENCE_PENDING', 'READY_TO_REVIEW']);
const SUBMISSION_MODE = new Set(['PORTAL', 'EMAIL', 'PHYSICAL', 'OTHER_STRUCTURED']);
const REQUIREMENT_CLASS = new Set([
  'ELIGIBILITY', 'TECHNICAL', 'EXPERIENCE', 'PRICE', 'FORM', 'CERTIFICATION', 'TEAMING', 'OTHER_STRUCTURED',
]);
const DIGEST = /^[0-9a-f]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$/;
const REF = /^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,159}$/;
const CURRENCY = /^[A-Z]{3}$/;
const SECRETISH = /(password|passwd|secret|api[-_]?key|access[-_]?token|authorization|bearer|private[-_]?key|session|cookie)/i;
const EMAILISH = /\b[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+\b/;
const PHONEISH = /(?:^|\D)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?:\D|$)/;

export class BidBridgeError extends Error {
  constructor(code, field = '') {
    super(field ? `${code}: ${field}` : code);
    this.name = 'BidBridgeError';
    this.code = code;
    this.field = field;
  }
}

const fail = (code, field = '') => { throw new BidBridgeError(code, field); };
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
const requireObject = (value, field) => { if (!plain(value)) fail('OBJECT_REQUIRED', field); return value; };
function exactKeys(value, keys, field) {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, i) => key !== expected[i])) fail('SHAPE_MISMATCH', field);
}
function text(value, field, { min = 1, max = 160, pattern = null } = {}) {
  if (typeof value !== 'string' || value.trim() !== value || value.length < min || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) fail('INVALID_TEXT', field);
  if (SECRETISH.test(value) || EMAILISH.test(value) || PHONEISH.test(value) || value.includes('@')) fail('SENSITIVE_TEXT', field);
  if (pattern && !pattern.test(value)) fail('INVALID_TEXT', field);
  return value;
}
const id = (value, field) => text(value, field, { min: 2, max: 96, pattern: ID });
const ref = (value, field) => text(value, field, { min: 1, max: 160, pattern: REF });
function digest(value, field) { if (typeof value !== 'string' || !DIGEST.test(value)) fail('INVALID_DIGEST', field); return value; }
function bool(value, field) { if (typeof value !== 'boolean') fail('INVALID_BOOLEAN', field); return value; }
function integer(value, field, { min = 0, max = Number.MAX_SAFE_INTEGER } = {}) {
  if (typeof value === 'boolean' || !Number.isSafeInteger(value) || value < min || value > max) fail('INVALID_INTEGER', field);
  return value;
}
function timestamp(value, field) {
  if (typeof value !== 'string') fail('INVALID_TIMESTAMP', field);
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) fail('INVALID_TIMESTAMP', field);
  const canonical = new Date(ms).toISOString();
  if (canonical !== value) fail('NONCANONICAL_TIMESTAMP', field);
  return { ms, canonical };
}
const nullableTimestamp = (value, field) => value === null ? null : timestamp(value, field);

function normalizeRequirement(raw, i, submissionDueMs) {
  const row = requireObject(raw, `requirements[${i}]`);
  exactKeys(row, ['requirementId', 'class', 'dueAt', 'evidenceRequired', 'teamingAllowed', 'effortHours'], `requirements[${i}]`);
  const requirementId = id(row.requirementId, `requirements[${i}].requirementId`);
  if (!REQUIREMENT_CLASS.has(row.class)) fail('INVALID_REQUIREMENT_CLASS', requirementId);
  const due = timestamp(row.dueAt, `${requirementId}.dueAt`);
  if (due.ms > submissionDueMs) fail('REQUIREMENT_AFTER_SUBMISSION', requirementId);
  return {
    requirementId,
    class: row.class,
    dueAt: due.canonical,
    evidenceRequired: bool(row.evidenceRequired, `${requirementId}.evidenceRequired`),
    teamingAllowed: bool(row.teamingAllowed, `${requirementId}.teamingAllowed`),
    effortHours: integer(row.effortHours, `${requirementId}.effortHours`, { max: 100000 }),
  };
}

function normalizeOpportunity(raw, asOfMs) {
  const row = requireObject(raw, 'opportunity');
  exactKeys(row, [
    'opportunityId', 'revision', 'sourceDigest', 'sourceRef', 'capturedAt', 'opensAt', 'questionsDueAt',
    'submissionDueAt', 'submissionMode', 'currency', 'referenceAmountCents', 'requirements',
  ], 'opportunity');
  const captured = timestamp(row.capturedAt, 'opportunity.capturedAt');
  if (captured.ms > asOfMs) fail('FUTURE_CAPTURE', 'opportunity.capturedAt');
  const opens = timestamp(row.opensAt, 'opportunity.opensAt');
  const questions = nullableTimestamp(row.questionsDueAt, 'opportunity.questionsDueAt');
  const submission = timestamp(row.submissionDueAt, 'opportunity.submissionDueAt');
  if (opens.ms > submission.ms || (questions && (questions.ms < opens.ms || questions.ms > submission.ms))) fail('INVALID_CHRONOLOGY', 'opportunity');
  if (!SUBMISSION_MODE.has(row.submissionMode)) fail('INVALID_SUBMISSION_MODE', 'opportunity.submissionMode');
  let currency = null;
  let referenceAmountCents = null;
  if (row.currency !== null) {
    if (typeof row.currency !== 'string' || !CURRENCY.test(row.currency)) fail('INVALID_CURRENCY', 'opportunity.currency');
    currency = row.currency;
    referenceAmountCents = integer(row.referenceAmountCents, 'opportunity.referenceAmountCents');
  } else if (row.referenceAmountCents !== null) {
    fail('REFERENCE_AMOUNT_WITHOUT_CURRENCY', 'opportunity.referenceAmountCents');
  }
  if (!Array.isArray(row.requirements) || row.requirements.length === 0 || row.requirements.length > 4096) fail('INVALID_REQUIREMENTS', 'opportunity.requirements');
  const requirements = row.requirements.map((entry, i) => normalizeRequirement(entry, i, submission.ms)).sort((a, b) => a.requirementId.localeCompare(b.requirementId));
  for (let i = 1; i < requirements.length; i += 1) if (requirements[i - 1].requirementId === requirements[i].requirementId) fail('DUPLICATE_REQUIREMENT', requirements[i].requirementId);
  if (requirements.some(req => Date.parse(req.dueAt) < opens.ms)) fail('REQUIREMENT_BEFORE_OPEN', 'opportunity.requirements');
  return {
    opportunityId: id(row.opportunityId, 'opportunity.opportunityId'),
    revision: integer(row.revision, 'opportunity.revision', { min: 1, max: 1000000 }),
    sourceDigest: digest(row.sourceDigest, 'opportunity.sourceDigest'),
    sourceRef: ref(row.sourceRef, 'opportunity.sourceRef'),
    capturedAt: captured.canonical,
    opensAt: opens.canonical,
    questionsDueAt: questions?.canonical ?? null,
    submissionDueAt: submission.canonical,
    submissionMode: row.submissionMode,
    currency,
    referenceAmountCents,
    requirements,
  };
}

function normalizePolicy(raw) {
  const row = requireObject(raw, 'capacityPolicy');
  exactKeys(row, ['availablePrepHours', 'reserveHours', 'minSubmissionBufferMinutes', 'maxEvidenceAgeMinutes', 'questionWarningMinutes'], 'capacityPolicy');
  const availablePrepHours = integer(row.availablePrepHours, 'capacityPolicy.availablePrepHours', { max: 100000 });
  const reserveHours = integer(row.reserveHours, 'capacityPolicy.reserveHours', { max: 100000 });
  if (reserveHours > availablePrepHours) fail('RESERVE_EXCEEDS_AVAILABLE', 'capacityPolicy');
  return {
    availablePrepHours,
    reserveHours,
    minSubmissionBufferMinutes: integer(row.minSubmissionBufferMinutes, 'capacityPolicy.minSubmissionBufferMinutes', { max: 5256000 }),
    maxEvidenceAgeMinutes: integer(row.maxEvidenceAgeMinutes, 'capacityPolicy.maxEvidenceAgeMinutes', { min: 1, max: 5256000 }),
    questionWarningMinutes: integer(row.questionWarningMinutes, 'capacityPolicy.questionWarningMinutes', { max: 5256000 }),
  };
}

function normalizeEvidence(raw, i) {
  const row = requireObject(raw, `evidence[${i}]`);
  exactKeys(row, ['eventId', 'requirementId', 'opportunityRevision', 'status', 'observedAt', 'evidenceDigest', 'evidenceRef', 'naAuthorityDigest'], `evidence[${i}]`);
  if (!STATUS.has(row.status)) fail('INVALID_EVIDENCE_STATUS', `evidence[${i}].status`);
  return {
    eventId: id(row.eventId, `evidence[${i}].eventId`),
    requirementId: id(row.requirementId, `evidence[${i}].requirementId`),
    opportunityRevision: integer(row.opportunityRevision, `evidence[${i}].opportunityRevision`, { min: 1, max: 1000000 }),
    status: row.status,
    observedAt: timestamp(row.observedAt, `evidence[${i}].observedAt`).canonical,
    evidenceDigest: digest(row.evidenceDigest, `evidence[${i}].evidenceDigest`),
    evidenceRef: ref(row.evidenceRef, `evidence[${i}].evidenceRef`),
    naAuthorityDigest: row.naAuthorityDigest === null ? null : digest(row.naAuthorityDigest, `evidence[${i}].naAuthorityDigest`),
  };
}

function normalizeTeam(raw, i) {
  const row = requireObject(raw, `teaming[${i}]`);
  exactKeys(row, ['requirementId', 'partnerCandidateId', 'state', 'observedAt', 'evidenceDigest'], `teaming[${i}]`);
  if (!TEAM_STATE.has(row.state)) fail('INVALID_TEAM_STATE', `teaming[${i}].state`);
  return {
    requirementId: id(row.requirementId, `teaming[${i}].requirementId`),
    partnerCandidateId: id(row.partnerCandidateId, `teaming[${i}].partnerCandidateId`),
    state: row.state,
    observedAt: timestamp(row.observedAt, `teaming[${i}].observedAt`).canonical,
    evidenceDigest: digest(row.evidenceDigest, `teaming[${i}].evidenceDigest`),
  };
}

function priority(type) {
  return ({ HARD_BLOCKER: 0, CAPACITY_SHORTFALL: 0, EXTERNAL_DEPENDENCY: 1, PARTIAL_GAP: 2, QUESTION_DEADLINE_WARNING: 3, SUBMISSION_BUFFER_WARNING: 4 })[type] ?? 9;
}

export function compileBidBridge(raw, { asOf } = {}) {
  const clock = timestamp(asOf, 'asOf');
  const input = requireObject(raw, 'input');
  exactKeys(input, ['schemaVersion', 'opportunity', 'evidence', 'teaming', 'capacityPolicy'], 'input');
  if (input.schemaVersion !== SCHEMA) fail('SCHEMA_MISMATCH', 'input.schemaVersion');
  const opportunity = normalizeOpportunity(input.opportunity, clock.ms);
  const policy = normalizePolicy(input.capacityPolicy);
  if (!Array.isArray(input.evidence) || input.evidence.length > 4096) fail('INVALID_EVIDENCE', 'evidence');
  if (!Array.isArray(input.teaming) || input.teaming.length > 4096) fail('INVALID_TEAMING', 'teaming');
  const evidence = input.evidence.map(normalizeEvidence).sort((a, b) => a.requirementId.localeCompare(b.requirementId) || a.eventId.localeCompare(b.eventId));
  const teaming = input.teaming.map(normalizeTeam).sort((a, b) => a.requirementId.localeCompare(b.requirementId));
  const reqMap = new Map(opportunity.requirements.map(req => [req.requirementId, req]));
  const holds = [];
  const byReq = new Map();
  const eventBytes = new Map();
  for (const row of evidence) {
    const bytes = JSON.stringify(row);
    if (eventBytes.has(row.eventId) && eventBytes.get(row.eventId) !== bytes) holds.push({ reason: 'CONFLICTING_EVENT_ID', requirementId: row.requirementId });
    else eventBytes.set(row.eventId, bytes);
    if (!reqMap.has(row.requirementId)) holds.push({ reason: 'UNKNOWN_REQUIREMENT_EVIDENCE', requirementId: row.requirementId });
    if (row.opportunityRevision !== opportunity.revision) holds.push({ reason: 'EVIDENCE_REVISION_MISMATCH', requirementId: row.requirementId });
    const observedMs = Date.parse(row.observedAt);
    if (observedMs > clock.ms) holds.push({ reason: 'FUTURE_EVIDENCE', requirementId: row.requirementId });
    if (observedMs < Date.parse(opportunity.capturedAt)) holds.push({ reason: 'EVIDENCE_BEFORE_CAPTURE', requirementId: row.requirementId });
    if (clock.ms - observedMs > policy.maxEvidenceAgeMinutes * 60000) holds.push({ reason: 'STALE_EVIDENCE', requirementId: row.requirementId });
    if (row.status === 'NOT_APPLICABLE_CONFIRMED' && row.naAuthorityDigest === null) holds.push({ reason: 'NA_AUTHORITY_MISSING', requirementId: row.requirementId });
    if (row.status !== 'NOT_APPLICABLE_CONFIRMED' && row.naAuthorityDigest !== null) holds.push({ reason: 'UNEXPECTED_NA_AUTHORITY', requirementId: row.requirementId });
    if (!byReq.has(row.requirementId)) byReq.set(row.requirementId, []);
    if (!byReq.get(row.requirementId).some(existing => JSON.stringify(existing) === bytes)) byReq.get(row.requirementId).push(row);
  }
  for (const req of opportunity.requirements) {
    const rows = byReq.get(req.requirementId) ?? [];
    if (rows.length === 0) holds.push({ reason: 'INCOMPLETE_REQUIREMENT_MATRIX', requirementId: req.requirementId });
    if (rows.length > 1) holds.push({ reason: 'CONFLICTING_REQUIREMENT_EVIDENCE', requirementId: req.requirementId });
  }
  const teamByReq = new Map();
  for (const row of teaming) {
    const req = reqMap.get(row.requirementId);
    if (!req) holds.push({ reason: 'UNKNOWN_TEAMING_REQUIREMENT', requirementId: row.requirementId });
    else if (!req.teamingAllowed) holds.push({ reason: 'TEAMING_NOT_ALLOWED', requirementId: row.requirementId });
    const observedMs = Date.parse(row.observedAt);
    if (observedMs > clock.ms) holds.push({ reason: 'FUTURE_TEAMING_EVIDENCE', requirementId: row.requirementId });
    if (observedMs < Date.parse(opportunity.capturedAt)) holds.push({ reason: 'TEAMING_BEFORE_CAPTURE', requirementId: row.requirementId });
    if (clock.ms - observedMs > policy.maxEvidenceAgeMinutes * 60000) holds.push({ reason: 'STALE_TEAMING_EVIDENCE', requirementId: row.requirementId });
    if (teamByReq.has(row.requirementId) && JSON.stringify(teamByReq.get(row.requirementId)) !== JSON.stringify(row)) holds.push({ reason: 'CONFLICTING_TEAMING_ROW', requirementId: row.requirementId });
    else teamByReq.set(row.requirementId, row);
  }

  const requirements = [];
  const queue = [];
  let remainingEffortHours = 0;
  let hardMissing = false;
  let hasRecoverableGap = false;
  for (const req of opportunity.requirements) {
    const rows = byReq.get(req.requirementId) ?? [];
    const evidenceRow = rows.length === 1 ? rows[0] : null;
    const status = evidenceRow?.status ?? 'HOLD';
    const team = teamByReq.get(req.requirementId) ?? null;
    if (evidenceRow && !['SATISFIED', 'NOT_APPLICABLE_CONFIRMED'].includes(status)) remainingEffortHours += req.effortHours;
    if (!Number.isSafeInteger(remainingEffortHours)) fail('INTEGER_OVERFLOW', 'remainingEffortHours');
    if (status === 'MISSING' && !req.teamingAllowed) {
      hardMissing = true;
      queue.push({ type: 'HARD_BLOCKER', requirementId: req.requirementId, dueAt: req.dueAt, reason: 'MANDATORY_NON_TEAMABLE_REQUIREMENT_MISSING' });
    } else if (status === 'MISSING' && req.teamingAllowed) {
      hasRecoverableGap = true;
      queue.push({ type: 'EXTERNAL_DEPENDENCY', requirementId: req.requirementId, dueAt: req.dueAt, reason: 'TEAMABLE_MANDATORY_REQUIREMENT_MISSING' });
    } else if (status === 'NEEDS_EXTERNAL_PARTNER') {
      hasRecoverableGap = true;
      queue.push({ type: 'EXTERNAL_DEPENDENCY', requirementId: req.requirementId, dueAt: req.dueAt, reason: team?.state === 'READY_TO_REVIEW' ? 'PARTNER_EVIDENCE_READY_FOR_OWNER_REVIEW' : 'PARTNER_DEPENDENCY_NOT_READY' });
    } else if (status === 'PARTIAL') {
      hasRecoverableGap = true;
      queue.push({ type: 'PARTIAL_GAP', requirementId: req.requirementId, dueAt: req.dueAt, reason: 'MANDATORY_REQUIREMENT_PARTIAL' });
    }
    requirements.push({
      requirementId: req.requirementId,
      class: req.class,
      dueAt: req.dueAt,
      status,
      teamingAllowed: req.teamingAllowed,
      evidenceRef: evidenceRow?.evidenceRef ?? null,
      teamState: team?.state ?? null,
      effortHours: req.effortHours,
    });
  }

  const usablePrepHours = policy.availablePrepHours - policy.reserveHours;
  const minutesToSubmission = Math.floor((Date.parse(opportunity.submissionDueAt) - clock.ms) / 60000);
  const capacityShortfall = remainingEffortHours > usablePrepHours || minutesToSubmission < (remainingEffortHours * 60 + policy.minSubmissionBufferMinutes);
  if (capacityShortfall) queue.push({ type: 'CAPACITY_SHORTFALL', requirementId: null, dueAt: opportunity.submissionDueAt, reason: 'OWNER_SUPPLIED_CAPACITY_OR_BUFFER_INSUFFICIENT' });
  if (opportunity.questionsDueAt !== null) {
    const minutesToQuestions = Math.floor((Date.parse(opportunity.questionsDueAt) - clock.ms) / 60000);
    if (minutesToQuestions >= 0 && minutesToQuestions <= policy.questionWarningMinutes) queue.push({ type: 'QUESTION_DEADLINE_WARNING', requirementId: null, dueAt: opportunity.questionsDueAt, reason: 'QUESTIONS_DEADLINE_WITHIN_WARNING_WINDOW' });
  }
  if (minutesToSubmission >= 0 && minutesToSubmission < policy.minSubmissionBufferMinutes) queue.push({ type: 'SUBMISSION_BUFFER_WARNING', requirementId: null, dueAt: opportunity.submissionDueAt, reason: 'SUBMISSION_BUFFER_BELOW_POLICY' });

  let state;
  if (holds.length > 0) state = 'HOLD';
  else if (clock.ms < Date.parse(opportunity.opensAt)) state = 'NOT_OPEN';
  else if (clock.ms >= Date.parse(opportunity.submissionDueAt) || hardMissing || capacityShortfall) state = 'NO_BID_REVIEW_REQUIRED';
  else if (hasRecoverableGap) state = 'READY_FOR_GAP_REVIEW';
  else state = 'READY_FOR_BID_DECISION';

  queue.sort((a, b) => priority(a.type) - priority(b.type) || a.dueAt.localeCompare(b.dueAt) || (a.requirementId ?? '').localeCompare(b.requirementId ?? '') || a.reason.localeCompare(b.reason));
  holds.sort((a, b) => a.reason.localeCompare(b.reason) || a.requirementId.localeCompare(b.requirementId));

  return {
    generatedAt: clock.canonical,
    opportunity: {
      opportunityId: opportunity.opportunityId,
      revision: opportunity.revision,
      sourceDigest: opportunity.sourceDigest,
      sourceRef: opportunity.sourceRef,
      submissionMode: opportunity.submissionMode,
      questionsDueAt: opportunity.questionsDueAt,
      submissionDueAt: opportunity.submissionDueAt,
      currency: opportunity.currency,
      referenceAmountCents: opportunity.referenceAmountCents,
    },
    evaluation: {
      state,
      minutesToSubmission,
      remainingEffortHours,
      usablePrepHours,
      hardMissing,
      capacityShortfall,
      holdCount: holds.length,
    },
    requirements,
    holds,
    queue,
    authorities: {
      issuerContact: false,
      partnerContact: false,
      vendorRegistration: false,
      portalMutation: false,
      questionSubmission: false,
      bidSubmission: false,
      teamingCommitment: false,
      contractOrSignature: false,
      eligibilityOrComplianceRepresentation: false,
      staffingOrScheduling: false,
      paymentOrBankMutation: false,
      autonomousGoNoGo: false,
      awardOrRevenueClaim: false,
    },
  };
}

export function formatMinutes(minutes) {
  if (!Number.isFinite(minutes)) return 'unknown';
  if (minutes < 0) return `${Math.abs(minutes)} min past deadline`;
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  const parts = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (mins || parts.length === 0) parts.push(`${mins}m`);
  return parts.join(' ');
}

export function moneyLabel(currency, cents) {
  if (currency === null || cents === null) return 'Not supplied';
  return `${currency} ${(cents / 100).toFixed(2)} source reference`;
}

export function appendText(parent, tag, textValue, className = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = String(textValue);
  parent.appendChild(node);
  return node;
}
