# SPDX-License-Identifier: Apache-2.0
import copy
from fractions import Fraction as F
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import certificate_consumer as consumer
from run_checks import build_receipt, DEFAULT_CORE, load_core


class CertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core_path = Path(os.environ.get('TRIAD_CORE', DEFAULT_CORE))
        cls.core, cls.source = load_core(cls.core_path)
        cls.receipt = build_receipt(cls.core_path)
        cls.case = cls.receipt['cases'][0]
        cls.deltas = cls.case['deltas']
        cls.solution = cls.case['solution']

    def test_all_actual_core_outputs(self):
        self.assertEqual(len(self.receipt['cases']), 9)
        self.assertTrue(all(row['independent_check']['valid'] for row in self.receipt['cases']))

    def test_positive_three_support(self):
        check = consumer.check_certificate(self.deltas, self.solution)
        self.assertTrue(check['positive_optimum'])
        self.assertEqual(check['support'], [1,2,3])
        self.assertEqual(check['lower_bound'], '1/3')

    def test_closed_bounds_not_completed(self):
        check = self.receipt['cases'][4]['independent_check']
        self.assertTrue(check['bounds_closed'])
        self.assertFalse(check['completed'])
        self.assertFalse(check['positive_optimum'])

    def test_bit_limit_remains_baseline(self):
        row = self.receipt['cases'][3]
        self.assertEqual(row['solution']['weights'], ['1','0','0','0'])
        self.assertEqual(row['independent_check']['status'], 'bit_limit')

    def test_pivot_limit_remains_baseline(self):
        for row in self.receipt['cases'][1:3]:
            self.assertEqual(row['solution']['support'], [0])
            self.assertFalse(row['independent_check']['completed'])

    def test_zero_optimal_not_positive(self):
        check = self.receipt['cases'][5]['independent_check']
        self.assertTrue(check['completed'])
        self.assertFalse(check['positive_optimum'])

    def test_no_input_mutation(self):
        data, solution = copy.deepcopy(self.deltas), copy.deepcopy(self.solution)
        consumer.check_certificate(data, solution)
        self.assertEqual((data, solution), (self.deltas, self.solution))

    def test_no_provider_calls(self):
        with patch.object(self.core, 'verify_certificate', side_effect=AssertionError('provider verifier called')):
            with patch.object(self.core, 'solve_full_table', side_effect=AssertionError('solver called')):
                self.assertTrue(consumer.check_certificate(self.deltas, self.solution)['valid'])
        self.assertNotIn('import full_support', inspect.getsource(consumer))

    def test_provider_validity_flag_not_trusted(self):
        altered = dict(self.solution, certificate_valid=False)
        self.assertTrue(consumer.check_certificate(self.deltas, altered)['valid'])
        altered['value'] = '900'
        altered['certificate_valid'] = True
        self.assertFalse(consumer.check_certificate(self.deltas, altered)['valid'])

    def test_support_identity(self):
        for support in ([0], [3,2,1], [True,2,3], [1,2,3,3], (1,2,3)):
            with self.subTest(support=support):
                self.assertFalse(consumer.check_certificate(self.deltas, dict(self.solution, support=support))['valid'])

    def test_reported_bounds(self):
        for field in ('value','upper_bound','gap'):
            self.assertFalse(consumer.check_certificate(self.deltas, dict(self.solution, **{field: '91'}))['valid'])

    def test_expectation_vectors(self):
        for field in ('column_expectations','row_expectations_under_dual','pure_minima'):
            altered = dict(self.solution, **{field: ['0']})
            self.assertFalse(consumer.check_certificate(self.deltas, altered)['valid'])

    def test_distribution_corruption(self):
        for field, values in [('weights', ['-1','1','1','0']), ('weights', ['0','0','0','0']),
                              ('weights', ['1']), ('dual_weights', ['0','0','0']),
                              ('dual_weights', ['-1','1','1']), ('weights', [False, '1/3','1/3','1/3'])]:
            self.assertFalse(consumer.check_certificate(self.deltas, dict(self.solution, **{field: values}))['valid'])

    def test_nonfinite_fields(self):
        for value in (float('nan'),float('inf'),'1/0', True):
            self.assertFalse(consumer.check_certificate(self.deltas, dict(self.solution, value=value))['valid'])

    def test_flags_and_status(self):
        for field, value in [('exact', 'true'), ('exact', 1), ('arithmetic_exact', False),
                             ('arithmetic_exact', 1), ('status', 'pending'), ('status', None),
                             ('alpha', False), ('alpha', 1), ('probabilities', [1,0,0])]:
            self.assertFalse(consumer.check_certificate(self.deltas, dict(self.solution, **{field: value}))['valid'])

    def test_declared_computation_limits(self):
        for field, value in [('pivots', True), ('pivots', -1), ('pivots', 999),
                             ('max_pivots', -1), ('max_pivots', 4097), ('max_bits', 15), ('max_bits', '512')]:
            self.assertFalse(consumer.check_certificate(self.deltas, dict(self.solution, **{field: value}))['valid'])

    def test_table_reordering(self):
        reversed_rows = [self.deltas[0]]+list(reversed(self.deltas[1:]))
        reversed_columns = [list(reversed(row)) for row in self.deltas]
        self.assertFalse(consumer.check_certificate(reversed_rows, self.solution)['valid'])
        self.assertFalse(consumer.check_certificate(reversed_columns, self.solution)['valid'])

    def test_stale_hash(self):
        self.assertFalse(consumer.check_certificate(self.deltas, dict(self.solution, table_sha256='0'*64))['valid'])

    def test_missing_fields(self):
        for field in ('weights','dual_weights','table_sha256','support','status','exact','pure_minima','max_bits'):
            result = dict(self.solution)
            del result[field]
            self.assertFalse(consumer.check_certificate(self.deltas, result)['valid'])

    def test_invalid_tables(self):
        for table in ([], [[]], [[0],[1,2]], [[1],[0]], [[0]*33], [[0]]*10, [[0],[True]]):
            self.assertFalse(consumer.check_certificate(table, self.solution)['valid'])

    def test_canonical_rational_digest(self):
        values = [[0,0], [0.1,F(1,2)]]
        strings = [['0','0'], ['1/10','1/2']]
        self.assertEqual(consumer.table_digest(values), consumer.table_digest(strings))
        body = json.dumps(strings,separators=(',',':')).encode('ascii')
        self.assertEqual(consumer.table_digest(values), hashlib.sha256(body).hexdigest())

    def test_budget_positive_strategy_is_not_accepted(self):
        result = dict(self.solution, status='pivot_limit', exact=False)
        self.assertFalse(consumer.check_certificate(self.deltas, result)['valid'])

    def test_budget_zero_gap_is_not_fabricated_completion(self):
        row = self.receipt['cases'][4]
        altered = dict(row['solution'], exact=True)
        self.assertFalse(consumer.check_certificate(row['deltas'], altered)['valid'])

    def test_zero_tie_preserves_baseline(self):
        row = self.receipt['cases'][5]
        result = dict(row['solution'], weights=['0','1'], support=[1])
        self.assertFalse(consumer.check_certificate(row['deltas'], result)['valid'])

    def test_loader_source_attribution(self):
        expected = ('3457d8f149b2bb07de6d9993a41ae0e0f19eb57f'
                    if self.source['git_blob'] == 'b04f7bc4ff2137dee4b70ec6f10e7f02ccaebd06' else None)
        self.assertEqual(self.source['reference_commit'], expected)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory)/'same_api_new_source.py'
            file.write_bytes(self.core_path.read_bytes()+b'\n# source-label test\n')
            _, source = load_core(file)
            self.assertIsNone(source['reference_commit'])
            self.assertNotEqual(source['sha256'], self.source['sha256'])

    def test_cli_outputs_verified_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            record=root/'input.json'
            output=root/'output.json'
            record.write_text(json.dumps({'deltas':self.deltas,'solution':self.solution}))
            run=subprocess.run([sys.executable, str(Path(consumer.__file__)), str(record),'--output',str(output)],
                               capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertTrue(json.loads(output.read_text())['positive_optimum'])

    def test_cli_invalid_certificate_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            record=Path(directory)/'input.json'
            record.write_text(json.dumps({'deltas':self.deltas,'solution':dict(self.solution,value='9')}))
            run=subprocess.run([sys.executable,str(Path(consumer.__file__)),str(record)],capture_output=True,text=True)
            self.assertEqual(run.returncode,1)
            self.assertFalse(json.loads(run.stdout)['valid'])

    def test_cli_malformed_input_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            record=Path(directory)/'input.json';record.write_text('{bad')
            run=subprocess.run([sys.executable,str(Path(consumer.__file__)),str(record)],capture_output=True,text=True)
            self.assertEqual(run.returncode,2)
            self.assertNotIn('Traceback',run.stderr)


if __name__ == '__main__':
    unittest.main()
