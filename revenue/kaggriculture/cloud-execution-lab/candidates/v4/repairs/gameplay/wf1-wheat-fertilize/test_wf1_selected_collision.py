# SPDX-License-Identifier: Apache-2.0
"""WF1 selected-actor composition checks on the full pinned official engine.

Run beside wf1_current_adapter.py and the unchanged r04_wheat_fert.py:
  TITAN_ENGINE=/path/to/kaggriculture.py python -m unittest -v test_wf1_selected_collision
The sibling kaggriculture.json and utils.py must have their pinned bytes too.
No network calls, substitute game transitions, or full-game strength claims.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import types
import typing
import unittest
from unittest.mock import patch

import r04_wheat_fert as donor
import wf1_current_adapter as adapter

PINS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}
DONOR = "b35a30431f64c1d6b40d1d599190338a9d50b555"


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def load_engine():
    value = os.environ.get("TITAN_ENGINE")
    if not value:
        raise RuntimeError("TITAN_ENGINE must point to the pinned full kaggriculture.py")
    path = Path(value).resolve()
    for name, expected in PINS.items():
        data = path.with_name(name).read_bytes()
        if blob(data) != expected:
            raise ValueError("Pinned official source mismatch: " + name)
    # Compile the real upstream seed helper, not a substitute implementation.
    parsed = ast.parse(path.with_name("utils.py").read_bytes())
    function = next(n for n in parsed.body
                    if isinstance(n, ast.FunctionDef) and n.name == "resolve_episode_seed")
    namespace = {"Any": typing.Any, "Callable": typing.Callable, "random": random}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 str(path.with_name("utils.py")), "exec"), namespace)
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = namespace["resolve_episode_seed"]
    spec = importlib.util.spec_from_file_location("wf1_selected_engine", path)
    engine = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"kaggle_environments": package,
                                 "kaggle_environments.utils": utils}):
        spec.loader.exec_module(engine)
    return engine


class SelectedCollision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if blob(Path(donor.__file__).read_bytes()) != DONOR:
            raise ValueError("Exact WF1 donor changed; review source pin explicitly")
        cls.engine = load_engine()

    def setUp(self):
        self.reset_donor()

    @staticmethod
    def reset_donor():
        donor._STATE.clear()
        for key in donor.REPORT:
            donor.REPORT[key] = 0

    def fixture(self, seat=0, age=2, actors=2, water=0, fertilizer=1,
                held=1, independent=False):
        e = self.engine
        cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                      for k, v in e.specification["configuration"].items()})
        cfg.weedSpawnChance = 0
        farms = [e._new_farm(10, 3000) for _ in range(2)]
        market = e._new_market()
        market["inventory"]["FERTILIZER"] = 10400
        market["inventory"]["WHEAT"] = 9500
        e._refresh_prices(market)
        town = {"unlocked_shops": []}
        state = []
        step = age * 24 + 1
        for player in (0, 1):
            state.append(Struct(
                observation=Struct(player=player, step=step, day=age, hour=1,
                                   farms=farms, private=e._new_private(),
                                   market=market, town=town),
                action={"farmer": ["PASS"], "hands": [], "market": []},
                status="ACTIVE", reward=0))
        farm = farms[seat]
        positions = [[1, 1] for _ in range(actors)]
        commands = [["PASS"] for _ in range(actors)]
        inventories = [{"FERTILIZER": 1} for _ in range(actors)]
        commands[water] = ["WATER"]
        commands[fertilizer] = ["FERTILIZE"]
        inventories[fertilizer]["FERTILIZER"] = held
        if independent:
            positions.append([2, 1])
            commands.append(["WATER"])
            inventories.append({"FERTILIZER": 1})
        farm["farmer"], farm["hands"] = positions[0], positions[1:]
        for x in (1, 2) if independent else (1,):
            tile = e._new_plant("WHEAT", age - 1 if x == 2 else 0, 24)
            tile["consecutive_unwatered"] = 0
            farm["tiles"][1][x] = tile
        state[seat].observation.private["inventories"] = inventories
        state[seat].action = {"farmer": commands[0], "hands": commands[1:], "market": []}
        return state, Struct(configuration=cfg, done=False, info={"seed": 9600803})

    def apply(self, state, env, seat=0, enabled=True):
        return adapter.apply_wf1_current(state[seat].observation, state[seat].action,
                                         env.configuration, enabled=enabled)

    def test_literal_off_preserves_object_and_memory(self):
        state, env = self.fixture()
        for flag in (False, None, 0, 1, "true", [], {}):
            with self.subTest(flag=flag):
                self.assertIs(self.apply(state, env, enabled=flag), state[0].action)
        self.assertEqual(donor._STATE, {})
        self.assertTrue(all(value == 0 for value in donor.REPORT.values()))

    def test_full_interpreter_collision_matrix(self):
        """96 paired complete interpreter callbacks across actor counts and both seats."""
        pairs = 0
        for seat in (0, 1):
            for age in (1, 2):
                for actors in range(2, 8):
                    for water, fertilizer in ((0, actors-1), (actors-1, 0)):
                        for held in (1, 3):
                            with self.subTest(seat=seat, age=age, actors=actors,
                                              water=water, fertilizer=fertilizer, held=held):
                                self.reset_donor()
                                state, env = self.fixture(seat, age, actors, water, fertilizer, held)
                                before = deepcopy((state, env))
                                result = self.apply(state, env, seat)
                                self.assertEqual((state, env), before)
                                self.assertEqual(result, state[seat].action)
                                self.assertEqual(donor.REPORT["swap_units"], 0)
                                self.assertEqual(donor._STATE[seat]["tiles"], {})
                                other, other_env = deepcopy((state, env))
                                other[seat].action = result
                                self.engine.interpreter(state, env)
                                self.engine.interpreter(other, other_env)
                                self.assertEqual(other, state)
                                pairs += 1
        self.assertEqual(pairs, 96)

    def test_raw_donor_resource_and_yield_falsifier(self):
        """Eight baseline/raw/fixed full-interpreter triples expose the defect."""
        for seat in (0, 1):
            for age in (1, 2):
                for water in (0, 1):
                    with self.subTest(seat=seat, age=age, water=water):
                        self.reset_donor()
                        state, env = self.fixture(seat, age, water=water, fertilizer=1-water)
                        raw, raw_env = deepcopy((state, env))
                        fixed, fixed_env = deepcopy((state, env))
                        raw[seat].action = donor.apply_wheat_fertilize(
                            raw[seat].observation, raw[seat].action, enabled=True)
                        self.assertGreater(donor.REPORT["swap_units"], 0)
                        self.reset_donor()
                        fixed[seat].action = self.apply(fixed, fixed_env, seat)
                        for states, environment in ((state, env), (raw, raw_env), (fixed, fixed_env)):
                            self.engine.interpreter(states, environment)
                        base_obs, raw_obs = state[seat].observation, raw[seat].observation
                        base_fert = sum(i.get("FERTILIZER", 0) for i in base_obs.private["inventories"])
                        raw_fert = sum(i.get("FERTILIZER", 0) for i in raw_obs.private["inventories"])
                        base_tile, raw_tile = (o.farms[seat]["tiles"][1][1] for o in (base_obs, raw_obs))
                        self.assertEqual(base_fert - raw_fert, 1)
                        self.assertEqual(base_tile["fertilized_until_day"], raw_tile["fertilized_until_day"])
                        self.assertEqual(base_tile["yield_units"] - raw_tile["yield_units"],
                                         0 if age == 1 else 1 + water)
                        self.assertEqual(fixed, state)

    def test_collision_does_not_suppress_existing_credit_sale(self):
        state, env = self.fixture()
        state[0].observation.private["shed"]["WHEAT"] = 10
        state[0].action["market"] = [["PASS"] for _ in range(9)] + [["SELL", "WHEAT", 1]]
        donor._STATE[0] = {"last_step": 48, "day": 2, "tiles": {}, "credit": 3}
        before = deepcopy(state)
        result = self.apply(state, env)
        self.assertEqual(result["farmer"], state[0].action["farmer"])
        self.assertEqual(result["hands"], state[0].action["hands"])
        self.assertEqual(result["market"][-1], ["SELL", "WHEAT", 4])
        self.assertEqual(donor._STATE[0]["tiles"], {})
        self.assertEqual(donor._STATE[0]["credit"], 0)
        self.assertEqual(state, before)

    def test_middle_hand_indices(self):
        for seat in (0, 1):
            for water, fertilizer in ((1, 2), (2, 1), (3, 5), (5, 3)):
                with self.subTest(seat=seat, water=water, fertilizer=fertilizer):
                    self.reset_donor()
                    state, env = self.fixture(seat, actors=7, water=water, fertilizer=fertilizer)
                    self.assertEqual(self.apply(state, env, seat), state[seat].action)

    def test_independent_tile_still_substitutes(self):
        for seat in (0, 1):
            for age in (1, 2):
                for reverse in (False, True):
                    with self.subTest(seat=seat, age=age, reverse=reverse):
                        self.reset_donor()
                        state, env = self.fixture(seat, age, water=int(reverse),
                                                  fertilizer=int(not reverse), independent=True)
                        before = deepcopy(state)
                        result = self.apply(state, env, seat)
                        original = state[seat].action
                        self.assertEqual(result["farmer"], original["farmer"])
                        self.assertEqual(result["hands"][:-1], original["hands"][:-1])
                        self.assertEqual(result["hands"][-1], ["FERTILIZE"])
                        self.assertEqual(result["market"], original["market"])
                        self.assertNotIn((1, 1), donor._STATE[seat]["tiles"])
                        self.assertIn((2, 1), donor._STATE[seat]["tiles"])
                        self.assertEqual(state, before)

    def test_unfunded_selected_fertilizer_does_not_block(self):
        for seat in (0, 1):
            for reverse in (False, True):
                with self.subTest(seat=seat, reverse=reverse):
                    self.reset_donor()
                    state, env = self.fixture(seat, water=int(reverse),
                                              fertilizer=int(not reverse), held=0)
                    result = self.apply(state, env, seat)
                    self.assertEqual([result["farmer"], *result["hands"]][int(reverse)], ["FERTILIZE"])
                    self.assertGreater(donor.REPORT["swap_units"], 0)

    def test_different_tile_fertilizer_does_not_block(self):
        state, env = self.fixture()
        state[0].observation.farms[0]["hands"][0] = [2, 2]
        self.assertEqual(self.apply(state, env)["farmer"], ["FERTILIZE"])

    def test_zero_fertilizer_water_stays_water(self):
        state, env = self.fixture()
        state[0].observation.private["inventories"][0]["FERTILIZER"] = 0
        self.assertEqual(self.apply(state, env), state[0].action)

    def test_nonwater_actor_is_not_masked(self):
        state, env = self.fixture()
        state[0].action["farmer"] = ["PASS"]
        obs = state[0].observation
        with patch.object(donor, "apply_wheat_fertilize", return_value=state[0].action) as call:
            self.apply(state, env)
        self.assertIs(call.call_args.args[0], obs)

    def test_no_collision_passes_original_observation_identity(self):
        state, env = self.fixture(held=0)
        obs = state[0].observation
        with patch.object(donor, "apply_wheat_fertilize", return_value=state[0].action) as call:
            self.apply(state, env)
        self.assertIs(call.call_args.args[0], obs)

    def test_only_eligibility_inventory_is_masked(self):
        state, env = self.fixture(independent=True)
        obs = state[0].observation
        saved = deepcopy(obs)
        with patch.object(donor, "apply_wheat_fertilize", return_value=state[0].action) as call:
            self.apply(state, env)
        masked = call.call_args.args[0]
        self.assertEqual(obs, saved)
        self.assertIsNot(masked, obs)
        self.assertIs(masked["farms"], obs["farms"])
        self.assertIs(masked["market"], obs["market"])
        self.assertIs(masked["private"]["shed"], obs["private"]["shed"])
        self.assertEqual(masked["private"]["inventories"][0]["FERTILIZER"], 0)
        for index in (1, 2):
            self.assertIs(masked["private"]["inventories"][index], obs["private"]["inventories"][index])

    def test_multiple_waters_on_covered_tile_are_all_preserved(self):
        state, env = self.fixture(actors=4, fertilizer=3)
        state[0].action["hands"][:2] = [["WATER"], ["WATER"]]
        self.assertEqual(self.apply(state, env), state[0].action)
        self.assertEqual(donor.REPORT["swap_units"], 0)

    def test_tuple_positions_match_list_positions(self):
        state, env = self.fixture()
        state[0].observation.farms[0]["farmer"] = (1, 1)
        self.assertEqual(self.apply(state, env), state[0].action)

    def test_extra_fertilizer_arguments_follow_engine_verb_semantics(self):
        state, env = self.fixture()
        state[0].action["hands"][0] = ["FERTILIZE", "ignored"]
        self.assertEqual(self.apply(state, env), state[0].action)

    def test_independent_credit_bookkeeping_matches_donor_without_collision(self):
        state, env = self.fixture(held=0, independent=True)
        obs, action = state[0].observation, state[0].action
        expected = donor.apply_wheat_fertilize(obs, action, enabled=True)
        expected_memory, expected_report = deepcopy(donor._STATE), deepcopy(donor.REPORT)
        self.reset_donor()
        actual = self.apply(state, env)
        self.assertEqual(actual, expected)
        self.assertEqual(donor._STATE, expected_memory)
        self.assertEqual(donor.REPORT, expected_report)

    def test_supported_market_rows_unchanged(self):
        state, env = self.fixture()
        state[0].action["market"] = [["SELL", "MILK", 0] for _ in range(10)]
        action = deepcopy(state[0].action)
        self.assertEqual(self.apply(state, env), action)

    def test_unsupported_configuration_never_calls_donor(self):
        state, env = self.fixture()
        for key, value in (("episodeSteps", 719), ("boardSize", 8),
                           ("turnsPerDay", 12), ("shedCapacity", 101),
                           ("maxMarketOrdersPerTurn", 11), ("marketParams", {"WHEAT": {}})):
            with self.subTest(key=key):
                cfg = deepcopy(env.configuration)
                cfg[key] = value
                with patch.object(donor, "apply_wheat_fertilize", side_effect=AssertionError("called")) as call:
                    self.assertIs(adapter.apply_wf1_current(state[0].observation, state[0].action,
                                                           cfg, enabled=True), state[0].action)
                call.assert_not_called()

    def test_bad_shapes_never_call_donor(self):
        state, env = self.fixture()
        cases = []
        for field, value in (("player", True), ("player", 2), ("step", -1), ("step", 720)):
            obs = deepcopy(state[0].observation)
            obs[field] = value
            cases.append((obs, deepcopy(state[0].action)))
        for value in (None, [], [["WATER"], ["PASS"]]):
            action = deepcopy(state[0].action)
            action["hands"] = value
            cases.append((deepcopy(state[0].observation), action))
        for amount in (True, -1, 1.5, float("nan"), "1"):
            obs = deepcopy(state[0].observation)
            obs["private"]["inventories"][1]["FERTILIZER"] = amount
            cases.append((obs, deepcopy(state[0].action)))
        for obs, action in cases:
            with self.subTest(obs=repr(obs.get("player"))):
                with patch.object(donor, "apply_wheat_fertilize", side_effect=AssertionError("called")) as call:
                    self.assertIs(adapter.apply_wf1_current(obs, action, env.configuration,
                                                           enabled=True), action)
                call.assert_not_called()

    def test_exception_returns_exact_parent(self):
        state, env = self.fixture()
        with patch.object(donor, "apply_wheat_fertilize", side_effect=ValueError("test")):
            self.assertIs(self.apply(state, env), state[0].action)


if __name__ == "__main__":
    unittest.main()
