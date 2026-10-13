# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
COMPOSER_PATH = HERE / "compose_current_fertilizer_deadline.py"

spec = importlib.util.spec_from_file_location("fertdeadline_composer", COMPOSER_PATH)
composer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(composer)


class Controller:
    def __init__(self, route):
        self.R = {"case": route}
        self.cur = "case"


class FertilizerDeadlineComposerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "spatial_tempo.py").read_text(encoding="utf-8")
        cls.output = composer.compose(cls.source)
        baseline_ns = {"__name__": "fertdeadline_baseline"}
        patched_ns = {"__name__": "fertdeadline_patched"}
        exec(compile(cls.source, "spatial_tempo.py", "exec"), baseline_ns)
        exec(compile(cls.output, "spatial_tempo.py", "exec"), patched_ns)
        cls.BaselineSpatialTempo = baseline_ns["SpatialTempo"]
        cls.PatchedSpatialTempo = patched_ns["SpatialTempo"]

    def fixture(self, *, fed_today=True, consecutive_unfed=0):
        tile = {
            "kind": "COOP",
            "animal": "GOOSE",
            "yield_units": 0,
            "fertilizer_available": True,
            "fed_today": fed_today,
            "cared_today": False,
            "consecutive_unfed": consecutive_unfed,
        }
        board = [[None for _ in range(10)] for _ in range(10)]
        board[3][4] = tile
        farm = {"farmer": [4, 4], "hands": [[0, 0]], "tiles": board}
        private = {"shed": {"WHEAT": 5}, "inventories": [{}, {}], "seeds": {}}
        obs = {"step": 33, "day": 1, "hour": 9, "player": 0,
               "farms": [farm, deepcopy(farm)], "private": private}
        row = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
        route = [deepcopy(row) for _ in range(720)]
        return obs, route

    @staticmethod
    def mechanics():
        return SimpleNamespace(CROPS={}, PRODUCTS=("FERTILIZER", "WHEAT"))

    def owner(self, cls, *, enabled=True):
        owner = cls(self.mechanics(), pathing=False, tempo=False, idle_fertilizer=enabled)
        owner.configure({})
        return owner

    def collect(self, cls, obs, route, *, enabled=True):
        owner = self.owner(cls, enabled=enabled)
        controller = Controller(route)
        selected = deepcopy(route[obs["step"]])
        return owner, owner._collect_idle_fertilizer(obs, selected, controller, 48)

    def test_exact_current_source_and_one_line_postimage(self):
        self.assertEqual(composer.git_blob_sha(self.source), composer.EXPECTED_SOURCE_BLOB)
        self.assertEqual(self.source.count(composer.OLD), 1)
        self.assertNotIn(composer.OLD, self.output)
        self.assertEqual(self.output.count(composer.NEW), 1)
        self.assertEqual(len(self.output.splitlines()), len(self.source.splitlines()) - 1)

    def test_source_drift_fails_closed(self):
        drift = self.source.replace("not tile.get('fertilizer_available')",
                                    "tile.get('fertilizer_available') is not True", 1)
        with self.assertRaisesRegex(ValueError, "source drift"):
            composer.compose(drift)

    def test_healthy_fed_animal_becomes_deadline_collectible(self):
        obs, route = self.fixture(fed_today=True, consecutive_unfed=0)
        baseline, before = self.collect(self.BaselineSpatialTempo, deepcopy(obs), deepcopy(route))
        self.assertIsNone(before)
        self.assertEqual(baseline.plans, {})

        patched, after = self.collect(self.PatchedSpatialTempo, obs, route)
        self.assertIsNotNone(after)
        self.assertEqual(after["farmer"], ["NORTH"])
        self.assertEqual(patched.plans[0]["extra"]["tile"], (4, 3))
        self.assertEqual(patched.plans[0]["replacement"],
                         [["NORTH"], ["COLLECT_FERTILIZER"], ["SOUTH"], ["DROP"]])

    def test_surviving_unfed_day_zero_is_also_deadline_collectible(self):
        obs, route = self.fixture(fed_today=False, consecutive_unfed=0)
        _, after = self.collect(self.PatchedSpatialTempo, obs, route)
        self.assertIsNotNone(after)
        self.assertEqual(after["farmer"], ["NORTH"])

    def test_authored_future_collect_and_feed_still_own_the_tile(self):
        for op in ("COLLECT_FERTILIZER", "FEED"):
            with self.subTest(op=op):
                obs, route = self.fixture()
                obs["farms"][0]["hands"][0] = [4, 3]
                route[40]["hands"][0] = [op]
                owner, after = self.collect(self.PatchedSpatialTempo, obs, route)
                self.assertIsNone(after)
                self.assertEqual(owner.plans, {})

    def test_same_day_fertilizer_input_use_still_blocks_surplus_sale(self):
        obs, route = self.fixture()
        obs["farms"][0]["hands"][0] = [4, 3]
        route[40]["hands"][0] = ["PICKUP", "FERTILIZER", 1]
        owner, after = self.collect(self.PatchedSpatialTempo, obs, route)
        self.assertIsNone(after)
        self.assertEqual(owner.plans, {})

    def test_disabled_feature_is_identity_and_single_job_invariant_survives(self):
        obs, route = self.fixture()
        owner, after = self.collect(self.PatchedSpatialTempo, obs, route, enabled=False)
        self.assertIsNone(after)
        self.assertEqual(owner.plans, {})

        owner = self.owner(self.PatchedSpatialTempo)
        owner.plans = {0: {"kind": "idle_fertilizer"}}
        selected = deepcopy(route[33])
        self.assertIsNone(owner._collect_idle_fertilizer(obs, selected, Controller(route), 48))


if __name__ == "__main__":
    unittest.main()
