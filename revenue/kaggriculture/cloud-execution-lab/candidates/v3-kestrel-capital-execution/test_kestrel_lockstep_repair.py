"""Exact blockers and positive boundary witnesses for the KESTREL successor."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
for source in (HERE, LAB):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

import mechanics as m
from kestrel_early_capital import _post_unit_state as predecessor_post_unit_state
from lockstep_early_capital import (
    _atomic_post_unit_snapshot,
    _rival_lockstep_certificate,
    order_early_capital,
)

EVALUATOR = LAB / "reference/evaluator/evaluate.py"
LOADER = LAB / "reference/evaluator/loader.py"
ENGINE_DIR = LAB / "reference/engine"

CFG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "farmHandCostMult": 1,
    "maxMarketOrdersPerTurn": 10,
    "shedCapacity": 100,
}


def _route():
    return [
        {"farmer": ["PASS"], "hands": [], "market": []}
        for _ in range(720)
    ]


def _farm(money=900, hands=()):
    return {
        "money": float(money),
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
        "tiles": [[None] * 10 for _ in range(10)],
        "farmer": [0, 0],
        "hands": [list(position) for position in hands],
    }


def _plain_observation(*, money=900, shed=None, hands=(), seeds=None):
    farms = [_farm(money, hands), _farm(3000)]
    inventory = {item: 10000 for item in m.PRODUCTS}
    market = {
        "inventory": inventory,
        "prices": {
            item: m.market_price(item, inventory[item], None)
            for item in m.PRODUCTS
        },
        "params": None,
    }
    private = {
        "shed": {item: 0 for item in m.PRODUCTS + list(m.ANIMALS)},
        "seeds": {crop: 0 for crop in m.CROPS},
        "inventories": [{} for _ in range(1 + len(hands))],
    }
    private["shed"].update(shed or {})
    private["seeds"].update(seeds or {})
    return {
        "step": 150,
        "day": 150 // 24,
        "hour": 150 % 24,
        "player": 0,
        "farms": farms,
        "private": private,
        "market": market,
        "town": {"unlocked_shops": []},
    }


class KestrelLockstepRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "kestrel_lockstep_evaluator", EVALUATOR
        )
        cls.ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ev)
        cls.engine, cls.engine_hashes = cls.ev.get_engine(ENGINE_DIR, LOADER)

    def _official_fixture(
        self,
        *,
        own_money=900,
        own_shed=None,
        rival_shed=None,
        inventories=None,
    ):
        e, S = self.engine, self.ev.Struct
        cfg = S({
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in e.specification["configuration"].items()
        })
        cfg.weedSpawnChance = 0
        farms = [e._new_farm(10, own_money), e._new_farm(10, 3000)]
        market = e._new_market()
        for item, value in (inventories or {}).items():
            market["inventory"][item] = value
        e._refresh_prices(market)
        state = []
        for seat in range(2):
            private = e._new_private()
            private["shed"].update(
                (own_shed or {}) if seat == 0 else (rival_shed or {})
            )
            observation = S(
                player=seat,
                step=150,
                day=150 // 24,
                hour=150 % 24,
                farms=farms,
                private=private,
                market=market,
                town={"unlocked_shops": []},
            )
            state.append(S(
                observation=observation,
                action={"farmer": ["PASS"], "hands": [], "market": []},
                status="ACTIVE",
                reward=0,
            ))
        env = S(configuration=cfg, done=False, info={"seed": 9923114})
        return state, env

    def _official_market(
        self,
        own,
        rival,
        *,
        own_money=900,
        own_shed=None,
        rival_shed=None,
        inventories=None,
    ):
        state, env = self._official_fixture(
            own_money=own_money,
            own_shed=own_shed,
            rival_shed=rival_shed,
            inventories=inventories,
        )
        state[0].action["market"] = deepcopy(own)
        state[1].action["market"] = deepcopy(rival)
        self.engine._process_market(state, env)
        return state

    def test_atomic_same_crop_plant_prepass_discriminates_predecessor(self):
        observation = _plain_observation(
            hands=((1, 0),),
            seeds={"WHEAT": 1},
        )
        selected = {
            "farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"]],
            "market": [],
        }

        sequential_farm, sequential_private, _, source = predecessor_post_unit_state(
            m, observation, CFG, selected, None
        )
        self.assertEqual(source, "computed_unit_replay")
        sequential_plants = sum(
            isinstance(tile, dict) and tile.get("crop") == "WHEAT"
            for row in sequential_farm["tiles"] for tile in row
        )
        self.assertEqual(sequential_plants, 1)
        self.assertEqual(sequential_private["seeds"]["WHEAT"], 0)

        atomic = _atomic_post_unit_snapshot(m, observation, CFG, selected)
        atomic_farm = atomic["farms"][0]
        atomic_plants = sum(
            isinstance(tile, dict) and tile.get("crop") == "WHEAT"
            for row in atomic_farm["tiles"] for tile in row
        )
        self.assertEqual(atomic_plants, 0)
        self.assertEqual(atomic["private"]["seeds"]["WHEAT"], 1)

    def test_exact_official_rival_price_witness_is_rejected(self):
        original = [
            ["BUY_PRODUCT", "WHEAT", 1],
            ["BUY_LAND"],
            ["SELL", "FERTILIZER", 1],
        ]
        proposed = [
            ["SELL", "FERTILIZER", 1],
            ["BUY_LAND"],
            ["BUY_PRODUCT", "WHEAT", 1],
        ]
        rival = [["BUY_PRODUCT", "WHEAT", 2]]

        original_state = self._official_market(
            original,
            rival,
            own_shed={"FERTILIZER": 1},
            inventories={"FERTILIZER": 9870, "WHEAT": 10000},
        )
        proposed_state = self._official_market(
            proposed,
            rival,
            own_shed={"FERTILIZER": 1},
            inventories={"FERTILIZER": 9870, "WHEAT": 10000},
        )
        original_private = original_state[0].observation.private
        proposed_private = proposed_state[0].observation.private
        original_farm = original_state[0].observation.farms[0]
        proposed_farm = proposed_state[0].observation.farms[0]

        self.assertEqual(original_private["shed"]["WHEAT"], 1)
        self.assertEqual(proposed_private["shed"]["WHEAT"], 0)
        self.assertEqual(original_farm["unlocked_quadrants"], ["NW"])
        self.assertEqual(proposed_farm["unlocked_quadrants"], ["NW", "NE"])
        self.assertEqual(proposed_farm["money"], 26)
        self.assertEqual(self.engine.market_price("WHEAT", 9997), 27)

        state, _ = self._official_fixture(
            own_shed={"FERTILIZER": 1},
            inventories={"FERTILIZER": 9870, "WHEAT": 10000},
        )
        selected = {"farmer": ["PASS"], "hands": [], "market": original}
        result, report = order_early_capital(
            m, state[0].observation, CFG, selected, _route()
        )
        self.assertEqual(result, selected)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "rival_interleaving_unproven")
        self.assertEqual(report["pre_lockstep_reason"], "execution_gain_proved")
        barriers = set(report["lockstep_certificate"]["barriers"])
        self.assertIn("unsupported_active_op:BUY_PRODUCT", barriers)
        self.assertIn("rival_buyable_sale:FERTILIZER", barriers)
        self.assertIn("effectful_order_after_capital", barriers)

    def test_single_terminal_carrot_funding_is_admitted(self):
        observation = _plain_observation(
            money=900,
            shed={"CARROT": 3},
        )
        selected = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["BUY_LAND"], ["SELL", "CARROT", 3]],
        }
        result, report = order_early_capital(
            m, observation, CFG, selected, _route()
        )
        self.assertEqual(
            result["market"],
            [["SELL", "CARROT", 3], ["BUY_LAND"]],
        )
        self.assertTrue(report["changed"])
        self.assertEqual(
            report["reason"], "rival_lockstep_nonregression_proved"
        )
        certificate = report["lockstep_certificate"]
        self.assertTrue(certificate["certified"])
        self.assertEqual(certificate["schema"], 2)
        self.assertEqual(certificate["products"], ["CARROT"])
        self.assertEqual(certificate["capital"]["op"], "BUY_LAND")
        self.assertIn("strength_boundary", certificate)
        self.assertEqual(report["post_unit_binding"], "official_atomic_unit_replay")

    def test_public_gain_may_vanish_under_rival_without_regression(self):
        original = [
            ["BUY_LAND"],
            ["SELL", "CARROT", 1],
            ["SELL", "CARROT", 1],
            ["SELL", "CARROT", 1],
        ]
        observation = _plain_observation(
            money=900,
            shed={"CARROT": 3},
        )
        selected = {"farmer": ["PASS"], "hands": [], "market": original}
        result, report = order_early_capital(
            m, observation, CFG, selected, _route()
        )
        self.assertTrue(report["lockstep_certificate"]["certified"])
        proposed = result["market"]
        self.assertEqual(proposed[-1], ["BUY_LAND"])

        rival = [["SELL", "CARROT", 100]]
        original_state = self._official_market(
            original,
            rival,
            own_money=900,
            own_shed={"CARROT": 3},
            rival_shed={"CARROT": 100},
        )
        proposed_state = self._official_market(
            proposed,
            rival,
            own_money=900,
            own_shed={"CARROT": 3},
            rival_shed={"CARROT": 100},
        )
        original_farm = original_state[0].observation.farms[0]
        proposed_farm = proposed_state[0].observation.farms[0]

        # The own-only $105 receipt predicts LAND. Rival supply makes the later
        # two one-unit sales cheaper, so the gain disappears. Original own work
        # still cannot regress: both miss LAND and the earlier-sale queue ends
        # with at least as much money.
        self.assertEqual(original_farm["unlocked_quadrants"], ["NW"])
        self.assertEqual(proposed_farm["unlocked_quadrants"], ["NW"])
        self.assertGreaterEqual(proposed_farm["money"], original_farm["money"])

    def test_sale_row_count_is_not_a_unit_order_proof(self):
        observation = _plain_observation(shed={"CARROT": 11})
        original = {
            "market": [
                ["SELL", "CARROT", 10],
                ["BUY_LAND"],
                ["SELL", "CARROT", 1],
            ]
        }
        candidate = {
            "market": [
                ["SELL", "CARROT", 1],
                ["SELL", "CARROT", 10],
                ["BUY_LAND"],
            ]
        }
        certified, report = _rival_lockstep_certificate(
            m, observation, CFG, original, candidate
        )
        self.assertFalse(certified)
        self.assertIn("sale_units_moved_later", report["barriers"])

    def test_later_effectful_order_is_outside_the_theorem(self):
        observation = _plain_observation(shed={"CARROT": 3})
        original = {
            "market": [
                ["BUY_LAND"],
                ["SELL", "CARROT", 3],
                ["BUY_SEED", "WHEAT", 1],
            ]
        }
        candidate = {
            "market": [
                ["SELL", "CARROT", 3],
                ["BUY_LAND"],
                ["BUY_SEED", "WHEAT", 1],
            ]
        }
        certified, report = _rival_lockstep_certificate(
            m, observation, CFG, original, candidate
        )
        self.assertFalse(certified)
        self.assertIn("unsupported_active_op:BUY_SEED", report["barriers"])
        self.assertIn("effectful_order_after_capital", report["barriers"])

    def test_wheat_sale_funding_fails_closed(self):
        observation = _plain_observation(
            money=900,
            shed={"WHEAT": 5},
        )
        selected = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["BUY_LAND"], ["SELL", "WHEAT", 5]],
        }
        result, report = order_early_capital(
            m, observation, CFG, selected, _route()
        )
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "rival_interleaving_unproven")
        self.assertIn(
            "rival_buyable_sale:WHEAT",
            report["lockstep_certificate"]["barriers"],
        )

    def test_pinned_engine_identity_is_preserved(self):
        self.assertEqual(
            self.engine_hashes["kaggriculture.py"],
            hashlib.sha256((ENGINE_DIR / "kaggriculture.py").read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
