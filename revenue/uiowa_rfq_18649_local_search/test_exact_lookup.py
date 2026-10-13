"""Exact native-ID navigation is distinct from lexical relevance."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import evidence_search as mod

HERE = Path(__file__).resolve().parent


class ExactLookupTests(unittest.TestCase):
    def setUp(self):
        self.index = mod.build_index(mod.load_manifest(HERE / 'fixtures' / 'manifest.json'))

    def test_native_id_is_not_a_lexical_query(self):
        hit = mod.lookup(self.index, 'F-002')
        self.assertEqual(hit['record_id'], 'F-002')
        self.assertIsNone(hit['score'])
        self.assertEqual(hit['retrieval_mode'], 'exact_id')
        self.assertEqual(hit['linked_ids'], ['E-004', 'E-005', 'E-006'])
        self.assertTrue(hit['record_url'].endswith('findings.csv#L3'))

    def test_case_and_punctuation_are_not_silently_normalized(self):
        for rid in ('f-002', 'F002', 'F-002 ', 'F_002'):
            with self.subTest(rid=rid):
                self.assertIsNone(mod.lookup(self.index, rid))

    def test_empty_and_nonstring_ids_are_controlled_errors(self):
        for rid in ('', None, 2, False):
            with self.subTest(rid=rid), self.assertRaises(mod.SearchError):
                mod.lookup(self.index, rid)

    def test_symbol_only_native_id_does_not_need_search_tokens(self):
        row = mod._base('***', 'observation', 'Exact symbol ID', 'Unmodified',
                        'fixture.csv', 'b' * 40, 'row 1', 'https://example.test/fixture.csv')
        self.assertEqual(mod.lookup(mod.build_index([row]), '***')['record_id'], '***')

    def test_result_mutation_does_not_change_index(self):
        hit = mod.lookup(self.index, 'F-002')
        hit['linked_ids'].append('MUTATED')
        hit['original']['confidence'] = 'invented'
        again = mod.lookup(self.index, 'F-002')
        self.assertNotIn('MUTATED', again['linked_ids'])
        self.assertEqual(again['original']['confidence'], 'moderate')

    def test_tampered_index_is_refused_by_lookup_too(self):
        self.index['documents'][0]['text'] = 'modified'
        with self.assertRaisesRegex(mod.SearchError, 'digest'):
            mod.lookup(self.index, 'F-002')

    def test_missing_link_keeps_its_original_identity(self):
        row = mod._base('A', 'finding', '', 'Claim', 'fixture.csv', 'b' * 40,
                        'row 1', 'https://example.test/fixture.csv', linked_ids=['B'])
        hit = mod.lookup(mod.build_index([row]), 'A')
        self.assertEqual(hit['link_diagnostics'], [{'code': 'MISSING_LINKED_RECORD', 'record_id': 'B'}])

    def test_cli_exact_and_missing_have_distinct_structured_status(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / 'index.json'
            path.write_text(json.dumps(self.index), encoding='utf-8')
            for rid, status, code in [('F-002', 'found', 0), ('F002', 'not_found', 1)]:
                with self.subTest(rid=rid):
                    run = subprocess.run([sys.executable, str(HERE / 'evidence_search.py'),
                                          'lookup', str(path), rid], text=True, capture_output=True, timeout=30)
                    self.assertEqual(run.returncode, code, run.stderr)
                    payload = json.loads(run.stdout)
                    self.assertEqual(payload['status'], status)
                    self.assertIn('not evidence confidence', payload['notice'])
                    if code == 1:
                        self.assertIsNone(payload['result'])


if __name__ == '__main__':
    unittest.main()
