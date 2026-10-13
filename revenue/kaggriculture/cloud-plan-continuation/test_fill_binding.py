# SPDX-License-Identifier: Apache-2.0
"""Joined final-action/fill/continuation tests using existing real components.

From repository root: python path/to/test_fill_binding.py -v
Use --dependencies DIR for a relocated exact-source test cache (three files).
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WholePlanSelector = ObservedFillLedger = full_sale_verdict = None
from continuation import ContinuationPlanSelector


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dependencies(cache=None):
    paths = ({name: cache / name for name in ('solver.py', 'selector.py', 'observed_fills.py')}
             if cache else {
                 'solver.py': ROOT / 'cloud-market-game-theory/solver.py',
                 'selector.py': ROOT / 'cloud-market-game-theory/selector.py',
                 'observed_fills.py': ROOT / 'cloud-observed-fills/observed_fills.py'})
    solver = load('ash_fill_solver', paths['solver.py'])
    previous = sys.modules.get('solver')
    try:
        sys.modules['solver'] = solver
        selector = load('ash_fill_selector', paths['selector.py'])
    finally:
        if previous is None:
            sys.modules.pop('solver', None)
        else:
            sys.modules['solver'] = previous
    fills = load('ash_fill_evidence', paths['observed_fills.py'])
    return selector.WholePlanSelector, fills.ObservedFillLedger, fills.full_sale_verdict, paths


def obs(step=10, player=0, shed=None):
    return {'step': step, 'player': player, 'farms': [{'money': 1000}, {'money': 1000}],
            'private': {'shed': {'EGG': 2} if shed is None else shed}}


def base(item='EGG', quantity=2):
    return {'farmer': ['PASS'], 'hands': [['PASS']],
            'market': [[], ['SELL', item, quantity]], 'keep': {'x': [1, 2]}}


def win(start=10, end=12, item='EGG', key='lot', split=True):
    return {'key': key, 'item': item, 'quantity': 2, 'now': start, 'end': end, 'slot': 1,
            'plans': [{'id': 'now', 'sales': [[start, 2]]},
                      {'id': 'split', 'sales': [[start, 1], [end, 1]] if split else [[end, 2]]}],
            'deltas': [[0, 0], [1, 1]]}


def wrapped(**budgets):
    return ContinuationPlanSelector(WholePlanSelector(random.Random(0)),
                                    fill_ledger=ObservedFillLedger(**budgets),
                                    fill_verdict=full_sale_verdict)


def call(w, step=10, window=None, player=0, shed=None, action=None, verdict=True, cfg=None):
    o = obs(step, player, shed)
    return w.transform(o, cfg or {}, base() if action is None else action,
                       window=window, post_unit_shed=o['private']['shed'],
                       feasible=lambda p: True,
                       continuation_feasible=lambda p, c: verdict)


def record(w, action, *, step=10, player=0, shed=None, inventories=None, cfg=None):
    o = obs(step, player, shed)
    return w.record_final(o, cfg or {}, action, post_unit_shed=o['private']['shed'],
                          post_unit_inventories=inventories)


class FillBindingTests(unittest.TestCase):
    def test_full_fill_both_seats_allows_remaining_sale_one_draw(self):
        for player in (0, 1):
            w = wrapped(); out = call(w, window=win(), player=player)
            self.assertEqual(record(w, out, player=player)['status'], 'recorded')
            call(w, 11, player=player, shed={'EGG': 1})
            self.assertIs(w.last_fill['verdict'], True)
            self.assertEqual(call(w, 12, player=player, shed={'EGG': 1})['market'][1], ['SELL', 'EGG', 1])
            self.assertEqual(w.draws, 1)

    def test_earlier_final_sale_drains_due_slot_and_retires_before_replenished_suffix(self):
        w = wrapped(); out = call(w, window=win())
        out['market'][0] = ['SELL', 'EGG', 2]
        record(w, out)
        self.assertEqual(call(w, 11, shed={'EGG': 0}), base())
        self.assertEqual(w.last_decision['reason'], 'previous_sale_short_fill')
        self.assertIs(w.last_fill['verdict'], False)
        self.assertIsNone(w.active)
        self.assertIn('lot', w.selector.completed)
        self.assertEqual(call(w, 12, window=win(start=12, end=14), shed={'EGG': 2}), base())
        self.assertEqual(w.draws, 1)

    def test_ambiguous_round_trip_is_unknown_not_filled(self):
        w = wrapped(); out = call(w, window=win(item='WHEAT'), shed={'WHEAT': 2}, action=base('WHEAT'))
        out['market'][0] = ['BUY_PRODUCT', 'WHEAT', 1]
        # Finalizer changed workers; recorder gets the actual final unit-stage shed.
        record(w, out, shed={'WHEAT': 0})
        self.assertEqual(call(w, 11, shed={'WHEAT': 0}), base())
        self.assertEqual(w.last_fill['status'], 'unknown')
        self.assertIsNone(w.last_fill['verdict'])
        self.assertEqual(w.last_fill['result']['status'], 'ambiguous')

    def test_missing_final_record_is_not_an_observed_fill(self):
        w = wrapped(); call(w, window=win())
        self.assertEqual(call(w, 11, shed={'EGG': 1}), base())
        self.assertEqual(w.last_decision['reason'], 'final_sale_not_recorded')

    def test_changed_final_product_not_bound_to_original_plan(self):
        w = wrapped(); out = call(w, window=win())
        out['market'][1] = ['SELL', 'MILK', 1]
        self.assertEqual(record(w, out)['status'], 'unknown')
        self.assertEqual(call(w, 11), base())
        self.assertEqual(w.last_decision['reason'], 'final_sale_not_recorded')

    def test_changed_final_quantity_not_bound_to_original_plan(self):
        w = wrapped(); out = call(w, window=win())
        out['market'][1][2] = 2
        self.assertEqual(record(w, out)['status'], 'unknown')
        self.assertEqual(call(w, 11), base())

    def test_changed_slot_not_bound(self):
        w = wrapped(); out = call(w, window=win())
        out['market'] = [out['market'][1]]
        self.assertEqual(record(w, out)['status'], 'unknown')

    def test_different_player_record_not_bound(self):
        w = wrapped(); out = call(w, window=win())
        self.assertEqual(record(w, out, player=1)['status'], 'unknown')
        self.assertEqual(call(w, 11), base())

    def test_different_date_record_not_bound(self):
        w = wrapped(); out = call(w, window=win())
        self.assertEqual(record(w, out, step=11)['status'], 'unknown')

    def test_same_step_replacement_records_final_queue(self):
        w = wrapped(); out = call(w, window=win())
        first = record(w, out)
        changed = deepcopy(out); changed['keep']['x'].append(3)
        second = record(w, changed)
        self.assertNotEqual(first['binding']['action_sha256'], second['binding']['action_sha256'])
        call(w, 11, shed={'EGG': 1})
        self.assertEqual(w.last_fill['result']['binding'], second['binding'])
        self.assertEqual(w.draws, 1)

    def test_same_step_retry_has_one_draw_and_requires_new_final_record(self):
        w = wrapped(); first = call(w, window=win()); record(w, first)
        second = call(w, window=win())
        self.assertEqual(first, second); self.assertEqual(w.draws, 1)
        record(w, second); call(w, 11, shed={'EGG': 1})
        self.assertEqual(w.last_fill['status'], 'filled')

    def test_same_step_observation_does_not_consume_pending(self):
        w = wrapped(); out = call(w, window=win()); record(w, out)
        self.assertEqual(w.observe_fills(obs(10))['status'], 'pending')
        self.assertEqual(w.observe_fills(obs(10))['status'], 'pending')
        self.assertEqual(w.observe_fills(obs(11, shed={'EGG': 1}))['status'], 'filled')

    def test_gap_preserves_full_fallback(self):
        w = wrapped(); out = call(w, window=win()); record(w, out)
        self.assertEqual(call(w, 12, shed={'EGG': 1}), base())
        self.assertEqual(w.last_decision['reason'], 'fill_observation_not_adjacent')

    def test_wrong_observation_seat_does_not_confirm(self):
        w = wrapped(); out = call(w, window=win()); record(w, out)
        self.assertEqual(call(w, 11, player=1, shed={'EGG': 1}), base())
        self.assertIsNone(w.last_fill['verdict'])

    def test_replaced_shared_ledger_binding_is_detected(self):
        w = wrapped(); out = call(w, window=win()); record(w, out)
        other = deepcopy(out); other['keep']['x'].append(99)
        w._fill_ledger.record(obs(), {}, other, post_unit_shed={'EGG': 2})
        self.assertEqual(call(w, 11, shed={'EGG': 1}), base())
        self.assertEqual(w.last_decision['reason'], 'fill_binding_mismatch')

    def test_end_of_day_deposits_preserve_order_and_enable_full_verdict(self):
        w = wrapped(); out = call(w, 23, win(23, 25), shed={'EGG': 2, 'WHEAT': 98})
        record(w, out, step=23, shed={'EGG': 2, 'WHEAT': 98}, inventories=[{'MILK': 2}, {'WOOL': 3}])
        call(w, 24, shed={'EGG': 1, 'WHEAT': 98, 'MILK': 1})
        self.assertEqual(w.last_fill['status'], 'filled')

    def test_unknown_daily_deposits_dont_create_fill(self):
        w = wrapped(); out = call(w, 23, win(23, 25))
        record(w, out, step=23)
        self.assertEqual(call(w, 24, shed={'EGG': 1}), base())
        self.assertEqual(w.last_fill['result']['reason'], 'after_market_deposits_unknown')

    def test_terminal_result_can_be_observed_without_an_extra_action(self):
        w = wrapped(); out = call(w, 717, win(717, 718))
        record(w, out, step=717); call(w, 718, shed={'EGG': 1})
        out = call(w, 718, shed={'EGG': 1}); record(w, out, step=718, shed={'EGG': 1})
        self.assertEqual(w.observe_fills(obs(719, shed={'EGG': 0}))['status'], 'filled')
        self.assertEqual(w.draws, 1)

    def test_reconciliation_budget_exhaustion_keeps_unknown(self):
        w = wrapped(max_transitions=1); out = call(w, window=win())
        out['market'][0] = ['BUY_PRODUCT', 'WHEAT', 2]
        record(w, out)
        self.assertEqual(call(w, 11, shed={'EGG': 1, 'WHEAT': 2}), base())
        self.assertEqual(w.last_fill['result']['reason'], 'transition_budget_exceeded')

    def test_fill_truth_does_not_replace_current_physics(self):
        w = wrapped(); out = call(w, window=win()); record(w, out)
        self.assertEqual(call(w, 11, shed={'EGG': 1}, verdict=False), base())
        self.assertEqual(w.last_fill['status'], 'filled')
        self.assertEqual(w.last_decision['reason'], 'continuation_infeasible')

    def test_no_sale_does_not_require_record(self):
        w = wrapped(); out = call(w, window=win(split=False))
        self.assertEqual(record(w, out)['status'], 'no_due_sale')
        call(w, 11)
        self.assertEqual(call(w, 12)['market'][1], ['SELL', 'EGG', 2])
        self.assertEqual(w.draws, 1)

    def test_detached_final_inputs_and_results(self):
        w = wrapped(); out = call(w, window=win()); original = deepcopy(out)
        binding = record(w, out)
        self.assertEqual(out, original)
        binding['binding']['step'] = 555
        out['market'][1][2] = 999
        result = w.observe_fills(obs(11, shed={'EGG': 1}))
        self.assertEqual(result['status'], 'filled')
        result['result']['orders'].clear()
        self.assertTrue(w.last_fill['result']['orders'])

    def test_null_key_is_valid(self):
        w = wrapped(); out = call(w, window=win(key=None)); record(w, out)
        self.assertEqual(w.observe_fills(obs(11, shed={'EGG': 1}))['status'], 'filled')
        self.assertIsNone(w.last_fill['key'])

    def test_constructor_requires_coherent_optional_pair(self):
        with self.assertRaises(ValueError):
            ContinuationPlanSelector(WholePlanSelector(), fill_ledger=ObservedFillLedger())
        with self.assertRaises(ValueError):
            ContinuationPlanSelector(WholePlanSelector(), fill_verdict=full_sale_verdict)

    def test_deferral_and_baseline_keep_disabled_contract(self):
        w = ContinuationPlanSelector(WholePlanSelector(random.Random(0)))
        self.assertEqual(w.last_fill['status'], 'disabled')
        out = call(w, window=win())
        self.assertEqual(record(w, out)['status'], 'disabled')
        call(w, 11, shed={'EGG': 1})
        self.assertEqual(call(w, 12, shed={'EGG': 1})['market'][1], ['SELL', 'EGG', 1])
        self.assertEqual(w.draws, 1)

    def test_missing_terminal_record_not_labeled_complete(self):
        w = wrapped(); out = call(w, 717, win(717, 718)); record(w, out, step=717)
        call(w, 718, shed={'EGG': 1})
        self.assertEqual(w.observe_fills(obs(719, shed={'EGG': 0}))['status'], 'unknown')
        self.assertIn('lot', w.selector.completed)

    def test_reported_failure_survives_until_next_action(self):
        w = wrapped(); out = call(w, window=win())
        out['market'][0] = ['SELL', 'EGG', 2]; record(w, out)
        w.observe_fills(obs(11, shed={'EGG': 0}))
        self.assertEqual(call(w, 11, shed={'EGG': 0}), base())
        self.assertEqual(w.last_decision['reason'], 'previous_sale_short_fill')

    def test_same_step_invalid_record_can_be_replaced(self):
        w = wrapped(); out = call(w, window=win())
        wrong = deepcopy(out); wrong['market'][1][1] = 'MILK'; record(w, wrong)
        self.assertEqual(record(w, out)['status'], 'recorded')
        self.assertEqual(w.observe_fills(obs(11, shed={'EGG': 1}))['status'], 'filled')


def default_parity(original_path):
    """Compare default calls with exact original; RNG seeds are not game seeds."""
    original = load('ash_fill_original_continuation', original_path)
    body = original_path.read_bytes()
    original_blob = hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
    if original_blob != '165890d9e2534785ee4114e39549528e3f14ad82':
        raise ValueError('Expected the original ASH continuation Git blob')
    scenarios = []
    scenarios.append(('split', [(10, win(), {}), (11, None, {'shed': {'EGG': 1}}),
                               (12, None, {'shed': {'EGG': 1}}), (13, None, {})]))
    scenarios.append(('deferred', [(10, win(split=False), {}), (11, None, {}),
                                  (12, None, {}), (13, None, {})]))
    mixed = win(); mixed['plans'].append({'id': 'late', 'sales': [[12, 2]]})
    mixed['deltas'] = [[0, 0], [1, -1], [-1, 2]]
    scenarios.append(('mixed', [(10, mixed, {}), (10, mixed, {}), (11, None, {}),
                               (12, None, {}), (13, None, {})]))
    missed = win(); missed['plans'][1]['sales'] = [[11, 1], [12, 1]]
    scenarios.append(('missed', [(10, missed, {}), (12, None, {}), (13, None, {})]))
    scenarios.append(('backward', [(10, win(split=False), {}), (11, None, {}),
                                  (10, None, {}), (12, None, {})]))
    scenarios.append(('unknown', [(10, win(), {}), (11, None, {'verdict': None}), (12, None, {})]))
    scenarios.append(('infeasible', [(10, win(), {}), (11, None, {'verdict': False}), (12, None, {})]))
    scenarios.append(('stock', [(10, win(split=False), {}), (12, None, {'shed': {'EGG': 0}})]))
    occupied = base(); occupied['market'][1] = ['BUY_PRODUCT', 'WHEAT', 1]
    scenarios.append(('slot', [(10, win(split=False), {}), (12, None, {'action': occupied})]))
    scenarios.append(('terminal', [(717, win(717, 718), {}), (718, None, {'shed': {'EGG': 1}}), (719, None, {})]))
    scenarios.append(('rollover', [(10, win(), {}), (12, None, {}),
                                  (13, win(13, 15, key='next'), {}), (14, None, {}), (15, None, {})]))
    zero = win(); zero['deltas'][1] = [-1, -1]
    scenarios.append(('zero', [(10, zero, {}), (11, None, {}), (12, None, {})]))
    count = 0; transcript = hashlib.sha256()
    for sampler_seed in range(32):
        for name, sequence in scenarios:
            old = original.ContinuationPlanSelector(WholePlanSelector(random.Random(sampler_seed)))
            new = ContinuationPlanSelector(WholePlanSelector(random.Random(sampler_seed)))
            for step, window, options in sequence:
                left = call(old, step, deepcopy(window), **deepcopy(options))
                right = call(new, step, deepcopy(window), **deepcopy(options))
                def state(w, action):
                    return {'action': action, 'active': w.active, 'draws': w.draws,
                            'completed': sorted(w.selector.completed), 'decision': w.last_decision}
                expected, actual = state(old, left), state(new, right)
                if expected != actual:
                    raise AssertionError((name, sampler_seed, step, expected, actual))
                transcript.update(json.dumps([name, sampler_seed, step, actual],
                                  sort_keys=True, separators=(',', ':')).encode())
                count += 1
    return {'original_blob': original_blob, 'sampler_seeds': 32,
            'scenario_count': len(scenarios), 'scenarios': [name for name, _ in scenarios],
            'paired_invocations': count, 'differences': 0,
            'transcript_sha256': transcript.hexdigest(),
            'scope': 'default-mode action/state differential, not game seeds or game runs'}


def evidence(paths, result):
    def identity(path):
        body = path.read_bytes()
        return {'bytes': len(body), 'git_blob': hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest(),
                'sha256': hashlib.sha256(body).hexdigest()}
    rows = []
    for player in (0, 1):
        for kind in ('filled', 'short'):
            w=wrapped(); out=call(w, window=win(), player=player)
            if kind=='short': out['market'][0]=['SELL','EGG',2]
            record(w,out,player=player)
            next_shed={'EGG':1 if kind=='filled' else 0}
            got=call(w,11,player=player,shed=next_shed)
            rows.append({'case':kind,'player':player,'final_action':out,'next_shed':next_shed,
                         'next_action':got,'last_fill':w.last_fill,'draws':w.draws})
    return {'scope':'new joined consumer invocations; no engine/game run or cash-receipt claim',
            'tests':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)},
            'inputs':{name:identity(path) for name,path in paths.items()},
            'runtime':identity(HERE/'continuation.py'),'test':identity(Path(__file__)),
            'witnesses':rows}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dependencies',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--baseline-continuation',type=Path,
                        help='Optional exact original ASH file for default-mode differential')
    args,rest=parser.parse_known_args()
    WholePlanSelector,ObservedFillLedger,full_sale_verdict,paths=dependencies(args.dependencies)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FillBindingTests)
    result=unittest.TextTestRunner(verbosity=2 if '-v' in rest else 1).run(suite)
    packet=evidence(paths,result)
    packet['default_differential']=(default_parity(args.baseline_continuation)
                                   if args.baseline_continuation else None)
    if args.report: args.report.write_text(json.dumps(packet,indent=2)+'\n')
    if packet['default_differential']: print(json.dumps(packet['default_differential'],sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
else:
    WholePlanSelector,ObservedFillLedger,full_sale_verdict,_=dependencies()
