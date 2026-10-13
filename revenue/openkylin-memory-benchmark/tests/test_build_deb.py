from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "packaging" / "build_deb.py"
spec = importlib.util.spec_from_file_location("kylin_build_deb", MODULE_PATH)
build_deb = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build_deb)


class DebianPackageTests(unittest.TestCase):
    def _fixture(self, root: Path):
        for name, content in {
            "kylin_memory_bench.py": "print('baseline')\n",
            "memory_dynamics.py": "print('dynamics')\n",
            "README.md": "# Readme\n",
            "SUBMISSION.md": "# Submission\n",
        }.items():
            (root / name).write_text(content, encoding="utf-8")

    def test_package_is_deterministic_and_verifiable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            a = root / "a.deb"
            b = root / "b.deb"
            first = build_deb.build_package(root, a)
            second = build_deb.build_package(root, b)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(a.read_bytes(), b.read_bytes())
            verified = build_deb.verify_package(a)
            self.assertTrue(verified["valid"])
            self.assertEqual(verified["members"], ["debian-binary", "control.tar.gz", "data.tar.gz"])

    def test_package_changes_when_source_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            a = root / "a.deb"
            b = root / "b.deb"
            first = build_deb.build_package(root, a)
            (root / "memory_dynamics.py").write_text("print('changed')\n", encoding="utf-8")
            second = build_deb.build_package(root, b)
            self.assertNotEqual(first["sha256"], second["sha256"])

    def test_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            (root / "README.md").unlink()
            with self.assertRaisesRegex(ValueError, "missing package source"):
                build_deb.build_package(root, root / "x.deb")


if __name__ == "__main__":
    unittest.main()
