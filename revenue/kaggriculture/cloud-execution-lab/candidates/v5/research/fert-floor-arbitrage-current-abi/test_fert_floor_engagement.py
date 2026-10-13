# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import unittest

import fert_floor_engagement as eng
from fert_floor_current import ITEM, FERT_PRICE1_PREBUY_INVENTORY

SOURCE = "a" * 40
ENGINE = "official-engine:3c202c7e"


def observation(
    step, *, price=2, inventory=10489, shed=0, actor=(0, 0), cover=-1, player=0
):
    tiles = [[None for _ in range(3)] for _ in range(3)]
    tiles[1][1] = {
        "kind": "PLANT",
        "crop": "MELON",
        "fertilized_until_day": cover,
        "dead": False,
    }
    return {
        "player": player,
        "step": step,
        "farms": [
            {"farmer": [1, 1], "hands": [[2, 2]], "tiles": tiles, "money": 100},
            {"farmer": [0, 0], "hands": [], "tiles": [[None]], "money": 0},
        ],
        "private": {
            "inventories": [{ITEM: actor[0]}, {ITEM: actor[1]}],
            "shed": {ITEM: shed},
        },
        "market": {
            "inventory": {ITEM: inventory},
            "prices": {ITEM: price},
        },
    }


def action(*, farmer=("PASS",), hand=("PASS",), market=()):
    return {
        "farmer": list(farmer),
        "hands": [list(hand)],
        "market": [list(row) for row in market],
    }


def report(rows):
    return {
        "schema": eng.TAPE_SCHEMA,
        "source_sha": SOURCE,
        "engine_id": ENGINE,
        "rows": [
            {"observation": obs, "returned_action": returned}
            for obs, returned in rows
        ],
    }


