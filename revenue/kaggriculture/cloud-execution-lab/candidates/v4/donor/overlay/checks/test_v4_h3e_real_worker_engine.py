# SPDX-License-Identifier: Apache-2.0
"""H3e composition and pinned-interpreter regressions, without a fake worker.

Run in a materialized runtime with its root on PYTHONPATH. When running this
file from donor/overlay/checks, set TITAN_ENGINE_CHECKS to a materialized checks
folder containing reference/{engine,evaluator}. Missing/unpinned sources fail;
these tests never download an engine or substitute a transition model.

The parent tape callback is a fixture. r04_fert_hand.wrap, its parent-view and
command selection, H3e, and the official interpreter are real. This is NOT a
full-router, hosted-episode, activation-frequency, or profitability gate.
"""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import unittest

import r04_fert_hand as worker
import r04_h3e_cow_feed_recycle as lane


class RealWorkerEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checks = Path(os.environ.get("TITAN_ENGINE_CHECKS", Path(__file__).parent))
        evaluator = checks / "reference/evaluator/evaluate.py"
        spec = importlib.util.spec_from_file_location("h3e_engine_evaluator", evaluator)
        if spec is None or spec.loader is None:
            raise RuntimeError("Pinned evaluator is unavailable")
        cls.ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ev)
        cls.engine, cls.engine_hashes = cls.ev.get_engine(
            checks / "reference/engine", checks / "reference/evaluator/loader.py")

    def setUp(self):
        self.saved_flag = worker.FERT_HAND
        self.saved_state = dict(worker._STATE)
        self.saved_report = dict(worker.REPORT)
        self.saved_telemetry = dict(lane.telemetry)
        self.addCleanup(self.restore_globals)
        worker.FERT_HAND = True
        worker._STATE.clear()
        worker.REPORT.update({key: 0 for key in worker.REPORT})
        lane.telemetry.clear()

    def restore_globals(self):
        worker.FERT_HAND = self.saved_flag
        worker._STATE.clear()
        worker._STATE.update(self.saved_state)
        worker.REPORT.clear()
        worker.REPORT.update(self.saved_report)
        lane.telemetry.clear()
        lane.telemetry.update(self.saved_telemetry)

    def fixture(self, player=0, step=695, hidden_index=1, hidden_pos=(0, 0),
                fertilizer=1, hidden=True):
        e, S = self.engine, self.ev.Struct
        cfg = S({k: v.get("default") if isinstance(v, dict) else v
                 for k, v in e.specification["configuration"].items()})
        cfg.weedSpawnChance = 0
        farms = [e._new_farm(10, 1000), e._new_farm(10, 1000)]
        farm = farms[player]
        farm["farmer"] = [0, 0]
        farm["hands"] = [[2, 2], [3, 3]]
        cow = e._new_animal("COW", 0)
        cow.update(consecutive_unfed=1, cared_today=True)
        farm["tiles"][0][0] = cow
        carrot = e._new_plant("CARROT", step // 24 - 2, 24)
        farm["tiles"][0][1] = carrot
        inventories = [{"WHEAT": 1}, {"MILK": 2}, {"EGG": 3}]
        if hidden:
            farm["hands"].insert(hidden_index, list(hidden_pos))
            inventories.insert(hidden_index + 1, {"FERTILIZER": fertilizer})
            st = worker._Day(step // 24)
            st.index = hidden_index
            st.picked = True
            st.last_step = step - 1
            worker._STATE[player] = st
        market = e._new_market()
        town = {"unlocked_shops": []}
        state = []
        for seat in range(2):
            private = e._new_private()
            if seat == player:
                private["inventories"] = inventories
            observation = S(player=seat, step=step, day=step // 24,
                            hour=step % 24, farms=farms, private=private,
                            market=market, town=town)
            state.append(S(observation=observation,
                           action={"farmer": ["PASS"], "hands": [], "market": []},
                           status="ACTIVE", reward=0))
        return state, S(configuration=cfg, done=False, info={"seed": 96012618})

    def parent(self, action, seen):
        def tape(observation, configuration=None):
            seen.append((copy.deepcopy(observation), configuration))
            return action
        return tape

    def compose(self, observation, configuration, enabled=True, outer=True):
        parent_action = {"farmer": ["CARE"], "hands": [["NORTH"], ["SOUTH"]],
                         "market": [], "sentinel": {"keep": [1, 2]}}
        seen, completed = [], []
        parent = self.parent(parent_action, seen)
        if not outer:
            core = worker.wrap(lane.install(parent, enabled=enabled))
        else:
            real_core = worker.wrap(parent)

            def core(obs, cfg):
                result = real_core(obs, cfg)
                completed.append(result)
                return result

            core = lane.install(core, enabled=enabled)
        result = core(observation, configuration)
        return result, parent_action, seen, completed

    def transition(self, state, env, player, action):
        state[player].action = copy.deepcopy(action)
        self.engine.interpreter(state, env)
        return state[player].observation

    def test_actual_worker_moves_and_outer_guard_sees_all_indices_both_seats(self):
        for player in (0, 1):
            for index in (0, 1, 2):
                with self.subTest(player=player, hidden_index=index):
                    state, env = self.fixture(player=player, hidden_index=index)
                    obs = state[player].observation
                    before = copy.deepcopy(obs)
                    out, parent, seen, completed = self.compose(obs, env.configuration)
                    expected = [["NORTH"], ["SOUTH"]]
                    expected.insert(index, ["EAST"])
                    self.assertEqual(out["hands"], expected)
                    self.assertEqual(out["farmer"], ["CARE"])
                    self.assertIs(out, completed[0])
                    self.assertEqual(len(seen), 1)
                    self.assertIs(seen[0][1], env.configuration)
                    view = seen[0][0]
                    self.assertEqual(view["farms"][player]["hands"], [[2, 2], [3, 3]])
                    self.assertEqual(view["private"]["inventories"],
                                     [{"WHEAT": 1}, {"MILK": 2}, {"EGG": 3}])
                    self.assertEqual(obs, before)
                    self.assertEqual(parent["hands"], [["NORTH"], ["SOUTH"]])
                    self.assertEqual(lane.telemetry["activations"], 0)
                    self.assertEqual(worker.REPORT["hires"], 0)

    def test_wrong_inner_order_is_distinguished_with_real_east_not_mock_feed(self):
        for player in (0, 1):
            with self.subTest(player=player):
                state, env = self.fixture(player=player)
                outer, _, _, _ = self.compose(state[player].observation, env.configuration)
                state, env = self.fixture(player=player)
                inner, _, _, _ = self.compose(state[player].observation,
                                              env.configuration, outer=False)
                self.assertEqual(outer["hands"], inner["hands"])
                self.assertEqual(inner["hands"][1], ["EAST"])
                self.assertEqual(outer["farmer"], ["CARE"])
                self.assertEqual(inner["farmer"], ["FEED"])
                # This establishes the conservative seam contract, not that
                # an EAST move itself harms the cow or emits a second FEED.

    def test_stacked_actual_pass_allows_single_feed_without_reordering(self):
        for player in (0, 1):
            for index in (0, 1, 2):
                with self.subTest(player=player, hidden_index=index):
                    state, env = self.fixture(player=player, hidden_index=index, fertilizer=0)
                    obs = state[player].observation
                    before = copy.deepcopy(obs)
                    out, parent, _, completed = self.compose(obs, env.configuration)
                    expected = [["NORTH"], ["SOUTH"]]
                    expected.insert(index, ["PASS"])
                    self.assertEqual(out["farmer"], ["FEED"])
                    self.assertEqual(out["hands"], expected)
                    self.assertIsNot(out, completed[0])
                    self.assertEqual(completed[0]["farmer"], ["CARE"])
                    self.assertEqual(out["market"], parent["market"])
                    self.assertEqual(out["sentinel"], parent["sentinel"])
                    out["sentinel"]["keep"].append(3)
                    self.assertEqual(parent["sentinel"]["keep"], [1, 2])
                    self.assertEqual(obs, before)

    def test_unstacked_actual_active_hand_does_not_suppress_cow_rescue(self):
        for player in (0, 1):
            with self.subTest(player=player):
                state, env = self.fixture(player=player, hidden_pos=(3, 0))
                out, _, _, _ = self.compose(state[player].observation, env.configuration)
                self.assertEqual(out["farmer"], ["FEED"])
                self.assertEqual(out["hands"], [["NORTH"], ["WEST"], ["SOUTH"]])

    def test_key_off_returns_actual_wrapper_object(self):
        state, env = self.fixture(fertilizer=0)
        out, _, _, completed = self.compose(state[0].observation, env.configuration,
                                            enabled=False)
        self.assertIs(out, completed[0])
        self.assertEqual(out["farmer"], ["CARE"])
        self.assertEqual(lane.telemetry["activations"], 0)

    def test_official_interpreter_feed_before_eod_survival_and_exact_wheat_cost(self):
        for player in (0, 1):
            with self.subTest(player=player):
                baseline, env = self.fixture(player=player, fertilizer=0)
                candidate, cenv = copy.deepcopy((baseline, env))
                rescue, _, _, completed = self.compose(candidate[player].observation,
                                                        cenv.configuration)
                original = copy.deepcopy(completed[0])
                base_obs = self.transition(baseline, env, player, original)
                got = self.transition(candidate, cenv, player, rescue)
                self.assertEqual(base_obs.farms[player]["tiles"][0][0], {"kind": "PASTURE"})
                cow = got.farms[player]["tiles"][0][0]
                self.assertEqual(cow["animal"], "COW")
                self.assertEqual(cow["consecutive_unfed"], 0)
                # COW interval is two days: placement 0 has no production at next_day 29.
                self.assertEqual(cow["yield_units"], 0)
                self.assertFalse(cow["fed_today"])
                self.assertFalse(cow["cared_today"])
                self.assertEqual(cow["pending_care_bonus"], 1)
                self.assertEqual(base_obs.private["shed"].get("WHEAT", 0), 1)
                self.assertEqual(got.private["shed"].get("WHEAT", 0), 0)
                for product in ("MILK", "EGG", "FERTILIZER"):
                    self.assertEqual(got.private["shed"].get(product, 0),
                                     base_obs.private["shed"].get(product, 0))
                self.assertEqual(got.private["inventories"], [{}])
                self.assertEqual(got.farms[player]["hands"], [])
                self.assertEqual(got.farms[player]["money"], base_obs.farms[player]["money"])
                self.assertEqual(got.farms[1 - player], base_obs.farms[1 - player])

    def test_real_dead_service_actions_each_save_cow(self):
        for player in (0, 1):
            for op in ("CARE", "HARVEST", "COLLECT_FERTILIZER"):
                with self.subTest(player=player, op=op):
                    state, env = self.fixture(player=player, hidden=False)
                    obs = state[player].observation
                    action = {"farmer": [op], "hands": [["PASS"], ["PASS"]], "market": []}
                    before = copy.deepcopy((obs.farms[player], obs.private))
                    # The claimed replaced command really is inert in the engine.
                    self.engine._apply_unit_action(obs.farms[player], obs.private, 0,
                                                   action["farmer"], 10, 28, 24, 100)
                    self.assertEqual((obs.farms[player], obs.private), before)
                    out = lane.apply_cow_feed_recycle(action, obs, env.configuration, enabled=True)
                    self.assertEqual(out["farmer"], ["FEED"])
                    got = self.transition(state, env, player, out)
                    self.assertEqual(got.farms[player]["tiles"][0][0]["animal"], "COW")

    def test_production_phase_bonus_and_cap_use_pinned_engine(self):
        for player in (0, 1):
            for placed, units, bonus, expected_yield, expected_bonus in (
                    (0, 0, 2, 0, 3), (1, 0, 2, 3, 1), (1, 6, 2, 6, 1)):
                with self.subTest(player=player, placed=placed, units=units):
                    state, env = self.fixture(player=player, hidden=False)
                    obs = state[player].observation
                    cow = obs.farms[player]["tiles"][0][0]
                    cow.update(placed_day=placed, yield_units=units, pending_care_bonus=bonus)
                    action = {"farmer": ["CARE"], "hands": [["PASS"], ["PASS"]], "market": []}
                    out = lane.apply_cow_feed_recycle(action, obs, env.configuration, enabled=True)
                    self.assertEqual(out["farmer"], ["FEED"])
                    got = self.transition(state, env, player, out)
                    cow = got.farms[player]["tiles"][0][0]
                    self.assertEqual(cow["yield_units"], expected_yield)
                    self.assertEqual(cow["pending_care_bonus"], expected_bonus)
                    # Even the non-producing phase renews fertilizer. Survival
                    # is not equivalent to immediate MILK or to zero future value.
                    self.assertTrue(cow["fertilizer_available"])

    def test_engine_consumes_the_qualifying_hand_wheat_not_farmer_wheat(self):
        for player in (0, 1):
            for index in (0, 1):
                with self.subTest(player=player, hand=index):
                    state, env = self.fixture(player=player, hidden=False)
                    obs = state[player].observation
                    farm = obs.farms[player]
                    farm["farmer"] = [4, 4]
                    farm["hands"][index] = [0, 0]
                    obs.private["inventories"][0] = {"WHEAT": 2}
                    obs.private["inventories"][index + 1] = {"WHEAT": 1}
                    hands = [["PASS"], ["PASS"]]
                    hands[index] = ["CARE"]
                    action = {"farmer": ["PASS"], "hands": hands, "market": []}
                    out = lane.apply_cow_feed_recycle(action, obs, env.configuration, enabled=True)
                    self.assertEqual(out["farmer"], ["PASS"])
                    self.assertEqual(out["hands"][index], ["FEED"])
                    self.engine._apply_unit_action(farm, obs.private, index + 1,
                                                   out["hands"][index], 10, 28, 24, 100)
                    self.assertEqual(obs.private["inventories"][0]["WHEAT"], 2)
                    self.assertEqual(obs.private["inventories"][index + 1].get("WHEAT", 0), 0)
                    self.assertTrue(farm["tiles"][0][0]["fed_today"])

    def test_terminal_partial_day_does_not_spend_wheat_or_refresh_animals(self):
        for player in (0, 1):
            with self.subTest(player=player):
                state, env = self.fixture(player=player, step=718, hidden=False)
                action = {"farmer": ["CARE"], "hands": [["PASS"], ["PASS"]], "market": []}
                out = lane.apply_cow_feed_recycle(action, state[player].observation,
                                                   env.configuration, enabled=True)
                self.assertIs(out, action)
                got = self.transition(state, env, player, out)
                self.assertEqual(got.private["inventories"][0]["WHEAT"], 1)
                self.assertEqual(got.farms[player]["tiles"][0][0]["consecutive_unfed"], 1)
                self.assertEqual(state[player].status, "DONE")

    def test_poison_metadata_stays_on_engine_safe_escape_path(self):
        for field in ("placed_day", "pending_care_bonus"):
            with self.subTest(field=field):
                state, env = self.fixture(hidden=False)
                obs = state[0].observation
                del obs.farms[0]["tiles"][0][0][field]
                action = {"farmer": ["CARE"], "hands": [["PASS"], ["PASS"]], "market": []}
                out = lane.apply_cow_feed_recycle(action, obs, env.configuration, enabled=True)
                self.assertIs(out, action)
                got = self.transition(state, env, 0, out)
                self.assertEqual(got.farms[0]["tiles"][0][0], {"kind": "PASTURE"})

    def test_real_worker_resets_after_eod_without_phantom_hand(self):
        state, env = self.fixture(fertilizer=0)
        obs = state[0].observation
        out, _, _, _ = self.compose(obs, env.configuration)
        self.transition(state, env, 0, out)
        # The runner advances step externally; interpreter advances day/hour.
        obs.step = 696
        next_action = {"farmer": ["PASS"], "hands": [], "market": []}
        seen = []
        agent = lane.install(worker.wrap(self.parent(next_action, seen)), enabled=True)
        got = agent(obs, env.configuration)
        self.assertIs(got, next_action)
        self.assertEqual(got["hands"], [])
        self.assertIsNone(worker._STATE[0].index)
        self.assertEqual(worker._STATE[0].day, 29)
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
