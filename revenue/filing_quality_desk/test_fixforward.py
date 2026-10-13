import copy
import tempfile
import unittest
from pathlib import Path

from .core import FilingQualityError
from .engine import compile_packet, outputs, verify_outputs
from .files import compile_dir, verify_dir
from .test_support import b, src, pol


class FixForwardTests(unittest.TestCase):
    def test_compound_sec_unit_is_supported(self):
        s = src()
        revenue = s['facts']['us-gaap']['Revenue']['units'].pop('USD')
        s['facts']['us-gaap']['Revenue']['units']['USD/shares'] = revenue
        p = pol()
        p['selectors'][3]['unit'] = 'USD/shares'
        packet = compile_packet(b(s), b(p))
        row = next(x for x in packet['observations'] if x['selector_id'] == 'revenue')
        self.assertEqual(row['unit'], 'USD/shares')
        self.assertEqual(row['value'], '25.5')

    def test_duplicate_check_ids_are_rejected(self):
        p = pol()
        p['checks'].append(copy.deepcopy(p['checks'][0]))
        with self.assertRaises(FilingQualityError):
            compile_packet(b(src()), b(p))

    def test_changed_value_comparison_keeps_full_provenance_and_delta(self):
        packet = compile_packet(b(src(changed=True)), b(pol()))
        rows = [x for x in packet['comparisons'] if x['selector_id'] == 'assets']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['prior_value'], '99')
        self.assertEqual(row['prior_filed'], '2026-07-15')
        self.assertEqual(row['prior_accession'], 'A0')
        self.assertEqual(row['selected_value'], '100')
        self.assertEqual(row['selected_filed'], '2026-08-01')
        self.assertEqual(row['selected_accession'], 'A1')
        self.assertEqual(row['delta'], '1')
        self.assertEqual(row['delta_pct'], '1.01010101010101010101010101')

    def test_outputs_include_comparison_table_and_verify(self):
        s, p = b(src(changed=True)), b(pol())
        produced = outputs(s, p)
        self.assertIn('comparisons.csv', produced)
        self.assertIn(b'prior_accession', produced['comparisons.csv'])
        self.assertIn(b'A0', produced['comparisons.csv'])
        verify_outputs(s, p, produced)

    def test_compile_dir_refuses_nonempty_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.json'
            policy = root / 'policy.json'
            out = root / 'out'
            source.write_bytes(b(src()))
            policy.write_bytes(b(pol()))
            out.mkdir()
            sentinel = out / 'sentinel.txt'
            sentinel.write_text('preserve', encoding='utf-8')
            with self.assertRaises(FilingQualityError):
                compile_dir(source, policy, out)
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'preserve')

    def test_compile_dir_round_trip_and_second_compile_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.json'
            policy = root / 'policy.json'
            out = root / 'out'
            source.write_bytes(b(src(changed=True)))
            policy.write_bytes(b(pol()))
            compile_dir(source, policy, out)
            verify_dir(source, policy, out)
            with self.assertRaises(FilingQualityError):
                compile_dir(source, policy, out)

    def test_zero_prior_value_has_no_percent_change(self):
        s = src(changed=True)
        s['facts']['us-gaap']['Assets']['units']['USD'][0]['val'] = 0
        packet = compile_packet(b(s), b(pol()))
        row = next(x for x in packet['comparisons'] if x['selector_id'] == 'assets')
        self.assertEqual(row['prior_value'], '0')
        self.assertEqual(row['delta'], '100')
        self.assertIsNone(row['delta_pct'])

    def test_compile_dir_refuses_symlink_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.json'
            policy = root / 'policy.json'
            target = root / 'target'
            out = root / 'out'
            source.write_bytes(b(src()))
            policy.write_bytes(b(pol()))
            target.mkdir()
            out.symlink_to(target, target_is_directory=True)
            with self.assertRaises(FilingQualityError):
                compile_dir(source, policy, out)


if __name__ == '__main__':
    unittest.main()
