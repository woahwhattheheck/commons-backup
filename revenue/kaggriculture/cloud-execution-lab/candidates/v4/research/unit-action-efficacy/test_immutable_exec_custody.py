# SPDX-License-Identifier: Apache-2.0
"""Immutable execution-custody regressions for UNITWASTE."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import types
import sys
import unittest
from unittest.mock import patch

import unit_action_efficacy as u


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def blob(raw: bytes) -> str:
    return u.git_blob_sha(raw)


class ImmutableExecCustodyTests(unittest.TestCase):
    def fixture(self, root: Path):
        files = {
            "checks/reference/engine/kaggriculture.py": b"ENGINE_MARKER = 'captured-engine'\n",
            "checks/test_engine_semantics.py": (
                b"class EngineSemantics:\n"
                b"    @classmethod\n"
                b"    def setUpClass(cls):\n"
                b"        cls.engine = 'captured-engine'\n"
                b"        cls.ev = 'captured-ev'\n"
            ),
            "main.py": b"MARKER = 'captured-main'\n",
        }
        for name, raw in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        manifest = {
            "runtime": {
                name: {"source_path": name, "sha256": sha(raw), "bytes": len(raw)}
                for name, raw in files.items()
            }
        }
        manifest_raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (root / "SOURCE.json").write_bytes(manifest_raw)
        return manifest_raw, files

    def pins(self, manifest_raw, files):
        return patch.multiple(
            u,
            SOURCE_SHA256=sha(manifest_raw),
            ENGINE_GIT_BLOB=blob(files["checks/reference/engine/kaggriculture.py"]),
            MAIN_GIT_BLOB=blob(files["main.py"]),
        )

    def test_post_capture_path_swap_cannot_change_executed_fixture_or_main(self):
        with tempfile.TemporaryDirectory() as d:
            package = Path(d) / "package"
            package.mkdir()
            manifest_raw, files = self.fixture(package)
            with self.pins(manifest_raw, files):
                captured_manifest, captured = u.capture_runtime(package)
                (package / "checks/test_engine_semantics.py").write_text("raise RuntimeError('attacker helper')\n")
                (package / "checks/reference/engine/kaggriculture.py").write_text("raise RuntimeError('attacker engine')\n")
                (package / "main.py").write_text("raise RuntimeError('attacker main')\n")
                frozen = Path(d) / "frozen"
                u.materialize_runtime(frozen, captured_manifest, captured)
                engine, ev, main = u._load_captured_fixture(frozen)
            self.assertEqual(engine, "captured-engine")
            self.assertEqual(ev, "captured-ev")
            self.assertEqual(main.MARKER, "captured-main")

    def test_runtime_hash_drift_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            package = Path(d)
            manifest_raw, files = self.fixture(package)
            (package / "main.py").write_bytes(b"DRIFT = True\n")
            with self.pins(manifest_raw, files):
                with self.assertRaisesRegex(ValueError, "SOURCE.json: main.py"):
                    u.capture_runtime(package)

    def test_symlinked_runtime_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            package = Path(d) / "package"
            package.mkdir()
            manifest_raw, files = self.fixture(package)
            outside = Path(d) / "outside.py"
            outside.write_bytes(files["main.py"])
            (package / "main.py").unlink()
            (package / "main.py").symlink_to(outside)
            with self.pins(manifest_raw, files):
                with self.assertRaisesRegex(ValueError, "symlink runtime member"):
                    u.capture_runtime(package)

    def test_unsafe_manifest_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            package = Path(d)
            bad = b"x"
            manifest = {
                "runtime": {
                    "../escape.py": {
                        "source_path": "../escape.py",
                        "sha256": sha(bad),
                        "bytes": len(bad),
                    }
                }
            }
            raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
            (package / "SOURCE.json").write_bytes(raw)
            with patch.object(u, "SOURCE_SHA256", sha(raw)):
                with self.assertRaisesRegex(ValueError, "unsafe runtime member"):
                    u.capture_runtime(package)

    def test_manifest_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            package = Path(d)
            manifest_raw, files = self.fixture(package)
            (package / "SOURCE.json").write_text("{}\n")
            with self.pins(manifest_raw, files):
                with self.assertRaisesRegex(ValueError, "SOURCE.json SHA256 mismatch"):
                    u.capture_runtime(package)

    def test_preloaded_runtime_module_outside_system_fails_closed(self):
        attacker = types.ModuleType("scheduler")
        attacker.__file__ = "/tmp/unitwaste-attacker/scheduler.py"
        previous = sys.modules.get("scheduler")
        sys.modules["scheduler"] = attacker
        try:
            with self.assertRaisesRegex(ValueError, "preloaded runtime module escapes frozen custody"):
                u._reject_preloaded_runtime_modules({"scheduler.py": b"captured\n"})
        finally:
            if previous is None:
                sys.modules.pop("scheduler", None)
            else:
                sys.modules["scheduler"] = previous

    def test_preloaded_runtime_module_under_system_prefix_fails_closed(self):
        attacker = types.ModuleType("scheduler")
        attacker.__file__ = str(
            Path(sys.prefix).resolve() / "lib/python3.12/site-packages/scheduler.py"
        )
        previous = sys.modules.get("scheduler")
        sys.modules["scheduler"] = attacker
        try:
            with self.assertRaisesRegex(
                ValueError, "preloaded runtime module escapes frozen custody"
            ):
                u._reject_preloaded_runtime_modules({"scheduler.py": b"captured\n"})
        finally:
            if previous is None:
                sys.modules.pop("scheduler", None)
            else:
                sys.modules["scheduler"] = previous

    def test_fixture_import_path_excludes_ambient_repo_and_restores_after_close(self):
        with tempfile.TemporaryDirectory() as d:
            package = Path(d) / "package"
            package.mkdir()
            ambient = Path(d) / "ambient"
            ambient.mkdir()
            manifest_raw, files = self.fixture(package)
            prior = list(sys.path)
            sys.path.insert(0, str(ambient))
            expected_restore = list(sys.path)
            try:
                with self.pins(manifest_raw, files):
                    _engine, _ev, _main, custody = u._load_fixture(package)
                    try:
                        self.assertNotIn(str(ambient), sys.path)
                        self.assertNotIn(str(Path(__file__).resolve().parent), sys.path)
                    finally:
                        custody.close()
                self.assertEqual(sys.path, expected_restore)
            finally:
                sys.path[:] = prior


if __name__ == "__main__":
    unittest.main()
