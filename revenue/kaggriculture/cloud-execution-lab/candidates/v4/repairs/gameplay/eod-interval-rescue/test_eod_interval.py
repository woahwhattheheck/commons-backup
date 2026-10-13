# SPDX-License-Identifier: Apache-2.0
"""Independent exhaustive/permutation and pinned SELL/drop excerpt checks."""
from __future__ import annotations

import copy
import itertools
import random
import unittest
from collections import Counter

import eod_interval as lane
from engine_oracle import _commit_unit, _drop_inventories_to_shed


def ordered_cargo(inventories):
    choices = [list(itertools.permutations(inv.items())) for inv in inventories]
    for parts in itertools.product(*choices):
        yield [dict(part) for part in parts]


def brute_interval(inventories, left, right):
    outcomes = []
    for inventories_order in ordered_cargo(inventories):
        stream = [p for inv in inventories_order for p, n in inv.items() for _ in range(n)]
        outcomes.append(dict(Counter(stream[left:right])))
    return outcomes[0] if all(outcome == outcomes[0] for outcome in outcomes) else None


def brute_best(inventories, shed, capacity, order_slots):
    room = capacity - sum(shed.values())
    total = sum(sum(inv.values()) for inv in inventories)
    for k in range(min(total-room, sum(shed.get(p, 0) for p in lane.PRODUCTS)), 0, -1):
        expected = brute_interval(inventories, room, room+k)
        if (expected and len(expected) <= order_slots
                and all(shed.get(p, 0) >= n for p, n in expected.items())):
            return dict(sorted(expected.items()))
    return None


def prepared(inventories):
    snapshots = [[(p, n) for p, n in inv.items() if n] for inv in inventories]
    return [(sum(n for _, n in items), items, lane._block_starts(items))
            for items in snapshots]


