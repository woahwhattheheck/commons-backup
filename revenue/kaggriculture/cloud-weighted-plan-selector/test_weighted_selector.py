# SPDX-License-Identifier: Apache-2.0
"""Consumer tests against actual T15, ASH and POLY modules; no game panels."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import time
import unittest

from weighted_selector import make_selector

TABLE = [[0, 0, 0], [3, -1, -1], [-1, 3, -1], [-1, -1, 3]]
PLANS = [{'id': f'p{i}', 'sales': [[700 + i, 8]]} for i in range(4)]
CFG = {'episodeSteps': 720, 'turnsPerDay': 24, 'maxMarketOrdersPerTurn': 10}
BASE = {'farm': [['PASS']], 'hands': [['PASS']],
        'market': [['BUY_SEED', 'WHEAT', 1], ['SELL', 'TOMATO', 8],
                   ['HIRE'], ['SELL', 'CARROT', 1]], 'memory': {'unchanged': [1]}}


class Draw:
    def __init__(self, value=0):
        self.value, self.calls, self.bounds = value, 0, []
    def randrange(self, upper):
        self.calls += 1
        self.bounds.append(upper)
        return self.value


def obs(step=700, player=0):
    return {'step': step, 'player': player,
            'farms': [{'money': 500}, {'money': 500}]}


def window(key='lot', plans=None, table=None, now=700, end=703, slot=1):
    return {'key': key, 'item': 'TOMATO', 'quantity': 8, 'now': now, 'end': end,
            'slot': slot, 'plans': deepcopy(PLANS if plans is None else plans),
            'deltas': deepcopy(TABLE if table is None else table)}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def setup_sources(args):
    global Selector, ASH, POLY, OLD_SOLVER, SOURCES
    paths = {'selector': args.t15_dir / 'selector.py', 'solver': args.t15_dir / 'solver.py',
             'continuation': args.continuation_dir / 'continuation.py',
             'full_support': args.full_support_dir / 'full_support.py'}
    old = sys.modules.get('solver')
    OLD_SOLVER = load_module('solver', paths['solver'])
    try:
        Selector = load_module('prism_t15_selector', paths['selector']).WholePlanSelector
    finally:
        if old is None:
            sys.modules.pop('solver', None)
        else:
            sys.modules['solver'] = old
    ASH = load_module('prism_ash', paths['continuation']).ContinuationPlanSelector
    POLY = load_module('prism_poly', paths['full_support'])
    SOURCES = {}
    for name, path in paths.items():
        body = path.read_bytes()
        SOURCES[name] = {'git_blob': hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest(),
                         'sha256': hashlib.sha256(body).hexdigest()}


def make(draw=0, provider=None, **kwargs):
    return make_selector(Selector, POLY.solve_full_table if provider is None else provider,
                         rng=Draw(draw), **kwargs)


def act(selector, step=700, *, win=None, stock=8, player=0, base=None, **kw):
    return selector.transform(obs(step, player), CFG, deepcopy(BASE if base is None else base),
                              window=window() if win is None else win,
                              post_unit_shed={'TOMATO': stock, 'CARROT': 1},
                              feasible=lambda p: True, **kw)


class ConsumerTests(unittest.TestCase):
    def test_transform_is_original_function(self):
        self.assertIs(type(make()).transform, Selector.transform)

    def test_original_three_plan_limit_discriminates_extension(self):
        with self.assertRaises(ValueError):
            Selector().choose('a', PLANS, TABLE, feasible=lambda p: True)
        self.assertIsNotNone(make().choose('a', PLANS, TABLE, feasible=lambda p: True))

    def test_actual_poly_all_three_positive_support_indices(self):
        for draw in range(3):
            with self.subTest(draw=draw):
                s = make(draw)
                selected = s.choose('a', PLANS, TABLE, feasible=lambda p: True)
                self.assertEqual(selected['plan_index'], draw + 1)
                self.assertEqual(selected['weights'], ['0', '1/3', '1/3', '1/3'])
                self.assertEqual(selected['solution']['value'], '1/3')
                self.assertEqual(s.draws, 1)
                self.assertTrue(selected['solution']['provider_result']['certificate_valid'])

    def test_actual_poly_pivot_limit_keeps_baseline_without_draw(self):
        s = make(provider=lambda rows: POLY.solve_full_table(rows, max_pivots=0))
        self.assertEqual(act(s), BASE)
        self.assertEqual(s.draws, 0)
        self.assertEqual(s.last_decision['reason'], 'provider_not_optimal')
        self.assertEqual(s.last_decision['provider_status'], 'pivot_limit')

    def test_actual_poly_zero_optimum_keeps_baseline(self):
        s = make()
        rows = [[0, 0], [-1, -2], [-3, 1], [-2, -5]]
        self.assertEqual(act(s, win=window(table=rows)), BASE)
        self.assertEqual(s.draws, 0)

    def test_same_step_retry_does_not_resolve_or_redraw(self):
        s = make(1)
        a = act(s)
        self.assertEqual(act(s), a)
        self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_later_call_uses_chosen_plan_not_new_provider(self):
        s = make(1)
        act(s)
        self.assertEqual(act(s, 702)['market'][1], ['SELL', 'TOMATO', 8])
        self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_all_plan_callbacks_including_zero_weight(self):
        s = make()
        seen = []
        def feasible(p):
            seen.append(p['id'])
            return p['id'] != 'p0'
        self.assertIsNone(s.choose('a', PLANS, TABLE, feasible=feasible))
        self.assertEqual(seen, ['p0', 'p1', 'p2', 'p3'])
        self.assertEqual(s.provider_calls, 0)

    def test_unknown_or_truthy_feasibility_does_not_draw(self):
        for verdict in (None, 1, 'yes', False):
            s = make()
            self.assertIsNone(s.choose('a', PLANS, TABLE, feasible=lambda p: verdict))
            self.assertEqual(s.draws, 0)

    def test_callback_plan_mutation_is_detached(self):
        s = make()
        plans = deepcopy(PLANS)
        def feasible(p):
            p['sales'][0][1] = 999
            return True
        chosen = s.choose('a', plans, TABLE, feasible=feasible)
        self.assertEqual(plans, PLANS)
        self.assertEqual(chosen['plan']['sales'][0][1], 8)

    def test_provider_rows_are_immutable_and_complete(self):
        calls = []
        def provider(rows):
            self.assertIsInstance(rows, tuple)
            self.assertTrue(all(isinstance(r, tuple) for r in rows))
            self.assertEqual(rows, tuple(tuple(F(v) for v in row) for row in TABLE))
            calls.append(rows)
            return POLY.solve_full_table(rows)
        act(make(provider=provider))
        self.assertEqual(len(calls), 1)

    def test_other_fields_and_original_market_slots_preserved(self):
        for player in (0, 1):
            out = act(make(), player=player)
            self.assertEqual(out['farm'], BASE['farm'])
            self.assertEqual(out['hands'], BASE['hands'])
            self.assertEqual(out['memory'], BASE['memory'])
            for index in (0, 2, 3):
                self.assertEqual(out['market'][index], BASE['market'][index])
            self.assertEqual(out['market'][1], [])

    def test_source_inputs_and_returned_commitment_are_detached(self):
        s = make()
        plans = deepcopy(PLANS)
        chosen = s.choose('a', plans, TABLE, feasible=lambda p: True)
        plans[1]['sales'][0][1] = 1
        chosen['plan']['sales'][0][1] = 2
        chosen['solution']['weights'][1] = '0'
        self.assertEqual(s.active['plan']['sales'][0][1], 8)
        self.assertEqual(s.active['weights'][1], '1/3')

    def test_original_current_stock_abort_remains(self):
        s = make()
        act(s)
        self.assertEqual(act(s, 701, stock=0), BASE)
        self.assertIsNone(s.active)
        self.assertIn('lot', s.completed)
        self.assertEqual(s.draws, 1)

    def test_original_due_slot_obstruction_remains(self):
        s = make()
        act(s)
        changed = deepcopy(BASE)
        changed['market'][1] = ['BUY_SEED', 'TOMATO', 1]
        self.assertEqual(act(s, 701, base=changed), changed)
        self.assertEqual(s.draws, 1)

    def test_ash_changed_continuation_retires_without_redraw(self):
        s = make(2)
        wrapped = ASH(s)
        act(wrapped, continuation_feasible=lambda p, c: True)
        self.assertEqual(act(wrapped, 701, continuation_feasible=lambda p, c: None), BASE)
        self.assertEqual(act(wrapped, 701, continuation_feasible=lambda p, c: True), BASE)
        self.assertEqual(s.draws, 1)
        self.assertIn('lot', s.completed)

    def test_ash_skipped_positive_date_preserves_fallback(self):
        s = make()
        wrapped = ASH(s)
        act(wrapped, continuation_feasible=lambda p, c: True)
        self.assertEqual(act(wrapped, 702, continuation_feasible=lambda p, c: True), BASE)
        self.assertEqual(wrapped.last_decision['reason'], 'due_step_not_emitted')

    def test_ash_complete_path_one_draw_and_original_row_index(self):
        s = make(2)
        wrapped = ASH(s)
        records = []
        def current(p, context):
            records.append(context['plan_index'])
            return True
        for now in range(700, 704):
            out = act(wrapped, now, continuation_feasible=current)
            self.assertEqual(out['market'][1], ['SELL', 'TOMATO', 8] if now == 703 else [])
        self.assertEqual(records, [3, 3, 3, 3])
        self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_terminal_day_uses_original_last_market(self):
        plans = [{'id': str(i), 'sales': [[716 if i == 0 else 718, 8]]} for i in range(4)]
        s = make(2)
        wrapped = ASH(s)
        w = window(plans=plans, now=716, end=718)
        act(wrapped, 716, win=w, continuation_feasible=lambda p, c: True)
        out = act(wrapped, 718, win=w, continuation_feasible=lambda p, c: True)
        self.assertEqual(out['market'][1], ['SELL', 'TOMATO', 8])
        self.assertEqual(s.draws, 1)

    def test_malformed_weights_keep_entire_fallback(self):
        for weights in (['0', '1/2', '1/2'], ['0', '1', '-1', '1'],
                        ['0', '1/3', '1/3', '0'], ['0', 0.5, 0.5, '0'], ['0', 'nan', '0', '1']):
            s = make(provider=lambda rows: {'weights': weights, 'status': 'optimal', 'value': '1'})
            self.assertEqual(act(s), BASE)
            self.assertEqual(s.draws, 0)

    def test_claimed_value_cannot_override_actual_floor(self):
        def provider(rows):
            result = POLY.solve_full_table(rows)
            result['value'] = '999'
            return result
        s = make(provider=provider)
        self.assertEqual(act(s), BASE)
        self.assertEqual(s.last_decision['reason'], 'provider_value_mismatch')

    def test_negative_column_cannot_be_hidden_by_provider(self):
        s = make(provider=lambda rows: {'weights': ['0', '1', '0', '0'], 'value': '99', 'status': 'optimal'})
        self.assertEqual(act(s), BASE)
        self.assertEqual(s.last_decision['value'], '-1')

    def test_provider_exception_text_not_exposed(self):
        def provider(rows):
            raise RuntimeError('PRIVATE-CONTEXT-SENTINEL')
        s = make(provider=provider)
        self.assertEqual(act(s), BASE)
        self.assertNotIn('SENTINEL', repr(s.last_decision))
        act(s)
        self.assertEqual(s.provider_calls, 1)

    def test_duplicate_plan_ids_do_not_draw(self):
        plans = deepcopy(PLANS)
        plans[-1]['id'] = plans[0]['id']
        s = make()
        self.assertEqual(act(s, win=window(plans=plans)), BASE)
        self.assertEqual(s.draws, 0)

    def test_nonrectangular_nonzero_baseline_and_budget_inputs(self):
        for table in ([[0, 0], [1], [1], [1]], [[1], [2], [3], [4]]):
            self.assertEqual(act(make(), win=window(table=table)), BASE)
        self.assertEqual(act(make(max_plans=3)), BASE)
        self.assertEqual(act(make(max_streams=2)), BASE)

    def test_exact_sampling_keeps_all_original_mass_including_baseline(self):
        # Sampling-only injected record: not an optimization or game witness.
        # The runtime deliberately does not duplicate the independent checker.
        weights = ['1/2', '1/3', '1/10', '1/15']
        rows = [[0], [2], [2], [2]]
        record = {'weights': weights, 'status': 'optimal', 'value': '1'}
        count = Counter()
        for draw in range(30):
            s = make(draw, provider=lambda table: deepcopy(record))
            choice = s.choose(draw, PLANS, rows, feasible=lambda p: True)
            count[choice['plan_index']] += 1
            self.assertEqual(s.rng.bounds, [30])
        self.assertEqual(count, {0: 15, 1: 10, 2: 3, 3: 2})

    def test_exact_sampling_budget_preserves_baseline_without_rng(self):
        s = make(max_draw_bits=1)
        self.assertEqual(act(s), BASE)
        self.assertEqual(s.last_decision['reason'], 'sampling_budget_exhausted')
        self.assertEqual(s.rng.calls, 0)

    def test_invalid_rng_retires_key(self):
        s = make(9)
        self.assertEqual(act(s), BASE)
        self.assertEqual(s.draws, 0)
        act(s)
        self.assertEqual(s.rng.calls, 1)

    def test_existing_modes_preserve_baseline_and_pure_behavior(self):
        s = make()
        self.assertEqual(act(s, mode='baseline'), BASE)
        self.assertEqual((s.provider_calls, s.draws), (0, 0))
        s = make()
        rows = [[0, 0], [1, 2], [3, 2], [4, -1]]
        s.choose('a', PLANS, rows, feasible=lambda p: True, mode='pure')
        self.assertEqual(s.active['plan_index'], 2)
        self.assertEqual(s.provider_calls, 0)

    def test_previous_three_plan_actions_match_original(self):
        table = [[0, 0], [3, -1], [-1, 3]]
        for seed in range(12):
            original = Selector(rng=random.Random(seed))
            adapted = make_selector(Selector, lambda rows: dict(OLD_SOLVER.solve_table(rows), status='optimal'),
                                    rng=random.Random(seed))
            w = window(plans=PLANS[:3], table=table)
            for now in (700, 701, 702):
                self.assertEqual(act(original, now, win=w), act(adapted, now, win=w))
            self.assertEqual(original.draws, adapted.draws)

    def test_incomplete_dated_plan_keeps_original_action(self):
        plans = deepcopy(PLANS)
        plans[3]['sales'] = [[703, 7]]
        self.assertEqual(act(make(), win=window(plans=plans)), BASE)

    def test_new_key_cannot_replace_active_lot(self):
        s = make()
        s.choose('a', PLANS, TABLE, feasible=lambda p: True)
        with self.assertRaises(ValueError):
            s.choose('b', PLANS, TABLE, feasible=lambda p: True)
        self.assertEqual(s.draws, 1)

    def test_actual_poly_larger_row_family_keeps_original_index(self):
        plans = [{'id': str(i), 'sales': [[700, 8]]} for i in range(9)]
        rows = [[0, 0]] + [[i, i] for i in range(1, 9)]
        s = make()
        s.choose('a', plans, rows, feasible=lambda p: True)
        self.assertEqual(s.active['plan_index'], 8)
        self.assertEqual(len(s.active['weights']), 9)


def witness():
    s = make(2)
    wrapped = ASH(s)
    trace = []
    for now in range(700, 704):
        action = act(wrapped, now, continuation_feasible=lambda p, c: True)
        trace.append({'step': now, 'action': action, 'decision': deepcopy(wrapped.last_decision)})
    solution = deepcopy(s.active['solution'])
    timings = []
    for _ in range(100):
        start = time.perf_counter_ns()
        act(make())
        timings.append((time.perf_counter_ns() - start) / 1_000_000)
    return {'scope': 'actual consumer integration over an algebraic table; no engine or game execution',
            'table': TABLE, 'plans': PLANS, 'solution': solution, 'trace': trace,
            'draws': s.draws, 'provider_calls': s.provider_calls,
            'timing_samples': 100, 'warm_max_ms_including_poly': max(timings)}


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--t15-dir', type=Path, default=root / 'cloud-market-game-theory')
    parser.add_argument('--continuation-dir', type=Path, default=root / 'cloud-plan-continuation')
    parser.add_argument('--full-support-dir', type=Path, default=root / 'cloud-full-support')
    parser.add_argument('--json-output', type=Path)
    parser.add_argument('--witness-output', type=Path)
    args = parser.parse_args()
    setup_sources(args)
    capture = io.StringIO()
    result = unittest.TextTestRunner(stream=capture, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ConsumerTests))
    print(capture.getvalue(), end='')
    record = {'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'passed': result.wasSuccessful(),
              'dependencies': SOURCES, 'full_games': 0, 'engine_executions': 0,
              'policy_promotion': False}
    if result.wasSuccessful():
        record['witness'] = witness()
    if args.json_output:
        args.json_output.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    if args.witness_output and result.wasSuccessful():
        args.witness_output.write_text(json.dumps(record['witness'], indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
