# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from current_hire_window import prove_window, window_end
from scan_window_traces import scan


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "candidates" / "v3-p07-joint-actors"
ENGINE = ROOT / "reference" / "engine" / "kaggriculture.py"


def _farm(hands=1):
    return {
        "farmer": [2, 4],
        "hands": [[7, 4] for _ in range(hands)],
        "money": 50000,
        "tiles": [[None for _ in range(10)] for _ in range(10)],
        "hires_today": 0,
        "unlocked_quadrants": ["NW"],
    }


def _obs(step=10, hands=1):
    return {
        "step": step,
        "player": 0,
        "day": step // 24,
        "hour": step % 24,
        "farms": [_farm(hands), _farm(0)],
        "private": {"inventories": [{} for _ in range(hands + 1)], "shed": {}, "seeds": {}},
    }


def _row(market=None, hands=1):
    return {
        "farmer": ["PASS"],
        "hands": [["PASS"] for _ in range(hands)],
        "market": copy.deepcopy(market or []),
    }


def _route(step=10, market=None, hands=1):
    rows = [_row(hands=hands) for _ in range(720)]
    rows[step] = _row(market=market, hands=hands)
    return rows


class WindowProofTests(unittest.TestCase):
    def test_predecessor_discriminator_current_hire_is_admitted(self):
        obs = _obs()
        route = _route(market=[["HIRE"]])
        proof = prove_window(obs, route[10], route, 10)
        self.assertTrue(proof.accepted)
        self.assertEqual(proof.reason, "current_hire_existing_actor_prefix")
        self.assertEqual(proof.current_hires, 1)
        self.assertEqual(proof.existing_actors, 2)
        self.assertEqual(proof.end, 24)

    def test_future_hire_remains_a_hard_cut(self):
        obs = _obs()
        route = _route(market=[["HIRE"]])
        route[17]["market"] = [["HIRE"]]
        proof = prove_window(obs, route[10], route, 10)
        self.assertTrue(proof.accepted)
        self.assertEqual(proof.end, 17)
        self.assertEqual(proof.boundary_kind, "future_hire")

    def test_future_hire_too_close_fails_closed(self):
        obs = _obs()
        route = _route(market=[["HIRE"]])
        route[12]["market"] = [["HIRE"]]
        proof = prove_window(obs, route[10], route, 10)
        self.assertFalse(proof.accepted)
        self.assertEqual(proof.reason, "window_too_short")

    def test_inactive_suffix_hire_fails_closed(self):
        obs = _obs()
        market = [[] for _ in range(10)] + [["HIRE"]]
        route = _route(market=market)
        proof = prove_window(obs, route[10], route, 10)
        self.assertFalse(proof.accepted)
        self.assertEqual(proof.reason, "inactive_current_hire")
        self.assertEqual(proof.inactive_hire_slots, (10,))

    def test_unbound_new_actor_action_fails_closed(self):
        obs = _obs(hands=1)
        route = _route(market=[["HIRE"]], hands=3)
        proof = prove_window(obs, route[10], route, 10)
        self.assertFalse(proof.accepted)
        self.assertEqual(proof.reason, "unbound_new_actor_actions")

    def test_one_extra_action_per_current_hire_is_preserved_and_admitted(self):
        obs = _obs(hands=1)
        route = _route(market=[["HIRE"]], hands=2)
        proof = prove_window(obs, route[10], route, 10)
        self.assertTrue(proof.accepted)
        self.assertEqual(proof.extra_current_hand_actions, 1)

    def test_no_hire_retains_legacy_window(self):
        obs = _obs()
        route = _route()
        proof = prove_window(obs, route[10], route, 10)
        self.assertTrue(proof.accepted)
        self.assertEqual(proof.reason, "legacy_no_current_hire")
        self.assertEqual(window_end(obs, route[10], route, 10), 24)

    def test_checkpoint_and_end_of_day_are_unchanged(self):
        obs = _obs(step=224)
        route = _route(step=224, market=[["HIRE"]])
        proof = prove_window(obs, route[224], route, 224)
        self.assertFalse(proof.accepted)
        self.assertEqual(proof.reason, "window_too_short")
        self.assertEqual(proof.boundary_step, 226)
        self.assertEqual(proof.boundary_kind, "checkpoint")

    def test_malformed_market_and_route_fail_closed(self):
        obs = _obs()
        selected = _row()
        selected["market"] = "HIRE"
        route = _route()
        self.assertEqual(prove_window(obs, selected, route, 10).reason, "malformed_current_market")
        route[11] = "bad"
        self.assertEqual(prove_window(obs, _row(), route, 10).reason, "malformed_future_row")

    def test_step_and_cap_boolean_aliases_fail_closed(self):
        obs = _obs()
        route = _route()
        self.assertEqual(prove_window(obs, route[10], route, True).reason, "unsupported_step")
        self.assertEqual(
            prove_window(obs, route[10], route, 10, max_market_orders=True).reason,
            "unsupported_market_cap",
        )


