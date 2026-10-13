"""Independent transport regression cases, including actual upstream execution."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract import audit_pair, compare_json, differences, loads_exact

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / 'fixtures' / 'workbench'


class RoundTripOracleTests(unittest.TestCase):
    def compare(self, left, right):
        return compare_json(json.dumps(left, ensure_ascii=False), json.dumps(right, ensure_ascii=False))

    def test_all_synthetic_edge_cases_survive_json_text_reformatting(self):
        source = (HERE / 'fixtures' / 'transport_cases.json').read_bytes()
        returned = json.dumps(json.loads(source), indent=3, ensure_ascii=True)
        self.assertEqual(compare_json(source, returned)['result'], 'PASS')

    def test_semantic_match_is_not_a_byte_identity_claim(self):
        result = compare_json('{"b":2,"a":1}', '{ "a": 1, "b": 2 }')
        self.assertEqual(result['result'], 'PASS')
        self.assertFalse(result['byte_identical'])

    def test_null_empty_absent_are_distinct(self):
        self.assertEqual(self.compare({'x': None}, {'x': ''})['differences'][0]['code'], 'TYPE_CHANGED')
        self.assertEqual(self.compare({'x': None}, {})['differences'][0]['code'], 'FIELD_MISSING')
        self.assertEqual(self.compare({}, {'x': None})['differences'][0]['code'], 'FIELD_ADDED')

    def test_boolean_is_not_an_integer(self):
        self.assertEqual(self.compare({'x': False}, {'x': 0})['result'], 'FAIL')
        self.assertEqual(self.compare({'x': True}, {'x': 1})['result'], 'FAIL')

    def test_numeric_looking_identifier_is_not_a_number(self):
        self.assertEqual(self.compare({'id': '0000123'}, {'id': 123})['result'], 'FAIL')

    def test_large_integer_rounding_is_detected(self):
        self.assertEqual(compare_json('{"n":9007199254740993}', '{"n":9007199254740992}')['result'], 'FAIL')

    def test_high_precision_decimal_rounding_is_detected(self):
        self.assertEqual(compare_json('{"n":0.123456789012345678901}', '{"n":0.12345678901234568}')['result'], 'FAIL')

    def test_equivalent_decimal_notation_is_semantically_equal(self):
        self.assertEqual(compare_json('{"n":1.25e2}', '{"n":125.0}')['result'], 'PASS')

    def test_negative_decimal_zero_sign_is_retained(self):
        self.assertEqual(compare_json('{"n":-0.0}', '{"n":0.0}')['result'], 'FAIL')

    def test_duplicate_keys_are_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            loads_exact('{"x":null,"x":1}')

    def test_nonfinite_numbers_are_not_json(self):
        for token in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(token=token), self.assertRaises(ValueError):
                loads_exact('{"value":' + token + '}')

    def test_unicode_normalization_is_not_silent(self):
        self.assertEqual(self.compare({'x': 'e\u0301'}, {'x': 'é'})['result'], 'FAIL')

    def test_line_ending_normalization_is_not_silent(self):
        self.assertEqual(self.compare({'note': 'a\r\nb'}, {'note': 'a\nb'})['result'], 'FAIL')

    def test_timezone_and_date_text_are_not_normalized(self):
        self.assertEqual(self.compare({'at': '2026-09-19T09:15:00-04:00'}, {'at': '2026-09-19T13:15:00Z'})['result'], 'FAIL')

    def test_array_reordering_is_detected(self):
        self.assertEqual(self.compare({'ids': ['a', 'b']}, {'ids': ['b', 'a']})['result'], 'FAIL')

    def test_empty_collections_and_scalar_null_are_distinct(self):
        for before, after in [([], {}), ([], None), ({}, None)]:
            with self.subTest(before=before, after=after):
                self.assertTrue(differences(before, after))

    def test_json_pointer_escaping_and_no_raw_value_logging(self):
        result = self.compare({'a/b~c': 'source text'}, {'a/b~c': 'changed source text'})
        self.assertEqual(result['differences'], [{'pointer': '/a~1b~0c', 'code': 'VALUE_CHANGED'}])
        self.assertNotIn('source text', json.dumps(result))

    def test_formula_text_is_not_evaluated_or_stripped(self):
        for text in ('=1+1', '+1', '-1', '@example', "'literal", '\t=1+1'):
            with self.subTest(text=text):
                self.assertEqual(self.compare({'note': text}, {'note': text})['result'], 'PASS')
                self.assertEqual(self.compare({'note': text}, {'note': 2})['result'], 'FAIL')

    def test_long_locator_is_not_truncated(self):
        text = 'evidence://synthetic/' + 'segment/' * 5000
        self.assertEqual(self.compare({'locator': text}, {'locator': text})['result'], 'PASS')
        self.assertEqual(self.compare({'locator': text}, {'locator': text[:32767]})['result'], 'FAIL')


class WorkbenchPairTests(unittest.TestCase):
    def setUp(self):
        self.report = loads_exact((FIXTURE / 'report.json').read_bytes())
        self.handoff = loads_exact((FIXTURE / 'handoff.json').read_bytes())

    def codes(self):
        return {row['code'] for row in audit_pair(self.report, self.handoff)}

    def test_actual_capture_is_a_consistent_pair_not_verified_evidence(self):
        self.assertEqual(self.codes(), set())
        self.assertTrue(self.report['synthetic_demo'])
        self.assertIn('NOT_COMPILER_OUTPUT', self.report['schema'])

    def test_note_export_alone_is_insufficient_for_provenance(self):
        self.assertNotIn('assessment_matrix', self.handoff)
        self.assertIn('DOCUMENT_NOT_OBJECT', {r['code'] for r in audit_pair(None, self.handoff)})

    def test_cross_generation_handoff_is_detected(self):
        self.handoff['report_receipt_sha256'] = 'a' * 64
        self.assertIn('REPORT_GENERATION_MISMATCH', self.codes())

    def test_same_receipt_with_altered_status_is_detected(self):
        self.handoff['cell_notes'][0]['compiler_status'] = 'READY'
        self.assertIn('CELL_STATUS_MISMATCH', self.codes())

    def test_same_count_duplicate_cell_is_detected(self):
        self.handoff['cell_notes'][1] = copy.deepcopy(self.handoff['cell_notes'][0])
        self.assertIn('CELL_KEY_DUPLICATE', self.codes())
        self.assertIn('TWELVE_CELL_SET_MISMATCH', self.codes())

    def test_unknown_group_does_not_join_to_nearby_row(self):
        self.handoff['cell_notes'][0]['group'] = 'ESS '
        self.assertIn('CELL_KEY_UNKNOWN', self.codes())

    def test_missing_cell_is_detected(self):
        self.handoff['cell_notes'].pop()
        self.assertIn('TWELVE_CELL_SET_MISMATCH', self.codes())

    def test_cell_order_can_differ_when_stable_keys_match(self):
        self.handoff['cell_notes'].reverse()
        self.assertEqual(self.codes(), set())

    def test_scalar_zero_is_not_false_authority(self):
        self.handoff['authority']['buyer_approved'] = 0
        self.assertIn('HANDOFF_AUTHORITY_NOT_FALSE', self.codes())

    def test_omitted_authority_is_not_inferred_false(self):
        del self.handoff['authority']['submission_authorized']
        self.assertIn('HANDOFF_AUTHORITY_NOT_FALSE', self.codes())

    def test_synthetic_label_cannot_disappear(self):
        self.handoff['synthetic_demo'] = False
        self.assertIn('SYNTHETIC_LABEL_MISMATCH', self.codes())

    def test_null_note_is_not_an_empty_note(self):
        self.handoff['cell_notes'][0]['analyst_note'] = None
        self.assertIn('DRAFT_TEXT_NOT_STRING', self.codes())

    def test_lost_source_context_is_detected(self):
        del self.report['assessment_matrix'][0]['reason_codes']
        self.assertIn('SOURCE_CONTEXT_NOT_RETAINED', self.codes())

    def test_compilation_mode_is_not_promoted(self):
        self.report['mode'] = 'CURRENT'
        self.assertIn('NOT_WORKBENCH_INSPECTION', self.codes())
        self.assertIn('REPORT_METADATA_MISMATCH', self.codes())

    def test_malformed_input_diagnoses_instead_of_crashing(self):
        for bad in (None, 'oops', [], 0):
            self.assertTrue(audit_pair(bad, self.handoff))
        self.handoff['cell_notes'] = [None, {}, {'group': [], 'dimension': {}}]
        self.assertIn('CELL_KEY_INVALID', self.codes())

    def test_capture_artifact_hashes_are_bound(self):
        receipt = json.loads((FIXTURE / 'capture_receipt.json').read_text())
        for name in ('report', 'handoff'):
            self.assertEqual(hashlib.sha256((FIXTURE / (name + '.json')).read_bytes()).hexdigest(), receipt[name + '_sha256'])


class UpstreamExecutionTests(unittest.TestCase):
    def test_actual_workbench_source_rehearsal(self):
        app = Path(os.environ.get('WORKBENCH_APP_JS', str(HERE.parents[1] / 'uiowa_rfq_18649_workbench' / 'app.js')))
        if not app.exists() or not shutil.which('node'):
            self.skipTest('Requires actual sibling workbench app.js and Node; no copied-exporter substitute')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'capture'
            subprocess.run(['node', str(HERE / 'capture_workbench.cjs'), str(app), str(out)],
                           check=True, capture_output=True, text=True, timeout=20)
            report = loads_exact((out / 'report.json').read_bytes())
            handoff = loads_exact((out / 'handoff.json').read_bytes())
            self.assertEqual(audit_pair(report, handoff), [])
            receipt = json.loads((out / 'capture_receipt.json').read_text())
            self.assertEqual(receipt['result'], 'PASS')
            self.assertEqual(len(receipt['checks']), 6)
            self.assertIn('receipt-change-clears-notes-and-same-receipt-restores', receipt['checks'])
            workbench = app.parent
            page = (workbench / 'index.html').read_text(encoding='utf-8')
            # Live workbench loads navigation/sample/draft helpers between core scripts.
            self.assertIn(
                '<script src="/handoff.js" defer></script><script src="/handoff_import.js" defer></script><script src="/review_navigation.js" defer></script><script src="/app.js" defer></script><script src="/review_navigation_workbench.js" defer></script><script src="/sample_session.js" defer></script><script src="/draft_bundle.js" defer></script>',
                page)
            self.assertEqual(receipt['page_scripts'], ['handoff.js', 'handoff_import.js', app.name])
            for name in ('handoff.js', 'handoff_import.js'):
                digest = hashlib.sha256((workbench / name).read_bytes()).hexdigest()
                self.assertEqual(receipt['page_script_sha256'][name], digest)
            self.assertNotIn('buildDraft', (HERE / 'capture_workbench.cjs').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
