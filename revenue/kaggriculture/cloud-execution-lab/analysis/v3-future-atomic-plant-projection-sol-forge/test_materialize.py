#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Predecessor-killing contracts for the future atomic PLANT repair packet."""
from __future__ import annotations

import ast
from contextlib import contextmanager
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "sol_forge_materialize", HERE / "materialize.py"
)
materialize = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(materialize)

LAB = materialize.LAB
MECHANICS_SOURCE = LAB / "mechanics.py"
OBSERVED_CLONE_SOURCE = LAB.parent / "cloud-runtime-pulse" / "observed_clone.py"
ARLENE_SOURCE = LAB / "reference" / "next-panel" / "vendor" / "arlene.py"
DECISION_SOURCE = LAB / "reference" / "decision" / "decision.py"
ENGINE_JSON_SOURCE = LAB / "reference" / "engine" / "kaggriculture.json"

MECHANICS_GIT_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"
OBSERVED_CLONE_GIT_BLOB = "f810d53193d3035655a36c21021e18ba1d415916"
ARLENE_GIT_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
DECISION_GIT_BLOB = "2931aa55831204fbb473ab85a6f5b81ec947fcf7"

EXACT_REPOSITORY_SOURCES = all(
    path.is_file()
    for path in (
        materialize.DEFAULT_SOURCE,
        materialize.DEFAULT_ENGINE,
        ENGINE_JSON_SOURCE,
        MECHANICS_SOURCE,
        OBSERVED_CLONE_SOURCE,
        ARLENE_SOURCE,
        DECISION_SOURCE,
    )
)


class FakeMechanics:
    """Small deterministic unit-stage model used only for packet unit tests."""

    @staticmethod
    def _inventory(private, actor):
        while len(private["inventories"]) <= actor:
            private["inventories"].append({})
        return private["inventories"][actor]

    @classmethod
    def _apply_unit_action(
        cls,
        farm,
        private,
        actor,
        action,
        board_size,
        day,
        turns_per_day,
        shed_capacity,
    ):
        farm.setdefault("calls", []).append(copy.deepcopy(action))
        if not isinstance(action, list) or not action:
            return
        op = action[0]
        if op == "PASS":
            return
        tile = farm["tiles"][actor]
        if op == "PLANT" and len(action) >= 2:
            crop = action[1]
            if tile is not None or private["seeds"].get(crop, 0) <= 0:
                return
            private["seeds"][crop] -= 1
            farm["tiles"][actor] = {"kind": "PLANT", "crop": crop}
            return
        if op == "BUILD_PASTURE":
            if tile is None:
                farm["tiles"][actor] = {"kind": "PASTURE"}
            return
        if op == "PLACE" and len(action) >= 2:
            animal = action[1]
            inv = cls._inventory(private, actor)
            if not (isinstance(tile, dict) and tile.get("kind") == "PASTURE"):
                return
            if inv.get(animal, 0) <= 0:
                return
            inv[animal] -= 1
            if inv[animal] == 0:
                del inv[animal]
            tile["animal"] = animal

    @staticmethod
    def _drop_inventories_to_shed(private, shed_capacity):
        for inv in private["inventories"]:
            for item in list(inv):
                while (
                    inv.get(item, 0) > 0
                    and sum(private["shed"].values()) < shed_capacity
                ):
                    inv[item] -= 1
                    private["shed"][item] = private["shed"].get(item, 0) + 1
                if inv.get(item, 0) == 0:
                    inv.pop(item, None)


def _helper_from(candidate: Path, mechanics=FakeMechanics):
    tree = ast.parse(candidate.read_text(encoding="utf-8"), filename=str(candidate))
    node = next(
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_apply_unit_packet"
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"m": mechanics}
    exec(compile(module, str(candidate), "exec"), namespace)
    return namespace["_apply_unit_packet"], tree


def _blank_state(*, wheat_seeds=1, carrot_seeds=0, cow=False, shed=0):
    farm = {"tiles": [None, None], "calls": []}
    private = {
        "seeds": {"WHEAT": wheat_seeds, "CARROT": carrot_seeds},
        "inventories": [{"COW": 1} if cow else {}, {}],
        "shed": {"WHEAT": shed, "COW": 0},
    }
    return farm, private


