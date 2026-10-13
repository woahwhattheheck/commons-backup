# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_s6_fert_roi``."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_fert_hand as fert_hand  # noqa: E402
import r04_full_router as r04  # noqa: E402
import r04_s6_fert_roi as lane  # noqa: E402
from titan_runtime import Features  # noqa: E402

STANDARD_CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
    "farmHandCostMult": 1,
    "marketParams": {},
}


def plant(crop, *, planted_day, yield_units=1, watered_today=False, covered=-1):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "yield_units": yield_units,
        "watered_today": watered_today,
        "fertilized_until_day": covered,
        "max_lifespan_step": -1,
    }


def observation(*, step=24 * 24, tomato_watered=True, tomato_yield=1,
                tomato_covered=-1, prices=None):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[2][2] = plant("CARROT", planted_day=22)
    tiles[2][3] = plant(
        "TOMATO", planted_day=16, yield_units=tomato_yield,
        watered_today=tomato_watered, covered=tomato_covered,
    )
    farm = {
        "tiles": tiles,
        "farmer": [0, 0],
        "hands": [[2, 2]],
        "money": 1000,
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    market_prices = {"WHEAT": 25, "CARROT": 35, "TOMATO": 200, "FERTILIZER": 100}
    market_prices.update(prices or {})
    return {
        "step": step,
        "day": step // 24,
        "hour": step % 24,
        "player": 0,
        "farms": [farm, copy.deepcopy(farm)],
        "private": {
            "inventories": [{}, {"FERTILIZER": 1}],
            "shed": {"FERTILIZER": 0},
            "seeds": {},
        },
        "market": {"prices": market_prices},
        "town": {"unlocked_shops": ["PIZZA_SHOP"]},
    }


def clear_incumbent_carrot(obs):
    obs["farms"][0]["tiles"][2][2] = None
    return obs


def pass_tape():
    return [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(720)]


def tape_with_later_carrot(step):
    tape = pass_tape()
    tape[step + 2]["farmer"] = ["PLANT", "CARROT"]
    return tape


def hire_observation(*, step=24 * 24 + 3, wheat_price=200, fert_price=10):
    obs = observation(
        step=step,
        tomato_watered=False,
        prices={"WHEAT": wheat_price, "CARROT": 200, "TOMATO": 200, "FERTILIZER": fert_price},
    )
    farm = obs["farms"][0]
    farm["tiles"] = [[None for _ in range(10)] for _ in range(10)]
    farm["tiles"][3][4] = plant("CARROT", planted_day=22)
    farm["tiles"][2][4] = plant("WHEAT", planted_day=22)
    farm["farmer"] = [0, 0]
    farm["hands"] = []
    farm["hires_today"] = 0
    farm["money"] = 1000
    obs["farms"][1] = copy.deepcopy(farm)
    obs["private"]["inventories"] = [{}]
    obs["private"]["shed"] = {"FERTILIZER": 0}
    return obs


def consider_hire(obs, *, enabled, tape=None):
    tape = tape or pass_tape()
    st = fert_hand._Day(obs["step"] // 24)
    action = {"farmer": ["PASS"], "hands": [], "market": []}
    old = fert_hand.S6_FERT_ROI
    try:
        fert_hand.S6_FERT_ROI = enabled
        out = fert_hand._consider_hire(
            obs, action, st, tape, obs["farms"][0], [],
            obs["step"] // 24, obs["step"],
        )
    finally:
        fert_hand.S6_FERT_ROI = old
    return out, st


class S6FertRoiTest(unittest.TestCase):
    def test_s6_activation_requires_exact_semantic_configuration(self):
        self.assertTrue(lane.standard_configuration(dict(STANDARD_CONFIG)))
        no_market_params = dict(STANDARD_CONFIG)
        no_market_params.pop("marketParams")
        self.assertTrue(lane.standard_configuration(no_market_params))
        none_market_params = dict(STANDARD_CONFIG, marketParams=None)
        self.assertTrue(lane.standard_configuration(none_market_params))

        bad = []
        for name, value in (
            ("episodeSteps", 719),
            ("turnsPerDay", 12),
            ("boardSize", 9),
            ("shedCapacity", 99),
            ("maxMarketOrdersPerTurn", 1),
            ("farmHandCostMult", 2),
            ("farmHandCostMult", True),
            ("turnsPerDay", True),
            ("episodeSteps", 720.0),
        ):
            candidate = dict(STANDARD_CONFIG)
            candidate[name] = value
            bad.append(candidate)
        bad.extend((
            None,
            dict(STANDARD_CONFIG, marketParams={"WHEAT": {"base": 99}}),
            dict(STANDARD_CONFIG, marketParams=[]),
            dict(STANDARD_CONFIG, marketParams=True),
        ))
        for configuration in bad:
            with self.subTest(configuration=configuration):
                self.assertFalse(lane.standard_configuration(configuration))
        router_source = (ROOT / "r04_full_router.py").read_text(encoding="utf-8")
        self.assertIn(
            "s6_enabled = r04_s6_fert_roi.standard_configuration(configuration)",
            router_source,
        )

    def test_baseline_hire_trigger_is_identical_but_s6_reserves_one_unit(self):
        obs = hire_observation()
        off, off_state = consider_hire(copy.deepcopy(obs), enabled=False)
        on, on_state = consider_hire(copy.deepcopy(obs), enabled=True)
        self.assertEqual(sum(order[0] == "HIRE" for order in off["market"]), 1)
        self.assertEqual(sum(order[0] == "HIRE" for order in on["market"]), 1)
        self.assertEqual(off_state.want, 1)
        self.assertEqual(on_state.want, 2)
        self.assertIn(["BUY_PRODUCT", "FERTILIZER", 1], off["market"])
        self.assertIn(["BUY_PRODUCT", "FERTILIZER", 2], on["market"])

    def test_s6_never_creates_a_hire_without_incumbent_carrot_case(self):
        obs = hire_observation()
        obs["farms"][0]["tiles"][3][4] = None
        out, st = consider_hire(obs, enabled=True)
        self.assertFalse(any(order[0] == "HIRE" for order in out["market"] or []))
        self.assertEqual(st.want, 0)

    def test_future_carrot_disables_extra_reserve(self):
        obs = hire_observation()
        tape = tape_with_later_carrot(obs["step"])
        out, st = consider_hire(obs, enabled=True, tape=tape)
        self.assertEqual(sum(order[0] == "HIRE" for order in out["market"]), 1)
        self.assertEqual(st.want, 2)
        self.assertIn(["BUY_PRODUCT", "FERTILIZER", 2], out["market"])

    def test_low_roi_extension_does_not_reserve_extra(self):
        obs = hire_observation(wheat_price=5, fert_price=10)
        out, st = consider_hire(obs, enabled=True)
        self.assertEqual(sum(order[0] == "HIRE" for order in out["market"]), 1)
        self.assertEqual(st.want, 1)
        self.assertIn(["BUY_PRODUCT", "FERTILIZER", 1], out["market"])

    def test_real_hire_pickup_carrot_then_s6_wheat_path_is_reachable(self):
        obs = hire_observation()
        tape = pass_tape()
        _, st = consider_hire(obs, enabled=True, tape=tape)
        self.assertEqual(st.want, 2)

        st.index = 0
        st.pending = None
        after = copy.deepcopy(obs)
        after["step"] += 1
        after["farms"][0]["hands"] = [[4, 4]]
        after["private"]["inventories"] = [{}, {"FERTILIZER": 0}]
        after["private"]["shed"]["FERTILIZER"] = 2
        old = fert_hand.S6_FERT_ROI
        try:
            fert_hand.S6_FERT_ROI = True
            self.assertEqual(
                fert_hand._hand_command(after, st, tape, ()),
                ["PICKUP", "FERTILIZER", 2],
            )

            after["step"] += 1
            after["private"]["inventories"][1]["FERTILIZER"] = 2
            after["private"]["shed"]["FERTILIZER"] = 0
            self.assertEqual(fert_hand._hand_command(after, st, tape, ()), ["NORTH"])

            after["step"] += 1
            after["farms"][0]["hands"][0] = [4, 3]
            self.assertEqual(fert_hand._hand_command(after, st, tape, ()), ["FERTILIZE"])

            after["step"] += 1
            after["farms"][0]["tiles"][3][4]["fertilized_until_day"] = 26
            after["private"]["inventories"][1]["FERTILIZER"] = 1
            self.assertEqual(fert_hand._hand_command(after, st, tape, ()), ["NORTH"])

            after["step"] += 1
            after["farms"][0]["hands"][0] = [4, 2]
            self.assertEqual(fert_hand._hand_command(after, st, tape, ()), ["FERTILIZE"])
        finally:
            fert_hand.S6_FERT_ROI = old

    def test_current_incumbent_carrot_blocks_tomato_reprioritization(self):
        self.assertIsNone(lane.choose_fert_hand_target(observation(), (2, 2), ()))

    def test_zero_price_current_carrot_still_reserves_baseline(self):
        obs = observation(prices={"CARROT": 0, "TOMATO": 200})
        carrot = obs["farms"][0]["tiles"][2][2]
        self.assertGreater(fert_hand._gain(carrot, 24), 0)
        self.assertIsNone(lane.choose_fert_hand_target(obs, (2, 2), ()))

    def test_day28_carrot_reservation_mirrors_unclipped_incumbent(self):
        obs = observation(step=28 * 24, tomato_watered=True)
        carrot = plant("CARROT", planted_day=28)
        obs["farms"][0]["tiles"][2][2] = carrot
        obs["farms"][0]["tiles"][2][3] = plant("TOMATO", planted_day=20, watered_today=True)
        self.assertGreater(fert_hand._gain(carrot, 28), 0)
        self.assertIsNone(lane.choose_fert_hand_target(obs, (2, 2), ()))

    def test_v219_gate_owns_day24_tomato(self):
        obs = clear_incumbent_carrot(observation(prices={"FERTILIZER": 30}))
        self.assertIsNone(lane.choose_fert_hand_target(obs, (2, 2), ()))

    def test_tomato_remains_available_when_v219_price_gate_is_off(self):
        obs = clear_incumbent_carrot(observation(prices={"FERTILIZER": 31}))
        target = lane.choose_fert_hand_target(obs, (2, 2), ())
        self.assertIsNotNone(target)
        self.assertEqual(target["crop"], "TOMATO")

    def test_malformed_fertilizer_price_fails_closed(self):
        obs = clear_incumbent_carrot(observation())
        obs["market"]["prices"]["FERTILIZER"] = True
        self.assertIsNone(lane.choose_fert_hand_target(obs, (2, 2), ()))

    def test_guaranteed_tomato_is_used_only_when_incumbent_is_idle(self):
        obs = clear_incumbent_carrot(observation())
        target = lane.choose_fert_hand_target(obs, (2, 2), ())
        self.assertIsNotNone(target)
        self.assertEqual(target["crop"], "TOMATO")
        self.assertEqual(target["position"], (3, 2))
        self.assertEqual(target["marginal_units"], 1)

    def test_unwatered_covered_and_capped_tomato_are_rejected(self):
        for obs in (
            clear_incumbent_carrot(observation(tomato_watered=False)),
            clear_incumbent_carrot(observation(tomato_covered=24)),
            clear_incumbent_carrot(observation(tomato_yield=3)),
        ):
            self.assertIsNone(lane.choose_fert_hand_target(obs, (2, 2), ()))

    def test_tomato_eod_reachability_boundary(self):
        late = clear_incumbent_carrot(observation(step=24 * 24 + 23))
        self.assertIsNone(lane.choose_fert_hand_target(late, (2, 2), ()))
        ok = clear_incumbent_carrot(observation(step=24 * 24 + 22))
        self.assertEqual(lane.choose_fert_hand_target(ok, (2, 2), ())["position"], (3, 2))
        far = clear_incumbent_carrot(observation(step=24 * 24 + 22))
        far["farms"][0]["tiles"][2][4] = far["farms"][0]["tiles"][2][3]
        far["farms"][0]["tiles"][2][3] = None
        self.assertIsNone(lane.choose_fert_hand_target(far, (2, 2), ()))

    def test_wheat_annual_gain_can_use_idle_hand(self):
        obs = clear_incumbent_carrot(
            observation(tomato_watered=False, prices={"WHEAT": 80, "CARROT": 35})
        )
        obs["farms"][0]["tiles"][2][3] = plant("WHEAT", planted_day=22)
        target = lane.choose_fert_hand_target(obs, (2, 2), ())
        self.assertIsNotNone(target)
        self.assertEqual(target["crop"], "WHEAT")

    def test_episode_horizon_clips_only_new_wheat(self):
        dead = clear_incumbent_carrot(
            observation(step=28 * 24, tomato_watered=False, prices={"WHEAT": 10000})
        )
        dead["farms"][0]["tiles"][2][3] = plant("WHEAT", planted_day=28)
        self.assertIsNone(lane.choose_fert_hand_target(dead, (2, 2), ()))
        live = clear_incumbent_carrot(
            observation(step=28 * 24, tomato_watered=False, prices={"WHEAT": 80})
        )
        live["farms"][0]["tiles"][2][3] = plant("WHEAT", planted_day=27)
        self.assertEqual(lane.choose_fert_hand_target(live, (2, 2), ())["crop"], "WHEAT")

    def test_upcoming_and_later_today_carrot_reserve_baseline(self):
        obs = clear_incumbent_carrot(observation(tomato_watered=False))
        upcoming = ((2, 2, 1),)
        self.assertIsNone(lane.choose_fert_hand_target(obs, (2, 2), upcoming))
        state = fert_hand._Day(24)
        state.index = 0
        state.picked = True
        old = fert_hand.S6_FERT_ROI
        try:
            fert_hand.S6_FERT_ROI = True
            self.assertEqual(fert_hand._hand_command(obs, state, None, upcoming), ["PASS"])
            self.assertEqual(
                fert_hand._hand_command(obs, state, tape_with_later_carrot(obs["step"]), ()),
                ["PASS"],
            )
        finally:
            fert_hand.S6_FERT_ROI = old

    def test_malformed_state_fails_closed(self):
        bad_price = clear_incumbent_carrot(observation())
        bad_price["market"]["prices"]["TOMATO"] = True
        self.assertIsNone(lane.choose_fert_hand_target(bad_price, (2, 2), ()))
        bad_board = clear_incumbent_carrot(observation())
        bad_board["farms"][0]["tiles"] = bad_board["farms"][0]["tiles"][:-1]
        self.assertIsNone(lane.choose_fert_hand_target(bad_board, (2, 2), ()))
        good = clear_incumbent_carrot(observation())
        self.assertIsNone(lane.choose_fert_hand_target(good, (-1, 2), ()))
        self.assertIsNone(lane.choose_fert_hand_target(good, (10, 2), ()))

    def test_generated_key_contract_is_default_off(self):
        self.assertFalse(Features().r04_s6_fert_roi)
        self.assertFalse(fert_hand.S6_FERT_ROI)
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_s6_fert_roi"], False)

    def test_install_flag_round_trip(self):
        old = r04.S6_FERT_ROI
        try:
            r04.install(s6_fert_roi=True)
            self.assertIs(r04.S6_FERT_ROI, True)
            r04.install(s6_fert_roi=False)
            self.assertIs(r04.S6_FERT_ROI, False)
        finally:
            r04.S6_FERT_ROI = old


if __name__ == "__main__":
    unittest.main()
