# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from physical_fill import (
    END,
    EXPECTED_ENGINE_GIT_BLOB,
    EXPECTED_FROZEN_SELECTED_GIT_BLOB,
    EXPECTED_SCHEDULER_GIT_BLOB,
    NEW_METHOD,
    START,
    clip_requested_purchase,
    git_blob_sha1,
    git_blob_sha1_bytes,
    patch_scheduler_bytes,
)
from materialize import materialize
from compare import EXPECTED_SEEDS, compare
from trace_evaluator import transform as transform_evaluator

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]


class PureFactorTests(unittest.TestCase):
    def test_capacity_clip(self):
        self.assertEqual(clip_requested_purchase(3, 4, 2), 1)
        self.assertEqual(clip_requested_purchase(4, 4, 2), 0)
        self.assertEqual(clip_requested_purchase(5, 4, 2), 0)
        self.assertEqual(clip_requested_purchase(1, 4, -2), 0)

    def test_exact_method_patch_and_source_drift(self):
        source = b"prefix\n" + START + b"        return None\n" + END + b"suffix\n"
        expected = git_blob_sha1_bytes(source)
        candidate, receipt = patch_scheduler_bytes(source, expected_git_blob=expected)
        self.assertNotEqual(source, candidate)
        self.assertIn(NEW_METHOD, candidate)
        self.assertEqual(candidate.count(START), 1)
        self.assertEqual(receipt["predecessor_git_blob"], expected)
        with self.assertRaisesRegex(RuntimeError, "source drift"):
            patch_scheduler_bytes(source, expected_git_blob="0" * 40)

    def test_replacement_method_is_valid_class_syntax(self):
        ast.parse((b"class Probe:\n" + NEW_METHOD + b"    def act(self):\n        pass\n").decode("utf-8"))

    def test_method_anchor_ambiguity_fails_closed(self):
        source = START + b" pass\n" + END + START + b" pass\n"
        with self.assertRaisesRegex(RuntimeError, "cardinality drift"):
            patch_scheduler_bytes(source, expected_git_blob=git_blob_sha1_bytes(source))

    def test_evaluator_trace_patch_fails_closed_on_drift(self):
        path = LAB.parent / "cloud-eval" / "evaluate.py"
        if not path.is_file():
            self.skipTest("repository evaluator unavailable in local scratch layout")
        source = path.read_bytes()
        patched = transform_evaluator(source)
        self.assertIn(b"tested_action_sha256", patched)
        with self.assertRaisesRegex(RuntimeError, "evaluator source drift"):
            transform_evaluator(source + b"\n")


