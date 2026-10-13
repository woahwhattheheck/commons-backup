# SPDX-License-Identifier: Apache-2.0
"""Runtime regressions; actual pinned-engine consumers live in engine_cases.py."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import unittest

from route_frontier import (Alternative, BoundRoute, Incompatible, Trace,
                            dominates, exact_key, kernel_model, pareto_frontier,
                            rollout, splice)


def advance(state, action):
    state['step'] += 1
    state['cash'] += action['delta']
    return state


def trace(name='route', context='same', deltas=(1,), state=None):
    return rollout(name, state or {'step': 0, 'cash': 0},
                   [{'delta': d} for d in deltas], advance, context=context)


def alternative(name, values, *, context='same', endpoint=0, custom=False):
    t = trace(name, context, (endpoint,))
    kw = {'continuation_keys': ('DONE',), 'equivalence_label': 'terminal-only'} if custom else {}
    return Alternative(name, (t,), ('cash', 'deadline'), (values,), **kw)


class SnapshotTests(unittest.TestCase):
    def test_order_is_behavioral(self):
        a, b = {'MILK': 1, 'WOOL': 1}, {'WOOL': 1, 'MILK': 1}
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertNotEqual(exact_key(a), exact_key(b))

    def test_json_roundtrip_and_number_types(self):
        x = {'step': 3, 'v': [None, True, 1, 1.0, 'é']}
        self.assertEqual(json.loads(exact_key(x)), x)
        self.assertNotEqual(exact_key(1), exact_key(1.0))
        self.assertNotEqual(exact_key(-0.0), exact_key(0.0))

    def test_reject_lossy_values(self):
        for value in [float('nan'), float('inf'), (1,), {1: 'x'}, {1, 2}, object()]:
            with self.subTest(value=type(value)), self.assertRaises(ValueError):
                exact_key(value)

    def test_rollout_copies_inputs_and_reads(self):
        state, actions = {'step': 0, 'cash': 0}, [{'delta': 3}]
        original = deepcopy((state, actions))
        t = rollout('x', state, actions, advance, context='s')
        self.assertEqual((state, actions), original)
        t.state()['cash'] = 999
        t.action()['delta'] = 999
        self.assertEqual(t.state()['cash'], 3)
        self.assertEqual(t.action()['delta'], 3)

    def test_trace_freezes_supplied_collections(self):
        original = trace()
        states, actions = list(original.snapshots), list(original.actions)
        t = Trace('copy', 'same', states, actions)
        states.clear(); actions.clear()
        self.assertEqual(len(t.actions), 1)
        with self.assertRaises(FrozenInstanceError):
            t.name = 'changed'

    def test_trace_rejects_incomplete_and_noncanonical(self):
        good = trace()
        for states, actions in [(good.snapshots[:-1], good.actions),
                                ((good.entry, '{ "cash":1,"step":1}'), good.actions)]:
            with self.assertRaises(ValueError):
                Trace('bad', 'same', states, actions)
        for name, context in [('', 's'), ('x', ''), (4, 's'), ('x', [])]:
            with self.assertRaises(ValueError):
                Trace(name, context, good.snapshots, good.actions)

    def test_max_steps_never_returns_partial(self):
        calls = []
        def counted(s, a):
            calls.append(a); return advance(s, a)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            rollout('x', {'step': 0, 'cash': 0}, [{'delta': 0}] * 3,
                    counted, context='s', max_steps=2)
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ValueError):
            rollout('empty', {}, [], counted, context='s')

    def test_failed_callback_propagates_without_changing_input(self):
        state = {'step': 0, 'cash': 0}
        def fail(s, a):
            s['cash'] = 20; raise RuntimeError('transition unavailable')
        with self.assertRaises(RuntimeError):
            rollout('x', state, [{}], fail, context='s')
        self.assertEqual(state['cash'], 0)


class SpliceTests(unittest.TestCase):
    def test_exact_splice_is_full_rollout(self):
        a = trace(deltas=(1,))
        b = trace('suffix', deltas=(-1, 4), state=a.state())
        full = trace('full', deltas=(1, -1, 4))
        joined = splice(a, b)
        self.assertEqual(joined.actions, full.actions)
        self.assertEqual(joined.snapshots, full.snapshots)

    def test_context_mismatch_is_not_same_state(self):
        a = trace()
        b = trace('b', 'different-rival', state=a.state())
        with self.assertRaises(Incompatible):
            splice(a, b)

    def test_position_input_and_time_cannot_be_assumed(self):
        a = trace(state={'step': 0, 'cash': 0, 'pos': [4, 4], 'seed': 1})
        for key, value in [('step', 2), ('pos', [3, 4]), ('seed', 0)]:
            state = a.state(); state[key] = value
            b = trace('suffix', state=state)
            with self.subTest(key=key), self.assertRaises(Incompatible):
                splice(a, b)

    def test_inventory_order_cannot_be_sorted_for_splice(self):
        a = trace(state={'step': 0, 'cash': 0, 'carry': {'MILK': 1, 'WOOL': 1}})
        state = a.state(); state['carry'] = {'WOOL': 1, 'MILK': 1}
        with self.assertRaises(Incompatible):
            splice(a, trace('suffix', state=state))


class FrontierTests(unittest.TestCase):
    def test_tradeoffs_and_ties_are_retained(self):
        items = [alternative('early', (3, 3)), alternative('late', (4, 0)),
                 alternative('tie', (3, 3))]
        f = pareto_frontier(items)
        self.assertEqual([a.name for a in f.kept], ['early', 'late', 'tie'])
        self.assertFalse(f.approximate)

    def test_strict_dominance_only(self):
        a, b = alternative('a', (3, 2)), alternative('b', (2, 2))
        self.assertTrue(dominates(a, b))
        self.assertFalse(dominates(b, a))
        self.assertEqual(pareto_frontier([a, b]).dominated, (('b', 'a'),))

    def test_different_exact_exits_remain_incomparable(self):
        a = alternative('a', (10, 10), endpoint=1)
        b = alternative('b', (1, 1), endpoint=0)
        self.assertFalse(dominates(a, b))
        self.assertEqual(len(pareto_frontier([a, b]).kept), 2)

    def test_declared_terminal_equivalence_is_explicit(self):
        a = alternative('a', (10, 10), endpoint=1, custom=True)
        b = alternative('b', (1, 1), endpoint=0, custom=True)
        self.assertTrue(dominates(a, b))
        with self.assertRaises(ValueError):
            replace(a, equivalence_label='exact-state')
        with self.assertRaises(ValueError):
            replace(a, continuation_keys=('',))

    def test_contexts_entry_and_horizon_are_comparability_conditions(self):
        a = alternative('a', (10, 10))
        for b in [alternative('b', (0, 0), context='other'),
                  replace(a, name='b', traces=(trace('b', deltas=(0, 0)),), values=((0, 0),)),
                  replace(a, name='b', objectives=('deadline', 'cash'), values=((0, 0),))]:
            self.assertFalse(dominates(a, b))

    def test_scenario_order_is_aligned_not_averaged(self):
        x, y = trace('x', 'x', (0,)), trace('y', 'y', (0,))
        a = Alternative('a', (x, y), ('cash',), ((10,), (0,)))
        b = Alternative('b', (y, x), ('cash',), ((1,), (9,)))
        self.assertFalse(dominates(a, b))
        self.assertFalse(dominates(b, a))
        c = Alternative('c', (y, x), ('cash',), ((0,), (9,)))
        self.assertTrue(dominates(a, c))

    def test_mutable_constructor_inputs_are_frozen(self):
        traces, names, values, keys = [trace()], ['cash'], [[3]], ['DONE']
        a = Alternative('a', traces, names, values, keys, 'terminal-only')
        traces.clear(); names.clear(); values[0][0] = 900; keys[0] = 'changed'
        self.assertEqual(a.values, ((3,),))
        self.assertEqual(a.continuation_keys, ('DONE',))
        self.assertEqual(len(a.traces), 1)

    def test_invalid_vectors_and_names_are_rejected(self):
        a = alternative('a', (1, 1))
        for changes in [{'values': ((float('nan'), 1),)}, {'values': ((True, 1),)},
                        {'values': ((1,),)}, {'objectives': ('x', 'x')},
                        {'objectives': ('x', '')}, {'traces': ()},
                        {'name': 3}, {'traces': (a.traces[0], a.traces[0]),
                                      'values': ((1, 1), (1, 1))}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(a, **changes)

    def test_size_cap_is_not_exact_dominance(self):
        items = [alternative('early', (3, 3)), alternative('late', (4, 0)),
                 alternative('bad', (1, 0))]
        f = pareto_frontier(items, max_size=1, rank=lambda a: a.values[0][0])
        self.assertEqual([a.name for a in f.kept], ['late'])
        self.assertEqual(f.budget_dropped, ('early',))
        self.assertTrue(f.approximate)
        self.assertEqual(f.dominated[0][0], 'bad')

    def test_candidate_cap_rejects_without_silent_truncation(self):
        with self.assertRaises(ValueError):
            pareto_frontier([alternative(str(i), (i, -i)) for i in range(3)], max_candidates=2)
        with self.assertRaises(ValueError):
            pareto_frontier([], max_size=0)
        with self.assertRaises(ValueError):
            pareto_frontier([alternative('x', (0, 0)), alternative('x', (1, 1))])

    def test_exhaustive_small_frontiers(self):
        points = list(itertools.product(range(3), repeat=2))
        for subset in itertools.combinations(points, 4):
            items = [alternative(str(i), p) for i, p in enumerate(subset)]
            expected = {str(i) for i, p in enumerate(subset) if not any(
                all(x >= y for x, y in zip(q, p)) and q != p for q in subset)}
            self.assertEqual({a.name for a in pareto_frontier(items).kept}, expected)


class BoundRouteTests(unittest.TestCase):
    def test_progress_and_retry_are_idempotent(self):
        t = trace(deltas=(1, 2))
        live = BoundRoute(t)
        first = live.act(t.state(0), {'delta': 7})
        first['delta'] = 20
        self.assertEqual(live.act(t.state(0), {}), {'delta': 1})
        self.assertEqual(live.index, 1)
        self.assertEqual(live.act(t.state(1), {}), {'delta': 2})
        self.assertEqual(live.act(t.state(2), {'delta': 7}), {'delta': 7})
        self.assertEqual(live.status, 'complete')

    def test_mismatch_keeps_fallback_and_never_resumes_stale_tape(self):
        t = trace(deltas=(1, 2)); live = BoundRoute(t)
        fallback = {'farmer': ['PASS'], 'hands': [['MOVE', 'N']], 'market': [['HIRE']]}
        out = live.act({'step': 3}, fallback)
        self.assertEqual(out, fallback)
        out['hands'].clear()
        self.assertEqual(live.act(t.state(0), fallback), fallback)
        self.assertEqual(len(fallback['hands']), 1)
        self.assertEqual(live.index, 0)


class KernelAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Real T06 module, never a replacement fake implementation. A sibling
        # repository copy is used normally; the isolated test can supply its pin.
        import os
        path = Path(os.environ.get('T06_KERNEL_FILE', '../cloud-search-kernel/search_kernel.py'))
        if not path.is_file():
            raise unittest.SkipTest('T06 source not supplied; engine_cases has explicit optional consumer status')
        spec = importlib.util.spec_from_file_location('bridge_test_t06', path)
        cls.kernel = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.kernel
        spec.loader.exec_module(cls.kernel)

    def test_same_name_cannot_hide_scenario_dependent_commands(self):
        a = trace('plan', 'low', (1,))
        b = trace('plan', 'high', (2,))
        with self.assertRaisesRegex(ValueError, 'identical actions'):
            kernel_model(self.kernel, [a, b], lambda s, _: s['cash'])

    def test_real_search_uses_same_plan_across_scenarios(self):
        state = {'step': 0, 'cash': 0}
        traces = []
        for context, factor in [('low', 1), ('high', 2)]:
            for name, delta in [('small', 1), ('large', 3)]:
                def scenario(s, a, factor=factor):
                    s['step'] += 1; s['cash'] += factor * a['delta']; return s
                traces.append(rollout(name, state, [{'delta': delta}], scenario, context=context))
        model = kernel_model(self.kernel, traces, lambda s, _: s['cash'])
        result = self.kernel.search(model, [state, state], ['low', 'high'], 'small',
                                    limits=self.kernel.Limits(seconds=1, max_depth=1))
        self.assertEqual(result.action, 'large')
        self.assertEqual(result.values, (3.0, 6.0))
        self.assertEqual(result.status, 'complete')

    def test_missing_scenario_is_infeasible_not_replayed(self):
        a = trace()
        model = kernel_model(self.kernel, [a], lambda s, _: s['cash'])
        with self.assertRaises(self.kernel.Infeasible):
            model.transition(a.state(0), a.name, 'unseen')
        self.assertNotEqual(model.state_key({'a': 1, 'b': 2}), model.state_key({'b': 2, 'a': 1}))

    def test_conflicting_transition_and_return_mutation(self):
        a = trace()
        conflicting = Trace(a.name, a.context, (a.entry, exact_key({'step': 1, 'cash': 20})), a.actions)
        with self.assertRaises(ValueError):
            kernel_model(self.kernel, [a, conflicting], lambda s, _: s['cash'])
        model = kernel_model(self.kernel, [a], lambda s, _: s['cash'])
        out = model.transition(a.state(0), a.name, a.context)
        out['cash'] = 999
        self.assertEqual(model.transition(a.state(0), a.name, a.context)['cash'], 1)


if __name__ == '__main__':
    unittest.main()