def _apply_old_sequential(farm, private, action):
    acts = [action.get("farmer", ["PASS"]), *action.get("hands", [])]
    for actor, selected in enumerate(acts):
        FakeMechanics._apply_unit_action(
            farm, private, actor, selected, 2, 0, 24, 10**6
        )


def _synthetic_scheduler_source() -> str:
    """Minimal exact-preimage source for publication safety contracts."""
    return (
        "from types import SimpleNamespace\n"
        "m=SimpleNamespace(_apply_unit_action=lambda *args:None)\n"
        "detached_json_value=lambda value:value\n"
        "parent=SimpleNamespace(PASS={})\n"
        + materialize.OLD_POST_UNITS
        + "\nclass SellScheduler:\n"
        "    def receipt_profile(self, route, now):\n"
        "        f={'tiles': []};p={'seeds': {}}\n"
        "        for t in range(now,now+1):\n"
        + materialize.OLD_FUTURE_PACKET
        + "        return True\n"
    )


@contextmanager
def _synthetic_binding(root: Path):
    source = root / "scheduler.py"
    engine = root / "engine.py"
    source.write_text(_synthetic_scheduler_source(), encoding="utf-8")
    engine.write_text("# synthetic bound engine\n", encoding="utf-8")
    with mock.patch.multiple(
        materialize,
        BASE_SCHEDULER_GIT_BLOB=materialize.git_blob(source.read_bytes()),
        OFFICIAL_ENGINE_GIT_BLOB=materialize.git_blob(engine.read_bytes()),
    ):
        yield source, engine


