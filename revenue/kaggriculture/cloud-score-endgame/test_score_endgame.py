# SPDX-License-Identifier: Apache-2.0
"""Tests compose actual existing dependency modules; no game panels executed."""
from copy import deepcopy
from fractions import Fraction as F
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from full_support import solve_full_table, verify_certificate
from terminal_utility import build_table, solve_terminal
from solver import solve_table
from selector import WholePlanSelector
from weighted_selector import make_selector
from score_endgame import embedding, make_score_selector, solve_absolute


def document(rows):
    ids = ['baseline'] + ['p' + str(i) for i in range(1, len(rows))]
    columns = ['s' + str(j) for j in range(len(rows[0]))]
    return {'plan_ids': ids, 'scenario_ids': columns, 'baseline': ids[0],
            'receipts': [{'plan': ids[i], 'scenario': columns[j],
                          'own_cash': str(100 + (1 if F(x) == 1 else -1 if F(x) == 0 else 0)),
                          'rival_cash': 100, 'done': True}
                         for i, row in enumerate(rows) for j, x in enumerate(row)],
            'source': {'kind': 'manufactured_consumer_fixture_not_game_evidence'}}


def solve(doc, **kw):
    return solve_absolute(doc, build_table, solve_full_table, verify_certificate, **kw)


class Draw:
    def __init__(self, index=0):
        self.index, self.calls = index, []
    def randrange(self, n):
        self.calls.append(n)
        return self.index


def consumer(draw=None, **kw):
    return make_score_selector(WholePlanSelector, make_selector, build_table,
                               solve_full_table, verify_certificate, rng=draw or Draw(), **kw)


def schedules(n):
    return [{'id': 'baseline' if i == 0 else 'p' + str(i),
             'sales': [[716 if i == 0 else 718, 2]]} for i in range(n)]


class AbsoluteTests(unittest.TestCase):
    def test_varying_baseline(self):
        doc = document([[0, 1], [1, 1], [0, 1]])
        old = solve_terminal(build_table(doc), solve_table)
        self.assertEqual(old['status'], 'absolute_matrix_solver_needed')
        relative = solve_terminal(build_table(doc), solve_table, objective='baseline_relative')
        self.assertEqual(relative['weights'], ['1', '0', '0'])
        answer = solve(doc)
        self.assertEqual(answer['weights'], ['0', '1', '0'])
        self.assertEqual(answer['value'], '1')
        self.assertEqual(answer['raw_solver']['weights'][0], '0')

    def test_mixed_recovery(self):
        ans = solve(document([[0, 0], [1, 0], [0, 1]]))
        self.assertEqual(ans['weights'], ['0', '1/2', '1/2'])
        self.assertEqual(ans['value'], '1/2')

    def test_ties_are_half_points(self):
        ans = solve(document([[0, 1], ['1/2', '1/2']]))
        self.assertEqual(ans['weights'], ['0', '1'])
        self.assertEqual(ans['value'], '1/2')

    def test_equal_absolute_optimum_retains_baseline(self):
        ans = solve(document([[1, 1], [1, 1]]))
        self.assertEqual(ans['status'], 'baseline_optimal')
        self.assertEqual(ans['weights'], ['1', '0'])

    def test_zero_optimum_retains_real_not_virtual_baseline(self):
        ans = solve(document([[0, 0], [0, 0]]))
        self.assertEqual(ans['status'], 'baseline_optimal')
        self.assertEqual(ans['weights'], ['1', '0'])
        self.assertEqual(ans['value'], '0')

    def test_incomplete_and_nonterminal_never_solve(self):
        for change in ('missing', 'done', 'cash'):
            doc = document([[0, 1], [1, 1]])
            if change == 'missing': doc['receipts'].pop()
            if change == 'done': doc['receipts'][0]['done'] = False
            if change == 'cash': doc['receipts'][0]['own_cash'] = None
            answer = solve_absolute(doc, build_table, lambda *_a, **_k: self.fail('solver called'), verify_certificate)
            self.assertFalse(answer['solver_called'])
            self.assertIsNone(answer['weights'])

    def test_budget_limit_preserves_real_baseline(self):
        ans = solve(document([[0, 1], [1, 1]]), max_pivots=0)
        self.assertEqual(ans['status'], 'solver_incomplete')
        self.assertEqual(ans['weights'], ['1', '0'])
        self.assertEqual(ans['value'], '0')

    def test_invalid_certificate_preserves_baseline(self):
        def bad(rows, **kw):
            answer = solve_full_table(rows, **kw)
            answer['value'] = '99'
            return answer
        ans = solve_absolute(document([[0, 1], [1, 1]]), build_table, bad, verify_certificate)
        self.assertEqual(ans['status'], 'invalid_certificate')
        self.assertEqual(ans['weights'], ['1', '0'])

    def test_closed_bound_not_completed(self):
        def unfinished(rows, **kw):
            ans = solve_full_table(rows, **kw)
            ans['status'], ans['exact'] = 'pivot_limit', False
            return ans
        ans = solve_absolute(document([[0, 1], [1, 1]]), build_table, unfinished, verify_certificate)
        self.assertEqual(ans['status'], 'solver_incomplete')
        self.assertEqual(ans['weights'], ['1', '0'])

    def test_bounds_and_source_detached(self):
        doc = document([[0, 1], [1, 1]])
        original = deepcopy(doc)
        ans = solve(doc)
        ans['source']['kind'] = 'changed'
        self.assertEqual(doc, original)
        self.assertIsNone(ans['scenario_probabilities'])
        self.assertIsNone(ans['win_probability'])
        self.assertEqual(ans['absolute_upper_bound'], ans['value'])

    def test_eight_real_plans_and_32_columns(self):
        rows = [[0] * 32 for _ in range(8)]; rows[7] = [1] * 32
        ans = solve(document(rows))
        self.assertEqual(ans['support'], [7])
        with self.assertRaises(ValueError): solve(document(rows + [[1] * 32]))

    def test_one_real_plan(self):
        ans = solve(document([['1/2', 1]]))
        self.assertEqual(ans['status'], 'baseline_optimal')
        self.assertEqual(ans['value'], '1/2')

    def test_cli(self):
        import terminal_utility, full_support, score_endgame
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'receipts.json'
            path.write_text(json.dumps(document([[0, 1], [1, 1]])))
            run = subprocess.run([sys.executable, score_endgame.__file__, '--input', str(path),
                                  '--terminal-file', terminal_utility.__file__,
                                  '--solver-file', full_support.__file__], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['weights'], ['0', '1'])


