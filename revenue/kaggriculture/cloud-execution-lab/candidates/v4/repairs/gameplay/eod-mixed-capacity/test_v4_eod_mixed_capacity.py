# SPDX-License-Identifier: Apache-2.0
"""Mixed-product extension to the existing V4 EOD capacity-rescue key.

Run from the materialized package with standard-library unittest:
    python -B -m unittest -v checks.test_v4_eod_mixed_capacity

The independent drop/SELL oracle below is copied from pinned official engine
Git blob 3c202c7ee921da239356789e266b694635103fc4. It is not imported from the
candidate. These are mechanism/transition contracts, not a paired game gate.
"""
from __future__ import annotations

import copy
import itertools
import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_eod_capacity_rescue as lane
import r04_full_router as r04

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10}


# Literal independent official-engine functions; preserve their logic.
def _drop_inventories_to_shed(private, capacity):
    """Drop every per-farmer inventory into the shed up to `capacity`; overflow is discarded.
    Seeds are tracked separately in private["seeds"] and don't pass through the shed."""
    shed = private["shed"]
    for inv in private["inventories"]:
        for item, n in list(inv.items()):
            if n <= 0:
                del inv[item]
                continue
            current = sum(v for k, v in shed.items())
            room = max(0, capacity - current)
            take = min(n, room)
            if take > 0:
                shed[item] = shed.get(item, 0) + take
            del inv[item]


def _commit_unit(op, item, price, farm, private, market, shed_capacity=100):
    if op == "SELL":
        if private["shed"].get(item, 0) <= 0:
            return False
        private["shed"][item] -= 1
        farm["money"] += price
        # Sales at $1 do not increase market supply.
        if price > 1:
            market["inventory"][item] += 1
        return True
    if op == "BUY_PRODUCT":
        if farm["money"] < price:
            return False
        # Bought goods land in the shed, which obeys shedCapacity like every
        # other deposit path (pickup, shed-drop, end-of-day drop).
        if sum(private["shed"].values()) >= shed_capacity:
            return False
        farm["money"] -= price
        private["shed"][item] = private["shed"].get(item, 0) + 1
        market["inventory"][item] -= 1
        return True
    if op == "BUY_SEED":
        if farm["money"] < price:
            return False
        farm["money"] -= price
        private["seeds"][item] = private["seeds"].get(item, 0) + 1
        return True
    if op == "BUY_ANIMAL":
        if farm["money"] < price:
            return False
        if sum(private["shed"].values()) >= shed_capacity:
            return False
        farm["money"] -= price
        private["shed"][item] = private["shed"].get(item, 0) + 1
        return True
    return False


def world(shed, inventories, market=None, *, step=119):
    hands = [[5, 4] for _ in inventories[1:]]
    farm = {"farmer": [4, 4], "hands": hands}
    obs = {"step": step, "player": 0, "farms": [farm, copy.deepcopy(farm)],
           "private": {"shed": copy.deepcopy(shed),
                       "inventories": copy.deepcopy(inventories), "seeds": {"WHEAT": 2}},
           "market": {"prices": {p: 10 for p in r04.PRODUCTS}}}
    action = {"farmer": ["PASS"], "hands": [["PASS"] for _ in hands],
              "market": copy.deepcopy(market) if market is not None else []}
    return obs, action


def permutations_of_inventories(inventories):
    choices = [list(itertools.permutations(inv.items())) for inv in inventories]
    for choice in itertools.product(*choices):
        yield [dict(items) for items in choice]


def oracle_discarded(inventories, room):
    # Total capacity is always 100; animal ballast cannot be sold by this lane.
    before = {p: 0 for p in r04.PRODUCTS}
    before["COW"] = 100 - room
    private = {"shed": dict(before), "inventories": copy.deepcopy(inventories)}
    total = {p: sum(inv.get(p, 0) for inv in inventories) for p in r04.PRODUCTS}
    _drop_inventories_to_shed(private, 100)
    return {p: total[p] - (private["shed"][p] - before[p])
            for p in r04.PRODUCTS if total[p] != private["shed"][p] - before[p]}


