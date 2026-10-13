# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "overlay"))
import land_overlay as land


class DummyController:
    def __init__(self, routes):
        self.R = routes


class DummyAgent:
    def __init__(self, routes):
        self.controller = DummyController(routes)
        self.diagnostics = {}
        self.calls = 0

    def _initialize(self):
        self.calls += 1


class LandOverlayContracts(unittest.TestCase):
    @staticmethod
    def route(length=300):
        return [
            {"farmer": ["PASS"], "hands": [], "market": []}
            for _ in range(length)
        ]

    def test_exact_two_insertions_and_fallbacks_preserved(self):
        route = self.route()
        route[150]["market"] = [["BUY_LAND"]]
        route[265]["market"] = [["BUY_LAND"], ["BUY_SEED", "WHEAT", 2]]
        before = deepcopy(route)
        patched, report = land.patch_routes({"MAIN": route})
        self.assertEqual(report.insertions, 2)
        self.assertEqual(report.inserted_by_step, {"74": 1, "98": 1})
        self.assertEqual(patched["MAIN"][74]["market"], [["BUY_LAND"]])
        self.assertEqual(patched["MAIN"][98]["market"], [["BUY_LAND"]])
        self.assertEqual(patched["MAIN"][150], before[150])
        self.assertEqual(patched["MAIN"][265], before[265])
        self.assertEqual(route, before, "source route mutated")

    def test_copy_on_write_and_alias_preservation(self):
        shared = self.route()
        routes = {"a": shared, "b": shared}
        patched, report = land.patch_routes(routes)
        self.assertIs(routes["a"], shared)
        self.assertIs(patched["a"], patched["b"])
        self.assertIsNot(patched["a"], shared)
        self.assertIs(patched["a"][73], shared[73])
        self.assertIsNot(patched["a"][74], shared[74])
        self.assertIs(patched["a"][75], shared[75])
        self.assertEqual(shared[74]["market"], [])
        self.assertEqual(report.distinct_routes, 1)
        self.assertEqual(report.changed_routes, 1)
        self.assertEqual(report.insertions, 2)

    def test_duplicate_full_and_short_routes_fail_closed(self):
        duplicate = self.route()
        duplicate[74]["market"] = [["BUY_LAND"]]
        full = self.route()
        full[74]["market"] = [["PASS"]] * 10
        short = self.route(80)
        patched, report = land.patch_routes({"dup": duplicate, "full": full, "short": short})
        self.assertEqual(report.skipped_duplicate, 1)
        self.assertEqual(report.skipped_full, 1)
        self.assertEqual(report.skipped_short_route, 1)
        self.assertEqual(patched["dup"][74]["market"], [["BUY_LAND"]])
        self.assertEqual(patched["full"][74]["market"], [["PASS"]] * 10)
        self.assertEqual(len(patched["short"]), 80)

    def test_wrap_installs_before_first_production_and_only_once_per_controller(self):
        route = self.route()
        agent = DummyAgent({"MAIN": route})
        wrapped = land.wrap(agent)
        self.assertIs(wrapped, agent)
        agent._initialize()
        first = agent.controller.R
        agent._initialize()
        self.assertIs(agent.controller.R, first)
        self.assertEqual(agent.calls, 2)
        self.assertEqual(agent._land_7498_report.insertions, 2)

    def test_wrap_reinstalls_after_controller_replacement(self):
        agent = DummyAgent({"MAIN": self.route()})
        land.wrap(agent)
        agent._initialize()
        first_controller = agent.controller
        self.assertEqual(first_controller.R["MAIN"][74]["market"], [["BUY_LAND"]])

        replacement_source = self.route()
        agent.controller = DummyController({"MAIN": replacement_source})
        agent._initialize()

        self.assertIsNot(agent.controller, first_controller)
        self.assertEqual(agent.controller.R["MAIN"][74]["market"], [["BUY_LAND"]])
        self.assertEqual(agent.controller.R["MAIN"][98]["market"], [["BUY_LAND"]])
        self.assertEqual(replacement_source[74]["market"], [])
        self.assertIs(agent._land_7498_controller, agent.controller)

    def test_spatial_tempo_predecessor_preserves_buy_land_activation(self):
        """SpatialTempo captures pristine = controller.R before this overlay runs.
        Its wrapped act rebuilds routes from that capture and reassigns controller.R.
        In-place identity preservation is required so steps 74/98 still carry BUY_LAND.
        """
        class SpatialTempoLike:
            def __init__(self, controller):
                self.pristine = controller.R
                original_act = controller.act

                def act(obs=None):
                    routes = dict(self.pristine)
                    controller.R = routes
                    return original_act(obs)

                controller.act = act

        class ProducingController:
            def __init__(self, routes):
                self.R = routes
                self.seen = []

            def act(self, obs=None):
                self.seen.append(
                    (
                        self.R["MAIN"][74]["market"],
                        self.R["MAIN"][98]["market"],
                    )
                )
                return "ok"

        class Agent:
            def __init__(self):
                self.controller = None
                self.diagnostics = {}
                self.calls = 0

            def _initialize(self):
                self.calls += 1
                if self.controller is None:
                    source = LandOverlayContracts.route()
                    self.controller = ProducingController({"MAIN": source})
                    SpatialTempoLike(self.controller)

        agent = Agent()
        land.wrap(agent)
        agent._initialize()
        agent.controller.act({})
        self.assertEqual(
            agent.controller.seen[-1],
            ([["BUY_LAND"]], [["BUY_LAND"]]),
        )
        self.assertIs(agent.controller.R, agent._land_7498_controller.R)

        source2 = LandOverlayContracts.route()
        agent.controller = ProducingController({"MAIN": source2})
        SpatialTempoLike(agent.controller)
        agent._initialize()
        agent.controller.act({})
        self.assertEqual(
            agent.controller.seen[-1],
            ([["BUY_LAND"]], [["BUY_LAND"]]),
        )
        self.assertEqual(source2[74]["market"], [])

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(TypeError):
            land.patch_routes([])
        with self.assertRaises(ValueError):
            land.patch_routes({}, max_orders=0)
        with self.assertRaises(ValueError):
            land.patch_routes({}, land_steps=(74, 74))

    def test_official_extracted_buy_land_cost_and_order(self):
        mechanics_path = next(
            (ancestor / "mechanics.py" for ancestor in (ROOT, *ROOT.parents)
             if (ancestor / "mechanics.py").is_file()),
            None,
        )
        if mechanics_path is None:
            self.skipTest("official extracted mechanics.py is unavailable in this staging tree")
        spec = importlib.util.spec_from_file_location("land_test_mechanics", mechanics_path)
        mechanics = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mechanics)
        board = 10
        tiles = []
        for y in range(board):
            row = []
            for x in range(board):
                quadrant = ("N" if y < 5 else "S") + ("W" if x < 5 else "E")
                row.append(None if quadrant == "NW" else "LOCKED")
            tiles.append(row)
        farm = {
            "money": 4000,
            "unlocked_quadrants": ["NW"],
            "tiles": tiles,
            "farmer": [4, 4],
            "hands": [],
            "hires_today": 0,
        }
        mechanics._do_buy_land(farm, board)
        self.assertEqual(farm["unlocked_quadrants"], ["NW", "NE"])
        self.assertEqual(farm["money"], 3000)
        mechanics._do_buy_land(farm, board)
        self.assertEqual(farm["unlocked_quadrants"], ["NW", "NE", "SW"])
        self.assertEqual(farm["money"], 1000)
        self.assertIsNone(farm["tiles"][1][7])
        self.assertIsNone(farm["tiles"][7][1])


if __name__ == "__main__":
    unittest.main()
