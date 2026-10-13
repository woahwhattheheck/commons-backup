import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { analyzeAssociation, buildResearchExport, canonicalJson, LedgerError, normalizeLedger, syntheticDemo } from './core.mjs';

const NOW = new Date('2026-09-14T12:00:00Z');

function symptom(id, at, severity = 4, domain = 'fatigue') {
  return { id, kind: 'symptom', occurred_at: at, recorded_at: at, payload: { domain, severity, note: 'private words' } };
}
function diet(id, at, tag = 'test-food') {
  return { id, kind: 'diet', occurred_at: at, recorded_at: at, payload: { label: 'test meal', tags: [tag], note: 'private meal note' } };
}

const baseEvents = [
  symptom('sym0', '2026-09-10T08:00:00Z', 2),
  diet('diet0', '2026-09-10T12:00:00Z'),
  symptom('sym1', '2026-09-10T18:00:00Z', 5),
  symptom('sym2', '2026-09-11T08:00:00Z', 3),
  diet('diet1', '2026-09-11T12:00:00Z'),
  symptom('sym3', '2026-09-11T18:00:00Z', 6),
  symptom('sym4', '2026-09-12T08:00:00Z', 3),
  diet('diet2', '2026-09-12T12:00:00Z'),
  symptom('sym5', '2026-09-12T18:00:00Z', 6),
];

test('ledger normalization is deterministic', () => {
  const one = normalizeLedger([...baseEvents].reverse(), { now: NOW });
  const two = normalizeLedger(baseEvents, { now: NOW });
  assert.equal(canonicalJson(one), canonicalJson(two));
});

test('duplicate event ids fail closed', () => {
  assert.throws(() => normalizeLedger([baseEvents[0], { ...baseEvents[0] }], { now: NOW }), /duplicate event id/);
});

test('future timestamps fail closed', () => {
  assert.throws(() => normalizeLedger([symptom('future', '2026-09-15T12:00:00Z')], { now: NOW }), /future/);
});

test('symptom and validated score bounds are strict', () => {
  assert.throws(() => normalizeLedger([symptom('bad', '2026-09-10T08:00:00Z', 11)], { now: NOW }), /finite number/);
  const score = {
    id: 'score-1', kind: 'validated_score', occurred_at: '2026-09-10T08:00:00Z', recorded_at: '2026-09-10T08:00:00Z',
    payload: { instrument: 'Test', instrument_version: '1', domain: 'fatigue', score: 101, scale_min: 0, scale_max: 100, source_url: 'https://example.test/instrument' },
  };
  assert.throws(() => normalizeLedger([score], { now: NOW }), /finite number/);
});

test('matched analysis reports descriptive change and never causal language', () => {
  const report = analyzeAssociation(baseEvents, { exposure_tag: 'test-food', outcome_domain: 'fatigue', baseline_hours: 8, lag_hours: 8, now: NOW });
  assert.equal(report.matched_pair_count, 3);
  assert.equal(report.average_delta, 3);
  assert.ok(report.warnings.includes('DESCRIPTIVE_ASSOCIATION_NOT_CAUSATION'));
  const text = JSON.stringify(report).toLowerCase();
  for (const forbidden of ['causes ', 'caused ', 'treats ', 'treatment recommendation', 'should eat', 'should avoid']) {
    assert.equal(text.includes(forbidden), false, `forbidden causal/advice phrase leaked: ${forbidden}`);
  }
});

test('overlapping exposures are excluded from matched aggregate', () => {
  const events = [
    symptom('sym-a0', '2026-09-10T08:00:00Z', 2),
    diet('diet-a1', '2026-09-10T10:00:00Z'),
    diet('diet-a2', '2026-09-10T11:00:00Z'),
    symptom('sym-a3', '2026-09-10T14:00:00Z', 8),
  ];
  const report = analyzeAssociation(events, { exposure_tag: 'test-food', outcome_domain: 'fatigue', baseline_hours: 4, lag_hours: 4, now: NOW });
  assert.equal(report.matched_pair_count, 0);
  assert.ok(report.warnings.includes('OVERLAPPING_EXPOSURE_WINDOWS_EXCLUDED'));
});

test('context changes are preserved as confounder warnings', () => {
  const events = [...baseEvents, {
    id: 'ctx-1', kind: 'context', occurred_at: '2026-09-11T13:00:00Z', recorded_at: '2026-09-11T13:00:00Z',
    payload: { domain: 'medication_change', value: 'synthetic marker' },
  }];
  const report = analyzeAssociation(events, { exposure_tag: 'test-food', outcome_domain: 'fatigue', baseline_hours: 8, lag_hours: 8, now: NOW });
  assert.ok(report.warnings.includes('CONTEXT_CHANGES_PRESENT'));
  assert.ok(report.windows.some((window) => window.confounders.some((value) => value.domain === 'medication_change')));
});

test('sparse data is visibly low-sample', () => {
  const report = analyzeAssociation(baseEvents.slice(0, 3), { exposure_tag: 'test-food', outcome_domain: 'fatigue', baseline_hours: 8, lag_hours: 8, min_pairs: 3, now: NOW });
  assert.ok(report.warnings.includes('LOW_MATCHED_SAMPLE'));
});

test('research export reduces obvious free-text and identifier surfaces', () => {
  const events = [...baseEvents, {
    id: 'ctx-private', kind: 'context', occurred_at: '2026-09-11T13:00:00Z', recorded_at: '2026-09-11T13:00:00Z',
    payload: { domain: 'other', value: 'private context words' },
  }];
  const exported = buildResearchExport(events, { now: NOW });
  const text = JSON.stringify(exported);
  for (const forbidden of ['private words', 'private meal note', 'private context words', 'test meal', 'sym0', 'diet0', 'ctx-private']) {
    assert.equal(text.includes(forbidden), false, `reduced export leaked ${forbidden}`);
  }
  assert.equal(exported.privacy.explicit_identity_fields_in_schema, false);
  assert.equal(exported.privacy.event_ids_pseudonymized, true);
  assert.equal(exported.privacy.free_text_notes_removed, true);
  assert.equal(exported.privacy.diet_labels_removed, true);
  assert.equal(exported.privacy.context_values_removed, true);
  assert.equal(exported.records.every((record) => /^event-\d{4}$/.test(record.id)), true);
});

test('synthetic demo is valid and contains no network dependency', async () => {
  const demo = syntheticDemo(NOW);
  assert.ok(demo.length > 10);
  const source = await readFile(new URL('./app.mjs', import.meta.url), 'utf8');
  for (const forbidden of ['fetch(', 'XMLHttpRequest', 'WebSocket', 'sendBeacon']) {
    assert.equal(source.includes(forbidden), false, `network transport surface present: ${forbidden}`);
  }
});
