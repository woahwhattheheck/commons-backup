# SPDX-License-Identifier: Apache-2.0
import copy
import unittest

from constraint_repair import (
    RepairConfig,
    _bounded_actions,
    _jsonable,
    canonical_bytes,
    checkpoint_sha256,
    find_shortest_splice,
    kaggriculture_material_checkpoint,
    make_kaggriculture_projector,
)


class FakeClock:
    def __init__(self, values):
        self.values = iter(values)
        self.last = 0
    def __call__(self):
        try:
            self.last = next(self.values)
        except StopIteration:
            self.last += 1
        return self.last


def state(*, positions=((1, 2),), inventories=({},), shed=None, seeds=None,
          cash=100, funding=None, shared=None, public=None, market=None):
    return {
        'farm': {'farmer': list(positions[0]),
                 'hands': [list(p) for p in positions[1:]],
                 'money': cash},
        'private': {'inventories': [dict(x) for x in inventories],
                    'shed': dict(shed or {}), 'seeds': dict(seeds or {})},
        'funding': copy.deepcopy(funding or {}),
        'shared': copy.deepcopy(shared or {}),
        'public': copy.deepcopy(public or {}),
        'market': copy.deepcopy(market or {}),
    }


def graph_transition(graph):
    def transition(current, action):
        nxt = graph.get((current['node'], action))
        if nxt is None:
            return None
        out = copy.deepcopy(current)
        out.update(copy.deepcopy(nxt))
        return out
    return transition


class SourceCaseTests(unittest.TestCase):
    def test_hire_spawn_position_only_rejoin_is_rejected(self):
        target = state(positions=((1, 2), (0, 0)), inventories=({}, {}), cash=100,
                       funding={'hire_reserved': 0}, shared={'workers': 2})
        pseudo = state(positions=((1, 2), (0, 0)), inventories=({}, {}), cash=70,
                       funding={'hire_reserved': 30}, shared={'workers': 2})
        self.assertEqual(target['farm']['farmer'], pseudo['farm']['farmer'])
        self.assertNotEqual(kaggriculture_material_checkpoint(target),
                            kaggriculture_material_checkpoint(pseudo))

    def test_shared_wheat_position_only_rejoin_is_rejected(self):
        target = state(inventories=({'WHEAT': 8},), shed={'WHEAT': 0},
                       shared={'wheat_reserved': 0})
        pseudo = state(inventories=({'WHEAT': 0},), shed={'WHEAT': 8},
                       shared={'wheat_reserved': 8})
        self.assertEqual(target['farm']['farmer'], pseudo['farm']['farmer'])
        self.assertNotEqual(kaggriculture_material_checkpoint(target),
                            kaggriculture_material_checkpoint(pseudo))

    def test_deposit_after_sale_position_and_inventory_match_but_cash_does_not(self):
        target = state(inventories=({'WHEAT': 0},), shed={'WHEAT': 0}, cash=180,
                       funding={'pending_deposit': 0}, market={'WHEAT': 9992})
        pseudo = state(inventories=({'WHEAT': 0},), shed={'WHEAT': 0}, cash=100,
                       funding={'pending_deposit': 80}, market={'WHEAT': 9992})
        self.assertEqual(target['farm']['farmer'], pseudo['farm']['farmer'])
        self.assertEqual(target['private'], pseudo['private'])
        self.assertNotEqual(kaggriculture_material_checkpoint(target),
                            kaggriculture_material_checkpoint(pseudo))

    def test_producer_owned_valued_delta_is_material(self):
        base = state()
        a = kaggriculture_material_checkpoint(base, producer_values={'future_sale_value': 80})
        b = kaggriculture_material_checkpoint(base, producer_values={'future_sale_value': 0})
        self.assertNotEqual(checkpoint_sha256(a), checkpoint_sha256(b))


class CanonicalKeyTests(unittest.TestCase):
    def test_non_string_mapping_key_fails_closed(self):
        with self.assertRaises(ValueError) as ctx:
            _jsonable({1: 'x'})
        self.assertIn('non-string mapping key', str(ctx.exception))

    def test_int_and_str_keys_do_not_collide_into_false_exact(self):
        # Previously str(1) == "1" collapsed distinct maps.
        a = {1: 'x'}
        b = {'1': 'y'}
        with self.assertRaises(ValueError):
            canonical_bytes(a)
        # string-keyed map remains valid
        self.assertIsInstance(canonical_bytes(b), bytes)

    def test_mixed_int_str_keys_in_same_map_fail_closed(self):
        with self.assertRaises(ValueError):
            canonical_bytes({1: 'x', '1': 'y'})

    def test_string_keys_remain_order_independent(self):
        a = canonical_bytes({'b': 1, 'a': 2})
        b = canonical_bytes({'a': 2, 'b': 1})
        self.assertEqual(a, b)


