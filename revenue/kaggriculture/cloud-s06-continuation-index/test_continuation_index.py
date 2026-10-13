import sys
import unittest

from continuation_index import (
    ContinuationIndex, action_key, collision_reasons, exact_state_hash,
    product_quantized_key, project_public_state, _deep_size,
)


def state(*, money=100, carrots=8, market=40, phase=3, future=None):
    value = {
        'phase': phase,
        'positions': {'farmer': [2, 3], 'hands': [[1, 1]]},
        'resources': {'money': money, 'seeds': {'CARROT': carrots}},
        'structures': {'shed': 1, 'plots': 4},
        'animals': {'COW': 2},
        'market': {'inventory': {'MILK': market}, 'prices': {'MILK': 8}},
        'commitments': {'funding_reserved': 20, 'seed_reserved': {'CARROT': 2},
                        'blocked_routes': ['west']},
    }
    if future is not None:
        value['future_outcome'] = future
    return value


def action(name, **requires):
    return {'name': name, 'requires': requires}


class ContinuationIndexTests(unittest.TestCase):
    def test_projection_excludes_future_labels(self):
        a = state(future={'win': True})
        b = state(future={'win': False})
        self.assertEqual(project_public_state(a), project_public_state(b))
        self.assertEqual(exact_state_hash(a), exact_state_hash(b))

    def test_exact_hash_is_dict_order_invariant(self):
        a = state()
        b = dict(reversed(list(a.items())))
        self.assertEqual(exact_state_hash(a), exact_state_hash(b))

    def test_product_quantization_groups_nearby_resource_market_values(self):
        a = state(money=100, market=40)
        b = state(money=103, market=43)
        self.assertNotEqual(exact_state_hash(a), exact_state_hash(b))
        self.assertEqual(product_quantized_key(a), product_quantized_key(b))

    def test_exact_miss_still_returns_canonical(self):
        idx = ContinuationIndex()
        idx.add(state(money=80), action('old'), 't1')
        result = idx.retrieve(state(money=100), [action('canonical')], mode='exact')
        self.assertEqual([c.source for c in result], ['canonical'])

    def test_quantized_mode_unions_history_with_canonical(self):
        idx = ContinuationIndex()
        idx.add(state(money=100), action('history'), 't1')
        result = idx.retrieve(state(money=103), [action('canonical')], mode='quantized')
        self.assertEqual([c.source for c in result], ['canonical', 'history'])
        self.assertFalse(result[1].exact_match)

    def test_canonical_duplicate_wins_over_history(self):
        idx = ContinuationIndex()
        shared = action('same')
        idx.add(state(), shared, 't1')
        result = idx.retrieve(state(), [shared], mode='exact')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, 'canonical')

    def test_retrieve_32_bound_applies_before_economic_rerank(self):
        idx = ContinuationIndex(retrieve_limit=32)
        for i in range(50):
            idx.add(state(), action('h%02d' % i), 't%02d' % i)
        calls = []
        def score(a, _s):
            if a['name'].startswith('h'):
                calls.append(a['name'])
            return float(a['name'][1:]) if a['name'].startswith('h') else -1.0
        result = idx.retrieve(state(), [action('canonical')], mode='rerank', economic_score=score)
        self.assertEqual(len(calls), 32)
        self.assertEqual(sum(c.source == 'history' for c in result), 32)
        self.assertEqual(result[0].action['name'], 'h31')
        self.assertTrue(any(c.source == 'canonical' for c in result))

    def test_rerank_ties_prefer_canonical_and_are_deterministic(self):
        idx = ContinuationIndex()
        idx.add(state(), action('history'), 't1')
        expected = None
        for _ in range(5):
            got = idx.retrieve(state(), [action('canonical')], mode='rerank',
                               economic_score=lambda *_: 1.0)
            names = [(c.source, c.action['name']) for c in got]
            self.assertEqual(names[0], ('canonical', 'canonical'))
            if expected is None:
                expected = names
            self.assertEqual(names, expected)

    def test_funding_collision_rejects_history(self):
        idx = ContinuationIndex()
        idx.add(state(), action('expensive', funding=81), 't1')
        result = idx.retrieve(state(), [action('canonical')], mode='exact')
        self.assertEqual([c.source for c in result], ['canonical'])
        self.assertIn('funding', collision_reasons(action('x', funding=81), state()))

    def test_seed_collision_rejects_history(self):
        idx = ContinuationIndex()
        idx.add(state(), action('seed-heavy', seeds={'CARROT': 7}), 't1')
        result = idx.retrieve(state(), [action('canonical')], mode='exact')
        self.assertEqual([c.source for c in result], ['canonical'])
        self.assertIn('seed', collision_reasons(action('x', seeds={'CARROT': 7}), state()))

    def test_route_collision_rejects_history(self):
        idx = ContinuationIndex()
        idx.add(state(), action('blocked', route='west'), 't1')
        result = idx.retrieve(state(), [action('canonical')], mode='exact')
        self.assertEqual([c.source for c in result], ['canonical'])
        self.assertIn('route', collision_reasons(action('x', route='west'), state()))

    def test_legality_callback_rejects_history_but_not_canonical(self):
        idx = ContinuationIndex()
        idx.add(state(), action('history'), 't1')
        result = idx.retrieve(state(), [action('canonical')], mode='exact',
                              legal=lambda _a, _s: False)
        self.assertEqual([(c.source, c.action['name']) for c in result],
                         [('canonical', 'canonical')])

    def test_explicit_falsy_malformed_requires_fail_closed(self):
        for bad in ([], '', 0, False, None):
            with self.subTest(requires=repr(bad)):
                reasons = collision_reasons({'name': 'bad', 'requires': bad}, state())
                self.assertEqual(reasons, ('malformed_requirements',))

    def test_malformed_requires_history_is_rejected_but_canonical_survives(self):
        idx = ContinuationIndex()
        idx.add(state(), {'name': 'bad-history', 'requires': []}, 't1')
        result = idx.retrieve(state(), [action('canonical')], mode='exact')
        self.assertEqual([(c.source, c.action['name']) for c in result],
                         [('canonical', 'canonical')])

    def test_duplicate_trajectory_record_is_idempotent(self):
        idx = ContinuationIndex()
        self.assertTrue(idx.add(state(), action('h'), 't1'))
        self.assertFalse(idx.add(state(), action('h'), 't1'))
        self.assertEqual(idx.stats()['records'], 1)

    def test_memory_budget_fails_closed_before_mutation(self):
        idx = ContinuationIndex(max_bytes=5000)
        before = idx.stats().copy()
        with self.assertRaises(MemoryError):
            idx.add(state(), {'name': 'huge', 'payload': 'x' * 1000}, 't1')
        self.assertEqual(idx.stats(), before)

    def test_budget_edge_uses_full_record_admission_charge(self):
        probe = ContinuationIndex()
        base = probe.stats()['admission_bytes']
        probe.add(state(), action('edge'), 't1')
        charge = probe.stats()['admission_bytes'] - base
        idx = ContinuationIndex(max_bytes=base + charge - 1)
        before = idx.stats().copy()
        with self.assertRaises(MemoryError):
            idx.add(state(), action('edge'), 't1')
        self.assertEqual(idx.stats(), before)

    def test_admission_charge_bounds_owned_python_object_graph(self):
        idx = ContinuationIndex(max_bytes=8 * 1024 * 1024)
        for i in range(256):
            idx.add(state(money=100 + (i % 4)), action('h%03d' % i), 't%03d' % i)
        structural = _deep_size((idx._records, idx._exact, idx._product,
                                 idx._seen, idx.quanta)) + sys.getsizeof(idx)
        self.assertGreaterEqual(idx.stats()['admission_bytes'], structural)
        self.assertLessEqual(idx.stats()['admission_bytes'], idx.stats()['max_bytes'])

    def test_action_hash_is_content_order_invariant(self):
        self.assertEqual(action_key({'b': 2, 'a': 1}), action_key({'a': 1, 'b': 2}))


if __name__ == '__main__':
    unittest.main()
