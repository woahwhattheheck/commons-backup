import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

import build as builder


HERE = Path(__file__).resolve().parent


class BuildTests(unittest.TestCase):
    def exact_minimal_baseline(self, root):
        baseline = root / "baseline"
        baseline.mkdir()
        shutil.copyfile(builder.LAB_ROOT / "main.py", baseline / "main.py")
        return baseline

    def test_materializes_exact_parent_and_canonical_helper(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = self.exact_minimal_baseline(root)
            out = root / "candidate"
            receipt = builder.build_candidate(baseline, out)
            self.assertEqual(
                builder.git_blob(out / "baseline_main.py"),
                builder.EXPECTED_PARENT_MAIN_BLOB,
            )
            self.assertEqual(
                builder.git_blob(out / "animal_headroom_harvest.py"),
                builder.EXPECTED_HELPER_BLOB,
            )
            self.assertEqual(
                (out / "main.py").read_bytes(), builder.ENTRY_SOURCE.read_bytes()
            )
            self.assertNotEqual(
                receipt["control_package_sha256"],
                receipt["candidate_package_sha256"],
            )

    def test_rejects_parent_main_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = root / "baseline"
            baseline.mkdir()
            (baseline / "main.py").write_text("def agent(*_): return {}\n")
            with self.assertRaisesRegex(ValueError, "exact current V5 parent"):
                builder.build_candidate(baseline, root / "candidate")

    def test_rejects_nested_output_without_mutating_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = self.exact_minimal_baseline(root)
            marker = baseline / "marker.txt"
            marker.write_text("control\n")
            before = {
                path.relative_to(baseline).as_posix(): path.read_bytes()
                for path in sorted(baseline.rglob("*"))
                if path.is_file()
            }
            out = baseline / "candidate"
            with self.assertRaisesRegex(ValueError, "outside baseline root"):
                builder.build_candidate(baseline, out)
            self.assertFalse(out.exists())
            after = {
                path.relative_to(baseline).as_posix(): path.read_bytes()
                for path in sorted(baseline.rglob("*"))
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertEqual(
                builder.git_blob(baseline / "main.py"),
                builder.EXPECTED_PARENT_MAIN_BLOB,
            )

    def test_receipt_cannot_mutate_control_or_candidate_roots(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for placement in ("control", "candidate"):
                case = root / placement
                case.mkdir()
                baseline = self.exact_minimal_baseline(case)
                out = case / "candidate"
                receipt = (
                    baseline / "receipt.json"
                    if placement == "control"
                    else out / "receipt.json"
                )
                with self.assertRaisesRegex(ValueError, "outside package roots"):
                    builder.main(
                        [
                            "--baseline-root",
                            str(baseline),
                            "--out",
                            str(out),
                            "--receipt",
                            str(receipt),
                        ]
                    )
                self.assertFalse(out.exists())
                self.assertFalse(receipt.exists())
                self.assertEqual(
                    builder.git_blob(baseline / "main.py"),
                    builder.EXPECTED_PARENT_MAIN_BLOB,
                )

    def test_materialization_failure_removes_partial_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = self.exact_minimal_baseline(root)
            out = root / "candidate"
            original_copyfile = builder.shutil.copyfile

            def fail_entry_install(src, dst, *args, **kwargs):
                if Path(src).resolve() == builder.ENTRY_SOURCE.resolve():
                    raise RuntimeError("synthetic entry install failure")
                return original_copyfile(src, dst, *args, **kwargs)

            with mock.patch.object(
                builder.shutil, "copyfile", side_effect=fail_entry_install
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic entry"):
                    builder.build_candidate(baseline, out)
            self.assertFalse(out.exists())


class EntryTests(unittest.TestCase):
    def load_entry(self, baseline, helper):
        spec = importlib.util.spec_from_file_location(
            "animal_yield_cap_entry_test", HERE / "entry.py"
        )
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {"baseline_main": baseline, "animal_headroom_harvest": helper},
        ):
            spec.loader.exec_module(module)
        return module

    def test_uses_parent_canonical_identity_for_helper(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        changed = {"farmer": ["HARVEST"], "hands": [], "market": []}
        seen = {}
        baseline = types.ModuleType("baseline_main")
        baseline._canonical_entrypoint_observation = lambda obs, cfg: {
            "player": 0,
            "step": 23,
            "farms": obs["farms"],
            "private": obs["private"],
        }
        baseline.agent = lambda obs, cfg: action
        helper = types.ModuleType("animal_headroom_harvest")

        def plan(parent_action, observation, configuration):
            seen["plan_obs"] = observation
            self.assertIs(parent_action, action)
            return {"eligible": True, "reason": "provable_animal_product_clip"}

        def apply(parent_action, observation, configuration, *, enabled=False):
            seen["apply_obs"] = observation
            self.assertTrue(enabled)
            self.assertIs(parent_action, action)
            return changed

        helper.plan_animal_headroom_harvest = plan
        helper.apply_animal_headroom_harvest = apply
        module = self.load_entry(baseline, helper)
        obs = {"farms": [{"tiles": []}], "private": {}}
        self.assertIs(module.agent(obs, {}), changed)
        self.assertEqual(seen["plan_obs"], seen["apply_obs"])
        self.assertEqual(seen["plan_obs"]["step"], 23)
        report = module.last_report()
        report["eligible"] = False
        self.assertTrue(module.last_report()["eligible"])

    def test_ineligible_helper_preserves_parent_action_identity(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        baseline = types.ModuleType("baseline_main")
        baseline._canonical_entrypoint_observation = lambda obs, cfg: obs
        baseline.agent = lambda obs, cfg: action
        helper = types.ModuleType("animal_headroom_harvest")
        helper.plan_animal_headroom_harvest = lambda *args: {
            "eligible": False,
            "reason": "no_provable_clipping_pass",
        }
        helper.apply_animal_headroom_harvest = mock.Mock(
            side_effect=AssertionError("ineligible path must not re-run helper apply")
        )
        module = self.load_entry(baseline, helper)
        self.assertIs(module.agent({"player": 0, "step": 0}, {}), action)
        helper.apply_animal_headroom_harvest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
