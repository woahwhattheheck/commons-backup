"""Independent input-contract and run-isolation regressions.

Run against a checkout with SOUNDNESS_TARGET=/path/to/component python3 -m unittest.
No University data, network calls, external writes, or competing assessor.
SEXTANT owns the distinct zero-observation/inference repair.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

TARGET = Path(os.environ.get('SOUNDNESS_TARGET', Path(__file__).parent))
sys.path.insert(0, str(TARGET))
import soundness as S
import check_soundness as CLI

BASE = {'id': 'M-SYN-CONTRACT', 'label': 'fictional observations',
        'kind': 'PROPORTION', 'numerator': 58, 'denominator': 100,
        'reported_value': 58, 'reported_decimals': 0,
        'sampling': 'RANDOM', 'scope': 'SAMPLE'}


def packet(**changes):
    m = copy.deepcopy(BASE)
    m.update(changes)
    return {'synthetic': True, 'measures': [m]}


class InputContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='keyframe-soundness-')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'records.json'
        old_threshold = S.MIN_DENOMINATOR_FOR_RATE
        self.addCleanup(setattr, S, 'MIN_DENOMINATOR_FOR_RATE', old_threshold)

    def load(self, obj):
        self.path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
        return S.load_measures(str(self.path))

    def cli(self, obj=None, *extra):
        if obj is not None:
            self.path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = CLI.main(['--measures', str(self.path), '--format', 'json', *extra])
        return code, out.getvalue(), err.getvalue()

    def test_valid_packet_remains_a_clean_result(self):
        code, out, err = self.cli(packet())
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)['passed'])
        self.assertEqual(err, '')

    def test_synthetic_marker_is_literal_true(self):
        for marker in ('false', 'true', 1, [], {}, None):
            with self.subTest(marker=marker):
                obj = packet()
                obj['synthetic'] = marker
                with self.assertRaises(S.MeasureError):
                    self.load(obj)

    def test_top_level_shape_errors_are_reported_not_crashes(self):
        for obj in ([], None, 1, 'fiction', True):
            with self.subTest(obj=obj):
                code, out, err = self.cli(obj) if obj is not None else self.cli_raw('null')
                self.assertEqual(code, 2)
                self.assertEqual(out, '')
                self.assertIn('could not load measures', err)

    def cli_raw(self, text):
        self.path.write_text(text, encoding='utf-8')
        return self.cli()

    def test_missing_measures_is_not_silently_empty(self):
        with self.assertRaises(S.MeasureError):
            self.load({'synthetic': True})

    def test_measures_must_be_a_list(self):
        for items in (None, {}, 'records', 3, True):
            with self.subTest(items=items):
                code, out, err = self.cli({'synthetic': True, 'measures': items})
                self.assertEqual(code, 2)
                self.assertEqual(out, '')
                self.assertIn('could not load measures', err)

    def test_entries_must_be_objects(self):
        for item in (None, [], 'record', 3, False):
            with self.subTest(item=item):
                code, out, err = self.cli({'synthetic': True, 'measures': [item]})
                self.assertEqual(code, 2)
                self.assertEqual(out, '')

    def test_counts_are_nonnegative_integers_not_coercions(self):
        for field in ('numerator', 'denominator', 'stated_total'):
            for value in (-1, True, False, 1.5, '3'):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(S.MeasureError):
                        self.load(packet(**{field: value}))

    def test_decimals_are_not_truncated_or_coerced(self):
        for value in (-1, True, False, 1.9, '1', None):
            with self.subTest(value=value):
                with self.assertRaises(S.MeasureError):
                    self.load(packet(reported_decimals=value))

    def test_nonfinite_numbers_are_rejected(self):
        for field in ('numerator', 'denominator', 'reported_value', 'stated_total'):
            for value in (float('nan'), float('inf'), -float('inf')):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(S.MeasureError):
                        self.load(packet(**{field: value}))

    def test_json_exponent_overflow_is_rejected(self):
        text = json.dumps(packet()).replace('"reported_value": 58', '"reported_value": 1e999')
        self.path.write_text(text, encoding='utf-8')
        with self.assertRaises(S.MeasureError):
            S.load_measures(str(self.path))

    def test_out_of_domain_reported_percentages_are_rejected(self):
        for value in (-0.1, 100.1, True, '58'):
            with self.subTest(value=value):
                with self.assertRaises(S.MeasureError):
                    self.load(packet(reported_value=value))

    def test_large_finite_counts_do_not_crash_float_conversion(self):
        with self.assertRaises(S.MeasureError):
            self.load(packet(numerator=1, denominator=10 ** 400))

    def test_observations_are_a_finite_numeric_list(self):
        values = ('12345', {}, [1, 2, 3, 4, '5'], [1, 2, 3, 4, True],
                  [1, 2, 3, 4, float('nan')], [1, 2, 3, 4, float('inf')])
        for observations in values:
            with self.subTest(observations=observations):
                with self.assertRaises(S.MeasureError):
                    self.load(packet(kind='MEDIAN', observations=observations))

    def test_signed_real_observations_are_not_arbitrarily_forbidden(self):
        m = self.load(packet(kind='MEDIAN', observations=[-2.0, -1, 0, 1.5, 3]))
        self.assertEqual(S.check(m), [])

    def test_components_have_a_typed_count_contract(self):
        variants = ([], 'abc', {'a': -1}, {'a': True}, {'a': 1.5}, {'a': '5'},
                    {'a': float('inf')}, {'': 3})
        for components in variants:
            with self.subTest(components=components):
                with self.assertRaises(S.MeasureError):
                    self.load(packet(kind='COUNT', components=components))

    def test_unknown_measurements_still_get_semantic_not_parse_diagnostics(self):
        for changes, wanted in (({'numerator': None}, 'NUMERATOR_UNKNOWN'),
                                ({'numerator': 0, 'denominator': 0}, 'EMPTY_DENOMINATOR'),
                                ({'kind': 'MEDIAN', 'observations': []}, 'MEDIAN_WITHOUT_OBSERVATIONS'),
                                ({'kind': 'COUNT', 'components': {'known': 5, 'unknown': None},
                                  'stated_total': 5}, 'COMPONENT_UNKNOWN')):
            with self.subTest(changes=changes):
                code, out, err = self.cli(packet(**changes))
                self.assertEqual(code, 1)
                self.assertEqual(err, '')
                self.assertIn(wanted, {x['code'] for x in json.loads(out)['findings']})

    def test_explicit_zero_components_are_known_not_missing(self):
        m = self.load(packet(kind='COUNT', components={'a': 0, 'b': 0}, stated_total=0))
        self.assertEqual(S.check(m), [])

    def test_duplicate_json_keys_are_not_last_value_wins(self):
        texts = [json.dumps(packet()).replace('"numerator": 58', '"numerator": -1, "numerator": 58'),
                 json.dumps(packet()).replace('"synthetic": true', '"synthetic": false, "synthetic": true'),
                 '{"synthetic":true,"measures":[{"id":"M-SYN-C","label":"fiction",'
                 '"kind":"COUNT","components":{"a":-1,"a":1},"stated_total":1}]}']
        for text in texts:
            with self.subTest(text=text):
                self.path.write_text(text, encoding='utf-8')
                with self.assertRaises(S.MeasureError):
                    S.load_measures(str(self.path))

    def test_duplicate_id_is_not_ambiguous_finding_attribution(self):
        obj = packet()
        obj['measures'].append(copy.deepcopy(obj['measures'][0]))
        with self.assertRaises(S.MeasureError):
            self.load(obj)

    def test_invalid_identifiers_labels_and_units_are_reported(self):
        for field, value in (('id', []), ('id', ''), ('label', None),
                             ('label', 3), ('label', ''), ('unit', [])):
            with self.subTest(field=field, value=value):
                code, out, err = self.cli(packet(**{field: value}))
                self.assertEqual(code, 2)
                self.assertEqual(out, '')

    def test_empty_set_does_not_pass(self):
        code, out, err = self.cli({'synthetic': True, 'measures': []})
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertFalse(payload['passed'])
        self.assertEqual(payload['measures_checked'], 0)
        self.assertIn('EMPTY_MEASURE_SET', {f['code'] for f in payload['findings']})

    def test_invalid_utf8_is_a_load_error(self):
        self.path.write_bytes(b'\xff\xfe not UTF8')
        code, out, err = self.cli()
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('could not load measures', err)

    def test_prior_override_does_not_change_next_default(self):
        first_code, first_out, _ = self.cli(packet(), '--min-denominator', '200')
        self.assertEqual(first_code, 1)
        self.assertEqual(json.loads(first_out)['min_denominator_for_rate'], 200)
        next_code, next_out, _ = self.cli(packet())
        self.assertEqual(next_code, 0)
        self.assertEqual(json.loads(next_out)['min_denominator_for_rate'], 8)
        self.assertEqual(S.MIN_DENOMINATOR_FOR_RATE, 8)

    def test_failing_load_also_does_not_leak_threshold(self):
        code, _, _ = self.cli({'synthetic': False, 'measures': []}, '--min-denominator', '200')
        self.assertEqual(code, 2)
        next_code, out, _ = self.cli(packet())
        self.assertEqual(next_code, 0)
        self.assertEqual(json.loads(out)['min_denominator_for_rate'], 8)

    def test_public_api_cannot_bypass_input_validation(self):
        for changes in ({'numerator': -1}, {'denominator': True},
                        {'reported_value': float('inf')}, {'kind': 'VIBES'},
                        {'observations': [float('nan')]}, {'components': {'a': -2}}):
            with self.subTest(changes=changes):
                args = copy.deepcopy(BASE)
                args.update(changes)
                with self.assertRaises(S.MeasureError):
                    S.check([S.Measure(**args)])

    def test_public_api_empty_set_is_explicitly_unchecked(self):
        findings = S.check([])
        self.assertTrue(any(f.code == 'EMPTY_MEASURE_SET' and f.severity == S.ERROR
                            for f in findings))

    def test_public_api_duplicate_ids_are_rejected(self):
        with self.assertRaises(S.MeasureError):
            S.check([S.Measure(**BASE), S.Measure(**BASE)])

    def test_high_precision_request_does_not_raise_overflow(self):
        obj = packet(reported_decimals=10 ** 400)
        code, out, err = self.cli(obj)
        self.assertEqual(code, 1)
        self.assertIn('FALSE_PRECISION', {x['code'] for x in json.loads(out)['findings']})

    def test_large_finite_counts_do_not_overflow_percentage_calculation(self):
        # Both counts fit the supported finite range; multiply-after-division
        # avoids creating an infinite intermediate from 100 * numerator.
        code, out, err = self.cli(packet(numerator=10 ** 307,
                                         denominator=10 ** 307,
                                         reported_value=100,
                                         reported_decimals=308))
        self.assertEqual(code, 1)
        self.assertIn('FALSE_PRECISION', {x['code'] for x in json.loads(out)['findings']})
        self.assertEqual(err, '')

    def test_added_dataclass_field_survives_loading(self):
        # Exercise coexistence with a companion method repair without defining
        # or overriding that repair's fields or statistical semantics.
        original = S.Measure
        extended = dataclasses.make_dataclass(
            'ExtendedMeasure', [('source_note', str, dataclasses.field(default=''))],
            bases=(original,))
        self.addCleanup(setattr, S, 'Measure', original)
        S.Measure = extended
        loaded = self.load(packet(source_note='fictional extension retained'))
        self.assertEqual(loaded[0].source_note, 'fictional extension retained')

    def test_input_bytes_are_unchanged(self):
        self.load(packet())
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.cli()
        self.cli()
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_identical_invocations_are_byte_identical(self):
        self.assertEqual(self.cli(packet()), self.cli(packet()))

    def test_clean_output_does_not_claim_every_number_was_verified(self):
        # COUNT and MEDIAN records legitimately lack a denominator; the original
        # generic success sentence overstates the checks it has actually run.
        measures = self.load(packet(kind='COUNT', components={'a': 58}, stated_total=58))
        rendered = S.render_text(measures, S.check(measures))
        self.assertNotIn('Every measure states a denominator', rendered)
        self.assertIn('not independently verified evidence', rendered)


if __name__ == '__main__':
    unittest.main(verbosity=2)
