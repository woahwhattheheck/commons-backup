# SPDX-License-Identifier: Apache-2.0
"""Contracts for the benchmark coordinator; not policy or gameplay tests."""
import copy
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).with_name('bench_lazy_actor.py')
spec = importlib.util.spec_from_file_location('cove_bench_test', p)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def trace():
    return {'status': 'complete', 'sources_unchanged': True, 'input': {'id': 'same'},
            'records': [{'step': 0, 'action': {'market': []}, 'state': {'plan': 'a'},
                         'inputs_unchanged': True,
                         'work': {'captured_windows': 2, 'inspected_windows': 1,
                                  'compiled_windows': 1, 'admitted_index': 0}}]}


def timing(t=2.0):
    return {'status': 'complete', 'sources_unchanged': True,
            'calls': [{'wall_s': t}], 'action_sequence_sha256': 'abc',
            'p99_call_s': t, 'target_load_through_first_attempt_wall_s': 0.1,
            'expected_actions': {'mismatches': 0}}


class CoordinatorTests(unittest.TestCase):
    def test_control_only_materializes_generator(self):
        source = 'offers = (self._offers(cfg, base)\n          if ready else ())\n'
        self.assertEqual(b.eager_source(source), source.replace('self._offers(cfg, base)', 'list(self._offers(cfg, base))'))

    def test_control_rejects_missing_site(self):
        with self.assertRaises(ValueError): b.eager_source('x = 1\n')

    def test_control_rejects_repeated_site(self):
        with self.assertRaises(ValueError): b.eager_source((b.LAZY + ')\n') * 2)

    def test_control_rejects_already_eager(self):
        with self.assertRaises(ValueError): b.eager_source(b.EAGER + ')\n')

    def test_different_work_is_not_different_decision(self):
        a, z = trace(), trace()
        z['records'][0]['work'].update(inspected_windows=2, compiled_windows=2, admitted_index=1)
        r = b.compare_traces(a, z)
        self.assertTrue(r['complete_correspondence'])
        self.assertEqual(r['different_compilation_calls'], [{'step': 0, 'lazy_compiled': 1, 'eager_compiled': 2}])

    def test_action_difference_is_reported(self):
        a, z = trace(), trace(); z['records'][0]['action'] = {'market': [['SELL', 'MILK', 1]]}
        r = b.compare_traces(a, z)
        self.assertFalse(r['complete_correspondence']); self.assertEqual(r['action_differences'], [0])

    def test_selection_difference_is_reported(self):
        a, z = trace(), trace(); z['records'][0]['state']['plan'] = 'b'
        self.assertEqual(b.compare_traces(a, z)['state_differences'], [0])

    def test_incomplete_or_changed_source_is_not_parity(self):
        for field, value in [('status', 'error'), ('sources_unchanged', False)]:
            with self.subTest(field=field):
                a, z = trace(), trace(); z[field] = value
                self.assertFalse(b.compare_traces(a, z)['complete_correspondence'])

    def test_truncation_is_not_parity(self):
        a, z = trace(), trace(); z['records'] = []
        self.assertFalse(b.compare_traces(a, z)['complete_correspondence'])

    def test_input_identity_and_mutation_checked(self):
        a, z = trace(), trace(); z['input'] = {'id': 'other'}
        self.assertFalse(b.compare_traces(a, z)['complete_correspondence'])
        z = trace(); z['records'][0]['inputs_unchanged'] = False
        self.assertEqual(b.compare_traces(a, z)['input_mutations'], [0])

    def test_timing_summary_preserves_raw_and_median(self):
        result = b.summarize_passes({'lazy': [timing(1), timing(2), timing(3)],
                                     'eager': [timing(2), timing(4), timing(6)]})
        self.assertEqual(result['lazy']['total_action_s'], [1, 2, 3])
        self.assertEqual(result['median_action_time_reduction_pct'], 50)
        self.assertTrue(result['all_action_hashes_equal'])

    def test_incomplete_timing_rejected(self):
        x = timing(); x['status'] = 'error'
        with self.assertRaises(ValueError): b.summarize_passes({'lazy': [x], 'eager': [timing()]})

    def test_timing_action_mismatch_visible(self):
        x = timing(); x['action_sequence_sha256'] = 'other'
        self.assertFalse(b.summarize_passes({'lazy': [x], 'eager': [timing()]})['all_action_hashes_equal'])

    def test_plain_preserves_typed_keys_and_sets(self):
        self.assertEqual(b.plain({('MILK', 1): {3, 2}}), [[['MILK', 1], [2, 3]]])
        with self.assertRaises(TypeError): b.plain(object())


if __name__ == '__main__':
    unittest.main(verbosity=2)
