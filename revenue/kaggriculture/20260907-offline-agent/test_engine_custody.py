# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "offline_engine_custody_under_test", HERE / "evaluate.py"
)
loader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loader)


def _blob(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _fixture():
    utils = b"""from typing import Any, Callable\nimport random\n\ndef resolve_episode_seed(env):\n    return 7\n"""
    spec = b'{"configuration":{"episodeSteps":{"default":3},"turnsPerDay":{"default":1}}}\n'
    engine = b"""import json\nfrom os import path\nfrom kaggle_environments.utils import resolve_episode_seed\nwith open(path.join(path.dirname(__file__), "kaggriculture.json")) as stream:\n    specification = json.load(stream)\ndef interpreter(state, env):\n    return None\ndef starter_agent(obs):\n    return {}\n"""
    return {
        "kaggriculture.py": engine,
        "kaggriculture.json": spec,
        "utils.py": utils,
    }


class EngineCustodyTest(unittest.TestCase):
    def setUp(self):
        self.old_files = loader.ENGINE_FILES
        self.old_blobs = loader.ENGINE_BLOBS
        fixture = _fixture()
        loader.ENGINE_FILES = {
            name: "unused/" + name for name in fixture
        }
        loader.ENGINE_BLOBS = {name: _blob(raw) for name, raw in fixture.items()}
        self.fixture = fixture

    def tearDown(self):
        loader.ENGINE_FILES = self.old_files
        loader.ENGINE_BLOBS = self.old_blobs

    def _write_fixture(self, root: Path):
        for name, raw in self.fixture.items():
            (root / name).write_bytes(raw)

    def test_capture_is_single_read_and_independent_of_source_afterward(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_fixture(root)
            captured, hashes = loader.capture_engine_sources(root)
            (root / "kaggriculture.py").write_bytes(b"poison = True\n")
            (root / "utils.py").unlink()
            self.assertEqual(captured, self.fixture)
            self.assertEqual(
                hashes["kaggriculture.py"],
                hashlib.sha256(self.fixture["kaggriculture.py"]).hexdigest(),
            )

    def test_capture_rejects_wrong_blob(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_fixture(root)
            (root / "utils.py").write_bytes(b"def resolve_episode_seed(env): return 99\n")
            with self.assertRaisesRegex(ValueError, "Official engine source mismatch"):
                loader.capture_engine_sources(root)

    def test_capture_rejects_symlink_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_fixture(root)
            target = root / "real-utils.py"
            target.write_bytes(self.fixture["utils.py"])
            (root / "utils.py").unlink()
            try:
                (root / "utils.py").symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "ordinary file"):
                loader.capture_engine_sources(root)

    def test_capture_rejects_dangling_symlink_before_download(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_fixture(root)
            (root / "utils.py").unlink()
            try:
                (root / "utils.py").symlink_to(root / "missing-utils.py")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "dangling symlink"):
                loader.capture_engine_sources(root)
            self.assertFalse((root / "missing-utils.py").exists())

    def test_private_snapshot_uses_only_captured_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_fixture(root)
            captured, _ = loader.capture_engine_sources(root)
            (root / "kaggriculture.py").write_bytes(b"poison = True\n")
            custody, private = loader.private_engine_snapshot(captured)
            try:
                self.assertNotEqual(private.resolve(), root.resolve())
                for name, raw in self.fixture.items():
                    self.assertEqual((private / name).read_bytes(), raw)
            finally:
                custody.cleanup()

    def test_get_engine_retains_private_snapshot_after_source_swap_delete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_fixture(root)
            engine, hashes = loader.get_engine(root)
            private_engine_path = Path(engine.__file__).resolve()
            self.assertNotEqual(private_engine_path.parent, root.resolve())
            self.assertEqual(
                private_engine_path.read_bytes(), self.fixture["kaggriculture.py"]
            )
            (root / "kaggriculture.py").write_bytes(b"poison = True\n")
            (root / "utils.py").unlink()
            self.assertTrue(private_engine_path.exists())
            self.assertEqual(
                private_engine_path.read_bytes(), self.fixture["kaggriculture.py"]
            )
            self.assertEqual(engine.specification["configuration"]["episodeSteps"]["default"], 3)
            self.assertEqual(engine._engine_source_sha256, hashes)
            self.assertIsNotNone(engine._engine_source_custody)


if __name__ == "__main__":
    unittest.main()
