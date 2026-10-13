"""Exact-reference regressions against the real unchanged extractor/compiler."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from .contract import CitationError
from .resolver import Resolver
from .sample import make_sample


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet, self.report = make_sample(self.root)

    def resolve(self, index=0):
        finding = self.packet['findings'][index]
        return Resolver(self.packet, self.report, self.root).resolve(finding['evidence_refs'][0], finding)

    def expect(self, code, index=0):
        result = self.resolve(index)
        self.assertFalse(result['resolved'])
        self.assertIsNone(result['citation'])
        self.assertIn(code, result['diagnostics'])

    def test_exact_source_locator_quote_and_scope(self):
        result = self.resolve()
        self.assertTrue(result['resolved'])
        self.assertTrue(result['bound_to_compiler_source'])
        self.assertEqual(result['citation']['locator'], 'lines 6-7')
        self.assertIn('Change ENR-17', result['citation']['context'])
        self.assertEqual(result['citation']['evidence_kind'], 'artifact')

    def test_interview_keeps_evidence_kind_and_limit(self):
        result = self.resolve(1)
        self.assertTrue(result['resolved'])
        self.assertEqual(result['citation']['evidence_kind'], 'interview')
        self.assertIn('not proof', self.packet['findings'][1]['limits'])

    def test_missing_source_has_no_invented_citation(self):
        self.expect('MISSING_SOURCE_ID', 3)

    def test_unknown_version_does_not_choose_latest(self):
        self.packet['findings'][0]['evidence_refs'][0]['version'] = 'v99'
        self.expect('MISSING_VERSION')

    def test_duplicate_version_is_ambiguous_even_when_bytes_match(self):
        self.packet['sources'].append(copy.deepcopy(self.packet['sources'][0]))
        self.expect('AMBIGUOUS_SOURCE_VERSION')

    def test_reference_digest_cannot_rebind(self):
        self.packet['findings'][0]['evidence_refs'][0]['sha256'] = '1' * 64
        self.expect('REFERENCE_DIGEST_MISMATCH')

    def test_mutated_source_bytes_are_not_cited(self):
        (self.root / self.packet['sources'][0]['path']).write_text('Different record', encoding='utf-8')
        self.expect('CONTENT_HASH_MISMATCH')

    def test_missing_bytes_are_not_equated_to_a_changed_file(self):
        (self.root / self.packet['sources'][0]['path']).unlink()
        self.expect('MISSING_SOURCE_BYTES')

    def test_declared_unicode_rename_resolves_same_bytes(self):
        source = self.packet['sources'][0]
        alias = 'documents/Résumé #1 – notes.md'
        (self.root / source['path']).rename(self.root / alias)
        source['aliases'] = [alias]
        result = self.resolve()
        self.assertTrue(result['resolved'])
        self.assertEqual(result['citation']['source_path'], alias)
        self.assertIn('RENAMED_SOURCE_RESOLVED_BY_DECLARED_ALIAS', result['diagnostics'])

    def test_same_title_is_not_a_source_alias(self):
        source = self.packet['sources'][0]
        (self.root / source['path']).rename(self.root / 'documents/similar-name.md')
        self.expect('MISSING_SOURCE_BYTES')

    def test_historical_source_stays_distinct_from_report_version(self):
        result = self.resolve(2)
        self.assertTrue(result['resolved'])
        self.assertFalse(result['bound_to_compiler_source'])
        self.assertIsNone(result['citation']['observed_at'])
        self.assertIn('SOURCE_VERSION_NOT_IN_COMPILER_REPORT', result['diagnostics'])
        self.assertIn('SUPERSEDED_VERSION: v2', result['diagnostics'])

    def test_missing_old_version_does_not_redirect_to_v2(self):
        (self.root / 'documents/iam-v1.md').unlink()
        self.expect('MISSING_SOURCE_BYTES', 2)

    def test_cross_group_transplant_diagnosed(self):
        self.packet['findings'][0]['group'] = 'IAM'
        self.expect('SOURCE_SCOPE_MISMATCH')

    def test_source_not_in_compiler_cannot_be_minted_by_register(self):
        self.packet['sources'][0]['source_id'] = 'NEW-SOURCE'
        self.packet['findings'][0]['evidence_refs'][0]['source_id'] = 'NEW-SOURCE'
        self.expect('SOURCE_NOT_IN_COMPILER_REPORT')

    def test_missing_segment_does_not_guess_from_quote(self):
        self.packet['findings'][0]['evidence_refs'][0]['segment_id'] = 'text-9999'
        self.expect('MISSING_SEGMENT')

    def test_locator_must_match_exact_extraction(self):
        self.packet['findings'][0]['evidence_refs'][0]['locator'] = 'page 1'
        self.expect('LOCATOR_MISMATCH')

    def test_quote_must_appear_in_requested_segment(self):
        self.packet['findings'][0]['evidence_refs'][0]['quote'] = 'All workflows are proven.'
        self.expect('QUOTE_MISMATCH')

    def test_wrong_report_receipt_rejected(self):
        self.packet['compiler_receipt_sha256'] = '1' * 64
        with self.assertRaisesRegex(CitationError, 'different compiler receipt'):
            self.resolve()

    def test_wrong_generation_rejected(self):
        self.packet['generation'] += '-other'
        with self.assertRaisesRegex(CitationError, 'different evidence generation'):
            self.resolve()

    def test_parent_detects_forged_report(self):
        self.report['aggregate_state'] = 'READY'
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            self.resolve()

    def test_recorded_authority_flags_stay_false_and_scores_absent(self):
        trace = Resolver(self.packet, self.report, self.root).run()
        self.assertFalse(trace['interpretation_verified'])
        self.assertTrue(all(value is False for value in trace['external_authority'].values()))
        self.assertTrue(all(row['maturity'] is None and row['confidence_bp'] is None
                            for row in trace['assessment_matrix']))
        self.assertEqual(len(trace['assessment_matrix']), 12)
        self.assertEqual(trace['counts'], {'resolved': 3, 'unresolved': 1})

    def test_snapshot_does_not_mutate_caller_inputs(self):
        before = copy.deepcopy((self.packet, self.report))
        Resolver(self.packet, self.report, self.root).run()
        self.assertEqual((self.packet, self.report), before)


if __name__ == '__main__':
    unittest.main()
