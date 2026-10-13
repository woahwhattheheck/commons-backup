# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

import candidate as c


def inventory(level=10000):
    return {item: level for item in c.PRODUCTS}


def obs(step, levels=None, shops=(), player=0):
    return {
        "step": step,
        "player": player,
        "market": {"inventory": dict(levels or inventory())},
        "town": {"unlocked_shops": list(shops)},
    }


NO_TOWN = {"townShopSellInterval": 9999, "townCenterSellInterval": 9999}


class PublicSupplyGateTests(unittest.TestCase):
    def test_clean_history_requires_full_eight_transition_warmup(self):
        gate = c.PublicSupplyGate(lookback=8)
        before = inventory()
        self.assertFalse(gate.begin(obs(647, before)))
        gate.finish(obs(647, before), {"market": [["SELL", "MILK", 5]]}, NO_TOWN)
        after = inventory()
        after["MILK"] += 5
        self.assertFalse(gate.begin(obs(648, after)))
        self.assertEqual(gate.last_evidence[0]["MILK"], 0)
        gate.finish(obs(648, after), {"market": []}, NO_TOWN)
        for step in range(649, 655):
            self.assertFalse(gate.begin(obs(step, after)))
            gate.finish(obs(step, after), {"market": []}, NO_TOWN)
        self.assertTrue(gate.begin(obs(655, after)))

    def test_positive_residual_proves_rival_net_supply_and_guards(self):
        gate = c.PublicSupplyGate(lookback=1)
        before = inventory()
        gate.begin(obs(647, before))
        gate.finish(obs(647, before), {"market": [["SELL", "MILK", 5]]}, NO_TOWN)
        after = inventory()
        after["MILK"] += 9
        self.assertFalse(gate.begin(obs(648, after)))
        self.assertEqual(gate.last_evidence[0]["MILK"], 4)

    def test_pressure_expires_after_eight_clean_transitions(self):
        gate = c.PublicSupplyGate(lookback=8)
        level = inventory()
        gate.begin(obs(647, level))
        gate.finish(obs(647, level), {"market": []}, NO_TOWN)
        pressured = inventory()
        pressured["WOOL"] += 1
        self.assertFalse(gate.begin(obs(648, pressured)))
        gate.finish(obs(648, pressured), {"market": []}, NO_TOWN)
        for step in range(649, 656):
            self.assertFalse(gate.begin(obs(step, pressured)))
            gate.finish(obs(step, pressured), {"market": []}, NO_TOWN)
        self.assertTrue(gate.begin(obs(656, pressured)))

    def test_gap_requires_full_fresh_window_before_reenable(self):
        gate = c.PublicSupplyGate(lookback=8)
        state = inventory()
        gate.begin(obs(640, state))
        gate.finish(obs(640, state), {"market": []}, NO_TOWN)
        self.assertFalse(gate.begin(obs(650, state)))
        gate.finish(obs(650, state), {"market": []}, NO_TOWN)
        for step in range(651, 658):
            self.assertFalse(gate.begin(obs(step, state)))
            gate.finish(obs(step, state), {"market": []}, NO_TOWN)
        self.assertTrue(gate.begin(obs(658, state)))

    def test_rewind_fails_closed(self):
        gate = c.PublicSupplyGate(lookback=1)
        state = inventory()
        gate.begin(obs(650, state))
        gate.finish(obs(650, state), {"market": []}, NO_TOWN)
        self.assertFalse(gate.begin(obs(649, state)))

    def test_duplicate_single_product_shops_and_center_consumption(self):
        got = c._town_consumption(
            obs(648, inventory(), shops=("YARN_STORE", "YARN_STORE")), {}
        )
        self.assertEqual(got["WOOL"], 5)
        self.assertEqual(got["MILK"], 1)
        self.assertEqual(got["FERTILIZER"], 0)

    def test_requested_sell_is_safe_upper_bound_even_if_unfillable(self):
        own = c._own_sell_upper_bound(
            {"market": [["SELL", "MILK", 99], ["SELL", "MILK", 2]]}
        )
        self.assertEqual(own["MILK"], 101)
        before = inventory()
        after = inventory()
        after["MILK"] += 7
        lower = c._rival_supply_lower_bound(
            before, after, own, {item: 0 for item in c.PRODUCTS}
        )
        self.assertLess(lower["MILK"], 0)

    def test_unknown_shop_fails_closed(self):
        gate = c.PublicSupplyGate(lookback=1)
        state = inventory()
        gate.begin(obs(647, state))
        gate.finish(obs(647, state, shops=("UNKNOWN",)), {"market": []}, {})
        self.assertFalse(gate.begin(obs(648, state)))

    def test_public_inventory_requires_exact_nonbool_integer(self):
        for bad_value in ("10000", 10000.75, True):
            with self.subTest(value=bad_value):
                gate = c.PublicSupplyGate(lookback=1)
                bad = obs(1, inventory())
                bad["market"]["inventory"]["MILK"] = bad_value
                self.assertFalse(gate.begin(bad))

    def test_missing_public_inventory_fails_closed(self):
        gate = c.PublicSupplyGate(lookback=1)
        bad = obs(1, inventory())
        del bad["market"]["inventory"]["MILK"]
        self.assertFalse(gate.begin(bad))

    def test_step_and_player_require_exact_nonbool_integer(self):
        cases = (
            ("step", "1"), ("step", 1.0), ("step", True),
            ("player", "0"), ("player", 0.0), ("player", False),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value):
                gate = c.PublicSupplyGate(lookback=1)
                bad = obs(1, inventory())
                bad[key] = value
                self.assertFalse(gate.begin(bad))

    def test_sell_quantity_requires_exact_nonbool_integer(self):
        for value in ("3", 3.0, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    c._own_sell_upper_bound({"market": [["SELL", "MILK", value]]})

    def test_town_intervals_require_exact_positive_integer(self):
        observation = obs(648, inventory())
        for value in ("4", 4.0, True, 0, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    c._town_consumption(
                        observation, {"townShopSellInterval": value}
                    )


if __name__ == "__main__":
    unittest.main()
