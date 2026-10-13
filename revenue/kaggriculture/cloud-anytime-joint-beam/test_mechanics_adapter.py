# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import unittest

from joint_action_beam import BeamConfig, propose_worker_action, search_joint_actions
from mechanics_adapter import (
    MechanicsContext,
    ScoreContext,
    bounded_worker_candidates,
    mechanics_scorer,
    mechanics_transition,
    score_components,
)

HERE = Path(__file__).resolve().parent
MECHANICS_PATH = Path(os.environ.get(
    "S01_MECHANICS",
    HERE.parent / "cloud-execution-lab" / "mechanics.py",
))


def load_mechanics():
    spec = importlib.util.spec_from_file_location("s01_official_mechanics", MECHANICS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fixture(workers=2):
    board = 10
    pos = [1, 1]
    return {
        "farm": {
            "farmer": list(pos),
            "hands": [list(pos) for _ in range(max(0, workers - 1))],
            "tiles": [[None for _ in range(board)] for _ in range(board)],
            "money": 500,
        },
        "private": {
            "shed": {},
            "seeds": {"WHEAT": 1},
            "inventories": [{} for _ in range(workers)],
        },
        "market": {"inventory": {item: 10000 for item in (
            "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")}},
    }


class OfficialMechanicsAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_mechanics()
        cls.ctx = MechanicsContext(board_size=10, day=0, turns_per_day=24)
        cls.transition = staticmethod(mechanics_transition(cls.m, cls.ctx))
        cls.score = staticmethod(mechanics_scorer(cls.m))

    def test_atomic_plant_oversubscription_rolls_back_all_requests(self):
        initial = fixture(2)
        first = self.transition(initial, 0, ["PLANT", "WHEAT"])
        self.assertIsNotNone(first)
        self.assertEqual(0, first["private"]["seeds"]["WHEAT"])
        self.assertEqual("PLANT", first["farm"]["tiles"][1][1]["kind"])

        second = self.transition(first, 1, ["PLANT", "WHEAT"])
        self.assertIsNotNone(second)
        self.assertEqual(1, second["private"]["seeds"]["WHEAT"])
        self.assertIsNone(second["farm"]["tiles"][1][1])
        self.assertEqual(1, initial["private"]["seeds"]["WHEAT"])
        self.assertIsNone(initial["farm"]["tiles"][1][1])

    def test_illegal_plant_request_still_counts_toward_atomic_demand(self):
        initial = fixture(2)
        initial["farm"]["hands"][0] = [2, 1]
        initial["farm"]["tiles"][1][1] = {"kind": "COOP"}

        # The first request cannot plant on its occupied tile, but the official
        # prepass counts syntactic demand before checking per-worker legality.
        first = self.transition(initial, 0, ["PLANT", "WHEAT"])
        self.assertIsNotNone(first)
        self.assertEqual(1, first["private"]["seeds"]["WHEAT"])
        self.assertEqual({"kind": "COOP"}, first["farm"]["tiles"][1][1])
        self.assertIsNone(first["farm"]["tiles"][1][2])

        second = self.transition(first, 1, ["PLANT", "WHEAT"])
        self.assertIsNotNone(second)
        self.assertEqual(1, second["private"]["seeds"]["WHEAT"])
        self.assertEqual({"kind": "COOP"}, second["farm"]["tiles"][1][1])
        self.assertIsNone(second["farm"]["tiles"][1][2])

    def test_atomic_rollback_reactivates_downstream_action(self):
        initial = fixture(3)
        first = self.transition(initial, 0, ["PLANT", "WHEAT"])
        self.assertIsNotNone(first)

        # Sequentially, BUILD_COOP is a no-op because the tentative plant owns
        # the tile. It must still stay in the prefix: the third worker makes the
        # two PLANT requests oversubscribed, both become PASS before execution,
        # and BUILD_COOP is then legal in the official interpreter.
        second = self.transition(first, 1, ["BUILD_COOP"])
        self.assertIsNotNone(second)
        self.assertEqual("PLANT", second["farm"]["tiles"][1][1]["kind"])

        third = self.transition(second, 2, ["PLANT", "WHEAT"])
        self.assertIsNotNone(third)
        self.assertEqual({"kind": "COOP"}, third["farm"]["tiles"][1][1])
        self.assertEqual(1, third["private"]["seeds"]["WHEAT"])

    def test_lazy_replay_preserves_preplant_actions_and_worker_indices(self):
        initial = fixture(4)
        initial["farm"]["farmer"] = [0, 0]

        moved = self.transition(initial, 0, ["EAST"])
        self.assertIsNotNone(moved)
        self.assertEqual([1, 0], moved["farm"]["farmer"])

        planted = self.transition(moved, 1, ["PLANT", "WHEAT"])
        self.assertIsNotNone(planted)
        blocked_build = self.transition(planted, 2, ["BUILD_COOP"])
        self.assertIsNotNone(blocked_build)
        rolled_back = self.transition(blocked_build, 3, ["PLANT", "WHEAT"])
        self.assertIsNotNone(rolled_back)

        # Replay begins at worker 1 from the already-moved state. Rewinding to
        # worker 0 or enumerating the suffix from zero would place work wrongly.
        self.assertEqual([1, 0], rolled_back["farm"]["farmer"])
        self.assertEqual({"kind": "COOP"}, rolled_back["farm"]["tiles"][1][1])
        self.assertEqual(1, rolled_back["private"]["seeds"]["WHEAT"])

    def test_pruned_first_worker_of_next_turn_drops_stale_prefix(self):
        # Multi-turn successor reuse (documented): turn 1 leaves prefix metadata
        # in its successor. If turn 2's first worker action prunes, the stale
        # metadata must not survive to make turn 2's second worker raise.
        initial = fixture(2)
        initial["farm"]["farmer"] = [0, 0]
        first = self.transition(initial, 0, ["PLANT", "WHEAT"])
        self.assertIsNotNone(first)
        second = self.transition(first, 1, ["PASS"])
        self.assertIsNotNone(second)

        # Turn 2 on the reused successor: worker 0's off-board WEST prunes.
        pruned = self.transition(second, 0, ["WEST"])
        self.assertIsNone(pruned)
        # Worker 1 must start fresh instead of raising on the stale prefix.
        continued = self.transition(second, 1, ["EAST"])
        self.assertIsNotNone(continued)
        self.assertEqual([2, 1], continued["farm"]["hands"][0])

    def test_beam_resolves_shared_plant_demand_atomically(self):
        canonical = (["PASS"], ["PASS"])
        result = search_joint_actions(
            fixture(2), canonical,
            lambda state, idx, base: (["PLANT", "WHEAT"], ["PASS"]),
            self.transition, self.score,
            config=BeamConfig(width=24, depth=4, budget_ns=35_000_000),
        )
        self.assertIn(result.reason, {"complete", "deadline-during-search", "deadline-during-finalization"})
        if result.complete:
            self.assertEqual(1, sum(action == ["PLANT", "WHEAT"] for action in result.actions))
            replayed = fixture(2)
            for idx, action in enumerate(result.actions):
                replayed = self.transition(replayed, idx, action)
                self.assertIsNotNone(replayed)
            self.assertEqual(0, replayed["private"]["seeds"]["WHEAT"])
            self.assertEqual("PLANT", replayed["farm"]["tiles"][1][1]["kind"])
        else:
            self.assertEqual(canonical, result.actions)

    def test_existing_selected_work_is_canonical_only(self):
        state = fixture(1)
        # The generic one-stage score cannot safely reinterpret downstream route
        # or production intent. Only canonical PASS gets an alternative family.
        for action in (["WEST"], ["HARVEST"], ["PICKUP", "WHEAT", 1],
                       ["DROP"], ["PLACE", "WHEAT", 1]):
            self.assertEqual((), tuple(bounded_worker_candidates(self.m, state, 0, action)))

    def test_candidate_family_is_bounded_and_deterministic(self):
        state = fixture(1)
        first = tuple(bounded_worker_candidates(self.m, state, 0, ["PASS"]))
        second = tuple(bounded_worker_candidates(self.m, copy.deepcopy(state), 0, ["PASS"]))
        self.assertEqual(first, second)
        self.assertIn(["PLANT", "WHEAT"], first)
        self.assertIn(["BUILD_COOP"], first)
        self.assertLessEqual(len(first), 16)

    def test_scorer_rewards_real_production_and_watered_survival(self):
        initial = fixture(1)
        planted = self.transition(initial, 0, ["PLANT", "WHEAT"])
        self.assertIsNotNone(planted)
        planted_score = score_components(self.m, planted, ScoreContext())
        watered = self.transition(planted, 0, ["WATER"])
        self.assertIsNotNone(watered)
        watered_score = score_components(self.m, watered, ScoreContext())
        self.assertGreater(planted_score["production"], 0)
        self.assertGreater(watered_score["survival"], planted_score["survival"])

    def test_proposer_preserves_controller_market_fields(self):
        canonical = {
            "farmer": ["PASS"],
            "hands": [["PASS"]],
            "market": [["SELL", "WHEAT", 1], ["BUY_PRODUCT", "CARROT", 1]],
            "hire": 1,
            "buyLand": 0,
        }
        proposed, result = propose_worker_action(
            canonical,
            fixture(2),
            lambda state, idx, base: bounded_worker_candidates(self.m, state, idx, base),
            self.transition,
            self.score,
            config=BeamConfig(width=24, depth=4, budget_ns=35_000_000),
        )
        self.assertEqual(canonical["market"], proposed["market"])
        self.assertEqual(canonical["hire"], proposed["hire"])
        self.assertEqual(canonical["buyLand"], proposed["buyLand"])
        if result.used_fallback:
            self.assertEqual(canonical, proposed)


if __name__ == "__main__":
    unittest.main()
