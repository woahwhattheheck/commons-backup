from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
RUNTIME = LAB.parent / "cloud-runtime-pulse"
SOURCE = LAB / "scheduler.py"

import materialize as subject

DIRECT_DEPENDENCY_BLOBS = (
    ("scheduler", SOURCE, "a483b24dd72b580d7d8811636b54d2d44f391575"),
    ("mechanics", LAB / "mechanics.py", "044a4f9c0a4a44dde10ada57563238bcaf82075d"),
    (
        "observed_clone",
        RUNTIME / "observed_clone.py",
        "f810d53193d3035655a36c21021e18ba1d415916",
    ),
    (
        "arlene",
        LAB / "reference" / "next-panel" / "vendor" / "arlene.py",
        "bdb9cf58148a3c7961c085f4902759537decabf6",
    ),
    (
        "decision",
        LAB / "reference" / "decision" / "decision.py",
        "2931aa55831204fbb473ab85a6f5b81ec947fcf7",
    ),
)


def _assert_direct_dependency_identity() -> None:
    mismatches = []
    for label, path, expected in DIRECT_DEPENDENCY_BLOBS:
        try:
            actual = subject.git_blob_sha1(path.read_bytes())
        except OSError as exc:
            mismatches.append(f"{label}: unreadable {path}: {exc}")
            continue
        if actual != expected:
            mismatches.append(f"{label}: expected {expected}, got {actual}")
    if mismatches:
        raise AssertionError("direct dependency closure drift:\n" + "\n".join(mismatches))


def setUpModule() -> None:
    # Fail before importing either scheduler if any direct theorem input drifts.
    _assert_direct_dependency_identity()


def _mirror(source: Path, destination: Path) -> None:
    try:
        destination.symlink_to(source, target_is_directory=source.is_dir())
    except (NotImplementedError, OSError):
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)


def _patched_root(parent: Path) -> tuple[Path, dict]:
    root = parent / "patched-lab"
    root.mkdir()
    _mirror(LAB / "mechanics.py", root / "mechanics.py")
    _mirror(RUNTIME / "observed_clone.py", root / "observed_clone.py")
    _mirror(LAB / "reference", root / "reference")
    receipt = subject.materialize(SOURCE, root / "scheduler.py")
    return root, receipt


def _load_scheduler(root: Path, name: str) -> types.ModuleType:
    path = root / "scheduler.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    previous_path = list(sys.path)
    displaced = {
        key: sys.modules.pop(key, None)
        for key in ("mechanics", "observed_clone", name)
    }
    try:
        # Current source imports observed_clone from cloud-runtime-pulse, while
        # the materialized mirror co-locates the exact helper with scheduler.py.
        for search_root in (RUNTIME, root):
            sys.path.insert(0, str(search_root))
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = previous_path
        sys.modules.pop(name, None)
        for key in ("mechanics", "observed_clone"):
            sys.modules.pop(key, None)
        for key, value in displaced.items():
            if value is not None:
                sys.modules[key] = value
    return module


def _negative_forced_witness(module: types.ModuleType):
    return module.optimize_lot(
        item="WOOL",
        quantity=1,
        inventory=10058,
        params=None,
        shops=["YARN_STORE"] * 8,
        config={},
        now=576,
        dates=[576, 577],
        reference=((576, 0), (577, 1)),
        rival_quantity=0,
        minimum_now=0,
        capacity_ok=lambda plan: dict(plan).get(576, 0) >= 1,
        last=718,
    )


class FakeController:
    def __init__(self):
        self.cur = 0
        route = [
            {"farmer": ["PASS"], "hands": [], "market": []}
            for _ in range(720)
        ]
        self.R = [route]

    def act(self, _observation):
        return {"farmer": ["PASS"], "hands": [], "market": []}