class SearchTests(unittest.TestCase):
    def test_shortest_exact_splice_is_deterministic(self):
        # Two exact 2-step routes exist. Lexical action order A,B wins over C,D.
        start = {'node': 's', 'material': {'position': [1, 2], 'cash': 50}}
        target = {'position': [4, 2], 'cash': 50}
        graph = {
            ('s', 'C'): {'node': 'c', 'material': {'position': [2, 2], 'cash': 50}},
            ('c', 'D'): {'node': 't2', 'material': target},
            ('s', 'A'): {'node': 'a', 'material': {'position': [3, 2], 'cash': 50}},
            ('a', 'B'): {'node': 't1', 'material': target},
        }
        provider = lambda st, depth: ('D', 'C', 'B', 'A')
        result = find_shortest_splice(
            start, target, provider, graph_transition(graph),
            projector=lambda st: st['material'],
            config=RepairConfig(max_nodes=128, max_depth=4, budget_ns=1_000_000_000),
            now_ns=FakeClock(range(10000)),
        )
        self.assertTrue(result.found)
        self.assertEqual(('A', 'B'), result.actions)
        self.assertEqual(2, result.depth)

    def test_geometric_match_with_cash_delta_is_not_accepted(self):
        start = {'node': 's', 'material': {'position': [1, 2], 'cash': 50}}
        target = {'position': [1, 2], 'cash': 100}
        graph = {('s', 'LOOP'): {'node': 'p', 'material': {'position': [1, 2], 'cash': 50}}}
        result = find_shortest_splice(
            start, target, lambda *_: ('LOOP',), graph_transition(graph),
            projector=lambda st: st['material'],
            config=RepairConfig(max_nodes=8, max_depth=2, budget_ns=1_000_000_000),
            now_ns=FakeClock(range(1000)),
        )
        self.assertFalse(result.found)
        self.assertIn(result.reason, {'no-match', 'node-cap'})

    def test_node_cap_fails_closed_at_128_or_less(self):
        def provider(st, depth):
            return tuple(range(32))
        def transition(st, action):
            return {'id': st['id'] * 100 + action + 1}
        result = find_shortest_splice(
            {'id': 0}, {'id': -1}, provider, transition,
            projector=lambda st: st,
            config=RepairConfig(max_nodes=128, max_depth=8, budget_ns=1_000_000_000),
            now_ns=FakeClock(range(100000)),
        )
        self.assertFalse(result.found)
        self.assertEqual('node-cap', result.reason)
        self.assertLessEqual(result.nodes_seen, 128)
        self.assertEqual((), result.actions)

    def test_deadline_fails_closed(self):
        result = find_shortest_splice(
            {'id': 0}, {'id': 1}, lambda *_: (1,), lambda s, a: {'id': 1},
            projector=lambda st: st,
            config=RepairConfig(max_nodes=128, max_depth=8, budget_ns=0),
            now_ns=lambda: 10,
        )
        self.assertFalse(result.found)
        self.assertTrue(result.used_fallback)
        self.assertEqual('deadline-before-search', result.reason)
        self.assertEqual((), result.actions)

    def test_mutating_transition_cannot_contaminate_sibling_nodes(self):
        start = {'node': 's', 'material': {'position': [0, 0], 'cash': 10}}
        target = {'position': [2, 0], 'cash': 10}
        def mutating(st, action):
            if st['node'] == 's' and action == 'A':
                st['material']['cash'] = 0
                st['node'] = 'dead'
                return st
            if st['node'] == 's' and action == 'B':
                st['node'] = 'b'
                st['material']['position'] = [1, 0]
                return st
            if st['node'] == 'b' and action == 'C':
                st['node'] = 't'
                st['material']['position'] = [2, 0]
                return st
            return None
        result = find_shortest_splice(
            start, target, lambda st, depth: ('A', 'B', 'C'), mutating,
            projector=lambda st: st['material'],
            config=RepairConfig(max_nodes=32, max_depth=3, budget_ns=1_000_000_000),
            now_ns=FakeClock(range(1000)),
        )
        self.assertTrue(result.found)
        self.assertEqual(('B', 'C'), result.actions)
        self.assertEqual(10, start['material']['cash'])

    def test_transition_error_fails_closed(self):
        def bad(*_):
            raise RuntimeError('boom')
        result = find_shortest_splice(
            {'id': 0}, {'id': 1}, lambda *_: ('x',), bad,
            projector=lambda st: st,
            config=RepairConfig(budget_ns=1_000_000_000),
            now_ns=FakeClock(range(1000)),
        )
        self.assertEqual('transition-error', result.reason)
        self.assertEqual((), result.actions)

    def test_already_equal_returns_empty_success(self):
        st = state()
        projector = make_kaggriculture_projector(producer_values={'delta': 0})
        target = projector(st)
        result = find_shortest_splice(
            st, target, lambda *_: (), lambda *_: None,
            projector=projector,
            config=RepairConfig(),
            now_ns=FakeClock(range(1000)),
        )
        self.assertTrue(result.found)
        self.assertEqual('already-equal', result.reason)
        self.assertEqual(0, result.depth)

    def test_duplicate_heavy_provider_is_raw_pull_bounded(self):
        pulls = {'n': 0}
        def infinite_dupes(st, depth):
            while True:
                pulls['n'] += 1
                yield 'SAME'
        result = find_shortest_splice(
            {'id': 0}, {'id': 1},
            infinite_dupes,
            lambda s, a: None,
            projector=lambda st: st,
            config=RepairConfig(max_nodes=8, max_depth=2, budget_ns=1_000_000_000,
                                max_candidates=4, max_raw_pulls=16),
            now_ns=FakeClock(range(100000)),
        )
        self.assertFalse(result.found)
        self.assertIn(result.reason, {'no-match', 'node-cap'})
        # One expansion level at depth 0: at most max_raw_pulls pulls.
        self.assertLessEqual(pulls['n'], 16)

    def test_candidate_enumeration_honors_deadline(self):
        clock = FakeClock([0, 0, 0, 5, 5, 5, 5])  # expire mid-enumeration
        def slow_dupes(st, depth):
            for i in range(1000):
                yield 'X'
        result = find_shortest_splice(
            {'id': 0}, {'id': 1},
            slow_dupes,
            lambda s, a: None,
            projector=lambda st: st,
            config=RepairConfig(max_nodes=32, max_depth=2, budget_ns=4,
                                max_candidates=8, max_raw_pulls=1000),
            now_ns=clock,
        )
        self.assertFalse(result.found)
        self.assertTrue(result.used_fallback)
        self.assertIn(result.reason, {'deadline', 'deadline-before-search', 'no-match'})


if __name__ == '__main__':
    unittest.main()
