# SPDX-License-Identifier: Apache-2.0
"""Run against real T15 source, never a selector/solver substitute.

python test_continuation.py --source-dir ../cloud-market-game-theory
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

from continuation import ContinuationPlanSelector

SOURCE = Path(__file__).resolve().parents[1] / 'cloud-market-game-theory'
WholePlanSelector = None
REFERENCE_COMMIT = '4d97474b0188b0373be1b52b610c0114ceb033c8'
REFERENCE_BLOBS = {
    'solver.py': '3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3',
    'selector.py': '546b71188fd44dc47cac99623d1967bc81413da7',
}


def source_provenance(path):
    blobs = {}
    for name in REFERENCE_BLOBS:
        body = (path / name).read_bytes()
        blobs[name] = hashlib.sha1(b'blob ' + str(len(body)).encode()
                                   + b'\0' + body).hexdigest()
    matches = blobs == REFERENCE_BLOBS
    return {
        'source_commit': REFERENCE_COMMIT if matches else None,
        'reference_commit': REFERENCE_COMMIT,
        'reference_source_matches': matches,
        'source_blobs': blobs,
    }


def load_source(path):
    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, path / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    previous = sys.modules.get('solver')
    try:
        sys.modules['solver'] = load('_continuation_real_solver', 'solver.py')
        return load('_continuation_real_selector', 'selector.py').WholePlanSelector
    finally:
        if previous is None:
            sys.modules.pop('solver', None)
        else:
            sys.modules['solver'] = previous


def obs(step):
    return {'step': step, 'player': 0, 'farms': [{'money': 500}, {'money': 500}]}


def action(quantity=2):
    return {'farmer': ['PASS'], 'hands': [['PASS']],
            'market': [['BUY_PRODUCT', 'WHEAT', 1], ['SELL', 'EGG', quantity]],
            'opaque': {'retain': [1, 2]}}


def window(key='egg-a', now=10, end=12, sales=None):
    return {'key': key, 'item': 'EGG', 'quantity': 2, 'now': now,
            'end': end, 'slot': 1,
            'plans': [{'id': 'baseline', 'sales': [[now, 2]]},
                      {'id': 'deferred', 'sales': sales or [[end, 2]]}],
            'deltas': [[0, 0], [1, 1]]}


def call(subject, step, win=None, verdict=True, base=None, shed=None, feasible=None):
    kwargs = {'window': win, 'post_unit_shed': {'EGG': 2} if shed is None else shed,
              'feasible': feasible or (lambda plan: True)}
    if isinstance(subject, ContinuationPlanSelector):
        kwargs['continuation_feasible'] = verdict if callable(verdict) else lambda p, c: verdict
    return subject.transform(obs(step), {}, action() if base is None else base, **kwargs)


def new():
    return ContinuationPlanSelector(WholePlanSelector(random.Random(0)))


class ContinuationTests(unittest.TestCase):
    def test_provenance_binds_only_matching_source(self):
        actual = source_provenance(SOURCE)
        expected = actual['source_blobs'] == REFERENCE_BLOBS
        self.assertEqual(actual['reference_source_matches'], expected)
        self.assertEqual(actual['source_commit'], REFERENCE_COMMIT if expected else None)
        self.assertEqual(actual['reference_commit'], REFERENCE_COMMIT)

    def test_changed_source_does_not_reuse_reference_commit(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            for name in REFERENCE_BLOBS:
                (path / name).write_bytes((SOURCE / name).read_bytes() + b'\n')
            actual = source_provenance(path)
        self.assertIsNone(actual['source_commit'])
        self.assertFalse(actual['reference_source_matches'])
        self.assertEqual(actual['reference_commit'], REFERENCE_COMMIT)
        self.assertNotEqual(actual['source_blobs'], REFERENCE_BLOBS)

    def test_exact_initial_output_matches_selector(self):
        plain = WholePlanSelector(random.Random(0)); wrapped = new()
        self.assertEqual(call(plain, 10, window()), call(wrapped, 10, window()))
        self.assertEqual(wrapped.draws, 1)

    def test_later_false_preserves_current_fallback(self):
        wrapped = new(); call(wrapped, 10, window())
        self.assertEqual(call(wrapped, 11, verdict=False), action())
        self.assertEqual(wrapped.last_decision['reason'], 'continuation_infeasible')
        self.assertIsNone(wrapped.active)
        self.assertIn('egg-a', wrapped.selector.completed)

    def test_unknown_preserves_fallback(self):
        wrapped = new(); call(wrapped, 10, window())
        self.assertEqual(call(wrapped, 11, verdict=None), action())
        self.assertEqual(wrapped.last_decision['reason'], 'continuation_unknown')

    def test_callback_exception_has_no_exception_text(self):
        def fail(plan, context):
            raise RuntimeError('do-not-copy-arbitrary-callback-text')
        wrapped = new(); call(wrapped, 10, window())
        self.assertEqual(call(wrapped, 11, verdict=fail), action())
        self.assertEqual(wrapped.last_decision['reason'], 'continuation_error')
        self.assertNotIn('do-not-copy', json.dumps(wrapped.last_decision))

    def test_truthy_nonboolean_is_not_feasibility(self):
        wrapped = new(); call(wrapped, 10, window())
        self.assertEqual(call(wrapped, 11, verdict={'score': 7}), action())
        self.assertEqual(wrapped.last_decision['reason'], 'continuation_invalid_verdict')

    def test_no_validator_does_not_draw(self):
        wrapped = new()
        got = wrapped.transform(obs(10), {}, action(), window=window(),
                                post_unit_shed={'EGG': 2}, feasible=lambda p: True,
                                continuation_feasible=None)
        self.assertEqual(got, action()); self.assertEqual(wrapped.draws, 0)

    def test_invalid_at_initial_choice_is_retired(self):
        wrapped = new()
        self.assertEqual(call(wrapped, 10, window(), verdict=False), action())
        self.assertEqual(wrapped.draws, 1)
        self.assertIn('egg-a', wrapped.selector.completed)

    def test_same_step_retry_never_redraws(self):
        wrapped = new(); first = call(wrapped, 10, window())
        self.assertEqual(first, call(wrapped, 10, window()))
        self.assertEqual(wrapped.draws, 1)

    def test_missed_positive_due_aborts_without_catchup(self):
        wrapped = new(); call(wrapped, 10, window(sales=[[11, 1], [12, 1]]))
        self.assertEqual(call(wrapped, 12), action())
        self.assertEqual(wrapped.last_decision['reason'], 'due_step_not_emitted')
        self.assertEqual(wrapped.last_decision['missing_steps'], [11])
        self.assertEqual(wrapped.draws, 1)

    def test_missing_due_detected_even_after_end(self):
        wrapped = new(); call(wrapped, 10, window())
        self.assertEqual(call(wrapped, 13), action())
        self.assertEqual(wrapped.last_decision['missing_steps'], [12])

    def test_skip_no_due_dates_is_allowed(self):
        wrapped = new(); call(wrapped, 10, window())
        self.assertEqual(call(wrapped, 12)['market'][1], ['SELL', 'EGG', 2])
        self.assertEqual(wrapped.draws, 1)

    def test_backward_step_aborts(self):
        wrapped = new(); call(wrapped, 10, window()); call(wrapped, 11)
        self.assertEqual(call(wrapped, 10), action())
        self.assertEqual(wrapped.last_decision['reason'], 'decision_time_reversed')

    def test_remaining_schedule_omits_prior_emitted_dates(self):
        seen = []
        def check(plan, context):
            seen.append((deepcopy(plan), deepcopy(context)))
            return True
        wrapped = new(); win = window(sales=[[10, 1], [12, 1]])
        call(wrapped, 10, win, verdict=check)
        call(wrapped, 11, verdict=check, shed={'EGG': 1})
        self.assertEqual(seen[-1][0]['sales'], [[12, 1]])
        self.assertEqual(seen[-1][1]['remaining_quantity'], 1)
        self.assertEqual(seen[-1][1]['original_quantity'], 2)

    def test_callback_cannot_mutate_live_inputs(self):
        def mutate(plan, context):
            plan['sales'].clear(); context['observation']['farms'].clear()
            context['reservations'].clear(); return True
        wrapped = new(); observed = obs(10); base = action(); win = window()
        original = deepcopy((observed, base, win))
        wrapped.transform(observed, {}, base, window=win, post_unit_shed={'EGG': 2},
                          reservations={'cash': 2}, feasible=lambda p: True,
                          continuation_feasible=mutate)
        self.assertEqual((observed, base, win), original)
        self.assertEqual(wrapped.active['plan']['sales'], [[12, 2]])

    def test_aborted_key_cannot_redraw(self):
        wrapped = new(); call(wrapped, 10, window()); call(wrapped, 11, verdict=False)
        self.assertEqual(call(wrapped, 11, window(now=11)), action())
        self.assertEqual(wrapped.draws, 1)

    def test_finished_window_allows_new_key(self):
        wrapped = new(); call(wrapped, 10, window()); call(wrapped, 12)
        call(wrapped, 13, window(key='egg-b', now=13, end=15))
        self.assertEqual(wrapped.draws, 2)
        self.assertIn('egg-a', wrapped.selector.completed)
        self.assertEqual(wrapped.active['key'], 'egg-b')

    def test_original_stock_obstruction_still_works(self):
        wrapped = new(); call(wrapped, 10, window())
        self.assertEqual(call(wrapped, 12, shed={'EGG': 1}), action())
        self.assertEqual(wrapped.last_decision['reason'], 'commitment_aborted')

    def test_original_non_sell_slot_obstruction_still_works(self):
        wrapped = new(); call(wrapped, 10, window())
        base = action(); base['market'][1] = ['BUY_PRODUCT', 'WHEAT', 1]
        self.assertEqual(call(wrapped, 12, base=base), base)
        self.assertEqual(wrapped.last_decision['reason'], 'commitment_aborted')

    def test_original_constituent_feasibility_still_controls_draw(self):
        wrapped = new()
        self.assertEqual(call(wrapped, 10, window(), feasible=lambda p: False), action())
        self.assertEqual(wrapped.draws, 0)

    def test_terminal_due_can_execute(self):
        wrapped = new(); call(wrapped, 717, window(now=717, end=718))
        self.assertEqual(call(wrapped, 718)['market'][1], ['SELL', 'EGG', 2])

    def test_fallback_is_detached_and_lossless(self):
        wrapped = new(); call(wrapped, 10, window()); base = action()
        out = call(wrapped, 11, verdict=False, base=base)
        self.assertEqual(out, base)
        out['opaque']['retain'].append(3)
        self.assertEqual(base['opaque']['retain'], [1, 2])

    def test_none_key_still_checks_initial_continuation(self):
        wrapped = new()
        self.assertEqual(call(wrapped, 10, window(key=None), verdict=False), action())
        self.assertEqual(wrapped.last_decision['reason'], 'continuation_infeasible')
        self.assertIn(None, wrapped.selector.completed)

    def test_mixed_weights_and_choice_are_preserved(self):
        win = window()
        win['plans'].append({'id': 'split', 'sales': [[10, 1], [12, 1]]})
        win['deltas'] = [[0, 0], [1, -1], [-1, 2]]
        plain = WholePlanSelector(random.Random(0)); wrapped = new()
        self.assertEqual(call(plain, 10, win), call(wrapped, 10, win))
        self.assertEqual(wrapped.active['weights'], ['0', '3/5', '2/5'])
        self.assertEqual(wrapped.active['plan_index'], plain.active['plan_index'])
        call(wrapped, 10, win)
        self.assertEqual(wrapped.draws, 1)

    def test_external_prior_emission_is_not_inferred(self):
        plain = WholePlanSelector(random.Random(0))
        call(plain, 10, window(sales=[[10, 1], [12, 1]]))
        wrapped = ContinuationPlanSelector(plain)
        self.assertEqual(call(wrapped, 11), action())
        self.assertEqual(wrapped.last_decision['missing_steps'], [10])

    def test_active_missing_validator_preserves_fallback(self):
        wrapped = new(); call(wrapped, 10, window())
        got = wrapped.transform(obs(11), {}, action(),
                                post_unit_shed={'EGG': 2},
                                continuation_feasible=None)
        self.assertEqual(got, action())
        self.assertEqual(wrapped.last_decision['reason'], 'continuation_unknown')

    def test_repeated_due_can_be_emitted_without_second_draw(self):
        wrapped = new(); call(wrapped, 10, window())
        first = call(wrapped, 12); second = call(wrapped, 12)
        self.assertEqual(first, second); self.assertEqual(wrapped.draws, 1)
        call(wrapped, 13)
        self.assertIsNone(wrapped.active)


def witness():
    plain = WholePlanSelector(random.Random(0)); wrapped = new()
    call(plain, 10, window()); call(wrapped, 10, window())
    previous = call(plain, 11, feasible=lambda p: False)
    actual = call(wrapped, 11, verdict=False)
    skip_plain = WholePlanSelector(random.Random(0)); skip_wrapped = new()
    split = window(sales=[[11, 1], [12, 1]])
    call(skip_plain, 10, split); call(skip_wrapped, 10, split)
    old_skip = call(skip_plain, 12); new_skip = call(skip_wrapped, 12)
    return {
        'scope': 'synthetic consumer invocation sequences using exact T15 runtime; no game or fill claim',
        **source_provenance(SOURCE),
        'changed_continuation': {'admission_only_market': previous['market'],
                                 'wrapped_market': actual['market'],
                                 'decision': wrapped.last_decision},
        'skipped_due_date': {'admission_only_market': old_skip['market'],
                            'wrapped_market': new_skip['market'],
                            'decision': skip_wrapped.last_decision},
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path, default=SOURCE)
    parser.add_argument('--witness', type=Path)
    args, rest = parser.parse_known_args()
    SOURCE = args.source_dir.resolve()
    WholePlanSelector = load_source(SOURCE)
    result = unittest.main(argv=[sys.argv[0]] + rest, exit=False)
    if args.witness:
        args.witness.write_text(json.dumps(witness(), indent=2) + '\n')
    sys.exit(not result.result.wasSuccessful())
else:
    if (SOURCE / 'selector.py').exists():
        WholePlanSelector = load_source(SOURCE)
