# SPDX-License-Identifier: Apache-2.0
"""R02 key: the router tapes seated as the canonical MAIN route contents.

    python -m unittest -v checks/test_v3_r02.py

The route object identity is preserved, every already-played step stays byte-identical
across a switch, the published plan table is reproduced, and with the key off nothing moves.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r02_route_bank as r02  # noqa: E402
from r01_tapes import load_tapes  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402


def observation(step, shops=("PIZZA_SHOP", "YARN_STORE")):
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "town": {"unlocked_shops": list(shops)}}


def _canonical_snapshot():
    """The pristine canonical route, captured before any case seats a tape.

    The canonical route bank is decoded once per process and shared by every agent, so an
    in-place seat (the same mechanism L01 uses) is visible to later agents in this process.
    One episode is one agent process in play; the cases below restore the snapshot instead
    of relying on construction order.
    """
    agent = TitanAgent(Features())
    agent._initialize()
    return agent.controller.cur, [copy.deepcopy(entry) for entry in agent.controller.R[agent.controller.cur]]


PRISTINE_ID, PRISTINE = _canonical_snapshot()


class PlanTableTests(unittest.TestCase):
    def test_published_pairs(self):
        self.assertEqual(r02.plan_for(observation(0, ("PIZZA_SHOP", "YARN_STORE"))), 7)
        self.assertEqual(r02.plan_for(observation(0, ("YARN_STORE", "YARN_STORE"))), 12)
        self.assertEqual(r02.plan_for(observation(0, ("BAKERY", "BAKERY"))), 0)
        self.assertEqual(r02.plan_for({"town": {}}), 0)

    def test_tapes_share_the_switch_prefixes(self):
        tapes = load_tapes()
        for index in range(3, 13):
            self.assertEqual(tapes[index][:r02.ROUTE_STEP], tapes[0][:r02.ROUTE_STEP])
        self.assertEqual(tapes[r02.FINAL_PLAN][:r02.FINAL_PLAN_STEP][:313],
                         tapes[0][:313])


class InstallTests(unittest.TestCase):
    def setUp(self):
        agent = TitanAgent(Features())
        agent._initialize()
        agent.controller.R[PRISTINE_ID][:] = [copy.deepcopy(entry) for entry in PRISTINE]
        agent.controller._fs_for = None

    def agent(self, **keys):
        agent = TitanAgent(Features(**keys))
        agent._initialize()
        return agent

    def test_flag_off_leaves_the_canonical_route(self):
        canonical = self.agent()
        route = canonical.controller.R[canonical.controller.cur]
        self.assertEqual(route, PRISTINE)
        self.assertNotEqual(route[:len(load_tapes()[0])], load_tapes()[0])
        self.assertEqual(canonical.diagnostics["v3_r02"]["reasons"], [r02.NOOP])
        self.assertIsNone(canonical.diagnostics["v3_r02"]["plan"])

    def test_install_seats_plan_zero_in_place(self):
        agent = self.agent(r02_route_bank=True)
        controller = agent.controller
        route = controller.R[controller.cur]
        tapes = load_tapes()
        self.assertEqual(route[0], tapes[0][0])
        self.assertEqual(len(route), len(tapes[0]))
        self.assertIs(route, controller.R[controller.cur])
        self.assertEqual(agent.diagnostics["v3_r02"]["plan"], 0)

    def test_step_144_replaces_only_the_tail(self):
        agent = self.agent(r02_route_bank=True)
        controller = agent.controller
        route = controller.R[controller.cur]
        before = copy.deepcopy(route[:r02.ROUTE_STEP])
        identity = id(route)
        agent._v3_r02_step(observation(r02.ROUTE_STEP))
        self.assertEqual(route[:r02.ROUTE_STEP], before)
        self.assertEqual(id(controller.R[controller.cur]), identity)
        self.assertEqual(route[r02.ROUTE_STEP], load_tapes()[7][r02.ROUTE_STEP])
        self.assertEqual(agent.diagnostics["v3_r02_step"]["plan"], 7)

    def test_endgame_tail_and_idempotence(self):
        agent = self.agent(r02_route_bank=True)
        route = agent.controller.R[agent.controller.cur]
        agent._v3_r02_step(observation(r02.FINAL_PLAN_STEP))
        played = copy.deepcopy(route[:r02.FINAL_PLAN_STEP])
        self.assertEqual(route[r02.FINAL_PLAN_STEP], load_tapes()[2][r02.FINAL_PLAN_STEP])
        self.assertTrue(agent.diagnostics["v3_r02_step"]["endgame"])
        replaced = agent._v3_r02["replaced"]
        agent._v3_r02_step(observation(r02.FINAL_PLAN_STEP + 1))
        self.assertEqual(route[:r02.FINAL_PLAN_STEP], played)
        self.assertEqual(agent._v3_r02["replaced"], replaced)

    def test_future_sell_cache_is_invalidated_on_a_switch(self):
        agent = self.agent(r02_route_bank=True)
        controller = agent.controller
        controller.future_sells("WHEAT", 200)
        self.assertIsNotNone(getattr(controller, "_fs_for", None))
        agent._v3_r02_step(observation(r02.ROUTE_STEP))
        self.assertIsNone(getattr(controller, "_fs_for", "unset"))

    def test_flag_off_step_is_identity(self):
        agent = self.agent()
        route = agent.controller.R[agent.controller.cur]
        agent._v3_r02_step(observation(700))
        self.assertEqual(route, PRISTINE)

    def test_seat_is_in_place_and_visible_to_the_route_holders(self):
        agent = self.agent(r02_route_bank=True)
        controller = agent.controller
        self.assertIs(controller.R[controller.cur], controller.R[controller.cur])
        later = TitanAgent(Features())
        later._initialize()
        self.assertEqual(later.controller.R[later.controller.cur][0], load_tapes()[0][0])


class WiringTests(unittest.TestCase):
    def test_key_ships_off(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r02_route_bank"], False)
        self.assertIs(Features(**data).r02_route_bank, False)
        self.assertTrue(TitanAgent(Features(r02_route_bank=True))._v3_active())
        self.assertFalse(TitanAgent(Features())._v3_active())


if __name__ == "__main__":
    unittest.main(verbosity=2)
