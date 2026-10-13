"""Regression coverage for S11b leader-clone repair (#11467 / #11425 review)."""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BANK = ROOT.parent


def _load():
    spec = importlib.util.spec_from_file_location("spataro_clone", ROOT / "spataro_clone.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _tiles(w=4, h=4, fill=None):
    return [[fill for _ in range(w)] for _ in range(h)]


def _obs(*, day=0, step=0, farmer=(0, 0), tiles=None, money=5000, hands=None, shed=None, seeds=None):
    farm = {
        "tiles": tiles if tiles is not None else _tiles(),
        "farmer": farmer,
        "money": money,
        "hands": list(hands or []),
    }
    return {
        "player": 0,
        "day": day,
        "step": step,
        "farms": [farm],
        "private": {"shed": dict(shed or {}), "seeds": dict(seeds or {})},
    }


class SpataroCloneRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def test_syntax_and_replay_animal_targets(self):
        ast.parse((ROOT / "spataro_clone.py").read_text())
        self.assertEqual(self.mod.SHEEP_TARGET, 38)
        self.assertEqual(self.mod.COW_TARGET, 8)

    def test_day0_products_are_one_shot_not_repeated(self):
        step0 = self.mod.agent(_obs(day=0, step=0))
        products0 = [row for row in step0["market"] if row and row[0] == "BUY_PRODUCT"]
        self.assertGreaterEqual(len(products0), 1)
        for later in (1, 2, 3, 4):
            step_n = self.mod.agent(_obs(day=0, step=later))
            products_n = [row for row in step_n["market"] if row and row[0] == "BUY_PRODUCT"]
            self.assertEqual(products_n, [], msg=f"day0 step {later} repeated dump")

    def test_hire_after_dump_window(self):
        step1 = self.mod.agent(_obs(day=0, step=1, hands=[]))
        self.assertTrue(any(row and row[0] == "HIRE" for row in step1["market"]))

    def test_buy_land_at_recorded_step(self):
        got = self.mod.agent(_obs(day=3, step=74, money=2000))
        self.assertTrue(any(row and row[0] == "BUY_LAND" for row in got["market"]))

    def test_buy_animal_sheep_toward_full_target(self):
        got = self.mod.agent(_obs(day=1, step=25, money=5000))
        self.assertTrue(any(row[:2] == ["BUY_ANIMAL", "SHEEP"] for row in got["market"]))

    def test_feed_on_unfed_pasture(self):
        tiles = _tiles()
        tiles[0][0] = {"kind": "PASTURE", "animal": "SHEEP", "fed_today": False}
        got = self.mod.agent(_obs(tiles=tiles, farmer=(0, 0)))
        self.assertEqual(got["farmer"], ["FEED"])

    def test_build_pasture_when_shed_has_animals(self):
        got = self.mod.agent(_obs(shed={"SHEEP": 2}, farmer=(0, 0)))
        self.assertEqual(got["farmer"], ["BUILD_PASTURE"])

    def test_place_sheep_on_empty_pasture(self):
        tiles = _tiles()
        tiles[0][0] = {"kind": "PASTURE"}
        got = self.mod.agent(_obs(tiles=tiles, farmer=(0, 0), shed={"SHEEP": 1}))
        self.assertEqual(got["farmer"], ["PLACE", "SHEEP"])

    def test_source_quarantined_and_current_callable_blob(self):
        source = json.loads((ROOT / "SOURCE.json").read_text())
        self.assertEqual(source["status"], "quarantined")
        blob = subprocess.check_output(
            ["git", "hash-object", str(ROOT / "spataro_clone.py")],
            text=True,
        ).strip()
        self.assertEqual(source["callable_blob"], blob)
        self.assertEqual(source["reviewed_callable_blob"], "af0391ae32a2765a866afbdac8db1b437e200924")

    def test_not_admitted_to_active_manifest(self):
        manifest = json.loads((BANK / "MANIFEST.json").read_text())
        encoded = json.dumps(manifest)
        self.assertNotIn("leader-clones", encoded)
        self.assertNotIn("spataro_clone", encoded)


if __name__ == "__main__":
    unittest.main()