class FertFloorNaturalEngagementTests(unittest.TestCase):
    def full_chain(self, *, price=2, inventory=10489):
        day = 92 // 24
        return [
            (
                observation(90, price=price, inventory=inventory),
                action(market=(("BUY_PRODUCT", ITEM, 1),)),
            ),
            (
                observation(91, price=price, inventory=inventory - 1, shed=1),
                action(farmer=("PICKUP", ITEM)),
            ),
            (
                observation(92, price=price, inventory=inventory - 1, shed=0, actor=(1, 0)),
                action(farmer=("FERTILIZE",)),
            ),
            (
                observation(
                    93,
                    price=price,
                    inventory=inventory - 1,
                    shed=0,
                    actor=(0, 0),
                    cover=day + 2,
                ),
                action(),
            ),
        ]

    def test_complete_real_custody_chain_is_engaged(self):
        receipt = eng.reduce_tape(report(self.full_chain()))
        self.assertTrue(receipt["engaged"])
        self.assertEqual(receipt["completed_cycle_count"], 1)
        self.assertEqual(receipt["floor_buy_custody_confirmed"], 1)
        self.assertEqual(receipt["pickup_custody_confirmed"], 1)
        self.assertEqual(receipt["fertilize_effect_confirmed"], 1)
        cycle = receipt["cycles"][0]
        self.assertEqual(cycle["buy_step"], 90)
        self.assertEqual(cycle["buy_price_ceiling"], 2)
        self.assertEqual(cycle["observed_public_price"], 2)
        self.assertEqual(cycle["source_postbuy_price"], 2)
        self.assertEqual(cycle["fert_market_inventory_before"], 10489)
        self.assertEqual(cycle["actor_index"], 0)

    def test_true_floor_price_one_chain_is_engaged(self):
        rows = self.full_chain(price=1, inventory=FERT_PRICE1_PREBUY_INVENTORY)
        receipt = eng.reduce_tape(report(rows))
        self.assertTrue(receipt["engaged"])
        cycle = receipt["cycles"][0]
        self.assertEqual(cycle["observed_public_price"], 1)
        self.assertEqual(cycle["source_postbuy_price"], 1)

    def test_buy_outside_source_boundary_does_not_start(self):
        rows = self.full_chain(price=2, inventory=10488)
        receipt = eng.reduce_tape(report(rows))
        self.assertFalse(receipt["engaged"])
        self.assertEqual(receipt["floor_buy_returned"], 0)

    def test_public_quote_inventory_drift_does_not_start(self):
        rows = self.full_chain(price=1, inventory=10489)
        receipt = eng.reduce_tape(report(rows))
        self.assertFalse(receipt["engaged"])
        self.assertEqual(receipt["floor_buy_returned"], 0)

    def test_returned_buy_without_shed_custody_is_not_engagement(self):
        rows = self.full_chain()
        rows[1] = (observation(91, inventory=10488, shed=0), action())
        receipt = eng.reduce_tape(report(rows))
        self.assertFalse(receipt["engaged"])
        self.assertEqual(receipt["aborted_cycles"], 1)

    def test_pickup_without_actor_custody_aborts_chain(self):
        rows = self.full_chain()
        rows[2] = (observation(92, inventory=10488, shed=1, actor=(0, 0)), action())
        receipt = eng.reduce_tape(report(rows))
        self.assertFalse(receipt["engaged"])
        self.assertEqual(receipt["pickup_returned"], 1)
        self.assertEqual(receipt["pickup_custody_confirmed"], 0)

    def test_fertilize_without_engine_effect_aborts_chain(self):
        rows = self.full_chain()
        rows[3] = (
            observation(93, inventory=10488, shed=0, actor=(1, 0), cover=-1),
            action(),
        )
        receipt = eng.reduce_tape(report(rows))
        self.assertFalse(receipt["engaged"])
        self.assertEqual(receipt["fertilize_returned"], 1)
        self.assertEqual(receipt["fertilize_effect_confirmed"], 0)

    def test_unrelated_pickup_cannot_start_floor_chain(self):
        rows = [
            (observation(90, shed=1), action(farmer=("PICKUP", ITEM))),
            (observation(91, inventory=10488, shed=0, actor=(1, 0)), action()),
        ]
        receipt = eng.reduce_tape(report(rows))
        self.assertFalse(receipt["engaged"])
        self.assertEqual(receipt["pickup_returned"], 0)

    def test_second_fertilizer_market_action_aborts_active_chain(self):
        rows = [
            (observation(90), action(market=(("BUY_PRODUCT", ITEM, 1),))),
            (
                observation(91, inventory=10488, shed=1),
                action(market=(("SELL", ITEM, 1),)),
            ),
            (observation(92, inventory=10489, shed=0), action()),
        ]
        receipt = eng.reduce_tape(report(rows))
        self.assertFalse(receipt["engaged"])
        self.assertEqual(receipt["aborted_cycles"], 1)

    def test_step_gap_is_fail_closed(self):
        rows = self.full_chain()
        rows.pop(1)
        with self.assertRaisesRegex(eng.EngagementError, "strictly contiguous"):
            eng.reduce_tape(report(rows))

    def test_player_change_is_fail_closed(self):
        rows = self.full_chain()
        other = observation(91, player=1, inventory=10488, shed=1)
        other["private"]["inventories"] = [{ITEM: 0}]
        rows[1] = (other, {"farmer": ["PASS"], "hands": [], "market": []})
        with self.assertRaisesRegex(eng.EngagementError, "player changed"):
            eng.reduce_tape(report(rows))

    def test_fertilize_by_different_actor_does_not_complete(self):
        rows = [
            (observation(90), action(market=(("BUY_PRODUCT", ITEM, 1),))),
            (
                observation(91, inventory=10488, shed=1),
                action(hand=("PICKUP", ITEM)),
            ),
            (
                observation(92, inventory=10488, shed=0, actor=(0, 1)),
                action(farmer=("FERTILIZE",)),
            ),
            (
                observation(93, inventory=10488, shed=0, actor=(0, 1), cover=5),
                action(),
            ),
        ]
        receipt = eng.reduce_tape(report(rows))
        self.assertFalse(receipt["engaged"])
        self.assertEqual(receipt["pickup_custody_confirmed"], 1)
        self.assertEqual(receipt["fertilize_returned"], 0)

    def test_malformed_inventory_bool_rejected(self):
        bad = observation(90)
        bad["private"]["inventories"][0][ITEM] = True
        with self.assertRaisesRegex(eng.EngagementError, "plain int"):
            eng.reduce_tape(report([(bad, action())]))

    def test_huge_price_does_not_overflow(self):
        bad = observation(90, price=10**1000)
        receipt = eng.reduce_tape(
            report([(bad, action(market=(("BUY_PRODUCT", ITEM, 1),)))])
        )
        self.assertFalse(receipt["engaged"])

    def test_source_sha_and_engine_are_bound(self):
        receipt = eng.reduce_tape(report(self.full_chain()))
        self.assertEqual(receipt["source_sha"], SOURCE)
        self.assertEqual(receipt["engine_id"], ENGINE)
        self.assertRegex(receipt["rows_sha256"], r"^[0-9a-f]{64}$")

    def test_strict_json_rejects_duplicate_and_nan(self):
        with self.assertRaisesRegex(eng.EngagementError, "duplicate"):
            eng.loads_strict('{"a":1,"a":2}')
        with self.assertRaisesRegex(eng.EngagementError, "non-finite"):
            eng.loads_strict('{"a":NaN}')

    def test_inputs_are_not_mutated(self):
        payload = report(self.full_chain())
        before = deepcopy(payload)
        eng.reduce_tape(payload)
        self.assertEqual(payload, before)

    def test_exact_top_level_and_row_shapes_required(self):
        payload = report(self.full_chain())
        payload["extra"] = True
        with self.assertRaisesRegex(eng.EngagementError, "exact"):
            eng.reduce_tape(payload)
        payload = report(self.full_chain())
        payload["rows"][0]["extra"] = True
        with self.assertRaisesRegex(eng.EngagementError, "exact"):
            eng.reduce_tape(payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