class SelectorTests(unittest.TestCase):
    def test_original_transform_inherited(self):
        self.assertIs(type(consumer()).transform, WholePlanSelector.transform)

    def test_exact_draw_and_original_indices(self):
        for draw, index in ((0, 1), (1, 2)):
            rng = Draw(draw); obj = consumer(rng)
            doc = document([[0, 0], [1, 0], [0, 1]])
            result = obj.choose('w', schedules(3), doc, feasible=lambda _: True)
            self.assertEqual(result['plan_index'], index)
            self.assertEqual(result['weights'], ['0', '1/2', '1/2'])
            self.assertEqual(result['solution']['value'], '1/2')
            self.assertEqual(rng.calls, [2])
            repeated = obj.choose('w', [], {}, feasible=lambda _: self.fail('rechecked'))
            self.assertEqual(repeated, result)
            self.assertEqual(obj.provider_calls, 1)
            self.assertEqual(obj.draws, 1)

    def test_baseline_optimal_no_draw(self):
        obj = consumer(); doc = document([[1, 1], [1, 1]])
        self.assertIsNone(obj.choose('w', schedules(2), doc, feasible=lambda _: True))
        self.assertEqual(obj.draws, 0)
        self.assertEqual(obj.last_objective['status'], 'baseline_optimal')
        obj.choose('w', [], {}, feasible=lambda _: True)
        self.assertEqual(obj.provider_calls, 1)

    def test_limits_and_unknown_no_draw(self):
        obj = consumer(max_pivots=0)
        self.assertIsNone(obj.choose('w', schedules(2), document([[0, 1], [1, 1]]), feasible=lambda _: True))
        self.assertEqual(obj.draws, 0)
        self.assertEqual(obj.last_objective['status'], 'solver_incomplete')
        for verdict in (None, False, 1):
            obj = consumer()
            self.assertIsNone(obj.choose('w', schedules(2), document([[0, 1], [1, 1]]), feasible=lambda _: verdict))
            self.assertEqual(obj.provider_calls, 0)
            self.assertEqual(obj.draws, 0)

    def test_each_real_feasibility_once(self):
        seen = []; obj = consumer()
        obj.choose('w', schedules(3), document([[0, 0], [1, 0], [0, 1]]),
                   feasible=lambda p: seen.append(p['id']) or True)
        self.assertEqual(seen, ['baseline', 'p1', 'p2'])

    def test_mismatched_plan_order_and_nonterminal(self):
        obj = consumer()
        self.assertIsNone(obj.choose('w', list(reversed(schedules(2))), document([[0, 1], [1, 1]]), feasible=lambda _: True))
        self.assertEqual(obj.provider_calls, 0)
        obj = consumer(); doc = document([[0, 1], [1, 1]]); doc['receipts'][0]['done'] = False
        self.assertIsNone(obj.choose('w', schedules(2), doc, feasible=lambda _: True))
        self.assertEqual(obj.provider_calls, 0)

    def test_virtual_name_collision(self):
        obj = consumer(); doc = document([[0, 1], [1, 1]])
        doc['plan_ids'][1] = '__score_embedding_zero__'
        for r in doc['receipts']:
            if r['plan'] == 'p1': r['plan'] = '__score_embedding_zero__'
        plans = schedules(2); plans[1]['id'] = '__score_embedding_zero__'
        ans = obj.choose('w', plans, doc, feasible=lambda _: True)
        self.assertEqual(ans['plan_index'], 1)
        self.assertEqual(ans['plan']['id'], '__score_embedding_zero__')

    def test_transformed_action_and_abort_preserve_other_slots(self):
        doc = document([[0, 1], [1, 1]])
        obj = consumer()
        base = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': [['SELL', 'WHEAT', 2], ['HIRE', 1]]}
        obs = {'step': 716, 'player': 0, 'farms': [{'money': 1000}, {'money': 1000}]}
        window = {'key': 'w', 'item': 'WHEAT', 'quantity': 2, 'now': 716, 'end': 718,
                  'slot': 0, 'plans': schedules(2), 'deltas': doc}
        out = obj.transform(obs, {}, base, window=window, post_unit_shed={'WHEAT': 2}, feasible=lambda _: True)
        self.assertEqual(out, {**base, 'market': [[], ['HIRE', 1]]})
        obs['step'] = 718
        out = obj.transform(obs, {}, base, post_unit_shed={'WHEAT': 2})
        self.assertEqual(out, base)
        self.assertEqual(obj.last_decision['plan_index'], 1)
        self.assertEqual(obj.last_decision['expected_floor_at_commit'], '1')
        self.assertEqual(obj.draws, 1)
        obj = consumer(); obs['step'] = 716
        obj.transform(obs, {}, base, window=window, post_unit_shed={'WHEAT': 2}, feasible=lambda _: True)
        obs['step'] = 718
        blocked = {**base, 'market': [['HIRE', 1], ['BUY_PRODUCT', 'FEED', 1]]}
        self.assertEqual(obj.transform(obs, {}, blocked, post_unit_shed={'WHEAT': 2}), blocked)
        self.assertIsNone(obj.active)
        self.assertEqual(obj.draws, 1)

    def test_terminal_full_queue_and_boundaries(self):
        doc = document([[0, 1], [1, 1]])
        base = {'farmer': ['PASS'], 'hands': [], 'market': [[], ['SELL', 'WHEAT', 2], ['SELL', 'MILK', 2]]}
        alternative = {**base, 'market': [['SELL', 'WHEAT', 2], ['SELL', 'MILK', 2]]}
        for r in doc['receipts']:
            r['own_action'] = deepcopy(base if r['plan'] == 'baseline' else alternative)
            r['step'] = 718
        obs = {'step': 718, 'player': 0}
        obj = consumer()
        self.assertEqual(obj.transform_terminal(obs, {}, base, document=doc, feasible=lambda _: True), alternative)
        self.assertEqual(obj.transform_terminal(obs, {}, base, document=doc, feasible=lambda _: True), alternative)
        self.assertEqual(obj.draws, 1)
        self.assertEqual(consumer().transform_terminal({**obs, 'step': 717}, {}, base, document=doc, feasible=lambda _: True), base)
        for change in ('worker', 'non_sale', 'step', 'action', 'baseline', 'unknown'):
            bad = deepcopy(doc)
            if change == 'worker':
                for r in bad['receipts'][2:]: r['own_action']['farmer'] = ['MOVE', 'N']
            if change == 'non_sale':
                for r in bad['receipts'][2:]: r['own_action']['market'][0] = ['HIRE', 1]
            if change == 'step': bad['receipts'][2]['step'] = 717
            if change == 'action': bad['receipts'][2]['own_action']['market'] = []
            if change == 'baseline': bad['receipts'][0]['own_action']['market'] = []
            obj = consumer()
            out = obj.transform_terminal(obs, {}, base, document=bad, feasible=lambda _: None if change == 'unknown' else True)
            self.assertEqual(out, base, change)
            self.assertEqual(obj.draws, 0, change)


    def test_terminal_current_feasibility_rechecked_without_redraw(self):
        doc = document([[0, 1], [1, 1]])
        base = {'farmer': ['PASS'], 'hands': [], 'market': [[], ['SELL', 'WHEAT', 2]]}
        better = {**base, 'market': [['SELL', 'WHEAT', 2]]}
        for receipt in doc['receipts']:
            receipt['own_action'] = deepcopy(base if receipt['plan'] == 'baseline' else better)
            receipt['step'] = 718
        obj = consumer(); obs = {'step': 718, 'player': 0}
        self.assertEqual(obj.transform_terminal(obs, {}, base, document=doc, feasible=lambda _: True), better)
        self.assertEqual(obj.transform_terminal(obs, {}, base, document=doc, feasible=lambda _: False), base)
        self.assertEqual(obj.draws, 1)
        self.assertIsNone(obj.active)
        self.assertEqual(obj.transform_terminal(obs, {}, base, document=doc, feasible=lambda _: True), base)
        self.assertEqual(obj.draws, 1)

    def test_unconsumed_private_metadata_does_not_change_choice(self):
        doc = document([[0, 0], [1, 0], [0, 1]])
        copy = deepcopy(doc)
        for i, receipt in enumerate(copy['receipts']):
            receipt['evaluation_only_hidden_stock'] = {'MILK': i * 100}
        left = consumer(Draw(1)).choose('w', schedules(3), doc, feasible=lambda _: True)
        right = consumer(Draw(1)).choose('w', schedules(3), copy, feasible=lambda _: True)
        self.assertEqual(left, right)


if __name__ == '__main__':
    unittest.main()
