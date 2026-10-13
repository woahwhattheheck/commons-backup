# SPDX-License-Identifier: Apache-2.0
"""Exact emitted-prefix checks for the existing continuation consumer.

Default imports use neighboring real T15/ESTUARY source. --source-root points
at a relocated revenue/kaggriculture tree. No engine or policy game is run.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import unittest

HERE = Path(__file__).resolve().parent
SUBJECT = None
BASELINE = None
SELECTOR = None
FILLS = None
CORE = None
RECOURSE = None
SOURCES = {}
WITNESSES = []
COUNTS = {'default_pairs': 0, 'compiled_tables': 0, 'compiled_outputs': 0}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fingerprint(path):
    body = Path(path).read_bytes()
    return {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()}


def configure(subject, root, baseline=None):
    global SUBJECT, BASELINE, SELECTOR, FILLS, CORE, RECOURSE, SOURCES
    paths = {
        'continuation': subject,
        'solver': root / 'cloud-market-game-theory/solver.py',
        'selector': root / 'cloud-market-game-theory/selector.py',
        'observed_fills': root / 'cloud-observed-fills/observed_fills.py',
        'recourse': root / 'cloud-market-game-theory/adaptive/recourse.py',
        'core': root / 'cloud-execution-lab/selected_sell_core.py',
        'mechanics': root / 'cloud-execution-lab/mechanics.py',
        'receipts': root / 'cloud-execution-lab/reference/decision/decision.py',
    }
    SUBJECT = load(subject, '_ash_prefix_subject')
    saved = {name: sys.modules.get(name) for name in ('solver', 'mechanics')}
    try:
        sys.modules['solver'] = load(paths['solver'], '_ash_prefix_solver')
        SELECTOR = load(paths['selector'], '_ash_prefix_selector').WholePlanSelector
        sys.modules['mechanics'] = load(paths['mechanics'], '_ash_prefix_mechanics')
        CORE = load(paths['core'], '_ash_prefix_core')
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    FILLS = load(paths['observed_fills'], '_ash_prefix_fills')
    RECOURSE = load(paths['recourse'], '_ash_prefix_recourse')
    SOURCES = {name: fingerprint(path) for name, path in paths.items()}
    if baseline is not None:
        BASELINE = load(baseline, '_ash_prefix_baseline')
        SOURCES['baseline'] = fingerprint(baseline)


def observation(step, seat=0, shed=None):
    return {'step': step, 'player': seat,
            'farms': [{'money': 500}, {'money': 500}],
            'private': {'shed': deepcopy(shed if shed is not None else {'EGG': 3})}}


def fallback(item='EGG', slot=1):
    queue = [['HIRE']] + [[] for _ in range(slot)]
    queue[slot] = ['SELL', item, 2]
    return {'farmer': ['PASS'], 'hands': [['PASS']], 'market': queue,
            'caller_metadata': {'keep': [1, 2]}}


def window(sales=None, *, item='EGG', slot=1, key='lot', now=10, end=14):
    sales = deepcopy(sales if sales is not None else [[10, 1], [13, 2]])
    quantity = sum(q for _, q in sales)
    return {'key': key, 'item': item, 'slot': slot, 'quantity': quantity,
            'now': now, 'end': end,
            'plans': [{'id': 'baseline', 'sales': [[now, quantity]]},
                      {'id': 'split', 'sales': sales}],
            'deltas': [[0, 0], [1, 1]]}


def wrapper(module=None, *, fill=False, seed=0):
    extra = {'fill_ledger': FILLS.ObservedFillLedger(),
             'fill_verdict': FILLS.full_sale_verdict} if fill else {}
    return (module or SUBJECT).ContinuationPlanSelector(SELECTOR(random.Random(seed)), **extra)


def invoke(policy, step, *, win=None, seat=0, shed=None, base=None, verdict=True):
    shed = {'EGG': 3, 'MILK': 3, 'WOOL': 3} if shed is None else shed
    return policy.transform(observation(step, seat, shed), {}, base or fallback(),
                            window=win, post_unit_shed=shed,
                            feasible=lambda plan: True,
                            continuation_feasible=lambda plan, context: verdict)


def start(policy, sales=None, *, key='lot', seat=0, item='EGG', slot=1):
    return invoke(policy, 10, win=window(sales, key=key, item=item, slot=slot),
                  seat=seat, base=fallback(item, slot), shed={item: 10})


def replace_sales(policy, sales):
    policy.selector.active['plan']['sales'] = deepcopy(sales)
    policy.selector.active['completion_step'] = max(t for t, q in sales if q > 0)


def legacy_state(policy):
    return deepcopy({'active': policy.active, 'draws': policy.draws,
                     'retired': sorted(policy.selector.completed),
                     'decision': policy.last_decision, 'fill': policy.last_fill})


class EmittedPrefixTests(unittest.TestCase):
    def assert_aborted(self, policy, action, base=None, reason='emitted_prefix_changed'):
        self.assertEqual(action, base or fallback())
        self.assertIsNone(policy.active)
        self.assertEqual(policy.last_decision['reason'], reason)
        self.assertEqual(policy.draws, 1)
        self.assertIn('lot', policy.selector.completed)

    def test_prior_quantity_increase_retires(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                p = wrapper(); first = start(p, seat=seat)
                replace_sales(p, [[10, 2], [13, 1]])
                out = invoke(p, 11, seat=seat)
                WITNESSES.append({'case': 'increased_prior_quantity', 'seat': seat,
                                  'first': first, 'next': out, 'state': legacy_state(p)})
                self.assert_aborted(p, out)

    def test_prior_quantity_decrease_retires(self):
        p = wrapper(); start(p, [[10, 2], [13, 1]])
        replace_sales(p, [[10, 1], [13, 2]])
        self.assert_aborted(p, invoke(p, 11))

    def test_deleted_prior_sale_retires(self):
        p = wrapper(); start(p); replace_sales(p, [[13, 3]])
        self.assert_aborted(p, invoke(p, 11))

    def test_zeroing_prior_sale_retires(self):
        p = wrapper(); start(p); replace_sales(p, [[10, 0], [13, 3]])
        self.assert_aborted(p, invoke(p, 11))

    def test_changing_lot_product_retires(self):
        p = wrapper(); start(p); p.selector.active['item'] = 'MILK'
        base = fallback('MILK')
        self.assert_aborted(p, invoke(p, 11, base=base), base)

    def test_changing_fixed_slot_retires(self):
        p = wrapper(); start(p); p.selector.active['slot'] = 2
        base = fallback(slot=2)
        self.assert_aborted(p, invoke(p, 11, base=base), base)

    def test_duplicate_past_sale_retires(self):
        p = wrapper(); start(p)
        replace_sales(p, [[10, 1], [10, 1], [13, 1]])
        self.assert_aborted(p, invoke(p, 11))

    def test_redistribution_across_two_prior_dates_retires(self):
        p = wrapper(); start(p, [[10, 1], [11, 2], [14, 1]])
        invoke(p, 11)
        replace_sales(p, [[10, 2], [11, 1], [14, 1]])
        self.assert_aborted(p, invoke(p, 12))

    def test_preexpiry_history_change_checked_before_retirement(self):
        p = wrapper(); start(p, [[10, 2], [11, 1]]); invoke(p, 11)
        replace_sales(p, [[10, 1], [11, 2]])
        self.assert_aborted(p, invoke(p, 12))

    def test_backdated_unemitted_sale_keeps_existing_reason(self):
        p = wrapper(); start(p); replace_sales(p, [[9, 1], [13, 2]])
        self.assert_aborted(p, invoke(p, 11), reason='due_step_not_emitted')

    def test_retired_key_does_not_redraw(self):
        p = wrapper(); start(p); replace_sales(p, [[13, 3]])
        self.assert_aborted(p, invoke(p, 11))
        self.assertEqual(invoke(p, 12, win=window([[12, 1], [13, 2]], now=12)), fallback())
        self.assertEqual(p.draws, 1)

    def test_same_prefix_future_date_change_is_allowed(self):
        p = wrapper(); start(p)
        replace_sales(p, [[10, 1], [12, 2]])
        p.selector.active['plan']['id'] = 'new_observed_suffix'
        p.selector.active['plan_index'] = 0
        self.assertEqual(invoke(p, 11)['market'][1], [])
        self.assertEqual(invoke(p, 12)['market'][1], ['SELL', 'EGG', 2])
        self.assertEqual(p.draws, 1)

    def test_same_prefix_future_split_is_allowed(self):
        p = wrapper(); start(p); replace_sales(p, [[10, 1], [12, 1], [14, 1]])
        invoke(p, 11)
        self.assertEqual(invoke(p, 12)['market'][1], ['SELL', 'EGG', 1])
        invoke(p, 13)
        self.assertEqual(invoke(p, 14)['market'][1], ['SELL', 'EGG', 1])
        self.assertEqual(p.draws, 1)

    def test_past_date_serialization_order_is_irrelevant(self):
        p = wrapper(); start(p, [[10, 1], [11, 1], [13, 1]])
        invoke(p, 11); replace_sales(p, [[11, 1], [10, 1], [13, 1]])
        self.assertEqual(invoke(p, 12)['market'][1], [])
        self.assertIsNotNone(p.active)

    def test_explicit_past_zero_is_equivalent(self):
        p = wrapper(); start(p); replace_sales(p, [[9, 0], [10, 1], [12, 2]])
        self.assertEqual(invoke(p, 11)['market'][1], [])
        self.assertIsNotNone(p.active)

    def test_same_step_retry_preserves_one_draw(self):
        p = wrapper(); first = start(p)
        self.assertEqual(first, start(p)); self.assertEqual(p.draws, 1)
        self.assertEqual(invoke(p, 11)['market'][1], [])
        self.assertIsNotNone(p.active)

    def test_detached_active_copy_cannot_change_prefix(self):
        p = wrapper(); start(p); copied = p.active
        copied['plan']['sales'][0][1] = 2
        self.assertEqual(invoke(p, 11)['market'][1], [])
        self.assertEqual(p.active['plan']['sales'][0], [10, 1])

    def test_null_key_tracks_prefix(self):
        p = wrapper(); start(p, key=None); replace_sales(p, [[13, 3]])
        self.assertEqual(invoke(p, 11), fallback())
        self.assertIsNone(p.active); self.assertIn(None, p.selector.completed)
        self.assertEqual(p.last_decision['reason'], 'emitted_prefix_changed')

    def test_clean_rollover_clears_prefix(self):
        p = wrapper(); start(p, [[10, 1], [11, 2]]); invoke(p, 11)
        second = window([[12, 2], [14, 1]], key='second', now=12)
        self.assertEqual(invoke(p, 12, win=second)['market'][1], ['SELL', 'EGG', 2])
        self.assertEqual(invoke(p, 13)['market'][1], [])
        self.assertEqual(p.draws, 2)

    def test_fallback_is_whole_detached_input(self):
        p = wrapper(); start(p); replace_sales(p, [[13, 3]])
        base = fallback(); out = invoke(p, 11, base=base)
        self.assertEqual(out, base)
        out['caller_metadata']['keep'].append(3)
        self.assertEqual(base['caller_metadata']['keep'], [1, 2])

    def test_current_physics_still_runs_after_matching_prefix(self):
        p = wrapper(); start(p)
        self.assert_aborted(p, invoke(p, 11, verdict=False), reason='continuation_infeasible')

    def test_prior_full_fill_does_not_authorize_rewritten_prefix(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                p = wrapper(fill=True); first = start(p, seat=seat)
                p.record_final(observation(10, seat), {}, first, post_unit_shed={'EGG': 3})
                replace_sales(p, [[10, 2], [13, 1]])
                out = invoke(p, 11, seat=seat, shed={'EGG': 2})
                self.assert_aborted(p, out)
                self.assertEqual(p.last_fill['status'], 'filled')

    def test_real_fill_and_valid_suffix_both_continue(self):
        p = wrapper(fill=True); first = start(p)
        p.record_final(observation(10), {}, first, post_unit_shed={'EGG': 3})
        replace_sales(p, [[10, 1], [12, 2]])
        self.assertEqual(invoke(p, 11, shed={'EGG': 2})['market'][1], [])
        self.assertEqual(p.last_fill['status'], 'filled')
        self.assertEqual(invoke(p, 12, shed={'EGG': 2})['market'][1], ['SELL', 'EGG', 2])

    def test_missing_fill_keeps_existing_failure_priority(self):
        p = wrapper(fill=True); start(p); replace_sales(p, [[13, 3]])
        self.assert_aborted(p, invoke(p, 11), reason='final_sale_not_recorded')

    def test_short_fill_keeps_existing_failure_priority(self):
        p = wrapper(fill=True); first = start(p)
        final = deepcopy(first); final['market'][0] = ['SELL', 'EGG', 3]
        p.record_final(observation(10), {}, final, post_unit_shed={'EGG': 3})
        replace_sales(p, [[13, 3]])
        self.assert_aborted(p, invoke(p, 11, shed={'EGG': 0}), reason='previous_sale_short_fill')
        self.assertEqual(p.last_fill['status'], 'short_fill')

    def test_actual_compiler_same_prefix_recourse_is_preserved(self):
        # Real compiler/MarketPath/selector/adapter with an explicit admitted
        # window and own-snapshot callback, not a complete AdaptiveAgent game.
        for inv in (9900, 9950, 9999, 10000):
            for seat in (0, 1):
                with self.subTest(inventory=inv, seat=seat):
                    plans = [{'id': 'late', 'sales': [[71, 1], [73, 2]]},
                             {'id': 'early', 'sales': [[71, 1], [72, 2]]}]
                    model = CORE.MarketPath('WOOL', inv, None, [], {}, 71, 79)
                    tree = RECOURSE.compile_policy(model, plans, 3,
                        [('constructed_later_order', ((72, 2),), 'after')], 72, CORE.absorption)
                    COUNTS['compiled_tables'] += 1
                    self.assertTrue(tree['active'])
                    p = wrapper()
                    p.selector.active = {'key': 'compiled', 'plan': deepcopy(plans[0]),
                        'plan_index': 0, 'weights': ['1', '0'],
                        'solution': {'value': str(tree['worst_margin'])}, 'mode': 'adaptive',
                        'item': 'WOOL', 'quantity': 3, 'now': 71, 'end': 79, 'slot': 1,
                        'completion_step': 73}
                    first = invoke(p, 71, seat=seat, shed={'WOOL': 3}, base=fallback('WOOL'))
                    self.assertEqual(first['market'][1], ['SELL', 'WOOL', 1])
                    seen = observation(72, seat, {'WOOL': 2})
                    seen['market'] = {'inventory': {'WOOL': inv + 1}}
                    index = RECOURSE.choose_observed(tree, seen, 'WOOL')
                    self.assertEqual(index, 1)
                    p.selector.active['plan'] = deepcopy(tree['plans'][index])
                    p.selector.active['plan_index'] = index
                    p.selector.active['completion_step'] = 72
                    out = p.transform(seen, {}, fallback('WOOL'), post_unit_shed={'WOOL': 2},
                                      continuation_feasible=lambda plan, c: sum(q for t, q in plan['sales']) <= 2)
                    self.assertEqual(out['market'][1], ['SELL', 'WOOL', 2])
                    self.assertEqual(p.draws, 0)
                    COUNTS['compiled_outputs'] += 2
                    WITNESSES.append({'case': 'actual_compiler_valid_prefix', 'inventory': inv,
                        'seat': seat, 'prefix': tree['prefix'], 'first': first, 'next': out,
                        'conditional_deltas': tree['deltas'], 'draws': p.draws})

    def test_unmutated_sequences_match_original(self):
        if BASELINE is None:
            self.skipTest('--baseline not supplied: original-source differential not requested')
        schedules = [[[10, 1], [13, 2]], [[11, 1], [13, 2]], [[10, 2], [12, 1]],
                     [[10, 3]], [[10, 1], [11, 1], [14, 1]]]
        for seed in range(16):
            for seat in (0, 1):
                for sales in schedules:
                    for stop in (None, 12):
                        a = wrapper(BASELINE, seed=seed); b = wrapper(seed=seed)
                        w = window(sales)
                        w['plans'].append({'id': 'late', 'sales': [[14, 3]]})
                        w['deltas'] = [[0, 0], [1, -1], [-1, 2]]
                        for step in (10, 10, 11, 12, 13, 14, 15):
                            args = dict(win=w if step == 10 else None, seat=seat,
                                        verdict=step != stop)
                            self.assertEqual(invoke(a, step, **args), invoke(b, step, **args))
                            self.assertEqual(legacy_state(a), legacy_state(b))
                            COUNTS['default_pairs'] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, default=HERE / 'continuation.py')
    parser.add_argument('--source-root', type=Path, default=HERE.parent)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    configure(args.module.resolve(), args.source_root.resolve(),
              args.baseline.resolve() if args.baseline else None)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2 if args.verbose else 1).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(EmittedPrefixTests))
    text = output.getvalue(); sys.stdout.write(text)
    report = {'scope': 'synthetic actual-component continuity sequences; no engine transitions or full games',
              'sources': SOURCES, 'tests': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped),
              'successful': result.wasSuccessful(), 'counts': COUNTS, 'witnesses': WITNESSES,
              'test_log': text}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
