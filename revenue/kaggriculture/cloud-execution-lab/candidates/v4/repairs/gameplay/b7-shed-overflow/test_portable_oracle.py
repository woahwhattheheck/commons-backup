#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real pinned B7 execution plus bounded-staging and no-execution-on-drift tests."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import warnings
import zipfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("b7_portable_testee", HERE / "run_portable_oracle.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


def fixture_root() -> Path:
    for root in (HERE, *HERE.parents):
        if (root / R.ORACLE).is_file() and (root / R.HELPER).is_file():
            return root
    raise RuntimeError("exact canonical B7 sources not found")


class PortableOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archives = [Path(x) for x in os.environ.get("B7_PORTABLE_TEST_ARTIFACTS", "").split(os.pathsep) if x]
        cls.inputs = R.collect(fixture_root(), archives)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="b7-portable-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.fill(self.inputs)

    def fill(self, mapping):
        for relative, payload in mapping.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}

    def archive(self, name, entries):
        path = self.base / name
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for member, payload in entries:
                zf.writestr(member, payload)
        return path

    def remove_dependencies(self):
        for relative in self.inputs:
            if relative not in (R.ORACLE, R.HELPER):
                (self.root / relative).unlink()

    def test_full_real_oracle_both_modes_and_input_identity(self):
        before = self.snapshot()
        result = R.run(self.root, [], "both")
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["normal_optimized_identical"])
        self.assertEqual(result["pins"], R.PINS)
        self.assertEqual(result["runs"]["normal"]["oracle"]["matrix"]["cells"], 128)
        self.assertEqual(result["runs"]["optimized"]["seed_resolver_calls"], 0)
        self.assertEqual(self.snapshot(), before)

    def test_real_execution_from_two_archives_with_old_runtime_ignored(self):
        self.remove_dependencies()
        before = self.snapshot()
        deps = {k: v for k, v in self.inputs.items() if k not in (R.ORACLE, R.HELPER)}
        first = self.archive("old.zip", [("older/titan_runtime.py", b"old runtime")]
                             + [("reference/" + Path(k).name, v) for k, v in deps.items()
                                if not k.endswith("titan_runtime.py")])
        second = self.archive("current.zip", [("current/titan_runtime.py", deps[R.LAB + "titan_runtime.py"])])
        result = R.run(self.root, [first, second], "both")
        self.assertTrue(result["normal_optimized_identical"])
        self.assertEqual(self.snapshot(), before)

    def test_each_of_six_changed_pins_rejects_before_execution(self):
        for relative, payload in self.inputs.items():
            with self.subTest(relative=relative), patch.object(R.subprocess, "run") as execute:
                path = self.root / relative
                path.write_bytes(payload + b"\n")
                try:
                    with self.assertRaises(R.PortableError):
                        R.run(self.root, [])
                    execute.assert_not_called()
                finally:
                    path.write_bytes(payload)

    def test_existing_wrong_runtime_not_masked_by_correct_archive(self):
        relative = R.LAB + "titan_runtime.py"
        (self.root / relative).write_bytes(b"wrong local runtime")
        archive = self.archive("good.zip", [("titan_runtime.py", self.inputs[relative])])
        with self.assertRaises(R.PortableError), patch.object(R.subprocess, "run") as execute:
            R.run(self.root, [archive])
        execute.assert_not_called()

    def test_missing_canonical_oracle_not_replaced_from_archive(self):
        (self.root / R.ORACLE).unlink()
        archive = self.archive("source.zip", [("current_engine_oracle.py", self.inputs[R.ORACLE])])
        with self.assertRaisesRegex(R.PortableError, "canonical source missing"):
            R.collect(self.root, [archive])

    def test_missing_dependencies_fail_closed(self):
        self.remove_dependencies()
        with self.assertRaisesRegex(R.PortableError, "missing pinned dependencies"):
            R.collect(self.root, [])

    def test_matching_zip_symlink_is_rejected(self):
        info = zipfile.ZipInfo("titan_runtime.py")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        path = self.archive("link.zip", [(info, b"target")])
        with self.assertRaises(R.PortableError):
            R.archive_bytes([path], {R.LAB + "titan_runtime.py"})

    def test_unsafe_archive_member_names_rejected(self):
        for name in ("../titan_runtime.py", "/titan_runtime.py", "a\\b/titan_runtime.py"):
            with self.subTest(name=name):
                path = self.archive("unsafe.zip", [(name, self.inputs[R.LAB + "titan_runtime.py"])])
                with self.assertRaises(R.PortableError):
                    R.archive_bytes([path], {R.LAB + "titan_runtime.py"})

    def test_oversized_candidate_rejected(self):
        path = self.archive("big.zip", [("titan_runtime.py", b"x" * (R.MAX_FILE_BYTES + 1))])
        with self.assertRaises(R.PortableError):
            R.archive_bytes([path], {R.LAB + "titan_runtime.py"})

    def test_member_count_bound(self):
        path = self.archive("many.zip", [(str(i), b"") for i in range(R.MAX_MEMBERS + 1)])
        with self.assertRaises(R.PortableError):
            R.archive_bytes([path], {R.LAB + "titan_runtime.py"})

    def test_identical_duplicate_members_allowed_without_extraction(self):
        relative = R.LAB + "titan_runtime.py"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            path = self.archive("duplicate.zip", [("titan_runtime.py", self.inputs[relative])] * 2)
        self.assertEqual(R.archive_bytes([path], {relative}), {relative: self.inputs[relative]})
        self.assertFalse((self.base / "titan_runtime.py").exists())

    def test_source_symlink_rejected(self):
        path = self.root / R.ORACLE
        other = self.base / "external.py"
        other.write_bytes(self.inputs[R.ORACLE])
        path.unlink()
        path.symlink_to(other)
        with self.assertRaisesRegex(R.PortableError, "symlink source"):
            R.collect(self.root, [])

    def test_directory_instead_of_source_rejected(self):
        path = self.root / R.HELPER
        path.unlink()
        path.mkdir()
        with self.assertRaises(R.PortableError):
            R.collect(self.root, [])

    def test_cli_wrong_root_exit_two_no_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = R.main(["--root", str(self.base / "absent")])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("B7_PORTABLE_FAIL", err.getvalue())

    def test_cli_corrupt_zip_exit_two_no_stdout(self):
        self.remove_dependencies()
        path = self.base / "bad.zip"
        path.write_bytes(b"not a zip")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = R.main(["--root", str(self.root), "--artifact", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")

    def test_child_timeout_exit_two_no_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(R.subprocess, "run", side_effect=subprocess.TimeoutExpired("child", 30)):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = R.main(["--root", str(self.root)])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")

    def test_child_failed_status_is_not_pass(self):
        result = types.SimpleNamespace(returncode=1, stderr="deliberate failure", stdout="{}")
        with patch.object(R.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(R.PortableError, "subprocess failed"):
                R.execute(self.base, False)

    def test_child_malformed_output_is_not_pass(self):
        for stdout in ("{}", "null", "[]", "not JSON"):
            result = types.SimpleNamespace(returncode=0, stderr="", stdout=stdout)
            with self.subTest(stdout=stdout), patch.object(R.subprocess, "run", return_value=result):
                with self.assertRaises(R.PortableError):
                    R.execute(self.base, False)

    def test_caller_kaggle_import_namespace_unchanged(self):
        package, utils = types.ModuleType("sentinel"), types.ModuleType("sentinel-utils")
        with patch.dict(sys.modules, {"kaggle_environments": package, "kaggle_environments.utils": utils}):
            result = R.run(self.root, [], "normal")
            self.assertEqual(result["status"], "PASS")
            self.assertIs(sys.modules["kaggle_environments"], package)
            self.assertIs(sys.modules["kaggle_environments.utils"], utils)
        self.assertIsNone(result["normal_optimized_identical"])

    def test_unknown_mode_rejected_before_execution(self):
        with patch.object(R.subprocess, "run") as execute:
            with self.assertRaises(R.PortableError):
                R.run(self.root, [], "unknown")
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
