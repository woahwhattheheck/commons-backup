import assert from 'node:assert/strict';
import test from 'node:test';
import { evaluateReadiness } from './readiness.mjs';

const all = {
  entrant_eligibility_evidenced: true,
  challenge_registration_complete: true,
  patient_or_advocacy_engagement_evidenced: true,
  scientific_measure_provenance_complete: true,
  prototype_demo_passed: true,
  privacy_security_review_complete: true,
  accessibility_review_complete: true,
  narrative_ready: true,
  video_ready: true,
  ai_use_disclosure_ready: true,
};

test('owner template truth remains HOLD and never authorizes external action', async () => {
  const facts = JSON.parse(await (await import('node:fs/promises')).readFile(new URL('./owner_evidence.template.json', import.meta.url), 'utf8'));
  const receipt = evaluateReadiness(facts);
  assert.equal(receipt.state, 'HOLD');
  assert.equal(receipt.external_action_authorized, false);
  assert.equal(receipt.registration_or_submission_performed, false);
  assert.ok(receipt.blockers.includes('patient_or_advocacy_engagement_evidenced'));
});

test('complete evidence reaches owner decision only, never submission authority', () => {
  const receipt = evaluateReadiness(all);
  assert.equal(receipt.state, 'READY_FOR_OWNER_SUBMISSION_DECISION');
  assert.equal(receipt.external_action_authorized, false);
  assert.equal(receipt.award_or_revenue_claimed, false);
});

test('unknown or missing readiness fields fail closed', () => {
  const missing = { ...all };
  delete missing.video_ready;
  assert.throws(() => evaluateReadiness(missing), /fields differ/);
  assert.throws(() => evaluateReadiness({ ...all, invented: true }), /fields differ/);
});
