# SPDX-License-Identifier: Apache-2.0
"""Source-only route tests; no economic or official-engine result is implied."""
import copy
import itertools
import random
import unittest

from r04_s1_collection_route import plan_collection_route


def cost(start, route):
    used = 0
    for target in route:
        used += abs(start[0] - target[0]) + abs(start[1] - target[1]) + 1
        start = target
    return used


def oracle(start, targets, callbacks, max_collect=6):
    # Independently enumerate permutations, without the planner's bounds/cache.
    best = (0, 0)
    for size in range(1, min(len(targets), max_collect) + 1):
        found = False
        for route in itertools.permutations(targets, size):
            used = cost(start, route)
            if used <= callbacks:
                found = True
                if size > best[0] or (size == best[0] and used < best[1]):
                    best = size, used
        if not found:
            break
    return best


def incumbent_count(start, targets, callbacks):
    # Faithful _reachable_count extraction from #12630 helper Git blob
    # f14e18e67b5c0b95943f3c9b9db649d3327d5eb4; REACH == 6.
    pos = tuple(start)
    remaining = list(targets)
    used = 0
    count = 0
    while remaining and count < 6:
        target = min(
            remaining,
            key=lambda p: (abs(pos[0] - p[0]) + abs(pos[1] - p[1]), p[1], p[0]),
        )
        distance = abs(pos[0] - target[0]) + abs(pos[1] - target[1])
        step_cost = distance + 1
        if used + step_cost > callbacks:
            break
        used += step_cost
        count += 1
        pos = target
        remaining.remove(target)
    return count


def replay(start, targets, callbacks):
    # Replan each callback, just as the proposed S1 _hand_command adapter does.
    # Every movement is x-first, preserving incumbent _step_toward semantics.
    remaining = set(targets)
    pos = start
    collected = 0
    for tick in range(callbacks):
        route = plan_collection_route(pos, sorted(remaining), callbacks - tick)
        if not route:
            continue
        target = route[0]
        if pos == target:
            remaining.remove(target)
            collected += 1
        elif pos[0] != target[0]:
            pos = (pos[0] + (1 if pos[0] < target[0] else -1), pos[1])
        else:
            pos = (pos[0], pos[1] + (1 if pos[1] < target[1] else -1))
    return collected


