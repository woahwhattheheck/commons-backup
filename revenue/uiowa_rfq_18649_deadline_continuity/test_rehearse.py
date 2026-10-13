"""Actual UIOWA-107 case reproduction and output-preservation tests."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import continuity
import rehearse


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads(rehearse.FIXTURE.read_bytes())
        self.cases = rehearse.build_cases(self.base)
        self.summary = rehearse.summarize(self.cases)
        self.by_name = {c['case']: c for c in self.summary['cases']}

    def test_six_unique_cases_and_four_native_options(self):
        self.assertEqual(len(self.by_name), 6)
        for case in self.by_name.values():
            self.assertEqual(set(case['verdicts']), {'OPT-A', 'OPT-B', 'OPT-C', 'OPT-D'})

    def test_original_is_not_mutated(self):
        self.assertEqual(self.base, json.loads(rehearse.FIXTURE.read_bytes()))
        self.assertEqual(self.cases[0]['scenario'], self.base)
        self.cases[1]['scenario']['deadline']['label'] = 'changed'
        self.assertNotEqual(self.cases[1]['scenario']['deadline'], self.base['deadline'])
        self.assertEqual(self.cases[0]['scenario'], self.base)

    def test_changes_are_only_explicit_assumption_edits(self):
        for case in self.cases:
            restored = copy.deepcopy(case['scenario'])
            for change in case['changes']:
                idx = next(i for i, a in enumerate(restored['assumptions'])
                           if a['id'] == change['assumption_id'])
                self.assertEqual(restored['assumptions'][idx], change['after'])
                restored['assumptions'][idx] = change['before']
            self.assertEqual(restored, self.base)

    def test_no_synthetic_change_becomes_measured(self):
        for case in self.cases:
            for change in case['changes']:
                row = change['after']
                self.assertIn(row['basis'], ('ASSUMED', 'UNKNOWN'))
                self.assertIsNone(row['source_ref'])
                if row['basis'] == 'UNKNOWN':
                    self.assertIsNone(row['low'])
                    self.assertIsNone(row['high'])

    def test_native_baseline_verdicts(self):
        self.assertEqual(self.by_name['baseline']['verdicts'],
                         {'OPT-A': 'NOT_DETERMINED', 'OPT-B': 'FITS',
                          'OPT-C': 'NOT_DETERMINED', 'OPT-D': 'NOT_DETERMINED'})

    def test_bounded_wait_is_not_enough_to_choose_between_options(self):
        row = self.by_name['wait-bounded']
        self.assertEqual(row['verdicts'], {'OPT-A': 'NOT_DETERMINED', 'OPT-B': 'FITS',
                                         'OPT-C': 'FITS', 'OPT-D': 'NOT_DETERMINED'})
        pair = next(p for p in row['comparisons'] if p['pair'] == ['OPT-A', 'OPT-D'])
        self.assertIsNone(pair['lower_in_window_exposure'])

    def test_added_capacity_makes_d_fit_but_does_not_lower_exposure(self):
        row = self.by_name['capacity-added']
        self.assertEqual(row['verdicts']['OPT-D'], 'FITS')
        options = {r['option_id']: r for r in row['options']}
        self.assertEqual(options['OPT-A']['exposure'], options['OPT-D']['exposure'])
        self.assertEqual(options['OPT-D']['capacity'], {'low': 48, 'high': 56})

    def test_peak_window_preserves_the_capacity_problem(self):
        self.assertEqual(self.by_name['peak-window']['verdicts'],
                         {'OPT-A': 'AT_RISK', 'OPT-B': 'FITS',
                          'OPT-C': 'AT_RISK', 'OPT-D': 'NOT_DETERMINED'})

    def test_unknown_capacity_does_not_mean_zero_or_fits(self):
        row = self.by_name['capacity-unknown']
        self.assertEqual(set(row['verdicts'].values()), {'NOT_DETERMINED'})
        self.assertEqual(row['unresolved_assumptions'], ['ASM-002', 'ASM-003'])
        self.assertEqual(row['options'][1]['capacity'], {'low': 0, 'high': None})

    def test_long_wait_peak_is_at_risk_for_proceed_choices(self):
        self.assertEqual(self.by_name['long-wait-peak']['verdicts'],
                         {'OPT-A': 'AT_RISK', 'OPT-B': 'FITS',
                          'OPT-C': 'AT_RISK', 'OPT-D': 'AT_RISK'})

    def test_every_report_retains_fiction_and_exclusions(self):
        for case in self.cases:
            output = continuity.Analysis(case['scenario']).as_dict()
            self.assertIs(output['meta']['synthetic'], True)
            self.assertEqual(output['meta']['authority'], 'FICTIONAL_REHEARSAL_ONLY')
            self.assertEqual([o['not_modelled'] for o in output['options']],
                             [o['not_modelled'] for o in self.base['options']])
            self.assertEqual(output['deadline'], self.base['deadline'])

    def test_all_24_intervals_match_independent_endpoint_sums(self):
        for case, result in zip(self.cases, self.summary['cases']):
            assumptions = {a['id']: a for a in case['scenario']['assumptions']}
            for option, row in zip(case['scenario']['options'], result['options']):
                for output_key, terms_key in [('exposure', 'exposure_terms'), ('capacity', 'capacity_terms')]:
                    values = [assumptions[t['assumption_ref']] for t in option[terms_key]]
                    low = sum(a['low'] if a['basis'] != 'UNKNOWN' else 0 for a in values)
                    high = None if any(a['basis'] == 'UNKNOWN' for a in values) else sum(a['high'] for a in values)
                    self.assertEqual(row[output_key], {'low': low, 'high': high})

    def test_complete_bundle_is_byte_identical_in_two_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            roots = [Path(tmp)/'one', Path(tmp)/'two']
            for root in roots:
                rehearse.run(root)
                self.assertFalse((root/'.incomplete').exists())
            def contents(root):
                return {p.relative_to(root).as_posix(): p.read_bytes()
                        for p in root.rglob('*') if p.is_file()}
            self.assertEqual(contents(roots[0]), contents(roots[1]))
            self.assertEqual(len(contents(roots[0])), 33)
            manifest = json.loads((roots[0]/'manifest.json').read_bytes())
            self.assertEqual(len(manifest['files']), 32)
            for name, desc in manifest['files'].items():
                self.assertEqual(rehearse.describe((roots[0]/name).read_bytes()), desc)

    def test_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'out'
            rehearse.run(root)
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(FileExistsError):
                rehearse.run(root)
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes()
                                     for p in root.rglob('*') if p.is_file()})

    def test_empty_directory_file_and_symlink_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'empty').mkdir()
            (root/'file').write_bytes(b'untouched')
            (root/'link').symlink_to(root/'empty', target_is_directory=True)
            (root/'dangling').symlink_to(root/'missing')
            for path in ('empty', 'file', 'link', 'dangling'):
                with self.subTest(path=path), self.assertRaises(FileExistsError):
                    rehearse.run(root/path)
            self.assertEqual((root/'file').read_bytes(), b'untouched')
            self.assertEqual(list((root/'empty').iterdir()), [])

    def test_interrupted_output_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'out'
            with mock.patch.object(continuity, 'write_evidence_csv', side_effect=OSError('injected I/O failure')):
                with self.assertRaises(OSError):
                    rehearse.run(root)
            self.assertTrue((root/'.incomplete').exists())
            self.assertFalse((root/'manifest.json').exists())
            self.assertTrue((root/'baseline'/'input.json').exists())

    def test_changed_fixture_is_refused_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'changed.json'
            source.write_bytes(rehearse.FIXTURE.read_bytes()+b' ')
            with mock.patch.object(rehearse, 'FIXTURE', source):
                with self.assertRaisesRegex(ValueError, 'fixture has changed'):
                    rehearse.run(root/'out')
            self.assertFalse((root/'out').exists())

    def test_real_cli_and_original_analysis_cli_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = [sys.executable] + (['-O'] if sys.flags.optimize else [])
            p = subprocess.run(command+[str(rehearse.HERE/'rehearse.py'), '--outdir', str(root/'bundle')],
                               capture_output=True, text=True, timeout=15, cwd=root)
            self.assertEqual(p.returncode, 0, p.stderr)
            for case in self.cases:
                name = case['case']
                p = subprocess.run(command+[str(rehearse.HERE/'continuity.py'),
                    '--input', str(root/'bundle'/name/'input.json'), '--outdir', str(root/(name+'-cli'))],
                    capture_output=True, text=True, timeout=15, cwd=root)
                self.assertEqual(p.returncode, 0, p.stderr)
                for filename in ('continuity_options.csv', 'continuity_report.md', 'evidence_requests.csv'):
                    self.assertEqual((root/(name+'-cli')/filename).read_bytes(),
                                     (root/'bundle'/name/filename).read_bytes())
                self.assertEqual(json.loads((root/(name+'-cli')/'continuity_analysis.json').read_bytes()),
                                 json.loads((root/'bundle'/name/'continuity_analysis.json').read_bytes()))


if __name__ == '__main__':
    unittest.main()