class ComparatorContractTests(unittest.TestCase):
    @staticmethod
    def _report(*, changed_key=None, own_delta=0.0):
        games = []
        for opponent in ("arlene", "v1"):
            for seed in EXPECTED_SEEDS:
                for seat in (0, 1):
                    key = (opponent, seed, seat)
                    changed = key == changed_key
                    scores = [100.0, 90.0]
                    scores[seat] += own_delta if changed else 0.0
                    games.append({
                        "opponent": opponent,
                        "seed": seed,
                        "candidate_seat": seat,
                        "status": "complete",
                        "failure": None,
                        "steps": 719,
                        "episode_steps": 720,
                        "tested_action_count": 719,
                        "tested_action_sha256": ("b" if changed else "a") * 64,
                        "trace_sha256": ("d" if changed else "c") * 64,
                        "scores": scores,
                    })
        return {
            "engine_ref": "engine",
            "engine_sha256": {"kaggriculture.py": "0" * 64},
            "loader_sha256": "1" * 64,
            "evaluator_sha256": "2" * 64,
            "seeds": list(EXPECTED_SEEDS),
            "agent_rng_seed": 20260907,
            "candidate": {"entry": "main.py", "callable": "agent", "sha256": "3" * 64},
            "opponents": {"arlene": {"sha256": "4" * 64}, "v1": {"sha256": "5" * 64}},
            "progress": {"state": "complete"},
            "games": games,
        }

    def test_changed_score_cells_is_a_count_not_delta_sum(self):
        key = ("arlene", EXPECTED_SEEDS[0], 0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            control = self._report()
            candidate = self._report(changed_key=key, own_delta=7.0)
            a = root / "control.json"; b = root / "candidate.json"
            a.write_text(json.dumps(control), encoding="utf-8")
            b.write_text(json.dumps(candidate), encoding="utf-8")
            result = compare(a, b)
        self.assertEqual(result["activated_cells"], 1)
        self.assertEqual(result["changed_score_cells"], 1)
        self.assertEqual(result["mean_own_delta_activated"], 7.0)
        self.assertEqual(result["verdict"], "MORE_EVIDENCE")

    def test_closed_loop_change_without_tested_action_divergence_is_rejected(self):
        key = ("v1", EXPECTED_SEEDS[1], 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            control = self._report()
            candidate = self._report(changed_key=key, own_delta=1.0)
            changed = next(
                game for game in candidate["games"]
                if (game["opponent"], game["seed"], game["candidate_seat"]) == key
            )
            changed["tested_action_sha256"] = "a" * 64
            a = root / "control.json"; b = root / "candidate.json"
            a.write_text(json.dumps(control), encoding="utf-8")
            b.write_text(json.dumps(candidate), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "without tested action divergence"):
                compare(a, b)


@unittest.skipUnless((LAB / "exports" / "titan-current.tar.gz").is_file(), "canonical archive unavailable")
class ExactArchiveTests(unittest.TestCase):
    def test_materialization_changes_only_scheduler_and_binds_sources(self):
        self.assertEqual(git_blob_sha1(LAB / "scheduler.py"), EXPECTED_SCHEDULER_GIT_BLOB)
        self.assertEqual(git_blob_sha1(LAB / "frozen_selected.py"), EXPECTED_FROZEN_SELECTED_GIT_BLOB)
        self.assertEqual(
            git_blob_sha1(LAB / "reference" / "engine" / "kaggriculture.py"),
            EXPECTED_ENGINE_GIT_BLOB,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "arms"
            receipt = materialize(root)
            self.assertEqual(receipt["candidate"]["changed_members"], ["scheduler.py"])
            self.assertEqual(
                receipt["candidate"]["patch"]["predecessor_git_blob"],
                EXPECTED_SCHEDULER_GIT_BLOB,
            )
            control = root / "control" / "scheduler.py"
            candidate = root / "candidate" / "scheduler.py"
            self.assertNotEqual(control.read_bytes(), candidate.read_bytes())
            self.assertEqual(control.read_bytes().count(START), 1)
            self.assertEqual(candidate.read_bytes().count(NEW_METHOD), 1)

    def _probe(
        self,
        arm: Path,
        *,
        route: list[dict],
        plan: tuple[tuple[int, int], ...],
        max_orders: int = 10,
    ) -> bool:
        code = textwrap.dedent(
            f"""
            import copy, json, sys
            from types import SimpleNamespace
            sys.path.insert(0, {str(arm)!r})
            import frozen_selected, scheduler

            route = {route!r}
            plan = {plan!r}
            obj = object.__new__(frozen_selected.FrozenSelected)
            obj.controller = SimpleNamespace(cur=0, R=[route])
            farm = {{'money':1000,'hires_today':0,'unlocked_quadrants':['NW'],
                    'hands':[],'tiles':[[None for _ in range(10)] for _ in range(10)]}}
            names = ['WHEAT','CARROT','TOMATO','STRAWBERRY','MELON','EGG','MILK','WOOL',
                     'FERTILIZER','GOOSE','COW','SHEEP']
            shed = {{name:0 for name in names}}; shed['CARROT']=3
            private = {{'shed':shed,'seeds':{{}},'inventories':[{{}}]}}
            original_post = scheduler.post_units
            original_apply = scheduler.m._apply_unit_action
            scheduler.post_units = lambda *_a, **_k: (copy.deepcopy(farm), copy.deepcopy(private))
            def projected_apply(f,p,i,a,*_args,**_kwargs):
                if isinstance(a,list) and a and a[0]=='INJECT':
                    p['shed'][a[1]]=p['shed'].get(a[1],0)+int(a[2])
            scheduler.m._apply_unit_action = projected_apply
            try:
                feasible = obj.receipt_profile(
                    {{'step':0}}, {{'farmer':['PASS'],'hands':[],'market':[]}},
                    farm, private, len(route)-1, 'CARROT',
                    {{'shedCapacity':4,'maxMarketOrdersPerTurn':{max_orders}}})
                result = bool(feasible(plan))
            finally:
                scheduler.post_units = original_post
                scheduler.m._apply_unit_action = original_apply
            print(json.dumps(result))
            """
        )
        output = subprocess.check_output([sys.executable, "-I", "-c", code], text=True)
        return bool(json.loads(output))

    @staticmethod
    def _route(*, rows: list[list], farmer_at_one: list | None = None, tail_farmer: list | None = None):
        return [
            {"farmer": ["PASS"], "hands": [], "market": []},
            {"farmer": farmer_at_one or ["PASS"], "hands": [], "market": rows},
            {"farmer": tail_farmer or ["PASS"], "hands": [], "market": []},
        ]

    def test_active_animal_request_cannot_invent_second_unit(self):
        route = self._route(rows=[["BUY_ANIMAL", "GOOSE", 2]])
        plan = ((0, 0), (1, 1), (2, 2))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "arms"; materialize(root)
            self.assertFalse(self._probe(root / "control", route=route, plan=plan))
            self.assertTrue(self._probe(root / "candidate", route=route, plan=plan))

    def test_active_product_request_obeys_same_capacity_boundary(self):
        route = self._route(rows=[["BUY_PRODUCT", "WHEAT", 2]])
        plan = ((0, 0), (1, 1), (2, 2))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "arms"; materialize(root)
            self.assertFalse(self._probe(root / "control", route=route, plan=plan))
            self.assertTrue(self._probe(root / "candidate", route=route, plan=plan))

    def test_same_turn_target_sale_order_controls_purchase_room(self):
        sale_before = self._route(rows=[
            ["SELL", "CARROT", 1], ["BUY_ANIMAL", "GOOSE", 2]
        ])
        purchase_before = self._route(rows=[
            ["BUY_ANIMAL", "GOOSE", 2], ["SELL", "CARROT", 1]
        ])
        plan = ((0, 0), (1, 1), (2, 2))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "arms"; materialize(root)
            # Selling first creates room for both requested animals, so one sale
            # does not preserve the existing one-slot reserve.
            self.assertFalse(self._probe(root / "candidate", route=sale_before, plan=plan))
            # Buying first clips at one unit; the later target sale restores the reserve.
            self.assertTrue(self._probe(root / "candidate", route=purchase_before, plan=plan))

    def test_engine_inactive_suffix_remains_predecessor_owned(self):
        route = self._route(rows=[[], ["BUY_ANIMAL", "GOOSE", 2]])
        plan = ((0, 0), (1, 1), (2, 2))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "arms"; materialize(root)
            control = self._probe(root / "control", route=route, plan=plan, max_orders=1)
            candidate = self._probe(root / "candidate", route=route, plan=plan, max_orders=1)
            self.assertFalse(control)
            self.assertEqual(candidate, control)

    def test_later_purchase_item_pickup_fails_closed_to_predecessor(self):
        route = self._route(
            rows=[["BUY_ANIMAL", "GOOSE", 2]],
            tail_farmer=["PICKUP", "GOOSE", 1],
        )
        plan = ((0, 0), (1, 1), (2, 2))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "arms"; materialize(root)
            control = self._probe(root / "control", route=route, plan=plan)
            candidate = self._probe(root / "candidate", route=route, plan=plan)
            self.assertFalse(control)
            self.assertEqual(candidate, control)

    def test_unit_stage_overflow_is_still_visible_before_market(self):
        route = self._route(
            rows=[],
            farmer_at_one=["INJECT", "MILK", 2],
        )
        route[2]["market"] = [["BUY_ANIMAL", "GOOSE", 2]]
        plan = ((0, 0), (1, 2), (2, 1))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "arms"; materialize(root)
            self.assertFalse(self._probe(root / "candidate", route=route, plan=plan))

    def test_official_engine_commits_only_physical_active_purchase_units(self):
        engine_path = LAB / "reference" / "engine" / "kaggriculture.py"
        spec = importlib.util.spec_from_file_location("_active_fill_engine", engine_path)
        self.assertIsNotNone(spec); self.assertIsNotNone(spec.loader)
        engine = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = engine
        spec.loader.exec_module(engine)

        from types import SimpleNamespace
        for order, item in (
            (["BUY_ANIMAL", "GOOSE", 2], "GOOSE"),
            (["BUY_PRODUCT", "WHEAT", 2], "WHEAT"),
        ):
            farms = [engine._new_farm(10, 1000), engine._new_farm(10, 1000)]
            privates = [engine._new_private(), engine._new_private()]
            privates[0]["shed"]["CARROT"] = 3
            market = engine._new_market()
            states = [
                SimpleNamespace(action={"market": [order]}, observation=SimpleNamespace(private=privates[0])),
                SimpleNamespace(action={"market": []}, observation=SimpleNamespace(private=privates[1])),
            ]
            states[0].observation.market = market
            states[0].observation.farms = farms
            env = SimpleNamespace(configuration={
                "boardSize": 10, "maxMarketOrdersPerTurn": 10,
                "farmHandCostMult": 1, "shedCapacity": 4,
            })
            engine._process_market(states, env)
            self.assertEqual(privates[0]["shed"][item], 1)
            self.assertEqual(sum(privates[0]["shed"].values()), 4)


if __name__ == "__main__":
    unittest.main()