class MixedEodCapacity(unittest.TestCase):
    def setUp(self):
        lane.telemetry.clear()

    def apply(self, obs, parent, configuration=None):
        before = copy.deepcopy((obs, parent))
        result = lane.apply_eod_capacity_rescue(
            parent, obs, dict(CONFIG) if configuration is None else configuration, enabled=True)
        self.assertEqual((obs, parent), before)
        return result

    def prove_transition(self, obs, rows):
        base = copy.deepcopy(obs["private"])
        candidate = copy.deepcopy(base)
        _drop_inventories_to_shed(base, 100)
        farm = {"money": 1000}
        market = {"inventory": {p: 10000 for p in r04.PRODUCTS}}
        for op, product, quantity in rows:
            for _ in range(quantity):
                self.assertTrue(_commit_unit(op, product, obs["market"]["prices"][product],
                                             farm, candidate, market))
        _drop_inventories_to_shed(candidate, 100)
        self.assertEqual(candidate, base)
        self.assertGreater(farm["money"], 1000)
        return market

    def test_full_shed_mixed_actor_cargo(self):
        obs, parent = world({"WHEAT": 50, "CARROT": 50},
                            [{"WHEAT": 2, "CARROT": 1}, {"CARROT": 2}])
        out = self.apply(obs, parent)
        self.assertEqual(out["market"], [["SELL", "CARROT", 3], ["SELL", "WHEAT", 2]])
        self.prove_transition(obs, out["market"])
        self.assertEqual(lane.telemetry["rescued_units"], 5)
        self.assertEqual(lane.telemetry["mixed_product_activations"], 1)

    def test_actor_boundary_discards_only_later_product(self):
        obs, parent = world({"WHEAT": 50, "CARROT": 49}, [{"WHEAT": 1}, {"CARROT": 2}])
        out = self.apply(obs, parent)
        self.assertEqual(out["market"], [["SELL", "CARROT", 2]])
        self.prove_transition(obs, out["market"])

    def test_partial_single_product_actor_then_mixed_tail(self):
        obs, parent = world({"WHEAT": 50, "CARROT": 49},
                            [{"WHEAT": 3}, {"CARROT": 2, "WHEAT": 1}])
        out = self.apply(obs, parent)
        self.assertEqual(out["market"], [["SELL", "CARROT", 2], ["SELL", "WHEAT", 3]])
        self.prove_transition(obs, out["market"])

    def test_fully_admitted_mixed_actor_needs_no_shed_coverage(self):
        obs, parent = world({"CARROT": 97},
                            [{"WHEAT": 1, "EGG": 2}, {"CARROT": 3}])
        out = self.apply(obs, parent)
        self.assertEqual(out["market"], [["SELL", "CARROT", 3]])
        self.prove_transition(obs, out["market"])

    def test_partial_mixed_actor_is_order_ambiguous(self):
        for inv in permutations_of_inventories([{"WHEAT": 1, "CARROT": 2}, {}]):
            obs, parent = world({"WHEAT": 50, "CARROT": 49}, inv)
            self.assertIs(self.apply(obs, parent), parent)
        self.assertNotEqual(oracle_discarded([{"WHEAT": 1, "CARROT": 2}], 1),
                            oracle_discarded([{"CARROT": 2, "WHEAT": 1}], 1))

    def test_sorted_json_roundtrip_cannot_change_result(self):
        obs, parent = world({"WHEAT": 50, "CARROT": 49},
                            [{"WHEAT": 1}, {"WHEAT": 3, "CARROT": 2}])
        sorted_obs = json.loads(json.dumps(obs, sort_keys=True))
        self.assertEqual(self.apply(obs, parent), self.apply(sorted_obs, parent))

    def test_inventory_list_order_is_not_sorted_or_collapsed(self):
        shed = {"WHEAT": 50, "CARROT": 48}
        first, parent = world(shed, [{"WHEAT": 2}, {"CARROT": 3}])
        second, other = world(shed, [{"CARROT": 3}, {"WHEAT": 2}])
        a, b = self.apply(first, parent), self.apply(second, other)
        self.assertEqual(a["market"], [["SELL", "CARROT", 3]])
        self.assertEqual(b["market"], [["SELL", "CARROT", 1], ["SELL", "WHEAT", 2]])
        self.prove_transition(first, a["market"])
        self.prove_transition(second, b["market"])

    def test_entire_vector_must_have_preexisting_shed_stock(self):
        obs, parent = world({"WHEAT": 100}, [{"WHEAT": 2}, {"CARROT": 1}])
        self.assertIs(self.apply(obs, parent), parent)
        self.assertEqual(lane.telemetry["activations"], 0)

    def test_no_partial_vector_when_second_product_lacks_stock(self):
        obs, parent = world({"CARROT": 100}, [{"CARROT": 2}, {"WHEAT": 1}])
        self.assertIs(self.apply(obs, parent), parent)
        self.assertEqual(lane.telemetry["rescued_units"], 0)

    def test_whole_vector_must_fit_executable_raw_prefix(self):
        for count in (8, 9, 10):
            obs, parent = world({"WHEAT": 50, "CARROT": 50},
                                [{"WHEAT": 2}, {"CARROT": 3}], [[] for _ in range(count)])
            out = self.apply(obs, parent)
            if count == 8:
                self.assertEqual(len(out["market"]), 10)
                self.assertEqual(out["market"][:count], parent["market"])
                self.prove_transition(obs, out["market"][count:])
            else:
                self.assertIs(out, parent)

    def test_each_product_price_is_strict_before_any_edit(self):
        for product in ("CARROT", "WHEAT"):
            for bad in (None, True, 10.0, "10", -1, 0, [], {}):
                obs, parent = world({"WHEAT": 50, "CARROT": 50},
                                    [{"WHEAT": 2}, {"CARROT": 3}])
                obs["market"]["prices"][product] = bad
                self.assertIs(self.apply(obs, parent), parent)
                self.assertEqual(lane.telemetry["activations"], 0)

    def test_floor_prices_preserve_private_state_without_public_supply(self):
        obs, parent = world({"WHEAT": 50, "CARROT": 50},
                            [{"WHEAT": 2}, {"CARROT": 3}])
        obs["market"]["prices"].update({"WHEAT": 1, "CARROT": 1})
        out = self.apply(obs, parent)
        market = self.prove_transition(obs, out["market"])
        self.assertEqual(set(market["inventory"].values()), {10000})
        self.assertEqual(lane.telemetry["floor_price_units"], 5)
        self.assertEqual(lane.telemetry["quoted_cash"], 5)

    def test_malformed_or_animal_cargo_even_in_later_actor_fails_closed(self):
        for bad in ({"WHEAT": True}, {"WHEAT": 1.0}, {"WHEAT": "1"},
                    {"WHEAT": -1}, {"COW": 1}, {"BOGUS": 1}, {1: 1}, [], None):
            obs, parent = world({"WHEAT": 50, "CARROT": 50}, [{"CARROT": 2}, bad])
            self.assertIs(self.apply(obs, parent), parent)

    def test_zeros_and_empty_actors_do_not_create_rescue_rows(self):
        obs, parent = world({"WHEAT": 50, "CARROT": 49},
                            [{"WHEAT": 1, "COW": 0}, {}, {"CARROT": 2, "WHEAT": 0}])
        out = self.apply(obs, parent)
        self.assertEqual(out["market"], [["SELL", "CARROT", 2]])
        self.prove_transition(obs, out["market"])

    def test_animal_shed_occupancy_counts_toward_total(self):
        obs, parent = world({"WHEAT": 3, "CARROT": 3, "COW": 94},
                            [{"WHEAT": 2}, {"CARROT": 3}])
        out = self.apply(obs, parent)
        self.prove_transition(obs, out["market"])
        self.assertEqual(out["market"], [["SELL", "CARROT", 3], ["SELL", "WHEAT", 2]])

    def test_disabled_and_inherited_timing_guards_preserve_identity(self):
        obs, parent = world({"WHEAT": 50, "CARROT": 50}, [{"WHEAT": 2}, {"CARROT": 3}])
        self.assertIs(lane.apply_eod_capacity_rescue(parent, obs, CONFIG), parent)
        for step in (118, 696, 718, 719, True, "119"):
            bad = copy.deepcopy(obs)
            bad["step"] = step
            self.assertIs(self.apply(bad, parent), parent)
        for key, value in (("episodeSteps", True), ("shedCapacity", 99),
                           ("maxMarketOrdersPerTurn", 9), ("townShopSellInterval", 1)):
            cfg = dict(CONFIG, **{key: value})
            self.assertIs(self.apply(obs, parent, cfg), parent)

    def test_inherited_unit_market_and_actor_barriers(self):
        obs, parent = world({"WHEAT": 50, "CARROT": 50}, [{"WHEAT": 2}, {"CARROT": 3}])
        for row in (["HARVEST"], ["PICKUP", "WHEAT", 1], ["DROP"], ["FEED"],
                    ["COLLECT_FERTILIZER"], [[]], [{}]):
            bad = copy.deepcopy(parent)
            bad["farmer"] = row
            self.assertIs(self.apply(obs, bad), bad)
        for row in (["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1],
                    ["BUY_ANIMAL", "COW", 1], ["BOGUS"], [{}]):
            bad = copy.deepcopy(parent)
            bad["market"] = [row]
            self.assertIs(self.apply(obs, bad), bad)
        bad = copy.deepcopy(parent)
        bad["hands"] = []
        self.assertIs(self.apply(obs, bad), bad)

    def test_single_product_contract_is_preserved(self):
        for product in r04.PRODUCTS:
            for total, q0, q1 in itertools.product(range(94, 101), range(5), range(5)):
                obs, parent = world({product: total}, [{product: q0}, {product: q1}])
                out = self.apply(obs, parent)
                loss = max(0, total + q0 + q1 - 100)
                if loss:
                    self.assertEqual(out["market"], [["SELL", product, loss]])
                    self.prove_transition(obs, out["market"])
                else:
                    self.assertIs(out, parent)

    def test_two_actor_exhaustive_all_key_orders(self):
        checked = 0
        for quantities in itertools.product(range(4), repeat=4):
            inventories = [{"WHEAT": quantities[0], "CARROT": quantities[1]},
                           {"WHEAT": quantities[2], "CARROT": quantities[3]}]
            for room in range(sum(quantities) + 2):
                predicted = lane._discarded_products(inventories, room, r04.PRODUCTS)
                actual_vectors = set()
                for permuted in permutations_of_inventories(inventories):
                    actual = oracle_discarded(permuted, room)
                    actual_vectors.add(tuple(sorted(actual.items())))
                    if predicted is not None:
                        self.assertEqual(predicted, actual)
                    checked += 1
                if predicted is None:
                    self.assertGreater(len(actual_vectors), 1)
                else:
                    self.assertEqual(len(actual_vectors), 1)
        self.assertEqual(checked, 8192)

    def test_randomized_nine_product_conservation(self):
        rng = random.Random(12612)
        activated = 0
        for _ in range(400):
            shed = {p: 7 for p in r04.PRODUCTS}
            shed["COW"] = rng.randrange(33, 38)
            inventories = []
            for _actor in range(rng.randrange(1, 5)):
                keys = rng.sample(list(r04.PRODUCTS), rng.randrange(1, 4))
                inventories.append({p: rng.randrange(1, 4) for p in keys})
            obs, parent = world(shed, inventories)
            out = self.apply(obs, parent)
            if out is not parent:
                activated += 1
                self.prove_transition(obs, out["market"])
                reordered = copy.deepcopy(obs)
                reordered["private"]["inventories"] = [dict(reversed(list(inv.items())))
                                                        for inv in inventories]
                self.assertEqual(self.apply(reordered, parent), out)
        self.assertGreater(activated, 100)


if __name__ == "__main__":
    unittest.main()
