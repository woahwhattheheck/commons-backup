from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
TARGET = HERE / "bridge.py"


def load_target():
    spec = importlib.util.spec_from_file_location("titan_v31_v4_bridge_test_target", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ArchiveVersionBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_target()

    def _archive(self, path: Path, files: dict[str, bytes], *, symlink=None):
        with tarfile.open(path, "w:gz") as archive:
            for name, payload in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            if symlink is not None:
                info = tarfile.TarInfo(symlink)
                info.type = tarfile.SYMTYPE
                info.linkname = "main.py"
                archive.addfile(info)

    def test_exact_authorities_are_pinned(self):
        self.assertEqual(
            self.m.VERSIONS["v31"]["archive_sha256"],
            "5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361",
        )
        self.assertEqual(
            self.m.VERSIONS["v4"]["archive_sha256"],
            "4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b",
        )
        self.assertEqual(self.m.EXPECTED_CALLBACKS, 719)

    def test_helper_pin_matches_current_authenticated_snapshot_helper(self):
        kg_root = HERE.parents[3]
        helper = kg_root / self.m.HELPER
        self.assertTrue(helper.is_file(), helper)
        self.assertEqual(self.m.git_blob_id(helper), self.m.HELPER_GIT_BLOB)

    def test_archive_reader_allows_different_member_sets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            left = root / "left.tar.gz"
            right = root / "right.tar.gz"
            self._archive(left, {"main.py": b"x=1\n", "r04.py": b"pass\n"})
            self._archive(
                right,
                {"main.py": b"x=2\n", "frozen_selected.py": b"pass\n", "runtime.py": b"pass\n"},
            )
            left_members = self.m.archive_members(left)
            right_members = self.m.archive_members(right)
            self.assertEqual(set(left_members), {"main.py", "r04.py"})
            self.assertEqual(
                set(right_members), {"main.py", "frozen_selected.py", "runtime.py"}
            )

    def test_archive_reader_rejects_escape_and_links(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "bad.tar.gz"
            self._archive(bad, {"main.py": b"pass\n", "../escape.py": b"pass\n"})
            with self.assertRaisesRegex(ValueError, "Invalid archive path"):
                self.m.archive_members(bad)

            linked = root / "linked.tar.gz"
            self._archive(linked, {"main.py": b"pass\n"}, symlink="alias.py")
            with self.assertRaisesRegex(ValueError, "Non-file"):
                self.m.archive_members(linked)

    def test_archive_reader_requires_root_main(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "no-main.tar.gz"
            self._archive(path, {"pkg/main.py": b"pass\n"})
            with self.assertRaisesRegex(ValueError, "root main.py"):
                self.m.archive_members(path)

    def test_action_hash_is_canonical_and_first_divergence_is_exact(self):
        left = [{"market": [["SELL", "MILK", 3]], "farmer": {"b": 2, "a": 1}}, {"x": 1}]
        same = [{"farmer": {"a": 1, "b": 2}, "market": [["SELL", "MILK", 3]]}, {"x": 1}]
        right = [{"farmer": {"a": 1, "b": 2}, "market": [["SELL", "MILK", 3]]}, {"x": 2}]
        self.assertEqual(self.m.actions_sha256(left), self.m.actions_sha256(same))
        self.assertIsNone(self.m.first_divergence(left, same))
        diff = self.m.first_divergence(left, right)
        self.assertEqual(diff["step"], 1)
        self.assertEqual(diff["kind"], "action")
        self.assertEqual(diff["v31_action"], {"x": 1})
        self.assertEqual(diff["v4_action"], {"x": 2})

    def test_length_divergence_is_visible(self):
        diff = self.m.first_divergence([{"x": 1}], [{"x": 1}, {"x": 2}])
        self.assertEqual(
            diff,
            {
                "step": 1,
                "kind": "length",
                "v31_action_count": 1,
                "v4_action_count": 2,
            },
        )

    def test_wrong_archive_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fake.tar.gz"
            self._archive(path, {"main.py": b"pass\n"})
            with self.assertRaisesRegex(ValueError, "archive identity mismatch"):
                self.m.require_archive_identity("v31", path)


if __name__ == "__main__":
    unittest.main()
