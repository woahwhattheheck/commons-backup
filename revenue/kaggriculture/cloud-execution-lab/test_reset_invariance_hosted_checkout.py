# SPDX-License-Identifier: Apache-2.0
"""Hosted reset-invariance checkout must include attributed package siblings.

GitHub Actions run 34671866030 (titan-reset-invariance, SHA
ac14e749cf7cc9f3ccc2f61c188bb0c87213aafd) failed in 0s at
``python3 -B build_integrated.py --check``:

    FileNotFoundError: .../cloud-execution-lab/../cloud-quickstep/seller_snapshot.py

The job sparse-checked out only cloud-execution-lab. The canonical builder
reads attributed siblings from cloud-quickstep, cloud-runtime-pulse,
cloud-opponent-league, cloud-committed-seed-retry, and cloud-economic-stress.
A lab-only copy also cannot import seller_snapshot / observed_clone under
``python3 -I``. This contract does not require the packaged tarball or a
full episode.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_worker_reset as reset

LAB = Path(__file__).resolve().parent
WORKFLOW = LAB.parents[2] / ".github/workflows/titan-reset-invariance.yml"
QUICKSTEP = LAB.parent / "cloud-quickstep"
PULSE = LAB.parent / "cloud-runtime-pulse"
REPO_LAB = "revenue/kaggriculture/cloud-execution-lab"
FAILED_SPARSE = (
    "/.github/workflows/titan-reset-invariance.yml",
    "/revenue/kaggriculture/cloud-execution-lab/",
)


def parse_sparse_checkout(text: str) -> list[str]:
    """Return the non-cone sparse-checkout patterns from the hosted workflow."""
    lines = text.splitlines()
    patterns: list[str] = []
    capturing = False
    for line in lines:
        if line.strip() == "sparse-checkout: |":
            capturing = True
            continue
        if capturing:
            if line.startswith("            ") and line.strip():
                patterns.append(line.strip())
                continue
            break
    if not patterns:
        raise AssertionError("workflow has no sparse-checkout patterns")
    return patterns


def uncovered_mapped_sources(patterns: list[str], lab: Path | None = None) -> list[str]:
    """Return source_files() origins not covered by sparse-checkout patterns."""
    lab = Path(lab or LAB).resolve()
    normalized = []
    for pattern in patterns:
        item = pattern[1:] if pattern.startswith("/") else pattern
        normalized.append(item)
    missing = []
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    from build_integrated import source_files

    for member, source in source_files().items():
        origin = (lab / source).resolve()
        try:
            relative = origin.relative_to(lab.parents[2]).as_posix()
        except ValueError:
            relative = f"{REPO_LAB}/{source}"
        if any(
            relative == item.rstrip("/")
            or relative.startswith(item if item.endswith("/") else item + "/")
            for item in normalized
        ):
            continue
        missing.append(f"{member} <- {source}")
    return missing


class HostedResetCheckoutContracts(unittest.TestCase):
    def test_lab_only_sparse_checkout_misses_seller_snapshot(self):
        missing = uncovered_mapped_sources(list(FAILED_SPARSE))
        self.assertTrue(missing)
        self.assertTrue(any("seller_snapshot.py" in row for row in missing))
        self.assertTrue(any("observed_clone.py" in row for row in missing))

    def test_repaired_workflow_covers_all_mapped_sources(self):
        patterns = parse_sparse_checkout(WORKFLOW.read_text(encoding="utf-8"))
        self.assertIn("/revenue/kaggriculture/cloud-quickstep/", patterns)
        self.assertIn("/revenue/kaggriculture/cloud-runtime-pulse/", patterns)
        self.assertEqual(uncovered_mapped_sources(patterns), [])

    def test_attributed_root_modules_name_quickstep_and_pulse(self):
        mapping = reset.attributed_root_modules(LAB)
        self.assertEqual(
            mapping["seller_snapshot.py"],
            (QUICKSTEP / "seller_snapshot.py").resolve(),
        )
        self.assertEqual(
            mapping["observed_clone.py"],
            (PULSE / "observed_clone.py").resolve(),
        )

    def test_lab_only_copy_cannot_import_seller_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="titan-reset-lab-only-") as folder:
            dest = Path(folder) / "live"
            dest.mkdir()
            (dest / "frozen_selected.py").write_text(
                "from seller_snapshot import seller_public_observation\n",
                encoding="utf-8",
            )
            env = {
                "PATH": os.defpath,
                "HOME": folder,
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import sys; sys.path.insert(0, sys.argv[1]); import frozen_selected",
                    str(dest),
                ],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("seller_snapshot", result.stderr)

    @unittest.skipUnless(
        (QUICKSTEP / "seller_snapshot.py").is_file()
        and (PULSE / "observed_clone.py").is_file(),
        "attributed siblings are not in this checkout",
    )
    def test_materialize_live_worker_root_exposes_attributed_modules(self):
        with tempfile.TemporaryDirectory(prefix="titan-reset-live-") as folder:
            dest = Path(folder) / "live"
            reset.materialize_live_worker_root(LAB, dest)
            self.assertTrue((dest / "seller_snapshot.py").is_file())
            self.assertTrue((dest / "observed_clone.py").is_file())
            self.assertEqual(
                (dest / "seller_snapshot.py").read_bytes(),
                (QUICKSTEP / "seller_snapshot.py").read_bytes(),
            )
            self.assertEqual(
                (dest / "observed_clone.py").read_bytes(),
                (PULSE / "observed_clone.py").read_bytes(),
            )
            published = LAB / "runtime/integrated-selected/CURRENT-SOURCE.json"
            if published.is_file():
                self.assertEqual(
                    (dest / "SOURCE.json").read_bytes(),
                    published.read_bytes(),
                )
            env = {
                "PATH": os.defpath,
                "HOME": folder,
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import sys; sys.path.insert(0, sys.argv[1]); "
                    "from seller_snapshot import seller_public_observation; "
                    "from observed_clone import detached_json_value; "
                    "assert callable(seller_public_observation); "
                    "assert callable(detached_json_value)",
                    str(dest),
                ],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_materialize_live_worker_root_exposes_mapped_checks_reference(self):
        """Run 34690162038: a real lab checks/ hid mapped raw-loader helpers.

        ``materialize_live_worker_root`` used to symlink ``checks -> .`` only
        when dest/checks was absent. The lab already has a real checks/
        directory, so the live worker then failed with FileNotFoundError on
        ``checks/reference/engine/utils.py`` after --materialize-live PASS.
        """
        self.assertTrue((LAB / "checks").is_dir())
        self.assertFalse((LAB / "checks").is_symlink())
        self.assertFalse((LAB / "checks/reference/engine/utils.py").is_file())
        self.assertTrue((LAB / "reference/engine/utils.py").is_file())
        if str(LAB) not in sys.path:
            sys.path.insert(0, str(LAB))
        from build_integrated import source_files

        mapped = [
            "checks/reference/engine/utils.py",
            "checks/reference/evaluator/official_agent.py",
            "checks/reference/evaluator/evaluate.py",
            "checks/reference/evaluator/loader.py",
        ]
        mapping = source_files()
        with tempfile.TemporaryDirectory(prefix="titan-reset-live-checks-") as folder:
            dest = Path(folder) / "live"
            reset.materialize_live_worker_root(LAB, dest)
            for member in mapped:
                origin = (LAB / mapping[member]).resolve()
                target = dest / member
                self.assertTrue(target.is_file(), member)
                self.assertEqual(target.read_bytes(), origin.read_bytes(), member)
            self.assertTrue((dest / "seller_snapshot.py").is_file())
            self.assertTrue((dest / "checks/test_town_procurement.py").is_file())
            env = {
                "PATH": os.defpath,
                "HOME": folder,
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "from pathlib import Path; import ast, sys; "
                    "root = Path(sys.argv[1]); "
                    "path = root / 'checks/reference/engine/utils.py'; "
                    "tree = ast.parse(path.read_text(encoding='utf-8')); "
                    "names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}; "
                    "assert 'read_file' in names, names",
                    str(dest),
                ],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hosted_workflow_pins_deterministic_deadline_mode(self):
        """Offline reset proof must not depend on CI wall-clock cancellation jitter."""
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("test_worker_reset_deterministic.py", workflow)
        self.assertIn("deterministic-reset-oracle/no-wallclock-cancellation", workflow)
        self.assertNotIn('test_worker_reset.py" --worker', workflow)

    def test_prewarm_fail_closed_and_worker_thread_submit(self):
        source = Path(reset.__file__).read_text(encoding="utf-8")
        self.assertIn(
            'getattr(executor, "submit")(_prewarm_dynamic_modules, root)',
            source,
        )
        self.assertIn("_warmup_worker_act", source)
        self.assertNotIn("except Exception:\n                pass", source)
        self.assertTrue(hasattr(reset, "_IDENTITY_KEYS"))
        self.assertNotIn("within_episode_instance_discards", reset._IDENTITY_KEYS)
        self.assertIn("action_sha256", reset._IDENTITY_KEYS)
        self.assertIn("rewards", reset._IDENTITY_KEYS)

    def test_prewarm_loads_present_live_modules(self):
        with tempfile.TemporaryDirectory(prefix="titan-reset-prewarm-") as folder:
            dest = Path(folder) / "live"
            reset.materialize_live_worker_root(LAB, dest)
            if str(dest) not in sys.path:
                sys.path.insert(0, str(dest))
            loaded = reset._prewarm_dynamic_modules(dest)
        self.assertIn("sell_priority", loaded)
        self.assertIn("_titan_pressure_priority", loaded)
        self.assertIn("_titan_pressure_mechanics", loaded)

    def test_prewarm_present_file_load_failure_is_not_swallowed(self):
        with tempfile.TemporaryDirectory(prefix="titan-reset-prewarm-hostile-") as folder:
            dest = Path(folder)
            (dest / "pressure_priority.py").write_text("not a module", encoding="utf-8")
            (dest / "sell_priority.py").write_text("raise RuntimeError('hostile sell')\n", encoding="utf-8")
            (dest / "mechanics.py").write_text("# missing\n", encoding="utf-8")
            import types
            fake = types.ModuleType("titan_runtime")

            def boom(name, path, *, cache=False):
                raise RuntimeError(f"load failed {name}")

            fake.load = boom
            sys.modules["titan_runtime"] = fake
            try:
                with self.assertRaises(RuntimeError):
                    reset._prewarm_dynamic_modules(dest)
            finally:
                sys.modules.pop("titan_runtime", None)


if __name__ == "__main__":
    unittest.main()
