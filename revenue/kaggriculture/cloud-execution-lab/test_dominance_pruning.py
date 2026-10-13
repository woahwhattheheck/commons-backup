# SPDX-License-Identifier: Apache-2.0
"""Correctness and countercase contracts for exact dominance pruning."""
import random
import unittest

from dominance_pruning import (
    DominanceNode,
    UnsafeDominanceState,
    dominates,
    prune_frontier,
)


def state(**changes):
    value = {
        "physical": {"farmer": [4, 4], "hands": [[5, 4]], "tiles": [[None]]},
        "market": {"inventory": {"WHEAT": 10000}, "rival": ()},
        "obligations": {"crop": None, "sale": None},
        "capacity": {"shed_capacity": 100, "reserved": 7},
        "care_bonus": {"pending": 0},
        "order_slots": {"used": 2, "limit": 10},
        "occupancy": {"reserved_tiles": [[2, 2]]},
        "cash": 1000,
        "inventory": {"WHEAT": 3},
        "slack": {"turns": 4},
        "safety": {"cash_reserve": 100, "capacity_headroom": 20},
    }
    value.update(changes)
    return value


def node(**changes):
    return DominanceNode.from_state(state(**changes))


class ExactDominanceTests(unittest.TestCase):
    def test_strict_cash_gain_dominates_same_identity(self):
        a = node(cash=1001); b = node(cash=1000)
        self.assertTrue(dominates(a, b)); self.assertFalse(dominates(b, a))
        self.assertEqual(prune_frontier([b, a]), [a])

    def test_equal_metrics_are_not_strict_dominance_but_hash_dedupe(self):
        a = node(); b = node()
        self.assertFalse(dominates(a, b))
        self.assertEqual(len(prune_frontier([a, b], mode="none")), 2)
        self.assertEqual(prune_frontier([a, b], mode="hash"), [a])
        self.assertEqual(prune_frontier([a, b]), [a])

    def test_incomparable_cash_vs_inventory_survive(self):
        a = node(cash=1001, inventory={"WHEAT": 2})
        b = node(cash=1000, inventory={"WHEAT": 3})
        self.assertFalse(dominates(a, b)); self.assertFalse(dominates(b, a))
        self.assertEqual(prune_frontier([a, b]), [a, b])

    def assert_identity_countercase(self, field, replacement):
        base = state(); changed = state(); changed[field] = replacement
        a = DominanceNode.from_state({**base, "cash": 2000})
        b = DominanceNode.from_state(changed)
        self.assertFalse(dominates(a, b), field)
        self.assertEqual(prune_frontier([b, a]), [b, a])

    def test_capacity_countercase(self):
        self.assert_identity_countercase("capacity", {"shed_capacity": 100, "reserved": 8})

    def test_care_bonus_countercase(self):
        self.assert_identity_countercase("care_bonus", {"pending": 1})

    def test_order_slot_countercase(self):
        self.assert_identity_countercase("order_slots", {"used": 3, "limit": 10})

    def test_occupancy_countercase(self):
        self.assert_identity_countercase("occupancy", {"reserved_tiles": [[2, 3]]})

    def test_physical_market_and_obligation_countercases(self):
        self.assert_identity_countercase("physical", {"farmer": [4, 5]})
        self.assert_identity_countercase("market", {"inventory": {"WHEAT": 9999}, "rival": ()})
        self.assert_identity_countercase("obligations", {"crop": {"step": 372}, "sale": None})

    def test_every_metric_dimension_is_monotone(self):
        richer = node(cash=2000, inventory={"WHEAT": 3}, slack={"turns": 4},
                      safety={"cash_reserve": 100, "capacity_headroom": 20})
        for changes in (
            {"inventory": {"WHEAT": 4}},
            {"slack": {"turns": 5}},
            {"safety": {"cash_reserve": 101, "capacity_headroom": 20}},
            {"safety": {"cash_reserve": 100, "capacity_headroom": 21}},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(dominates(richer, node(**changes)))

    def test_absent_metric_key_means_zero_not_unknown(self):
        richer = node(inventory={"WHEAT": 3, "MILK": 1})
        poorer = node(inventory={"WHEAT": 3})
        self.assertTrue(dominates(richer, poorer))
        self.assertFalse(dominates(poorer, richer))

    def test_missing_slack_or_safety_dimension_is_incomparable(self):
        full_safety = node(safety={"cash_reserve": 100, "capacity_headroom": 20})
        missing_safety = node(safety={"cash_reserve": 100})
        self.assertFalse(dominates(full_safety, missing_safety))
        self.assertFalse(dominates(missing_safety, full_safety))
        self.assertEqual(prune_frontier([missing_safety, full_safety]),
                         [missing_safety, full_safety])
        full_slack = node(slack={"turns": 4, "orders": 1})
        missing_slack = node(slack={"turns": 4})
        self.assertFalse(dominates(full_slack, missing_slack))
        self.assertFalse(dominates(missing_slack, full_slack))
        self.assertEqual(prune_frontier([missing_slack, full_slack]),
                         [missing_slack, full_slack])

    def test_protected_fallback_is_never_pruned(self):
        fallback = DominanceNode.from_state(state(cash=1000), protected=True)
        richer = node(cash=2000)
        self.assertEqual(prune_frontier([fallback, richer]), [fallback, richer])

    def test_protected_exact_duplicate_replaces_unprotected(self):
        ordinary = DominanceNode.from_state(state(), payload="ordinary")
        protected = DominanceNode.from_state(state(), payload="fallback", protected=True)
        self.assertEqual(prune_frontier([ordinary, protected], mode="hash"), [protected])

    def test_protected_exact_duplicates_all_survive(self):
        first = DominanceNode.from_state(state(), payload="deadline", protected=True)
        second = DominanceNode.from_state(state(), payload="canonical", protected=True)
        ordinary = DominanceNode.from_state(state(), payload="ordinary")
        for mode in ("hash", "dominance"):
            with self.subTest(mode=mode):
                kept = prune_frontier([ordinary, first, second], mode=mode)
                self.assertEqual([node.payload for node in kept], ["deadline", "canonical"])

    def test_hash_never_performs_pareto_pruning(self):
        poor = node(cash=1000); rich = node(cash=1001)
        self.assertEqual(prune_frontier([poor, rich], mode="hash"), [poor, rich])
        self.assertEqual(prune_frontier([poor, rich], mode="none"), [poor, rich])

    def test_missing_or_extra_identity_fields_fail_closed(self):
        missing = dict(state()); missing.pop("occupancy")
        extra = dict(state()); extra["weather"] = {"rain": False}
        for bad in (missing, extra):
            with self.subTest(keys=sorted(bad)):
                with self.assertRaises(UnsafeDominanceState): DominanceNode.from_state(bad)

    def test_unsupported_identity_value_fails_closed(self):
        bad = state(physical={"opaque": object()})
        with self.assertRaises(UnsafeDominanceState):
            prune_frontier([DominanceNode.from_state(bad)])

    def test_bool_and_int_identity_do_not_alias(self):
        a = node(physical={"flag": True})
        b = node(physical={"flag": 1}, cash=2000)
        self.assertFalse(dominates(b, a))
        self.assertEqual(prune_frontier([a, b]), [a, b])

    def test_generated_state_pairs_have_only_certified_removals(self):
        rng = random.Random(0x507)
        nodes = []
        for group in range(32):
            identity = state()["physical"] | {"group": group}
            for index in range(12):
                candidate = node(
                    physical=identity,
                    cash=1000 + rng.randrange(5),
                    inventory={"WHEAT": rng.randrange(4), "MILK": rng.randrange(3)},
                    slack={"turns": rng.randrange(4)},
                    safety={"cash_reserve": rng.randrange(4), "capacity_headroom": rng.randrange(4)},
                )
                nodes.append(candidate)
                if index % 6 == 0:
                    nodes.append(candidate)  # deterministic exact duplicate pressure
        kept = prune_frontier(nodes)
        self.assertLess(len(kept), len(nodes))
        for original in nodes:
            if any(original is survivor for survivor in kept):
                continue
            exact = any(original.identity_key() == survivor.identity_key()
                        and original.metric_key() == survivor.metric_key() for survivor in kept)
            dominated = any(dominates(other, original) for other in nodes if other is not original)
            self.assertTrue(exact or dominated)
        for survivor in kept:
            if survivor.protected:
                continue
            self.assertFalse(any(dominates(other, survivor) for other in nodes if other is not survivor))


if __name__ == "__main__":
    unittest.main()