class CollectionRouteTests(unittest.TestCase):
    def test_all_small_geometry_subsets_match_independent_oracle(self):
        points = ((3, 3), (4, 3), (5, 3), (3, 4), (4, 4), (5, 4))
        starts = ((4, 4), (5, 4), (4, 5), (5, 5))
        for mask in range(1 << len(points)):
            targets = [p for i, p in enumerate(points) if mask & (1 << i)]
            for start in starts:
                for budget in range(10):
                    route = plan_collection_route(start, targets, budget)
                    expected = oracle(start, targets, budget)
                    self.assertEqual((len(route), cost(start, route)), expected,
                                     (start, targets, budget, route))

    def test_seeded_sparse_geometry_matches_independent_oracle(self):
        rng = random.Random(20260911)
        grid = [(x, y) for y in range(10) for x in range(10)]
        for _ in range(240):
            start = rng.choice(grid)
            targets = rng.sample(grid, rng.randrange(7))
            budget = rng.randrange(10)
            limit = rng.randrange(7)
            route = plan_collection_route(start, targets, budget, max_collect=limit)
            self.assertEqual((len(route), cost(start, route)),
                             oracle(start, targets, budget, limit))

    def test_three_animal_witness_improves_worst_spawn(self):
        targets = ((4, 3), (2, 4), (2, 5))
        starts = ((4, 4), (5, 4), (4, 5), (5, 5))
        old = [incumbent_count(start, targets, 6) for start in starts]
        new = [len(plan_collection_route(start, targets, 6)) for start in starts]
        self.assertEqual(old, [2, 1, 1, 1])
        self.assertEqual(new, [2, 2, 2, 2])
        for start in starts:
            self.assertEqual(replay(start, targets, 6), 2)

    def test_replanning_realizes_predicted_collections(self):
        rng = random.Random(1789177911)
        points = [(x, y) for y in range(10) for x in range(10)
                  if not (x >= 5 and y >= 5)]
        for _ in range(300):
            targets = rng.sample(points, rng.randrange(20))
            start = rng.choice(((4, 4), (5, 4), (4, 5), (5, 5)))
            budget = rng.randrange(10)
            route = plan_collection_route(start, targets, budget)
            self.assertEqual(replay(start, targets, budget), len(route),
                             (start, targets, budget))

    def test_never_underperforms_incumbent_on_seeded_panel(self):
        rng = random.Random(9911)
        grid = [(x, y) for y in range(10) for x in range(10)]
        for _ in range(400):
            targets = rng.sample(grid, rng.randrange(1, 40))
            start = rng.choice(grid)
            budget = rng.randrange(10)
            route = plan_collection_route(start, targets, budget)
            self.assertGreaterEqual(len(route), incumbent_count(start, targets, budget))
            self.assertLessEqual(cost(start, route), budget)
            self.assertEqual(len(route), len(set(route)))
            self.assertTrue(set(route).issubset(targets))

    def test_full_grid_theoretical_limit(self):
        grid = [(x, y) for y in range(10) for x in range(10)]
        for budget in range(1, 10):
            route = plan_collection_route((4, 4), grid, budget)
            self.assertEqual(len(route), (budget + 1) // 2)
            self.assertEqual(cost((4, 4), route), 2 * len(route) - 1)

    def test_input_order_duplicates_and_repeat_are_stable(self):
        targets = [[4, 3], [2, 4], [2, 5], [1, 4]]
        before = copy.deepcopy(targets)
        expected = plan_collection_route([5, 5], targets, 9)
        for permutation in itertools.permutations(targets):
            self.assertEqual(plan_collection_route([5, 5], permutation, 9), expected)
        self.assertEqual(plan_collection_route([5, 5], targets + targets, 9), expected)
        self.assertEqual(targets, before)

    def test_target_at_origin_charges_collection_callback(self):
        self.assertEqual(plan_collection_route((4, 4), [(4, 4)], 0), ())
        self.assertEqual(plan_collection_route((4, 4), [(4, 4)], 1), ((4, 4),))
        self.assertEqual(plan_collection_route((4, 4), [(5, 4)], 1), ())
        self.assertEqual(plan_collection_route((4, 4), [(5, 4)], 2), ((5, 4),))

    def test_last_collection_needs_no_shed_return(self):
        self.assertEqual(plan_collection_route((4, 4), [(0, 4)], 5), ((0, 4),))

    def test_collection_cap(self):
        grid = [(x, y) for y in range(10) for x in range(10)]
        for limit in range(7):
            route = plan_collection_route((4, 4), grid, 9, max_collect=limit)
            self.assertEqual(len(route), min(limit, 5))

    def test_malformed_or_wider_domain_fails_closed(self):
        for bad in (None, True, 1.0, '1', -1, 10, 10**1000):
            self.assertEqual(plan_collection_route((4, 4), [(4, 4)], bad), ())
        for bad in (None, True, 1.0, '1', -1, 7, 10**1000):
            self.assertEqual(plan_collection_route((4, 4), [(4, 4)], 9, max_collect=bad), ())
        for bad in (None, '44', [4], [4, 4, 4], [True, 4], [4.0, 4], [-1, 4], [10, 4]):
            self.assertEqual(plan_collection_route(bad, [(4, 4)], 9), ())
            self.assertEqual(plan_collection_route((4, 4), [bad], 9), ())
        for bad in (None, {}, {(4, 4)}, 'targets', [[4, 4]] * 101):
            self.assertEqual(plan_collection_route((4, 4), bad, 9), ())

    def test_calls_do_not_retain_a_previous_game(self):
        self.assertTrue(plan_collection_route((4, 4), [(4, 4)], 1))
        self.assertEqual(plan_collection_route((4, 4), [], 1), ())
        self.assertEqual(plan_collection_route((0, 0), [(9, 9)], 9), ())


if __name__ == '__main__':
    unittest.main()
