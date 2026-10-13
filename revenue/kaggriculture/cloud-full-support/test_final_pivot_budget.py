# SPDX-License-Identifier: Apache-2.0
"""Final-table arithmetic-budget regressions for the existing POLY solver.

This runs the real core and unchanged T15/PRISM consumers. Receipt matrices are
algebraic fixtures, not game traces. No simulator or provider IO is invoked.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CORE = HERE / 'full_support.py'
KAG = HERE.parent
T15 = KAG / 'cloud-market-game-theory'
WEIGHTED = KAG / 'cloud-weighted-plan-selector'
REPORT = None
PURE = [[0, 0], [-188, 13], [190, 291]]
MIXED = [[0, 0], [-95, 48], [497, -106]]
INTERMEDIATE = [[0, 0, 0], [-101, 103, 107], [109, -113, 127], [131, 137, -139]]
RECORDS = []


def load_source(path, name):
    """Execute captured source bytes, without depending on timestamp pyc state."""
    import types
    source = Path(path).read_bytes()
    module = types.ModuleType(name)
    module.__file__ = str(Path(path).resolve())
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def identity(path):
    body = Path(path).read_bytes()
    return {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
            'git_blob': hashlib.sha1(f'blob {len(body)}\0'.encode() + body).hexdigest()}


def traced(core, rows, **budgets):
    """Observe a real solver exit; never substitute a tableau or certificate."""
    core.clear_table_cache()
    target = core._solve_normalized.__wrapped__.__code__
    seen = {}
    previous = sys.gettrace()
    def trace(frame, event, arg):
        if frame.f_code is target and event == 'return' and 'table' in frame.f_locals:
            table = frame.f_locals['table']
            seen['exit_table_max_bits'] = max(
                max(v.numerator.bit_length(), v.denominator.bit_length())
                for row in table for v in row)
            seen['improving_column_remains'] = any(v < 0 for v in table[-1][:-1])
        return trace
    sys.settrace(trace)
    try:
        result = core.solve_full_table(rows, **budgets)
    finally:
        sys.settrace(previous)
    RECORDS.append({'deltas': deepcopy(rows), 'budgets': budgets,
                    'result': deepcopy(result), 'trace': deepcopy(seen)})
    return result, seen


class FixedDraw:
    def __init__(self): self.calls = 0
    def randrange(self, n):
        self.calls += 1
        return 0


class FinalPivotBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_source(CORE, 'triad_poly_core')
        cls.weighted = load_source(WEIGHTED/'weighted_selector.py', 'triad_weighted')
        previous = sys.modules.get('solver')
        sys.modules['solver'] = load_source(T15/'solver.py', 'triad_original_t15_math')
        try:
            cls.base = load_source(T15/'selector.py', 'triad_original_t15_selector')
        finally:
            if previous is None: sys.modules.pop('solver', None)
            else: sys.modules['solver'] = previous

    def setUp(self): self.core.clear_table_cache()

    def limited(self, rows=MIXED, **kwargs):
        result, trace = traced(self.core, rows, max_bits=16, **kwargs)
        self.assertGreater(trace['exit_table_max_bits'], 16)
        self.assertFalse(trace['improving_column_remains'])
        self.assertEqual(result['status'], 'bit_limit')
        self.assertEqual(result['weights'], ['1'] + ['0']*(len(rows)-1))
        self.assertFalse(result['exact'])
        self.assertTrue(result['arithmetic_exact'])
        self.assertEqual(result['value'], '0')
        self.assertTrue(self.core.verify_certificate(rows, result)['valid'])
        return result

    def test_pure_optimum_after_over_budget_final_pivot(self):
        self.limited(PURE)

    def test_mixed_optimum_after_over_budget_final_pivot(self):
        result = self.limited()
        self.assertEqual(result['upper_bound'], '6893/373')
        self.assertEqual(result['gap'], '6893/373')
        self.assertEqual(result['pivots'], 2)

    def test_final_pivot_at_exact_pivot_allowance(self):
        self.limited(max_pivots=2)

    def test_sufficient_budget_retains_mixed_optimum(self):
        result, trace = traced(self.core, MIXED, max_bits=17)
        self.assertEqual(trace['exit_table_max_bits'], 17)
        self.assertEqual(result['status'], 'optimal')
        self.assertEqual(result['weights'], ['0', '603/746', '143/746'])
        self.assertEqual(result['value'], '6893/373')
        self.assertTrue(result['exact'])

    def test_default_budget_retains_same_result(self):
        result = self.core.solve_full_table(MIXED)
        high = self.core.solve_full_table(MIXED, max_bits=17)
        result.pop('max_bits'); high.pop('max_bits')
        self.assertEqual(result, high)

    def test_existing_zero_pivot_stop_preserved(self):
        result = self.core.solve_full_table(MIXED, max_bits=16, max_pivots=0)
        self.assertEqual(result['status'], 'pivot_limit')
        self.assertEqual(result['pivots'], 0)
        self.assertEqual(result['weights'], ['1', '0', '0'])

    def test_existing_nonfinal_pivot_stop_preserved(self):
        result, trace = traced(self.core, MIXED, max_bits=16, max_pivots=1)
        self.assertEqual(result['status'], 'pivot_limit')
        self.assertTrue(trace['improving_column_remains'])
        self.assertEqual(result['pivots'], 1)

    def test_existing_intermediate_bit_stop_preserved(self):
        result, trace = traced(self.core, INTERMEDIATE, max_bits=16)
        self.assertEqual(result['status'], 'bit_limit')
        self.assertTrue(trace['improving_column_remains'])
        self.assertGreater(trace['exit_table_max_bits'], 16)
        self.assertTrue(self.core.verify_certificate(INTERMEDIATE, result)['valid'])

    def test_initial_table_budget_still_applies(self):
        result, trace = traced(self.core, [[0], [-65535]], max_bits=16)
        self.assertEqual(result['status'], 'bit_limit')
        self.assertEqual(result['pivots'], 0)
        self.assertEqual(trace['exit_table_max_bits'], 17)

    def test_oversized_inputs_still_raise(self):
        with self.assertRaisesRegex(ValueError, 'Input receipts'):
            self.core.solve_full_table([[0], [65536]], max_bits=16)

    def test_zero_value_tie_keeps_baseline(self):
        result = self.core.solve_full_table([[0,0],[-1,1]], max_bits=16)
        self.assertEqual(result['status'], 'optimal')
        self.assertEqual(result['weights'], ['1','0'])
        self.assertEqual(result['value'], '0')

    def test_mathematical_certificate_remains_valid_at_limit(self):
        result = self.core.solve_full_table(MIXED, max_bits=16)
        p = list(map(F, result['weights'])); q = list(map(F, result['dual_weights']))
        self.assertEqual(sum(p), 1); self.assertEqual(sum(q), 1)
        lower = min(sum(p[i]*MIXED[i][j] for i in range(3)) for j in range(2))
        upper = max(sum(q[j]*row[j] for j in range(2)) for row in MIXED)
        self.assertEqual(F(result['value']), lower)
        self.assertEqual(F(result['upper_bound']), upper)
        self.assertLessEqual(lower, upper)
        self.assertTrue(self.core.verify_certificate(MIXED, result)['valid'])

    def test_budget_specific_cache_entries(self):
        low = self.core.solve_full_table(MIXED, max_bits=16)
        high = self.core.solve_full_table(MIXED, max_bits=17)
        again = self.core.solve_full_table(MIXED, max_bits=16)
        self.assertEqual(self.core.table_cache_info(), {'hits':1, 'misses':2, 'maxsize':64, 'currsize':2})
        self.assertEqual(low, again)
        self.assertEqual(low['status'], 'bit_limit')
        self.assertEqual(high['status'], 'optimal')

    def test_high_budget_cache_does_not_bypass_lower_budget(self):
        self.core.solve_full_table(MIXED, max_bits=512)
        low = self.core.solve_full_table(MIXED, max_bits=16)
        self.assertEqual(low['status'], 'bit_limit')
        self.assertEqual(self.core.table_cache_info()['misses'], 2)

    def test_cached_outputs_remain_detached(self):
        first = self.core.solve_full_table(MIXED, max_bits=16)
        expected = deepcopy(first)
        first['weights'][0] = '900'; first['dual_weights'].append('1'); first['status'] = 'changed'
        self.assertEqual(self.core.solve_full_table(MIXED, max_bits=16), expected)

    def test_inputs_and_limit_validation_preserved(self):
        original = deepcopy(MIXED)
        self.core.solve_full_table(original, max_bits=16)
        self.assertEqual(original, MIXED)
        for kwargs in ({'max_bits':True}, {'max_bits':15}, {'max_pivots':True}, {'max_pivots':-1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.core.solve_full_table(MIXED, **kwargs)

    def selector(self, max_bits):
        rng = FixedDraw()
        def provider(rows): return self.core.solve_full_table(rows, max_bits=max_bits)
        selector = self.weighted.make_selector(self.base.WholePlanSelector, provider, rng=rng)
        return selector, rng

    @staticmethod
    def fixture():
        action = {'farmer':['PASS'], 'hands':[['PASS']],
                  'market':[['SELL','EGG',3], ['BUY_SEED','WHEAT',1]]}
        obs = {'step':10, 'player':0, 'farms':[{'money':100}, {'money':100}]}
        plans = [{'id':'baseline', 'sales':[[10,3]]},
                 {'id':'split', 'sales':[[10,1],[14,2]]},
                 {'id':'later', 'sales':[[14,3]]}]
        window = {'key':'algebraic-budget-fixture','item':'EGG','quantity':3,
                  'now':10,'end':14,'slot':0,'plans':plans,'deltas':deepcopy(MIXED)}
        return action, obs, window

    def test_real_consumer_keeps_no_draw_on_limit(self):
        selector, rng = self.selector(16)
        _, _, window = self.fixture()
        result = selector.choose('limit', window['plans'], MIXED, feasible=lambda p: True)
        self.assertIsNone(result)
        self.assertEqual(selector.last_decision['reason'], 'provider_not_optimal')
        self.assertEqual(selector.last_decision['provider_status'], 'bit_limit')
        self.assertEqual((selector.provider_calls, selector.draws, rng.calls), (1,0,0))
        self.assertIsNone(selector.choose('limit', window['plans'], MIXED, feasible=lambda p: True))
        self.assertEqual(selector.provider_calls, 1)

    def test_real_transform_preserves_full_fallback_on_limit(self):
        selector, rng = self.selector(16)
        action, obs, window = self.fixture()
        original = deepcopy((action, obs, window))
        output = selector.transform(obs, {'episodeSteps':20}, action, window=window,
                                    post_unit_shed={'EGG':3}, feasible=lambda p: True)
        self.assertEqual(output, action)
        self.assertIsNot(output, action)
        self.assertEqual(selector.draws, 0)
        self.assertEqual((action,obs,window), original)

    def test_real_consumer_sufficient_budget_keeps_persistence(self):
        selector, rng = self.selector(17)
        action, obs, window = self.fixture()
        output = selector.transform(obs, {'episodeSteps':20}, action, window=window,
                                    post_unit_shed={'EGG':3}, feasible=lambda p: True)
        self.assertEqual(output['market'][0], ['SELL','EGG',1])
        self.assertEqual(output['market'][1], action['market'][1])
        obs['step'] = 14
        output = selector.transform(obs, {'episodeSteps':20}, action,
                                    post_unit_shed={'EGG':2})
        self.assertEqual(output['market'][0], ['SELL','EGG',2])
        self.assertEqual((selector.provider_calls, selector.draws, rng.calls), (1,1,1))

    def test_actual_cli_reports_budget_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            input_path = Path(folder)/'matrix.json'
            input_path.write_text(json.dumps(MIXED), encoding='utf-8')
            run = subprocess.run([sys.executable, '-B', str(CORE), str(input_path),
                                  '--max-bits', '16'], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            output = json.loads(run.stdout)
            self.assertEqual(output['status'], 'bit_limit')
            self.assertFalse(output['exact'])
            self.assertEqual(output['weights'], ['1','0','0'])

    def test_trace_restores_existing_debug_hook(self):
        previous = sys.gettrace()
        def hook(frame,event,arg): return hook
        sys.settrace(hook)
        try:
            traced(self.core, MIXED, max_bits=16)
            self.assertIs(sys.gettrace(), hook)
        finally:
            sys.settrace(previous)


def main():
    global CORE, T15, WEIGHTED, REPORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, default=CORE)
    parser.add_argument('--t15-dir', type=Path, default=T15,
                        help='Existing cloud-market-game-theory directory')
    parser.add_argument('--weighted-dir', type=Path, default=WEIGHTED,
                        help='Existing cloud-weighted-plan-selector directory')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    CORE, T15, WEIGHTED, REPORT = args.core, args.t15_dir, args.weighted_dir, args.report
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FinalPivotBudgetTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if REPORT:
        report = {'schema':'triad-final-pivot-budget-v1',
                  'core':identity(CORE),
                  'test_source':identity(__file__),
                  'consumers':{'solver.py':identity(T15/'solver.py'),
                               'selector.py':identity(T15/'selector.py'),
                               'weighted_selector.py':identity(WEIGHTED/'weighted_selector.py')},
                  'tests_run':result.testsRun,
                  'failures':[{'test':str(t),'traceback':s} for t,s in result.failures],
                  'errors':[{'test':str(t),'traceback':s} for t,s in result.errors],
                  'passed':result.wasSuccessful(), 'recorded_solver_calls':RECORDS,
                  'scope':'Algebraic solver and real consumer regressions; no game/engine calls.'}
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
