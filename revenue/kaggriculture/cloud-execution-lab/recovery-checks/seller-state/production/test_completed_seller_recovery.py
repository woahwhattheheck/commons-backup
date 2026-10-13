# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("rill_candidate_titan_runtime", ROOT / "titan_runtime.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def observation(step: int, *, player: int = 0, rival_yield: int = 0):
    own = {"tiles": [[None]], "hands": []}
    rival = {"tiles": [[{"kind": "PLANT", "crop": "WHEAT", "yield_units": rival_yield}]], "hands": []}
    farms = [own, rival] if player == 0 else [rival, own]
    return {"step": step, "player": player, "farms": farms, "private": {"shed": {}, "inventories": [{}]}}


class FakeSeller:
    def __init__(self):
        self.planned = {}
        self.pending = {}
        self.previous = None
        self.observed_harvests = {}
        self.selected_post_units = None
        self.capture_post_units = False
        self.observe_calls = []

    def observe(self, obs):
        self.observe_calls.append(int(obs["step"]))
        if self.previous is not None:
            rival = 1 - int(obs["player"])
            old = self.previous["farms"][rival]["tiles"][0][0]
            new = obs["farms"][rival]["tiles"][0][0]
            before = int(old.get("yield_units", 0)) if isinstance(old, dict) else 0
            after = int(new.get("yield_units", 0)) if isinstance(new, dict) else 0
            if before > after:
                self.observed_harvests.setdefault("WHEAT", []).append((int(obs["step"]), before - after))
        self.previous = copy.deepcopy(obs)

    def transform(self, obs, cfg, base):
        self.observe(obs)
        self.planned = {"WHEAT": [(int(obs["step"]) + 1, 3)]}
        self.pending = {"WHEAT": 3}
        return copy.deepcopy(base)


class Controller:
    def __init__(self):
        self.cur = "MAIN"


class Production:
    def __init__(self, action):
        self.action = action
        self.calls = 0

    def act(self, obs):
        self.calls += 1
        return copy.deepcopy(self.action)


class PassiveTimer:
    def __init__(self, seconds):
        self.seconds = seconds
        self.expired = MODULE.deadline.DeadlineExceeded("test deadline")

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        return False


class ExitExpiryTimer(PassiveTimer):
    def __exit__(self, kind, error, traceback):
        if kind is None:
            raise self.expired
        return False


class SellerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.original_timer = MODULE.deadline._DeadlineTimer

    def tearDown(self):
        MODULE.deadline._DeadlineTimer = self.original_timer

    def agent_with_fake_pipeline(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        agent = MODULE.TitanAgent(MODULE.Features(seed=False, funding=False))
        agent.ready = True
        agent.consumer = FakeSeller()
        agent.controller = Controller()
        agent.production = Production(action)
        return agent, action

    def test_public_observation_is_minimal_and_detached(self):
        obs = observation(9, rival_yield=7)
        obs["private"]["secret"] = 99
        public = MODULE.TitanAgent._seller_public_observation(obs)
        self.assertEqual(set(public), {"step", "player", "farms"})
        self.assertEqual(public["farms"][0]["tiles"], [])
        self.assertEqual(public["farms"][1]["tiles"][0][0]["yield_units"], 7)
        obs["farms"][1]["tiles"][0][0]["yield_units"] = 0
        self.assertEqual(public["farms"][1]["tiles"][0][0]["yield_units"], 7)

    def test_completed_state_is_detached_and_restored(self):
        agent, _ = self.agent_with_fake_pipeline()
        seller = agent.consumer
        seller.planned = {"WHEAT": [(10, 2)]}
        seller.pending = {"WHEAT": 2}
        seller.previous = observation(9, rival_yield=5)
        seller.observed_harvests = {"WHEAT": [(8, 1)]}
        agent._commit_seller_state()
        seller.planned["WHEAT"].append((11, 4))
        seller.pending["WHEAT"] = 99
        seller.previous = observation(10, rival_yield=0)
        seller.observed_harvests["WHEAT"].append((9, 9))

        replacement = FakeSeller()
        agent.consumer = replacement
        agent._restore_seller_state()
        self.assertEqual(replacement.planned, {"WHEAT": [(10, 2)]})
        self.assertEqual(replacement.pending, {"WHEAT": 2})
        self.assertEqual(replacement.previous["farms"][1]["tiles"][0][0]["yield_units"], 5)
        self.assertEqual(replacement.observed_harvests, {"WHEAT": [(8, 1)]})

    def test_consecutive_fallback_observations_replay_from_checkpoint(self):
        agent, _ = self.agent_with_fake_pipeline()
        agent.consumer.previous = observation(9, rival_yield=5)
        agent._commit_seller_state()
        agent._remember_seller_fallback(observation(10, rival_yield=3))
        agent._remember_seller_fallback(observation(11, rival_yield=1))

        first = FakeSeller()
        agent.consumer = first
        agent._restore_seller_state()
        self.assertEqual(first.observe_calls, [10, 11])
        self.assertEqual(first.observed_harvests, {"WHEAT": [(10, 2), (11, 2)]})
        self.assertEqual(first.previous["step"], 11)

        # Reconstruction can be retried without accumulating duplicate history.
        second = FakeSeller()
        agent.consumer = second
        agent._restore_seller_state()
        self.assertEqual(second.observe_calls, [10, 11])
        self.assertEqual(second.observed_harvests, first.observed_harvests)
        agent._commit_seller_state()
        self.assertEqual(agent._seller_fallback_observations, [])

    def test_same_step_retry_is_one_observation_and_reorder_resets(self):
        agent, _ = self.agent_with_fake_pipeline()
        agent._remember_seller_fallback(observation(10, rival_yield=4))
        agent._remember_seller_fallback(observation(10, rival_yield=2))
        self.assertEqual(len(agent._seller_fallback_observations), 1)
        self.assertEqual(agent._seller_fallback_observations[0]["farms"][1]["tiles"][0][0]["yield_units"], 2)
        agent._remember_seller_fallback(observation(11, rival_yield=1))
        agent._remember_seller_fallback(observation(5, rival_yield=9))
        self.assertEqual([row["step"] for row in agent._seller_fallback_observations], [5])

    def test_nonfrozen_modes_do_not_checkpoint_seller_state(self):
        for mode in ("parent", "ordered"):
            with self.subTest(mode=mode):
                agent = MODULE.TitanAgent(MODULE.Features(consumer=mode, seed=False, funding=False))
                agent.consumer = FakeSeller()
                agent._remember_seller_fallback(observation(1))
                agent._commit_seller_state()
                self.assertEqual(agent._seller_fallback_observations, [])
                self.assertIsNone(agent._completed_seller_state)

    def test_prelude_fallback_is_queued_and_forces_reconstruction(self):
        agent = MODULE.TitanAgent(MODULE.Features(seed=False, funding=False))
        obs = observation(0, rival_yield=3)
        result = agent.act(obs, {"episodeSteps": 720}, entry_started=time.perf_counter() - 2.0)
        self.assertEqual(result, {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertFalse(agent.ready)
        self.assertEqual(agent.diagnostics["fallback_stage"], "entrypoint_prelude")
        self.assertEqual([row["step"] for row in agent._seller_fallback_observations], [0])

    def test_exit_expiry_does_not_commit_unreturned_transform_state(self):
        agent, action = self.agent_with_fake_pipeline()
        old = {
            "planned": {"WHEAT": [(2, 1)]},
            "pending": {"WHEAT": 1},
            "previous": MODULE.TitanAgent._seller_public_observation(observation(0, rival_yield=5)),
            "observed_harvests": {"WHEAT": [(0, 1)]},
        }
        agent._completed_seller_state = copy.deepcopy(old)
        MODULE.deadline._DeadlineTimer = ExitExpiryTimer
        result = agent.act(observation(1, rival_yield=3), {"episodeSteps": 720})
        self.assertEqual(result, action)
        self.assertEqual(agent.diagnostics["status"], "deadline_fallback")
        self.assertEqual(agent._completed_seller_state, old)
        self.assertEqual([row["step"] for row in agent._seller_fallback_observations], [1])
        self.assertFalse(agent.ready)

    def test_success_commits_completed_transform_state_after_timer_exit(self):
        agent, action = self.agent_with_fake_pipeline()
        MODULE.deadline._DeadlineTimer = PassiveTimer
        result = agent.act(observation(1, rival_yield=3), {"episodeSteps": 720})
        self.assertEqual(result, action)
        self.assertEqual(agent.diagnostics["status"], "completed")
        self.assertEqual(agent._completed_seller_state["planned"], {"WHEAT": [(2, 3)]})
        self.assertEqual(agent._completed_seller_state["pending"], {"WHEAT": 3})
        self.assertEqual(agent._seller_fallback_observations, [])
        self.assertEqual(agent.production.calls, 1)


if __name__ == "__main__":
    unittest.main()
