import copy
import hashlib
import unittest

from floor_capacity_relief import (
    PRICE_FLOOR,
    git_blob_sha,
    plan_floor_capacity_relief,
    project_eod_drop,
    scenario_pack,
)


class DropProjectionTests(unittest.TestCase):
    def test_eod_drop_is_prefix_preserving_and_discards_suffix(self):
        p = project_eod_drop({"WHEAT": 2}, [{"MILK": 2, "MELON": 3}], 5)
        self.assertEqual(p.retained_sequence, ("MILK", "MILK", "MELON"))
        self.assertEqual(p.discarded_sequence, ("MELON", "MELON"))
        self.assertEqual(p.shed_after, {"WHEAT": 2, "MILK": 2, "MELON": 1})

    def test_multiple_actor_inventories_keep_list_order(self):
        p = project_eod_drop({}, [{"MILK": 2}, {"WOOL": 2}], 3)
        self.assertEqual(p.retained_sequence, ("MILK", "MILK", "WOOL"))
        self.assertEqual(p.discarded_sequence, ("WOOL",))

    def test_projection_is_pure(self):
        shed = {"MILK": 1}
        inv = [{"MELON": 2}]
        before = copy.deepcopy((shed, inv))
        project_eod_drop(shed, inv, 2)
        self.assertEqual((shed, inv), before)

    def test_rejects_impossible_preoverflow(self):
        with self.assertRaises(ValueError):
            project_eod_drop({"MILK": 3}, [], 2)


class FloorDrainTests(unittest.TestCase):
    def kwargs(self):
        return dict(
            shed={"MILK": 100},
            inventories=[{"MELON": 2}],
            capacity=100,
            floor_quotes={"MILK": 1},
            shed_shadow_values={"MILK": 4},
            incoming_retention_values={"MELON": 250},
            protected_min={"MILK": 98},
            available_market_rows=1,
        )

    def test_positive_floor_relief_preserves_discarded_cargo(self):
        p = plan_floor_capacity_relief(**self.kwargs())
        self.assertEqual(p.orders, (("SELL", "MILK", 2),))
        self.assertEqual(p.preserved_sequence, ("MELON", "MELON"))
        self.assertEqual(p.projected_discarded_sequence, ())
        self.assertEqual(p.floor_cash, 2)
        self.assertEqual(p.market_inventory_delta, 0)
        self.assertGreater(p.declared_value_gain, 0)

    def test_above_floor_quote_is_out_of_lane(self):
        k = self.kwargs(); k["floor_quotes"] = {"MILK": 2}
        p = plan_floor_capacity_relief(**k)
        self.assertFalse(p.orders)
        self.assertEqual(p.reason, "no_unprotected_floor_cargo")

    def test_reserve_guard_blocks_drain(self):
        k = self.kwargs(); k["protected_min"] = {"MILK": 100}
        p = plan_floor_capacity_relief(**k)
        self.assertFalse(p.orders)

    def test_nonpositive_declared_gain_blocks_drain(self):
        k = self.kwargs(); k["incoming_retention_values"] = {"MELON": 2}
        p = plan_floor_capacity_relief(**k)
        self.assertFalse(p.orders)
        self.assertEqual(p.reason, "nonpositive_declared_value")

    def test_preservation_is_prefix_not_sparse(self):
        k = self.kwargs()
        k.update(
            shed={"MILK": 100},
            inventories=[{"WOOL": 1, "MELON": 1}],
            protected_min={"MILK": 98},
            shed_shadow_values={"MILK": 4},
            incoming_retention_values={"WOOL": 0, "MELON": 250},
        )
        p = plan_floor_capacity_relief(**k)
        # Two slots are required to reach MELON; the first slot alone would keep
        # WOOL. The combined prefix is still strongly positive.
        self.assertEqual(p.orders, (("SELL", "MILK", 2),))
        self.assertEqual(p.preserved_sequence, ("WOOL", "MELON"))

    def test_later_high_value_cannot_be_preserved_without_prefix_budget(self):
        k = self.kwargs()
        k.update(
            shed={"MILK": 100},
            inventories=[{"WOOL": 1, "MELON": 1}],
            protected_min={"MILK": 99},
            shed_shadow_values={"MILK": 4},
            incoming_retention_values={"WOOL": 0, "MELON": 250},
        )
        p = plan_floor_capacity_relief(**k)
        self.assertFalse(p.orders)
        self.assertEqual(p.projected_discarded_sequence, ("WOOL", "MELON"))

    def test_no_overflow_means_no_sale(self):
        k = self.kwargs(); k["shed"] = {"MILK": 98}
        p = plan_floor_capacity_relief(**k)
        self.assertFalse(p.orders)
        self.assertEqual(p.reason, "no_projected_overflow")

    def test_one_market_row_can_drain_multiple_units_of_one_item(self):
        p = plan_floor_capacity_relief(**self.kwargs())
        self.assertEqual(len(p.orders), 1)
        self.assertEqual(p.orders[0][2], 2)

    def test_zero_market_rows_blocks_all_drain(self):
        k = self.kwargs(); k["available_market_rows"] = 0
        p = plan_floor_capacity_relief(**k)
        self.assertFalse(p.orders)

    def test_market_row_budget_limits_distinct_items(self):
        k = self.kwargs()
        k.update(
            shed={"MILK": 50, "WOOL": 50},
            inventories=[{"MELON": 2}],
            floor_quotes={"MILK": 1, "WOOL": 1},
            shed_shadow_values={"MILK": 2, "WOOL": 3},
            protected_min={"MILK": 49, "WOOL": 49},
            available_market_rows=1,
        )
        p = plan_floor_capacity_relief(**k)
        self.assertEqual(p.orders, (("SELL", "MILK", 1),))
        self.assertEqual(len(p.preserved_sequence), 1)

    def test_scenario_pack_has_positive_and_three_negative_controls(self):
        pack = scenario_pack()
        self.assertEqual(pack["positive_witness"]["reason"], "positive_floor_capacity_relief")
        reasons = {v["reason"] for v in pack["negative_controls"].values()}
        self.assertEqual(reasons, {
            "no_projected_overflow",
            "no_unprotected_floor_cargo",
            "nonpositive_declared_value",
        })

    def test_git_blob_sha_matches_git_object_rule(self):
        data = b"test\n"
        expected = hashlib.sha1(b"blob 5\0test\n").hexdigest()
        self.assertEqual(git_blob_sha(data), expected)

    def test_price_floor_constant_is_one(self):
        self.assertEqual(PRICE_FLOOR, 1)


if __name__ == "__main__":
    unittest.main()