class TraceScannerTests(unittest.TestCase):
    def test_scan_counts_eligible_current_hire_without_strength_claim(self):
        import json

        obs = _obs()
        admitted = _route(market=[["HIRE"]])
        blocked = _route(market=[["HIRE"]])
        blocked[12]["market"] = [["HIRE"]]
        rows = [
            json.dumps({"observation": obs, "selected": admitted[10], "route": admitted}),
            json.dumps({"observation": obs, "selected": blocked[10], "route": blocked}),
            "not-json",
        ]
        report = scan(rows)
        self.assertEqual(report["trace_rows"], 3)
        self.assertEqual(report["current_hire_rows"], 2)
        self.assertEqual(report["eligible_current_hire_rows"], 1)
        self.assertEqual(report["malformed_rows"], 1)
        self.assertIn("not accepted swap", report["boundary"])


class EngineOrderTheoremTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import the preserved official engine without requiring the external
        # package: only resolve_episode_seed is imported at module load.
        pkg = types.ModuleType("kaggle_environments")
        utils = types.ModuleType("kaggle_environments.utils")
        utils.resolve_episode_seed = lambda env: 0
        sys.modules.setdefault("kaggle_environments", pkg)
        sys.modules.setdefault("kaggle_environments.utils", utils)
        spec = importlib.util.spec_from_file_location("crosswind_official_engine", ENGINE)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.engine = module

    def test_interpreter_applies_units_before_market(self):
        source = ENGINE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "interpreter")
        body = ast.get_source_segment(source, node)
        self.assertIsNotNone(body)
        self.assertLess(body.index("_apply_unit_action"), body.index("_process_market"))

    def test_hire_appends_and_does_not_renumber_existing_actor_prefix(self):
        e = self.engine
        farm = _farm(hands=1)
        private = {
            "inventories": [{}, {}],
            "shed": {item: 0 for item in e.PRODUCTS + list(e.ANIMALS)},
            "seeds": {crop: 0 for crop in e.CROPS},
        }
        before_prefix = [list(farm["farmer"]), list(farm["hands"][0])]
        e._apply_unit_action(farm, private, 0, ["EAST"], 10, 0, 24, 100)
        e._apply_unit_action(farm, private, 1, ["WEST"], 10, 0, 24, 100)
        # An authored action for the not-yet-created actor is a no-op.
        e._apply_unit_action(farm, private, 2, ["NORTH"], 10, 0, 24, 100)
        moved_prefix = [list(farm["farmer"]), list(farm["hands"][0])]
        e._do_hire(farm, private, 10, 1)
        self.assertEqual(farm["farmer"], moved_prefix[0])
        self.assertEqual(farm["hands"][0], moved_prefix[1])
        self.assertEqual(len(farm["hands"]), 2)
        self.assertEqual(len(private["inventories"]), 3)
        self.assertNotEqual(before_prefix, moved_prefix)


class CandidateActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BASE.exists():
            raise unittest.SkipTest("canonical P07 source is unavailable")
        sys.path.insert(0, str(BASE))
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        sys.path.insert(0, str(ROOT))
        import joint_actors
        import current_hire_joint_actors

        cls.base = joint_actors
        cls.candidate = current_hire_joint_actors

    def _crossing(self):
        now = 10
        obs = _obs(step=now, hands=1)
        # Exact synthetic crossing from the preserved P07 existence witness.
        farmer = ([['EAST']] * 5 + [['HARVEST'], ['WEST'], ['WEST'], ['DROP']] + [['WEST']] * 3)
        hand = ([['WEST']] * 5 + [['HARVEST'], ['EAST'], ['EAST'], ['DROP']] + [['EAST']] * 3)
        route = [_row(hands=2) for _ in range(720)]
        for offset, action in enumerate(farmer):
            route[now + offset]['farmer'] = list(action)
        for offset, action in enumerate(hand):
            route[now + offset]['hands'][0] = list(action)
        # Distinct tail for the actor that HIRE may append after unit execution.
        for offset in range(14):
            route[now + offset]['hands'][1] = ['NORTH'] if offset % 2 == 0 else ['SOUTH']
        route[now]['market'] = [['HIRE']]
        return obs, route

    @staticmethod
    def _spatial():
        return SimpleNamespace(
            plans={}, active={}, events=[], crop_intent=None, joint_stats=None,
            joint_report=None, configuration={
                "turnsPerDay": 24, "episodeSteps": 720,
                "maxMarketOrdersPerTurn": 10,
            },
        )

    @staticmethod
    def _controller(route):
        return SimpleNamespace(cur=0, R={0: route})

    def test_no_current_hire_window_matches_predecessor_on_valid_matrix(self):
        cases = [
            (10, None),
            (10, 17),
            (21, None),
            (22, None),
            (224, None),
            (359, None),
            (430, 432),
        ]
        for now, future_hire in cases:
            with self.subTest(now=now, future_hire=future_hire):
                obs = _obs(step=now, hands=1)
                route = _route(step=now, hands=1)
                if future_hire is not None:
                    route[future_hire]["market"] = [["HIRE"]]
                self.assertEqual(
                    window_end(obs, route[now], route, now),
                    self.base._window(obs, route[now], route, now),
                )

    def test_no_current_hire_action_and_route_output_match_predecessor(self):
        obs, left_route = self._crossing()
        left_route[10]["market"] = []
        right_route = copy.deepcopy(left_route)
        left_selected = copy.deepcopy(left_route[10])
        right_selected = copy.deepcopy(right_route[10])
        left_spatial = self._spatial()
        right_spatial = self._spatial()
        left_result, left_report = self.base.reconcile(
            left_spatial, obs, left_selected, self._controller(left_route)
        )
        right_result, right_report = self.candidate.reconcile(
            right_spatial, obs, right_selected, self._controller(right_route)
        )
        self.assertEqual(right_result, left_result)
        self.assertEqual(right_route, left_route)
        self.assertEqual(right_report["changed"], left_report["changed"])
        self.assertEqual(right_report["reason"], left_report["reason"])
        self.assertEqual(right_report["pair"], left_report["pair"])
        self.assertEqual(right_report["saved_travel"], left_report["saved_travel"])

    def test_predecessor_rejects_but_candidate_activates_and_preserves_unowned_bytes(self):
        obs, route = self._crossing()
        selected = copy.deepcopy(route[10])
        predecessor_route = copy.deepcopy(route)
        predecessor_selected = copy.deepcopy(selected)
        old_result, old_report = self.base.reconcile(
            self._spatial(), obs, predecessor_selected, self._controller(predecessor_route)
        )
        self.assertIs(old_result, predecessor_selected)
        self.assertFalse(old_report['changed'])
        self.assertEqual(old_report['reason'], self.base.REASON_HIRE)

        original_market = copy.deepcopy(selected['market'])
        original_new_actor = [copy.deepcopy(row['hands'][1]) for row in route[10:24]]
        spatial = self._spatial()
        result, report = self.candidate.reconcile(
            spatial, obs, selected, self._controller(route)
        )
        self.assertTrue(report['changed'])
        self.assertEqual(report['reason'], self.base.REASON_ACCEPTED)
        self.assertEqual(report['pair'], [0, 1])
        self.assertEqual(report['actor_prefix_count'], 2)
        self.assertEqual(report['current_hire_window']['current_hires'], 1)
        self.assertEqual(result['market'], original_market)
        self.assertEqual(result['hands'][1], original_new_actor[0])
        self.assertEqual([row['hands'][1] for row in route[10:24]], original_new_actor)
        self.assertEqual(set(spatial.plans), {0, 1})
        self.assertTrue(all(worker < 2 for worker in report['pair']))


if __name__ == "__main__":
    unittest.main()
