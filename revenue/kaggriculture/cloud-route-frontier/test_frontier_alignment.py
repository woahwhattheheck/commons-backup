# SPDX-License-Identifier: Apache-2.0
"""Exact changed-path coverage for invocation-local frontier alignment reuse."""
from copy import deepcopy
from dataclasses import replace
import itertools
import random
import unittest
from unittest.mock import patch
import route_frontier as rf


def reference(items, max_size=64, max_candidates=256, rank=None):
    """The original scan order, independently kept as an executable oracle."""
    if type(max_size) is not int or max_size < 1:
        raise ValueError('max_size must be positive')
    if type(max_candidates) is not int or max_candidates < 1:
        raise ValueError('max_candidates must be positive')
    if len(items) > max_candidates:
        raise ValueError('candidate bound exceeded; no truncated exact frontier')
    if len({a.name for a in items}) != len(items):
        raise ValueError('alternative names must be unique')
    kept, removed, checks = [], [], 0
    for right in items:
        for left in items:
            if left is right:
                continue
            checks += 1
            if rf.dominates(left, right):
                removed.append((right.name, left.name))
                break
        else:
            kept.append(right)
    dropped = ()
    if len(kept) > max_size:
        if rank is not None:
            kept.sort(key=rank, reverse=True)
        dropped = tuple(a.name for a in kept[max_size:])
        kept = kept[:max_size]
    return rf.Frontier(tuple(kept), tuple(removed), dropped, checks)


def trace(context='s', group=0, name='route', trace_class=rf.Trace):
    start = rf.exact_key({'step': 0, 'cash': 0, 'group': group,
                          'carry': {'MILK': 1, 'WOOL': 1}})
    end = rf.exact_key({'step': 1, 'cash': 0, 'group': group,
                        'carry': {'MILK': 1, 'WOOL': 1}})
    return trace_class(name, context, (start, end), (rf.exact_key({'farmer': ['PASS']}),))


def alt(name, values, contexts=('s',), group=0, cls=rf.Alternative):
    return cls(name, tuple(trace(s, group, name) for s in contexts),
               ('cash', 'deadline'), tuple(tuple(x) for x in values))


