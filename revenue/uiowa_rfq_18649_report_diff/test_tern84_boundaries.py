"""Independent deterministic boundary checks for QUARTZ's exact report-diff source.

Fictional records only; no network, provider operation, or source mutation.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import unittest

import review_diff as diff
from synthetic_demo import BEFORE_AT, compile_inputs, make_inputs
from workshare_contract import ContractError, MAX_EVIDENCE_AGE_SECONDS, MAX_SOURCES


class IndependentBoundaryTests(unittest.TestCase):
    def test_all_132_directed_cross_cell_moves(self):
        for origin in diff.CELL_KEYS:
            for destination in diff.CELL_KEYS:
                if origin == destination:
                    continue
                with self.subTest(origin=origin, destination=destination):
                    candidate, authority = make_inputs()
                    before = compile_inputs(candidate, authority)
                    moved = next(s for s in authority['sources'] if diff.key(s) == origin)
                    source_id = moved['source_id']
                    moved['group'], moved['dimension'] = destination
                    after = compile_inputs(candidate, authority)
                    delta = diff.compare_reports(before, after)
                    changed = {diff.key(c): c for c in delta['cell_deltas'] if c['changed']}
                    self.assertEqual(set(changed), {origin, destination})
                    self.assertEqual(changed[origin]['after_status'], 'HOLD_MISSING_EVIDENCE')
                    self.assertEqual(changed[origin]['removed_source_ids'], [source_id])
                    self.assertEqual(changed[destination]['added_source_ids'], [source_id])
                    self.assertEqual(delta['summary']['source_records_substantively_changed'], 1)
                    self.assertEqual(delta['source_changes'][0]['kinds'], ['CELL_REASSIGNMENT'])
                    self.assertEqual(len(changed[destination]['after_source_ids']), 2)
                    self.assertTrue(diff.verify_diff(before, after, delta)['integrity_valid'])

    def test_exact_age_boundary_and_one_second_later_for_all_cells(self):
        candidate, authority = make_inputs()
        t0 = datetime.strptime(BEFORE_AT, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        boundary = (t0 + timedelta(seconds=MAX_EVIDENCE_AGE_SECONDS)).strftime('%Y-%m-%dT%H:%M:%SZ')
        expired = (t0 + timedelta(seconds=MAX_EVIDENCE_AGE_SECONDS + 1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        before = compile_inputs(candidate, authority, boundary)
        after = compile_inputs(candidate, authority, expired)
        delta = diff.compare_reports(before, after)
        self.assertEqual(delta['summary']['cells_with_evaluation_window_effect'], 12)
        self.assertEqual(delta['summary']['source_records_changed'], 0)
        self.assertTrue(all(c['before_status'] == 'UNTRUSTED_EVIDENCE_CONSISTENT' for c in delta['cell_deltas']))
        self.assertTrue(all(c['after_status'] == 'HOLD_STALE_EVIDENCE' for c in delta['cell_deltas']))
        self.assertTrue(all(not c['evidence_changed'] for c in delta['cell_deltas']))

    def test_generation_rebinding_cannot_hide_content_change_in_any_cell(self):
        for target in diff.CELL_KEYS:
            with self.subTest(target=target):
                candidate, authority = make_inputs()
                before = compile_inputs(candidate, authority)
                candidate['authority_generation'] = authority['generation'] = 'synthetic-tern-g2'
                for source in authority['sources']:
                    source['authority_generation'] = authority['generation']
                    if diff.key(source) == target:
                        source['source_content_sha256'] = 'e' * 64
                delta = diff.compare_reports(before, compile_inputs(candidate, authority))
                self.assertEqual(delta['summary']['generation_only_rebindings'], 11)
                self.assertEqual(delta['summary']['source_records_substantively_changed'], 1)
                self.assertEqual({diff.key(c) for c in delta['cell_deltas'] if c['changed']}, {target})

    def test_generation_only_plus_aging_keeps_cause_separate(self):
        candidate, authority = make_inputs()
        before = compile_inputs(candidate, authority)
        candidate['authority_generation'] = authority['generation'] = 'synthetic-tern-g2'
        for source in authority['sources']:
            source['authority_generation'] = authority['generation']
        after = compile_inputs(candidate, authority, '2027-02-01T15:00:00Z')
        delta = diff.compare_reports(before, after)
        self.assertEqual(delta['summary']['generation_only_rebindings'], 12)
        self.assertEqual(delta['summary']['cells_with_evaluation_window_effect'], 12)
        self.assertEqual(delta['summary']['source_records_substantively_changed'], 0)

    def test_persistent_missing_conflicting_and_stale_cells_survive_empty_diff(self):
        candidate, authority = make_inputs()
        authority['sources'] = [s for s in authority['sources'] if diff.key(s) != ('ESS', 'software')]
        conflict = copy.deepcopy(next(s for s in authority['sources'] if diff.key(s) == ('RIS', 'software')))
        conflict.update(source_id='synthetic-tern-dissent', maturity=4)
        authority['sources'].append(conflict)
        next(s for s in authority['sources'] if diff.key(s) == ('IAM', 'software'))['observed_at'] = '2025-01-01T00:00:00Z'
        report = compile_inputs(candidate, authority)
        delta = diff.compare_reports(report, report)
        self.assertEqual(delta['summary']['cells_changed'], 0)
        self.assertEqual({diff.key(q) for q in delta['review_queue']},
                         {('ESS', 'software'), ('RIS', 'software'), ('IAM', 'software')})
        self.assertTrue(all(q['trigger'] == 'PERSISTENT_HOLD' for q in delta['review_queue']))
        self.assertTrue(all(q['disposition'] == 'UNREVIEWED' for q in delta['review_queue']))

    def test_conflict_keeps_parent_precedence_when_records_also_age(self):
        candidate, authority = make_inputs()
        for source in list(authority['sources']):
            dissent = copy.deepcopy(source)
            dissent.update(source_id=source['source_id'] + '-dissent', maturity=3)
            authority['sources'].append(dissent)
        before = compile_inputs(candidate, authority)
        after = compile_inputs(candidate, authority, '2027-02-01T15:00:00Z')
        delta = diff.compare_reports(before, after)
        self.assertEqual(delta['summary']['cells_changed'], 0)
        self.assertEqual(len(delta['review_queue']), 12)
        self.assertTrue(all(c['persistent_hold'] and c['after_status'] == 'HOLD_CONFLICT'
                            for c in delta['cell_deltas']))

    def test_simultaneous_classification_preserves_all_five_categories(self):
        candidate, authority = make_inputs()
        before = compile_inputs(candidate, authority)
        authority['sources'][0].update(group='IAM', dimension='ai_readiness',
                                      source_ref='synthetic://tern/revision',
                                      source_content_sha256='f' * 64,
                                      claim='Fictional revised observation.', confidence_bp=3000,
                                      evidence_kind='interview', observed_at='2026-09-14T00:00:00Z')
        after = compile_inputs(candidate, authority, '2026-09-19T00:00:00Z')
        delta = diff.compare_reports(before, after)
        self.assertEqual(set(delta['source_changes'][0]['kinds']),
                         {name for name, _ in diff.FIELD_KINDS})
        self.assertEqual(delta['summary']['source_records_substantively_changed'], 1)
        self.assertEqual(delta['summary']['cells_changed'], 2)
        self.assertNotIn('Fictional revised observation.', json.dumps(delta))
        self.assertNotIn('synthetic://tern/revision', json.dumps(delta))

    def test_case_changed_identity_is_not_silently_joined(self):
        candidate, authority = make_inputs()
        before = compile_inputs(candidate, authority)
        authority['sources'][0]['source_id'] = authority['sources'][0]['source_id'].upper()
        delta = diff.compare_reports(before, compile_inputs(candidate, authority))
        self.assertEqual(len(delta['source_changes']), 2)
        self.assertEqual({tuple(s['kinds']) for s in delta['source_changes']},
                         {('REMOVED_SOURCE',), ('ADDED_SOURCE',)})
        self.assertFalse(delta['interpretation']['document_rename_inferred'])

    def test_maximum_source_universe_and_one_beyond(self):
        candidate, authority = make_inputs()
        template = authority['sources'][0]
        while len(authority['sources']) < MAX_SOURCES:
            source = copy.deepcopy(template)
            source['source_id'] = f'synthetic-tern-{len(authority["sources"]):03}'
            authority['sources'].append(source)
        report = compile_inputs(candidate, authority)
        self.assertEqual(diff.compare_reports(report, report)['summary']['cells_changed'], 0)
        extra = copy.deepcopy(template)
        extra['source_id'] = 'synthetic-tern-too-many'
        authority['sources'].append(extra)
        with self.assertRaises(ContractError):
            compile_inputs(candidate, authority)

    def test_boolean_for_integer_delta_tamper_is_not_equivalent(self):
        candidate, authority = make_inputs()
        report = compile_inputs(candidate, authority)
        delta = diff.compare_reports(report, report)
        delta['summary']['cells_changed'] = False  # Python False == 0, JSON types differ.
        delta['diff_receipt_sha256'] = diff.digest({k:v for k,v in delta.items() if k != 'diff_receipt_sha256'})
        with self.assertRaises(ContractError):
            diff.verify_diff(report, report, delta)

    def test_combined_reference_edit_and_aging_is_not_claimed_as_pure_clock_effect(self):
        candidate, authority = make_inputs()
        before = compile_inputs(candidate, authority)
        authority['sources'][0]['source_ref'] = 'synthetic://tern/relocated'
        after = compile_inputs(candidate, authority, '2027-02-01T15:00:00Z')
        delta = diff.compare_reports(before, after)
        target = next(c for c in delta['cell_deltas'] if diff.key(c) == ('ESS', 'software'))
        self.assertTrue(target['evidence_changed'])
        self.assertFalse(target['evaluation_window_effect'])
        self.assertEqual(target['after_status'], 'HOLD_STALE_EVIDENCE')
        self.assertEqual(delta['summary']['cells_with_evaluation_window_effect'], 11)

    def test_coherent_synthetic_input_never_proves_truth_or_external_authority(self):
        candidate, authority = make_inputs()
        report = compile_inputs(candidate, authority)
        delta = diff.compare_reports(report, report)
        self.assertEqual(delta['summary']['cells_changed'], 0)
        self.assertFalse(delta['interpretation']['evidence_authenticity_verified'])
        self.assertFalse(delta['interpretation']['current_evidence_review_authority'])
        self.assertTrue(all(v is False for v in delta['external_authority'].values()))


if __name__ == '__main__':
    unittest.main()
