from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

import native_census as census


def _runtime_row(member: str, data: bytes) -> dict:
    return {
        "source_path": member,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _write_package(root: Path, files: dict[str, bytes], *, runtime_override=None) -> None:
    for member, data in files.items():
        target = root / member
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    runtime = (
        runtime_override
        if runtime_override is not None
        else {member: _runtime_row(member, data) for member, data in files.items()}
    )
    manifest = {
        "entrypoint": "main.py::agent",
        "config": "TITAN-CONFIG.json",
        "runtime": runtime,
    }
    (root / "SOURCE.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _minimal_files() -> dict[str, bytes]:
    return {
        "main.py": b"MARKER='original-main'\ndef agent(observation, configuration=None):\n    return MARKER\n",
        "TITAN-CONFIG.json": b"{}\n",
        "checks/reference/engine/kaggriculture.py": b"ENGINE_MARKER='original-engine'\n",
        "checks/test_engine_semantics.py": (
            b"class _EV:\n    pass\n"
            b"class EngineSemantics:\n"
            b"    @classmethod\n"
            b"    def setUpClass(cls):\n"
            b"        cls.engine='original-engine'\n"
            b"        cls.ev=_EV\n"
        ),
    }


def _capture_synthetic(package: Path):
    return census._capture_native_runtime(
        package, required_git_blobs={}, required_source_sha256=None
    )


class NativeCensusImmutableCustodyTests(unittest.TestCase):
    def test_admission_helper_executes_captured_bytes_after_path_replacement(self):
        canonical = (census.HERE / "unit_pipeline_admission.py").read_bytes()
        self.assertEqual(census.git_blob_sha(canonical), census.ADMISSION_GIT_BLOB)
        with tempfile.TemporaryDirectory() as td:
            helper = Path(td) / "unit_pipeline_admission.py"
            helper.write_bytes(canonical)
            captured, function = census._load_admission_snapshot(helper)
            self.assertEqual(captured, canonical)
            helper.write_text("raise RuntimeError('attacker helper reopened')\n", encoding="utf-8")
            selected = {"farmer": ["PASS"], "hands": [], "market": []}
            result, report = function({}, selected, enabled=False)
            self.assertEqual(result, selected)
            self.assertFalse(report["changed"])
            self.assertEqual(report["refusals"], {"disabled": 1})

    def test_source_identity_blocks_self_consistent_runtime_rebinding(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            files["scheduler.py"] = b"ORIGINAL = True\n"
            _write_package(package, files)
            files["scheduler.py"] = b"ATTACKER = True\n"
            _write_package(package, files)
            with self.assertRaisesRegex(ValueError, "SOURCE.json SHA-256 mismatch"):
                census._capture_native_runtime(package, required_git_blobs={})

    def test_runtime_capture_survives_source_path_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            files["declared.txt"] = b"declared-original\n"
            _write_package(package, files)
            capture = _capture_synthetic(package)
            for member in files:
                (package / member).write_bytes(b"attacker-replacement\n")
            frozen = census._materialize_frozen_runtime(capture)
            for member, expected in files.items():
                self.assertEqual((frozen / member).read_bytes(), expected)

    def test_fixture_imports_only_frozen_captured_main_and_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            _write_package(package, files)
            capture = _capture_synthetic(package)
            (package / "main.py").write_text("raise RuntimeError('live main reopened')\n", encoding="utf-8")
            (package / "checks/test_engine_semantics.py").write_text(
                "raise RuntimeError('live fixture reopened')\n", encoding="utf-8"
            )
            (package / "checks/reference/engine/kaggriculture.py").write_text(
                "raise RuntimeError('live engine reopened')\n", encoding="utf-8"
            )
            original_path = list(sys.path)
            try:
                engine, _ev, main = census._load_fixture_from_capture(capture)
                self.assertEqual(engine, "original-engine")
                self.assertEqual(main.agent(None, None), "original-main")
                self.assertIn("titan-unitpipe-frozen-", str(Path(main.__file__).parent))
            finally:
                sys.path[:] = original_path

    def test_preloaded_lazy_runtime_module_fails_before_frozen_execution(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            files["main.py"] = (
                b"def agent(observation, configuration=None):\n"
                b"    from titan_runtime import MARKER\n"
                b"    return MARKER\n"
            )
            files["titan_runtime.py"] = b"MARKER='FROZEN'\n"
            _write_package(package, files)
            capture = _capture_synthetic(package)
            attacker = types.ModuleType("titan_runtime")
            attacker.__file__ = str(Path(td) / "ambient-titan_runtime.py")
            attacker.MARKER = "AMBIENT"
            previous = sys.modules.get("titan_runtime")
            sys.modules["titan_runtime"] = attacker
            try:
                with self.assertRaisesRegex(
                    ValueError, "declared runtime module is already loaded before frozen execution"
                ):
                    census._load_fixture_from_capture(capture)
            finally:
                if previous is None:
                    sys.modules.pop("titan_runtime", None)
                else:
                    sys.modules["titan_runtime"] = previous

    def test_undeclared_file_never_enters_frozen_tree(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            _write_package(package, files)
            (package / "rogue.py").write_text("raise RuntimeError('undeclared authority')\n", encoding="utf-8")
            capture = _capture_synthetic(package)
            frozen = census._materialize_frozen_runtime(capture)
            self.assertFalse((frozen / "rogue.py").exists())
            self.assertNotIn("rogue.py", capture["runtime"])

    def test_runtime_member_hash_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            runtime = {member: _runtime_row(member, data) for member, data in files.items()}
            runtime["main.py"] = dict(runtime["main.py"])
            runtime["main.py"]["sha256"] = "0" * 64
            _write_package(package, files, runtime_override=runtime)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                census._capture_native_runtime(
                    package, required_git_blobs={}, required_source_sha256=None
                )

    def test_runtime_member_symlink_fails_closed(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            package = base / "native"
            package.mkdir()
            files = _minimal_files()
            _write_package(package, files)
            target = base / "outside-main.py"
            target.write_bytes(files["main.py"])
            (package / "main.py").unlink()
            (package / "main.py").symlink_to(target)
            with self.assertRaises((OSError, ValueError)):
                census._capture_native_runtime(
                    package, required_git_blobs={}, required_source_sha256=None
                )

    def test_unsafe_runtime_member_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            runtime = {member: _runtime_row(member, data) for member, data in files.items()}
            runtime["../escape.py"] = _runtime_row("../escape.py", b"escape\n")
            _write_package(package, files, runtime_override=runtime)
            with self.assertRaisesRegex(ValueError, "unsafe runtime member path"):
                census._capture_native_runtime(
                    package, required_git_blobs={}, required_source_sha256=None
                )

    def test_duplicate_source_json_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            _write_package(package, files)
            (package / "SOURCE.json").write_text(
                '{"entrypoint":"main.py::agent","config":"TITAN-CONFIG.json",'
                '"runtime":{},"runtime":{}}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                census._capture_native_runtime(
                    package, required_git_blobs={}, required_source_sha256=None
                )

    def test_runtime_row_extra_authority_field_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "native"
            package.mkdir()
            files = _minimal_files()
            runtime = {member: _runtime_row(member, data) for member, data in files.items()}
            runtime["main.py"] = {**runtime["main.py"], "authority": True}
            _write_package(package, files, runtime_override=runtime)
            with self.assertRaisesRegex(ValueError, "unexpected shape"):
                census._capture_native_runtime(
                    package, required_git_blobs={}, required_source_sha256=None
                )


if __name__ == "__main__":
    unittest.main()
