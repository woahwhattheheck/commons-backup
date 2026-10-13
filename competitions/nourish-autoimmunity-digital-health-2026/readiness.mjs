export class ReadinessError extends Error {}

const REQUIRED_KEYS = new Set([
  'entrant_eligibility_evidenced',
  'challenge_registration_complete',
  'patient_or_advocacy_engagement_evidenced',
  'scientific_measure_provenance_complete',
  'prototype_demo_passed',
  'privacy_security_review_complete',
  'accessibility_review_complete',
  'narrative_ready',
  'video_ready',
  'ai_use_disclosure_ready',
]);

export function evaluateReadiness(facts) {
  if (!facts || typeof facts !== 'object' || Array.isArray(facts)) throw new ReadinessError('facts must be an object');
  const keys = Object.keys(facts);
  const missing = [...REQUIRED_KEYS].filter((key) => !Object.hasOwn(facts, key));
  const extra = keys.filter((key) => !REQUIRED_KEYS.has(key));
  if (missing.length || extra.length) throw new ReadinessError(`facts fields differ: missing=${missing.sort()} extra=${extra.sort()}`);
  for (const key of REQUIRED_KEYS) if (typeof facts[key] !== 'boolean') throw new ReadinessError(`${key} must be boolean`);
  const blockers = [...REQUIRED_KEYS].filter((key) => !facts[key]).sort();
  return {
    schema_version: 'nourish-readiness/v1',
    state: blockers.length ? 'HOLD' : 'READY_FOR_OWNER_SUBMISSION_DECISION',
    blockers,
    external_action_authorized: false,
    registration_or_submission_performed: false,
    award_or_revenue_claimed: false,
  };
}