class AlignmentTests(unittest.TestCase):
    def assert_same(self, items, **kwargs):
        expected = reference(items, **kwargs)
        actual = rf.pareto_frontier(items, **kwargs)
        self.assertEqual(actual, expected)
        for a, e in zip(actual.kept, expected.kept):
            self.assertIs(a, e)
        return actual

    def test_exhaustive_four_point_frontiers(self):
        points = list(itertools.product(range(3), repeat=2))
        for bank in itertools.combinations(points, 4):
            for limit in (1, 3, 64):
                self.assert_same([alt(str(i), [p]) for i, p in enumerate(bank)], max_size=limit)

    def test_random_multiscenario_inputs(self):
        rng = random.Random(81274)  # fixture generation, not a game seed
        for _ in range(180):
            contexts = tuple(f's{i}' for i in range(rng.randint(1, 5)))
            items = []
            for n in range(rng.randint(0, 15)):
                order = list(contexts); rng.shuffle(order)
                values = [(rng.randint(-8, 8), rng.uniform(-8, 8)) for _ in order]
                items.append(alt(str(n), values, tuple(order), rng.randint(0, 2)))
            self.assert_same(items, max_size=rng.randint(1, 8), rank=lambda a: sum(a.vector()))

    def test_one_alignment_and_vector_per_alternative(self):
        items = [alt(str(i), [(i, 32-i)] * 8, tuple(f's{x}' for x in range(8))) for i in range(32)]
        counts = {'keys': 0, 'vectors': 0}
        key, vector = rf.Alternative.comparison_key, rf.Alternative.vector
        def key_count(a):
            counts['keys'] += 1
            return key(a)
        def vec_count(a):
            counts['vectors'] += 1
            return vector(a)
        with patch.object(rf.Alternative, 'comparison_key', key_count), patch.object(rf.Alternative, 'vector', vec_count):
            result = rf.pareto_frontier(items)
        self.assertEqual(counts, {'keys': 32, 'vectors': 32})
        self.assertEqual(result.dominance_comparisons, 32 * 31)
        self.assertEqual(len(result.kept), 32)

    def test_incomparable_inputs_do_not_build_vectors(self):
        items = [alt(str(i), [(i, i)], group=i) for i in range(20)]
        with patch.object(rf.Alternative, 'vector', side_effect=AssertionError('unused vector')):
            result = rf.pareto_frontier(items)
        self.assertEqual(len(result.kept), 20)
        self.assertEqual(result.dominance_comparisons, 380)

    def test_empty_and_single_never_align(self):
        one = alt('one', [(1, 1)])
        with patch.object(rf.Alternative, 'comparison_key', side_effect=AssertionError('unused key')):
            self.assertEqual(rf.pareto_frontier([]).dominance_comparisons, 0)
            self.assertEqual(rf.pareto_frontier([one]).kept, (one,))

    def test_first_dominator_and_stable_ties(self):
        items = [alt('low', [(0, 0)]), alt('first', [(2, 2)]), alt('second', [(3, 3)]), alt('tie', [(3, 3)])]
        result = self.assert_same(items)
        self.assertEqual(result.dominated, (('low', 'first'), ('first', 'second')))
        self.assertEqual(tuple(a.name for a in result.kept), ('second', 'tie'))

    def test_rank_callback_order_and_references(self):
        items = [alt(str(i), [(i, 7-i)]) for i in range(8)]
        calls_a, calls_b = [], []
        expected = reference(items, max_size=3, rank=lambda a: calls_a.append(a) or a.values[0][0])
        actual = rf.pareto_frontier(items, max_size=3, rank=lambda a: calls_b.append(a) or a.values[0][0])
        self.assertEqual(actual, expected)
        self.assertEqual(calls_a, calls_b)
        self.assertTrue(actual.approximate)
        with patch.object(rf.Alternative, 'vector', wraps=None) as unused:
            rf.pareto_frontier([], rank=lambda a: self.fail('ranked empty input'))
            self.assertEqual(unused.call_count, 0)

    def test_cache_does_not_survive_next_invocation(self):
        items = [alt('a', [(2, 2)]), alt('b', [(1, 1)])]
        first = self.assert_same(items)
        changed = [replace(items[0], values=((0, 0),)), items[1]]
        second = self.assert_same(changed)
        self.assertEqual(first.kept[0].name, 'a')
        self.assertEqual(second.kept[0].name, 'b')

    def test_mutation_and_failure_leave_inputs_unchanged(self):
        items = [alt(str(i), [(i, 4-i)]) for i in range(5)]
        frozen = deepcopy(items)
        with self.assertRaisesRegex(RuntimeError, 'rank failure'):
            rf.pareto_frontier(items, max_size=1, rank=lambda a: (_ for _ in ()).throw(RuntimeError('rank failure')))
        self.assertEqual(items, frozen)
        self.assert_same(items)

    def test_subclass_method_call_order_is_preserved(self):
        calls = []
        class Custom(rf.Alternative):
            def comparison_key(self):
                calls.append(('key', self.name))
                return super().comparison_key()
            def vector(self):
                calls.append(('vector', self.name))
                return super().vector()
        items = [alt(str(i), [(i, 5-i)], cls=Custom) for i in range(6)]
        expected = reference(items); old_calls = list(calls); calls.clear()
        actual = rf.pareto_frontier(items)
        self.assertEqual(actual, expected)
        self.assertEqual(calls, old_calls)

    def test_custom_trace_dispatch_is_preserved(self):
        calls = []
        class CustomTrace(rf.Trace):
            @property
            def exit(self):
                calls.append(self.name)
                return super().exit
        items = [rf.Alternative(str(i), (trace(name=str(i), trace_class=CustomTrace),), ('cash',), ((i,),)) for i in range(5)]
        expected = reference(items); old_calls = list(calls); calls.clear()
        actual = rf.pareto_frontier(items)
        self.assertEqual(actual, expected)
        self.assertEqual(calls, old_calls)

    def test_scenario_alignment_and_continuation_boundaries(self):
        a = alt('a', [(9, 1), (1, 9)], ('x', 'y'))
        b = alt('b', [(1, 9), (9, 1)], ('y', 'x'))
        self.assert_same([a, b])
        different = replace(b, traces=(trace('x', 9), trace('y', 9)))
        self.assertEqual(len(self.assert_same([a, different]).kept), 2)
        left = replace(a, continuation_keys=('end', 'end'), equivalence_label='declared-terminal')
        right = replace(b, values=((0, 0), (0, 0)), continuation_keys=('end', 'end'), equivalence_label='declared-terminal')
        self.assertEqual(self.assert_same([left, right]).dominated, (('b', 'a'),))

    def test_ordered_snapshots_are_not_canonicalized(self):
        one = trace()
        x = one.state(); x['carry'] = {'WOOL': 1, 'MILK': 1}
        other = replace(one, snapshots=(one.entry, rf.exact_key(x)))
        items = [rf.Alternative('a', (one,), ('cash',), ((100,),)), rf.Alternative('b', (other,), ('cash',), ((1,),))]
        self.assertEqual(len(self.assert_same(items).kept), 2)

    def test_validation_precedes_alignment(self):
        one = alt('one', [(1, 1)])
        inputs = [([one, one], {}), ([one], {'max_size': 0}), ([one], {'max_candidates': False}), ([one, replace(one, name='two')], {'max_candidates': 1})]
        with patch.object(rf.Alternative, 'comparison_key', side_effect=AssertionError('validation order')):
            for items, options in inputs:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    rf.pareto_frontier(items, **options)

    def test_single_dominates_function_unchanged(self):
        a, b = alt('a', [(4, 4)]), alt('b', [(3, 4)])
        self.assertTrue(rf.dominates(a, b))
        self.assertFalse(rf.dominates(b, a))
        self.assertFalse(rf.dominates(a, a))


if __name__ == '__main__':
    unittest.main()