class MaterializerPublicationContracts(unittest.TestCase):
    def test_create_only_publication_has_exact_readback_and_no_temp_residue(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                output = root / "candidate.py"
                receipt_path = root / "receipt.json"
                receipt = materialize.materialize(
                    source, engine, output, receipt_path
                )
                self.assertEqual(
                    materialize.sha256(output.read_bytes()),
                    receipt["candidate"]["sha256"],
                )
                self.assertEqual(
                    json.loads(receipt_path.read_text(encoding="utf-8")), receipt
                )
                self.assertEqual(list(root.glob(".*.tmp")), [])
                self.assertEqual(
                    receipt["publication"]["mode"],
                    "atomic_create_only_hardlink",
                )

    def test_direct_candidate_source_alias_is_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                before = source.read_bytes()
                with self.assertRaisesRegex(
                    materialize.MaterializationError, "aliases immutable input"
                ):
                    materialize.materialize(source, engine, source, root / "r.json")
                self.assertEqual(source.read_bytes(), before)
                self.assertFalse((root / "r.json").exists())

    def test_direct_receipt_source_alias_is_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                before = source.read_bytes()
                with self.assertRaisesRegex(
                    materialize.MaterializationError, "aliases immutable input"
                ):
                    materialize.materialize(source, engine, root / "out.py", source)
                self.assertEqual(source.read_bytes(), before)
                self.assertFalse((root / "out.py").exists())

    def test_candidate_and_receipt_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                same = root / "same"
                with self.assertRaisesRegex(
                    materialize.MaterializationError,
                    "candidate output and receipt output alias",
                ):
                    materialize.materialize(source, engine, same, same)
                self.assertFalse(same.exists())

    def test_symlink_alias_to_source_is_rejected_without_damage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                before = source.read_bytes()
                alias = root / "candidate.py"
                try:
                    alias.symlink_to(source)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlinks unavailable: {exc}")
                with self.assertRaisesRegex(
                    materialize.MaterializationError, "aliases immutable input"
                ):
                    materialize.materialize(source, engine, alias, root / "r.json")
                self.assertEqual(source.read_bytes(), before)
                self.assertFalse((root / "r.json").exists())

    def test_hardlink_alias_to_source_is_rejected_without_damage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                before = source.read_bytes()
                alias = root / "candidate.py"
                try:
                    os.link(source, alias)
                except OSError as exc:
                    self.skipTest(f"hardlinks unavailable: {exc}")
                with self.assertRaisesRegex(
                    materialize.MaterializationError, "aliases immutable input"
                ):
                    materialize.materialize(source, engine, alias, root / "r.json")
                self.assertEqual(source.read_bytes(), before)
                self.assertFalse((root / "r.json").exists())

    def test_input_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                alias = root / "source-link.py"
                try:
                    alias.symlink_to(source)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlinks unavailable: {exc}")
                with self.assertRaisesRegex(
                    materialize.MaterializationError, "must not be a symlink"
                ):
                    materialize.materialize(
                        alias, engine, root / "out.py", root / "r.json"
                    )
                self.assertFalse((root / "out.py").exists())

    def test_preexisting_unrelated_target_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                output = root / "candidate.py"
                output.write_bytes(b"keep me")
                with self.assertRaisesRegex(
                    materialize.MaterializationError, "already exists"
                ):
                    materialize.materialize(
                        source, engine, output, root / "r.json"
                    )
                self.assertEqual(output.read_bytes(), b"keep me")

    def test_missing_target_parent_fails_without_creating_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                missing = root / "missing"
                with self.assertRaisesRegex(
                    materialize.MaterializationError, "parent must already exist"
                ):
                    materialize.materialize(
                        source,
                        engine,
                        missing / "out.py",
                        root / "receipt.json",
                    )
                self.assertFalse(missing.exists())

    def test_second_publication_failure_rolls_back_both_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                before_source = source.read_bytes()
                before_engine = engine.read_bytes()
                output = root / "candidate.py"
                receipt = root / "receipt.json"
                real_publish = materialize._publish_create_only
                calls = 0

                def fail_after_second_link(staged, target):
                    nonlocal calls
                    calls += 1
                    real_publish(staged, target)
                    if calls == 2:
                        raise OSError("injected after second publication")

                with mock.patch.object(
                    materialize,
                    "_publish_create_only",
                    side_effect=fail_after_second_link,
                ):
                    with self.assertRaisesRegex(
                        OSError, "injected after second publication"
                    ):
                        materialize.materialize(
                            source, engine, output, receipt
                        )
                self.assertFalse(output.exists())
                self.assertFalse(receipt.exists())
                self.assertEqual(source.read_bytes(), before_source)
                self.assertEqual(engine.read_bytes(), before_engine)
                self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_second_staging_failure_cleans_first_staging_inode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with _synthetic_binding(root) as (source, engine):
                real_stage = materialize._stage_bytes
                calls = 0

                def fail_second_stage(target, data):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise OSError("injected staging failure")
                    return real_stage(target, data)

                with mock.patch.object(
                    materialize, "_stage_bytes", side_effect=fail_second_stage
                ):
                    with self.assertRaisesRegex(OSError, "injected staging failure"):
                        materialize.materialize(
                            source,
                            engine,
                            root / "candidate.py",
                            root / "receipt.json",
                        )
                self.assertFalse((root / "candidate.py").exists())
                self.assertFalse((root / "receipt.json").exists())
                self.assertEqual(list(root.glob(".*.tmp")), [])


@unittest.skipUnless(
    materialize.DEFAULT_SOURCE.is_file() and materialize.DEFAULT_ENGINE.is_file(),
    "exact repository scheduler and engine are not present",
)
class FutureAtomicProjectionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / "candidate").mkdir()
        cls.candidate = cls.root / "candidate" / "scheduler.py"
        cls.receipt_path = cls.root / "candidate" / "RECEIPT.json"
        cls.source_before = materialize.DEFAULT_SOURCE.read_bytes()
        cls.engine_before = materialize.DEFAULT_ENGINE.read_bytes()
        cls.receipt = materialize.materialize(
            materialize.DEFAULT_SOURCE,
            materialize.DEFAULT_ENGINE,
            cls.candidate,
            cls.receipt_path,
        )
        helper, cls.tree = _helper_from(cls.candidate)
        cls.helper = staticmethod(helper)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def apply(self, farm, private, action):
        return self.helper(
            farm,
            private,
            action,
            board_size=2,
            day=0,
            turns_per_day=24,
            shed_capacity=10**6,
        )

    def test_exact_source_and_engine_are_bound(self):
        self.assertEqual(
            materialize.git_blob(materialize.DEFAULT_SOURCE.read_bytes()),
            materialize.BASE_SCHEDULER_GIT_BLOB,
        )
        self.assertEqual(
            materialize.git_blob(materialize.DEFAULT_ENGINE.read_bytes()),
            materialize.OFFICIAL_ENGINE_GIT_BLOB,
        )
        self.assertEqual(
            self.receipt["source_base_main"], materialize.SOURCE_BASE_MAIN
        )
        self.assertEqual(self.receipt["verified_main"], materialize.VERIFIED_MAIN)

    def test_oversubscribed_same_crop_blocks_every_request(self):
        farm, private = _blank_state(wheat_seeds=1)
        action = {
            "farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"]],
            "market": [],
        }
        before = copy.deepcopy(action)
        blocked = self.apply(farm, private, action)
        self.assertEqual(blocked, {"WHEAT"})
        self.assertEqual(private["seeds"]["WHEAT"], 1)
        self.assertEqual(farm["tiles"], [None, None])
        self.assertEqual(farm["calls"], [["PASS"], ["PASS"]])
        self.assertEqual(action, before)

    def test_exact_supply_plants_both_in_actor_order(self):
        farm, private = _blank_state(wheat_seeds=2)
        blocked = self.apply(
            farm,
            private,
            {
                "farmer": ["PLANT", "WHEAT"],
                "hands": [["PLANT", "WHEAT"]],
            },
        )
        self.assertEqual(blocked, set())
        self.assertEqual(private["seeds"]["WHEAT"], 0)
        self.assertEqual(
            [tile["crop"] for tile in farm["tiles"]], ["WHEAT", "WHEAT"]
        )

    def test_mixed_crop_blocks_only_the_oversubscribed_crop(self):
        farm, private = _blank_state(wheat_seeds=0, carrot_seeds=1)
        blocked = self.apply(
            farm,
            private,
            {
                "farmer": ["PLANT", "WHEAT"],
                "hands": [["PLANT", "CARROT"]],
            },
        )
        self.assertEqual(blocked, {"WHEAT"})
        self.assertIsNone(farm["tiles"][0])
        self.assertEqual(farm["tiles"][1]["crop"], "CARROT")
        self.assertEqual(private["seeds"]["CARROT"], 0)

    def test_predecessor_sequential_projection_is_killed(self):
        action = {
            "farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"]],
        }
        old_farm, old_private = _blank_state(wheat_seeds=1)
        new_farm, new_private = copy.deepcopy(old_farm), copy.deepcopy(old_private)
        _apply_old_sequential(old_farm, old_private, action)
        self.apply(new_farm, new_private, action)
        self.assertEqual(old_private["seeds"]["WHEAT"], 0)
        self.assertEqual(sum(tile is not None for tile in old_farm["tiles"]), 1)
        self.assertEqual(new_private["seeds"]["WHEAT"], 1)
        self.assertEqual(new_farm["tiles"], [None, None])

    def test_minimized_shed_capacity_to_sell_feasibility_witness(self):
        """False sequential plant blocks PLACE; carried cow then overfills at EOD."""
        oversubscribed = {
            "farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"]],
        }
        build = {"farmer": ["BUILD_PASTURE"], "hands": [["PASS"]]}
        place = {"farmer": ["PLACE", "COW"], "hands": [["PASS"]]}

        old_farm, old_private = _blank_state(wheat_seeds=1, cow=True, shed=99)
        new_farm, new_private = copy.deepcopy(old_farm), copy.deepcopy(old_private)
        _apply_old_sequential(old_farm, old_private, oversubscribed)
        self.apply(new_farm, new_private, oversubscribed)
        for packet in (build, place):
            _apply_old_sequential(old_farm, old_private, packet)
            self.apply(new_farm, new_private, packet)
        FakeMechanics._drop_inventories_to_shed(old_private, 10**6)
        FakeMechanics._drop_inventories_to_shed(new_private, 10**6)

        old_total = sum(old_private["shed"].values())
        new_total = sum(new_private["shed"].values())
        self.assertEqual((old_total, new_total), (100, 99))
        cap = 100
        self.assertFalse(not (old_total > cap - 1))
        self.assertTrue(not (new_total > cap - 1))

    def test_only_shared_primitive_directly_calls_unit_mechanics(self):
        owners = []
        functions = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "_apply_unit_action"
                and isinstance(func.value, ast.Name)
                and func.value.id == "m"
            ):
                continue
            containing = [fn for fn in functions if node in tuple(ast.walk(fn))]
            owners.append(min(containing, key=lambda fn: len(tuple(ast.walk(fn)))).name)
        self.assertEqual(owners, ["_apply_unit_packet"])

    def test_both_current_and_future_paths_use_shared_primitive(self):
        post = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "post_units"
        )
        scheduler_class = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.ClassDef) and node.name == "SellScheduler"
        )
        receipt = next(
            node
            for node in scheduler_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "receipt_profile"
        )

        def calls_named(node, name):
            return [
                call
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == name
            ]

        self.assertEqual(len(calls_named(post, "_apply_unit_packet")), 1)
        self.assertEqual(len(calls_named(receipt, "_apply_unit_packet")), 1)

    def test_materialization_is_deterministic_and_nonmutating(self):
        with tempfile.TemporaryDirectory() as other:
            other = Path(other)
            second_output = other / "scheduler.py"
            second_receipt = other / "receipt.json"
            receipt = materialize.materialize(
                materialize.DEFAULT_SOURCE,
                materialize.DEFAULT_ENGINE,
                second_output,
                second_receipt,
            )
            self.assertEqual(second_output.read_bytes(), self.candidate.read_bytes())
            self.assertEqual(
                receipt["candidate"]["git_blob"],
                self.receipt["candidate"]["git_blob"],
            )
            self.assertEqual(
                receipt["candidate"]["sha256"],
                self.receipt["candidate"]["sha256"],
            )
        self.assertEqual(materialize.DEFAULT_SOURCE.read_bytes(), self.source_before)
        self.assertEqual(materialize.DEFAULT_ENGINE.read_bytes(), self.engine_before)

    def test_source_drift_fails_before_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            drifted = temporary / "scheduler.py"
            drifted.write_bytes(
                materialize.DEFAULT_SOURCE.read_bytes() + b"# drift\n"
            )
            output = temporary / "candidate.py"
            with self.assertRaisesRegex(
                materialize.MaterializationError, "scheduler source drift"
            ):
                materialize.materialize(
                    drifted,
                    materialize.DEFAULT_ENGINE,
                    output,
                    temporary / "receipt.json",
                )
            self.assertFalse(output.exists())

    def test_receipt_is_strict_json_and_makes_no_strength_claim(self):
        parsed = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(parsed, self.receipt)
        self.assertFalse(parsed["canonical_source_mutated"])
        self.assertFalse(parsed["official_engine_mutated"])
        self.assertFalse(parsed["score_claim"])
        self.assertEqual(
            parsed["disposition"], "SOURCE_REAL_ACTION_UNMEASURED"
        )
        self.assertEqual(
            parsed["replacements"],
            {
                "future_receipt_profile_callsite": 1,
                "shared_atomic_unit_packet": 1,
            },
        )