class IntervalProof(unittest.TestCase):
    def prove_final_private(self, inventories, shed, vector, capacity=100, price=7):
        self.assertTrue(vector)
        total = sum(vector.values())
        count = 0
        for permutation in ordered_cargo(inventories):
            before = {"shed": dict(shed), "inventories": copy.deepcopy(permutation),
                      "seeds": {"WHEAT": 3}}
            baseline, candidate = copy.deepcopy(before), copy.deepcopy(before)
            _drop_inventories_to_shed(baseline, capacity)
            farm = {"money": 1000.0}
            market = {"inventory": {p: 10000 for p in lane.PRODUCTS}}
            for p, n in vector.items():
                for _ in range(n):
                    self.assertTrue(_commit_unit("SELL", p, price, farm, candidate, market, capacity))
            _drop_inventories_to_shed(candidate, capacity)
            # Includes cleared inventories, seed identity, zero keys, and animal ballast.
            self.assertEqual(candidate, baseline)
            self.assertEqual(farm["money"], 1000+price*total)
            for p in lane.PRODUCTS:
                self.assertEqual(market["inventory"][p], 10000+(vector.get(p, 0) if price > 1 else 0))
            count += 1
        return count

    def test_mixed_boundary_new_positive(self):
        inventories = [{"WHEAT": 5, "WOOL": 5}]
        shed = {"WHEAT": 48, "WOOL": 48}
        self.assertIsNone(brute_interval(inventories, 4, 10))
        vector = lane.certified_rescue_vector(inventories, shed)
        self.assertEqual(vector, {"WHEAT": 1, "WOOL": 1})
        self.assertEqual(self.prove_final_private(inventories, shed, vector), 2)

    def test_symmetric_larger_partial(self):
        inv = [{"WHEAT": 5, "WOOL": 5}]
        shed = {"WHEAT": 49, "WOOL": 49}
        vector = lane.certified_rescue_vector(inv, shed)
        self.assertEqual(vector, {"WHEAT": 3, "WOOL": 3})
        self.prove_final_private(inv, shed, vector)

    def test_naive_partial_is_not_a_proof(self):
        inventories = [{"WHEAT": 5, "WOOL": 5}]
        self.assertIsNone(brute_interval(inventories, 4, 5))
        self.assertIsNone(lane.certified_rescue_vector(inventories, {"WHEAT": 96}))

    def test_only_one_market_slot_rejects_two_product_witness(self):
        self.assertIsNone(lane.certified_rescue_vector(
            [{"WHEAT": 5, "WOOL": 5}], {"WHEAT": 48, "WOOL": 48}, order_slots=1))

    def test_safe_prefix_when_later_product_has_no_stock(self):
        inv, shed = [{"WHEAT": 2}, {"CARROT": 1}], {"WHEAT": 100}
        vector = lane.certified_rescue_vector(inv, shed)
        self.assertEqual(vector, {"WHEAT": 2})
        self.prove_final_private(inv, shed, vector)

    def test_order_budget_can_select_a_smaller_safe_prefix(self):
        inv, shed = [{"WHEAT": 2}, {"WOOL": 3}], {"WHEAT": 50, "WOOL": 50}
        self.assertEqual(lane.certified_rescue_vector(inv, shed), {"WHEAT": 2, "WOOL": 3})
        vector = lane.certified_rescue_vector(inv, shed, order_slots=1)
        self.assertEqual(vector, {"WHEAT": 2})
        self.prove_final_private(inv, shed, vector)

    def test_actor_list_order_is_material(self):
        shed = {"WHEAT": 50, "WOOL": 48}
        a, b = [{"WHEAT": 2}, {"WOOL": 3}], [{"WOOL": 3}, {"WHEAT": 2}]
        va = lane.certified_rescue_vector(a, shed)
        vb = lane.certified_rescue_vector(b, shed)
        self.assertEqual(va, {"WOOL": 3})
        self.assertEqual(vb, {"WHEAT": 2, "WOOL": 1})
        self.prove_final_private(a, shed, va)
        self.prove_final_private(b, shed, vb)

    def test_key_order_does_not_authorize_a_sale(self):
        inv = [{"WHEAT": 5, "WOOL": 5}]
        shed = {"WHEAT": 48, "WOOL": 48}
        variants = list(ordered_cargo(inv))
        self.assertEqual(lane.certified_rescue_vector(variants[0], shed),
                         lane.certified_rescue_vector(variants[1], dict(reversed(list(shed.items())))))

    def test_later_actor_variation_cannot_cancel_earlier_variation(self):
        inv = [{"WHEAT": 2, "WOOL": 2}, {"WHEAT": 2, "WOOL": 2}]
        self.assertIsNone(lane._interval_vector(prepared(inv), 1, 5))
        self.assertIsNone(brute_interval(inv, 1, 5))

    def test_all_three_product_intervals_exact(self):
        checked = 0
        for quantities in itertools.product(range(1, 5), repeat=3):
            inv = [dict(zip(("WHEAT", "CARROT", "WOOL"), quantities))]
            total = sum(quantities)
            for left in range(total+1):
                for right in range(left, total+1):
                    self.assertEqual(lane._interval_vector(prepared(inv), left, right),
                                     brute_interval(inv, left, right))
                    checked += 1
        self.assertEqual(checked, 2704)

    def test_two_actor_all_intervals_exact(self):
        checked = 0
        for quantities in itertools.product(range(3), repeat=4):
            inv = [{"WHEAT": quantities[0], "WOOL": quantities[1]},
                   {"CARROT": quantities[2], "WHEAT": quantities[3]}]
            total = sum(quantities)
            for left in range(total+1):
                for right in range(left, total+1):
                    self.assertEqual(lane._interval_vector(prepared(inv), left, right),
                                     brute_interval(inv, left, right))
                    checked += 1
        self.assertEqual(checked, 1323)

    def test_exhaustive_best_vector_stock_capacity_slot_constraints(self):
        checked = 0
        for quantities in itertools.product(range(3), repeat=4):
            inv = [{"WHEAT": quantities[0], "WOOL": quantities[1]},
                   {"WHEAT": quantities[2], "WOOL": quantities[3]}]
            for wheat, wool in itertools.product(range(4), repeat=2):
                shed = {"WHEAT": wheat, "WOOL": wool}
                for slots in (1, 2):
                    expected = brute_best(inv, shed, 6, slots)
                    actual = lane.certified_rescue_vector(inv, shed, capacity=6, order_slots=slots)
                    self.assertEqual(actual, expected, (inv, shed, slots))
                    if actual:
                        self.prove_final_private(inv, shed, actual, capacity=6)
                    checked += 1
        self.assertEqual(checked, 2592)

    def test_single_product_parity_where_full_loss_is_stocked(self):
        checked = 0
        for p in sorted(lane.PRODUCTS):
            for room, first, second in itertools.product(range(7), range(5), range(5)):
                shed, inv = {p: 100-room}, [{p: first}, {p: second}]
                loss = max(0, first+second-room)
                actual = lane.certified_rescue_vector(inv, shed)
                self.assertEqual(actual, {p: loss} if loss else None)
                if actual:
                    self.prove_final_private(inv, shed, actual)
                checked += 1
        self.assertEqual(checked, 1575)

    def test_full_shed_multi_product_preserves_original_success(self):
        inv = [{"WHEAT": 2, "WOOL": 1}, {"WOOL": 3, "EGG": 2}]
        shed = {"WHEAT": 30, "WOOL": 30, "EGG": 30, "COW": 10}
        vector = lane.certified_rescue_vector(inv, shed)
        self.assertEqual(vector, {"EGG": 2, "WHEAT": 2, "WOOL": 4})
        self.prove_final_private(inv, shed, vector)

    def test_floor_price_keeps_public_inventory_unchanged(self):
        inv, shed = [{"WHEAT": 5, "WOOL": 5}], {"WHEAT": 48, "WOOL": 48}
        vector = lane.certified_rescue_vector(inv, shed)
        self.prove_final_private(inv, shed, vector, price=1)

    def test_animal_shed_ballast_counts_but_is_not_sold(self):
        inv, shed = [{"WHEAT": 5, "WOOL": 5}], {"WHEAT": 1, "WOOL": 1, "COW": 94}
        vector = lane.certified_rescue_vector(inv, shed)
        self.assertEqual(vector, {"WHEAT": 1, "WOOL": 1})
        self.prove_final_private(inv, shed, vector)

    def test_empty_actors_and_zero_animal_cargo(self):
        inv, shed = [{}, {"WHEAT": 3, "COW": 0}, {}], {"WHEAT": 100}
        self.assertEqual(lane.certified_rescue_vector(inv, shed), {"WHEAT": 3})

    def test_invalid_quantities_and_unrecognized_items_fail_closed(self):
        for bad in (True, False, 1.0, "1", -1, None, [], {}):
            self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": bad}], {"WHEAT": 100}))
            self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 1}], {"WHEAT": bad}))
        for inv in ({"COW": 1}, {"MYSTERY": 0}, {"MYSTERY": 1}, {1: 2}):
            self.assertIsNone(lane.certified_rescue_vector([inv], {"WHEAT": 100}))
        self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 1}], {"MYSTERY": 100}))

    def test_malformed_late_actor_is_not_skipped(self):
        self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 100}, {"COW": 1}], {"WHEAT": 100}))

    def test_invalid_collections_and_operational_bounds(self):
        for inv in (None, {}, (), [], [None], [{}]*257):
            self.assertIsNone(lane.certified_rescue_vector(inv, {"WHEAT": 100}))
        for cap in (True, 100.0, "100", None, 0, 101):
            self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 1}], {}, capacity=cap))
        for slots in (True, 1.0, "1", None, -1, 11):
            self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 1}], {}, order_slots=slots))
        self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 1}], []))
        self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 1}], {"WHEAT": 101}))

    def test_no_overflow_empty_shed_and_no_slots(self):
        self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 1}], {"WHEAT": 1}))
        self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 101}], {}))
        self.assertIsNone(lane.certified_rescue_vector([{"WHEAT": 1}], {"WHEAT": 100}, order_slots=0))

    def test_input_and_returned_result_have_independent_custody(self):
        inv, shed = [{"WHEAT": 5, "WOOL": 5}], {"WHEAT": 48, "WOOL": 48}
        before = copy.deepcopy((inv, shed))
        result = lane.certified_rescue_vector(inv, shed)
        result["WHEAT"] = 999
        self.assertEqual((inv, shed), before)
        self.assertEqual(lane.certified_rescue_vector(inv, shed), {"WHEAT": 1, "WOOL": 1})

    def test_cargo_quantity_is_not_expanded_into_units(self):
        self.assertEqual(lane.certified_rescue_vector([{"WHEAT": 10**1000}], {"WHEAT": 100}),
                         {"WHEAT": 100})

    def test_nine_product_subset_bound(self):
        items = [(p, 1 << i) for i, p in enumerate(sorted(lane.PRODUCTS))]
        blocks = lane._block_starts(items)
        self.assertEqual(len(blocks), 9)
        self.assertTrue(all(len(starts) <= 256 for _, _, starts in blocks))

    def test_seeded_nine_product_full_private_conservation(self):
        rng, activated, permutations_checked = random.Random(1261201), 0, 0
        keys = sorted(lane.PRODUCTS)
        for _ in range(400):
            shed = {p: 7 for p in keys}
            shed["COW"] = rng.randrange(33, 38)
            inv = [{p: rng.randrange(1, 6) for p in rng.sample(keys, rng.randrange(1, 4))}
                   for _ in range(rng.randrange(1, 4))]
            vector = lane.certified_rescue_vector(inv, shed)
            if vector:
                activated += 1
                permutations_checked += self.prove_final_private(inv, shed, vector)
        self.assertGreater(activated, 100)
        self.assertGreater(permutations_checked, 1000)


if __name__ == "__main__":
    unittest.main()