def _selected_product(
    module: types.ModuleType,
    rows: dict[str, tuple[float, bool, float]],
) -> str | None:
    module.parent.Agent = FakeController
    module.parent.DECISIONS = []
    module.absorption = lambda *_args, **_kwargs: 1

    shed = {item: 1 for item in rows}
    farm = {
        "money": 100,
        "hires_today": 0,
        "unlocked_quadrants": [0],
        "tiles": [],
        "hands": [],
    }
    private = {"shed": shed, "seeds": {}, "inventories": []}
    module.post_units = lambda *_args, **_kwargs: (
        copy.deepcopy(farm),
        copy.deepcopy(private),
    )

    def fake_optimize(*, item, now, **_kwargs):
        gain, forced, own_gain = rows[item]
        return (
            ((now, 1),),
            {
                "item": item,
                "plan": [(now, 1)],
                "worst_relative_gain": gain,
                "worst_own_gain": own_gain,
                "forced_feasibility": forced,
            },
        )

    module.optimize_lot = fake_optimize
    policy = module.SellScheduler()
    policy.cash_reserve = lambda *_args, **_kwargs: 0
    policy.receipt_profile = lambda *_args, **_kwargs: (lambda _plan: True)
    policy.rival_supply = lambda *_args, **_kwargs: 0

    observation = {
        "step": 0,
        "player": 0,
        "farms": [{}, {}],
        "private": copy.deepcopy(private),
        "market": {
            "inventory": {item: 1000 for item in rows},
            "params": None,
        },
        "town": {"unlocked_shops": []},
    }
    action = policy.act(
        observation,
        {
            "episodeSteps": 720,
            "turnsPerDay": 24,
            "shedCapacity": 100,
            "maxMarketOrdersPerTurn": 10,
        },
    )
    sales = [
        row
        for row in action["market"]
        if row and row[0] == "SELL" and int(row[2]) > 0
    ]
    if not sales:
        return None
    if len(sales) != 1:
        raise AssertionError(f"expected at most one selected sale, got {sales!r}")
    return str(sales[0][1])


class MaterializationContracts(unittest.TestCase):
    def test_direct_import_dependencies_are_exact(self):
        _assert_direct_dependency_identity()

    def test_exact_current_source_materializes_five_bound_replacements(self):
        before = SOURCE.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scheduler.py"
            receipt = subject.materialize(SOURCE, output)
            self.assertEqual(receipt["operation"], subject.OPERATION)
            self.assertEqual(
                receipt["source"]["git_blob_sha1"],
                subject.EXPECTED_SOURCE_BLOB,
            )
            self.assertEqual(
                receipt["repair"]["kind"],
                "forced_feasibility_economic_floor",
            )
            self.assertEqual(len(receipt["repair"]["replacements"]), 5)
            self.assertTrue(receipt["repair"]["properties"]["negative_forced_plan_ineligible"])
            self.assertFalse(receipt["repair"]["properties"]["canonical_state_mutated"])
            patched = output.read_text(encoding="utf-8")
            for _label, old, new in subject.REPLACEMENTS:
                self.assertNotIn(old, patched)
                self.assertEqual(patched.count(new), 1)
        self.assertEqual(SOURCE.read_bytes(), before)

    def test_wrong_source_blob_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scheduler.py"
            source.write_bytes(SOURCE.read_bytes() + b"\n# drift\n")
            with self.assertRaises(subject.MaterializeError):
                subject.materialize(source, root / "output.py")

    def test_duplicate_replacement_needle_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scheduler.py"
            data = SOURCE.read_bytes() + subject.INITIAL_STATE_OLD.encode("utf-8")
            source.write_bytes(data)
            with self.assertRaises(subject.MaterializeError):
                subject.materialize(
                    source,
                    root / "output.py",
                    expected_source_blob=subject.git_blob_sha1(data),
                )

    def test_cli_rejects_receipt_aliasing_source_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.py"
            source.write_bytes(SOURCE.read_bytes())
            output = root / "output.py"
            before = source.read_bytes()
            with self.assertRaises(subject.MaterializeError):
                subject.main([
                    "--source", str(source),
                    "--output", str(output),
                    "--receipt", str(source),
                ])
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(output.exists())

    def test_cli_rejects_receipt_aliasing_output_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.py"
            source.write_bytes(SOURCE.read_bytes())
            output = root / "output.py"
            with self.assertRaises(subject.MaterializeError):
                subject.main([
                    "--source", str(source),
                    "--output", str(output),
                    "--receipt", str(output),
                ])
            self.assertFalse(output.exists())

    def test_cli_rejects_symlinked_parent_destination_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.py"
            source.write_bytes(SOURCE.read_bytes())
            real = root / "real"
            alias = root / "alias"
            real.mkdir()
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")
            output = real / "output.py"
            receipt = alias / "output.py"
            with self.assertRaises(subject.MaterializeError):
                subject.main([
                    "--source", str(source),
                    "--output", str(output),
                    "--receipt", str(receipt),
                ])
            self.assertFalse(output.exists())


class EconomicFloorContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root, cls.receipt = _patched_root(Path(cls.temporary.name))
        cls.control = _load_scheduler(LAB, "titan_economic_floor_control")
        cls.repaired = _load_scheduler(root, "titan_economic_floor_repaired")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_exact_minus_97_current_source_predecessor_is_rejected(self):
        control_plan, control = _negative_forced_witness(self.control)
        repaired_plan, repaired = _negative_forced_witness(self.repaired)

        self.assertEqual(control_plan, ((576, 1),))
        self.assertTrue(control["forced_feasibility"])
        self.assertTrue(control["feasible"])
        self.assertEqual(control["worst_relative_gain"], -97.0)
        self.assertEqual(
            {
                name: row["own_receipts"]
                for name, row in control["scenarios"].items()
            },
            {
                "no_rival": 5,
                "observed_paired": 5,
                "observed_later_order": 5,
                "observed_next_turn": 5,
            },
        )

        self.assertEqual(repaired_plan, ((576, 0), (577, 1)))
        self.assertFalse(repaired["forced_feasibility"])
        self.assertFalse(repaired["feasible"])
        self.assertFalse(repaired["reference_feasible"])
        self.assertTrue(repaired["physical_feasible_found"])
        self.assertGreaterEqual(repaired["economic_floor_rejections"], 1)
        self.assertEqual(repaired["worst_relative_gain"], 0.0)
        self.assertEqual(repaired["worst_own_gain"], 0.0)

    def test_negative_forced_candidate_cannot_beat_positive_product(self):
        rows = {
            "CARROT": (-5.0, True, -5.0),
            "MILK": (1.0, False, 1.0),
        }
        self.assertEqual(_selected_product(self.control, rows), "CARROT")
        self.assertEqual(_selected_product(self.repaired, rows), "MILK")

    def test_zero_forced_candidate_cannot_starve_positive_product(self):
        rows = {
            "CARROT": (0.0, True, 0.0),
            "MILK": (1.0, False, 1.0),
        }
        self.assertEqual(_selected_product(self.control, rows), "CARROT")
        self.assertEqual(_selected_product(self.repaired, rows), "MILK")

    def test_negative_forced_candidate_alone_is_ineligible(self):
        rows = {"CARROT": (-5.0, True, -5.0)}
        self.assertEqual(_selected_product(self.control, rows), "CARROT")
        self.assertIsNone(_selected_product(self.repaired, rows))

    def test_positive_forced_candidate_can_win_on_gain_not_boolean_priority(self):
        rows = {
            "CARROT": (2.0, True, 0.0),
            "MILK": (1.0, False, 1.0),
        }
        self.assertEqual(_selected_product(self.repaired, rows), "CARROT")

    def test_forced_candidate_requires_nonnegative_own_floor(self):
        rows = {
            "CARROT": (2.0, True, -1.0),
            "MILK": (1.0, False, 1.0),
        }
        self.assertEqual(_selected_product(self.repaired, rows), "MILK")


if __name__ == "__main__":
    unittest.main()