def _load_official_engine():
    engine_name = "_sol_forge_official_engine"
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = lambda *args, **kwargs: 0
    package.utils = utils
    saved = {
        name: sys.modules.get(name)
        for name in ("kaggle_environments", "kaggle_environments.utils", engine_name)
    }
    try:
        sys.modules["kaggle_environments"] = package
        sys.modules["kaggle_environments.utils"] = utils
        spec = importlib.util.spec_from_file_location(
            engine_name, materialize.DEFAULT_ENGINE
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load pinned official engine")
        module = importlib.util.module_from_spec(spec)
        sys.modules[engine_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def _official_farm_private(engine, *, hands=1, seeds=None):
    farm = engine._new_farm(10, 1000)
    farm["farmer"] = [0, 0]
    farm["hands"] = [[1 + index, 0] for index in range(hands)]
    private = engine._new_private()
    private["inventories"] = [{} for _ in range(1 + hands)]
    for crop, quantity in dict(seeds or {}).items():
        private["seeds"][crop] = quantity
    return farm, private


def _run_official_unit_packet(engine, farm, private, action):
    observation = types.SimpleNamespace(
        farms=[farm],
        private=private,
        step=1,
        day=0,
        hour=1,
    )
    state = [
        types.SimpleNamespace(
            observation=observation,
            action=copy.deepcopy(action),
            status="ACTIVE",
            reward=0.0,
        )
    ]
    configuration = types.SimpleNamespace(
        turnsPerDay=24,
        boardSize=10,
        shedCapacity=100,
        episodeSteps=720,
    )
    environment = types.SimpleNamespace(done=False, configuration=configuration)
    with (
        mock.patch.object(engine, "_process_market", lambda _state, _env: None),
        mock.patch.object(engine, "_town_consume", lambda _env, _state, _step: None),
        mock.patch.object(engine, "_decay_plants", lambda _farm, _step: None),
        mock.patch.object(engine, "_end_of_day", lambda _state, _env, _day: None),
    ):
        engine.interpreter(state, environment)
    return farm, private


@unittest.skipUnless(EXACT_REPOSITORY_SOURCES, "complete repository source closure absent")
class OfficialEngineDifferentialContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.candidate = cls.root / "scheduler.py"
        cls.receipt = cls.root / "receipt.json"
        materialize.materialize(
            materialize.DEFAULT_SOURCE,
            materialize.DEFAULT_ENGINE,
            cls.candidate,
            cls.receipt,
        )
        cls.engine = _load_official_engine()
        cls.helper, _ = _helper_from(cls.candidate, cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_generated_packet_matches_actual_pinned_interpreter_on_2d_states(self):
        cases = (
            (
                "oversubscribed_same_crop",
                1,
                {"WHEAT": 1},
                {
                    "farmer": ["PLANT", "WHEAT"],
                    "hands": [["PLANT", "WHEAT"]],
                },
            ),
            (
                "exact_supply",
                1,
                {"WHEAT": 2},
                {
                    "farmer": ["PLANT", "WHEAT"],
                    "hands": [["PLANT", "WHEAT"]],
                },
            ),
            (
                "mixed_crop_independence",
                1,
                {"WHEAT": 0, "CARROT": 1},
                {
                    "farmer": ["PLANT", "WHEAT"],
                    "hands": [["PLANT", "CARROT"]],
                },
            ),
            (
                "phantom_hand_participates_in_atomic_demand",
                0,
                {"WHEAT": 1},
                {
                    "farmer": ["PLANT", "WHEAT"],
                    "hands": [["PLANT", "WHEAT"]],
                },
            ),
        )
        for name, hand_count, seeds, action in cases:
            with self.subTest(name=name):
                official_farm, official_private = _official_farm_private(
                    self.engine, hands=hand_count, seeds=seeds
                )
                candidate_farm = copy.deepcopy(official_farm)
                candidate_private = copy.deepcopy(official_private)
                _run_official_unit_packet(
                    self.engine, official_farm, official_private, action
                )
                self.helper(
                    candidate_farm,
                    candidate_private,
                    copy.deepcopy(action),
                    board_size=10,
                    day=0,
                    turns_per_day=24,
                    shed_capacity=100,
                )
                self.assertEqual(candidate_farm, official_farm)
                self.assertEqual(candidate_private, official_private)

    def test_real_engine_blob_is_the_bound_source(self):
        self.assertEqual(
            materialize.git_blob(Path(self.engine.__file__).read_bytes()),
            materialize.OFFICIAL_ENGINE_GIT_BLOB,
        )


def _copy_bound_file(source: Path, target: Path, expected_blob: str) -> None:
    data = source.read_bytes()
    actual = materialize.git_blob(data)
    if actual != expected_blob:
        raise AssertionError(
            f"source drift for {source}: expected {expected_blob}, got {actual}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


@contextmanager
def _import_scheduler_closure(scheduler_source: Path, root: Path, module_name: str):
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(scheduler_source, root / "scheduler.py")
    _copy_bound_file(MECHANICS_SOURCE, root / "mechanics.py", MECHANICS_GIT_BLOB)
    _copy_bound_file(
        OBSERVED_CLONE_SOURCE,
        root / "observed_clone.py",
        OBSERVED_CLONE_GIT_BLOB,
    )
    _copy_bound_file(
        ARLENE_SOURCE,
        root / "reference" / "next-panel" / "vendor" / "arlene.py",
        ARLENE_GIT_BLOB,
    )
    _copy_bound_file(
        DECISION_SOURCE,
        root / "reference" / "decision" / "decision.py",
        DECISION_GIT_BLOB,
    )

    names = (
        module_name,
        "mechanics",
        "observed_clone",
        "intact_arlene",
        "pinned_receipt_math",
    )
    saved = {name: sys.modules.get(name) for name in names}
    sys.path.insert(0, str(root))
    try:
        for name in names:
            sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(
            module_name, root / "scheduler.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load materialized scheduler closure")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        origins = {
            "scheduler": str(Path(module.__file__).resolve()),
            "mechanics": str(Path(module.m.__file__).resolve()),
            "observed_clone": str(
                Path(sys.modules["observed_clone"].__file__).resolve()
            ),
            "arlene": str(Path(module.parent.__file__).resolve()),
            "decision": str(Path(module.receipt_math.__file__).resolve()),
        }
        yield module, origins
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def _receipt_profile_witness(module):
    packet = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
    route = [copy.deepcopy(packet) for _ in range(24)]
    route[21] = {
        "farmer": ["PLANT", "WHEAT"],
        "hands": [["PLANT", "WHEAT"]],
        "market": [],
    }
    route[22] = {
        "farmer": ["BUILD_PASTURE"],
        "hands": [["PASS"]],
        "market": [],
    }
    route[23] = {
        "farmer": ["PLACE", "COW"],
        "hands": [["PASS"]],
        "market": [],
    }
    tiles = [[None for _ in range(10)] for _ in range(10)]
    farm = {
        "money": 1000.0,
        "tiles": tiles,
        "farmer": [0, 0],
        "hands": [[1, 0]],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    shed = {item: 0 for item in module.m.PRODUCTS + list(module.m.ANIMALS)}
    shed["WHEAT"] = 99
    seeds = {crop: 0 for crop in module.m.CROPS}
    seeds["WHEAT"] = 1
    private = {
        "shed": shed,
        "seeds": seeds,
        "inventories": [{"COW": 1}, {}],
    }
    obs = {
        "step": 20,
        "player": 0,
        "farms": [copy.deepcopy(farm)],
        "private": copy.deepcopy(private),
    }
    config = {"turnsPerDay": 24, "shedCapacity": 100}
    scheduler = module.SellScheduler()
    scheduler.controller.cur = "witness"
    scheduler.controller.R = {"witness": route}
    feasible = scheduler.receipt_profile(
        obs,
        copy.deepcopy(packet),
        copy.deepcopy(farm),
        copy.deepcopy(private),
        23,
        "EGG",
        config,
    )
    return feasible(((20, 0),))


@unittest.skipUnless(EXACT_REPOSITORY_SOURCES, "complete repository source closure absent")
class MaterializedReceiptProfileClosureContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.candidate = cls.root / "materialized" / "scheduler.py"
        cls.receipt = cls.root / "materialized" / "receipt.json"
        cls.candidate.parent.mkdir()
        materialize.materialize(
            materialize.DEFAULT_SOURCE,
            materialize.DEFAULT_ENGINE,
            cls.candidate,
            cls.receipt,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_import_closure_reaches_capacity_predicate_and_kills_predecessor(self):
        with _import_scheduler_closure(
            materialize.DEFAULT_SOURCE,
            self.root / "original-closure",
            "_sol_forge_original_scheduler",
        ) as (original, original_origins):
            predecessor_feasible = _receipt_profile_witness(original)
        with _import_scheduler_closure(
            self.candidate,
            self.root / "candidate-closure",
            "_sol_forge_candidate_scheduler",
        ) as (candidate, candidate_origins):
            repaired_feasible = _receipt_profile_witness(candidate)

        self.assertFalse(predecessor_feasible)
        self.assertTrue(repaired_feasible)
        for label, path in original_origins.items():
            self.assertTrue(
                Path(path).is_relative_to(self.root / "original-closure"),
                (label, path),
            )
        for label, path in candidate_origins.items():
            self.assertTrue(
                Path(path).is_relative_to(self.root / "candidate-closure"),
                (label, path),
            )

    def test_complete_closure_dependencies_are_exactly_bound(self):
        expected = {
            MECHANICS_SOURCE: MECHANICS_GIT_BLOB,
            OBSERVED_CLONE_SOURCE: OBSERVED_CLONE_GIT_BLOB,
            ARLENE_SOURCE: ARLENE_GIT_BLOB,
            DECISION_SOURCE: DECISION_GIT_BLOB,
        }
        self.assertEqual(
            {
                str(path): materialize.git_blob(path.read_bytes())
                for path in expected
            },
            {str(path): digest for path, digest in expected.items()},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
