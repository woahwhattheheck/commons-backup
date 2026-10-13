from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pack import build_zip, scan_source, verify_zip


class PackTests(unittest.TestCase):
    def _good(self, root: Path):
        (root / "main.py").write_text("print('offline')\n", encoding="utf-8")
        (root / "model_config.json").write_text('{"models": []}\n', encoding="utf-8")

    def test_deterministic_archive_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "src"; root.mkdir(); self._good(root)
            a = Path(td) / "a.zip"; b = Path(td) / "b.zip"
            ra = build_zip(root, a); rb = build_zip(root, b)
            self.assertEqual(ra["archive_sha256"], rb["archive_sha256"])
            self.assertEqual(ra["members"], rb["members"])
            verify_zip(a, ra)

    def test_requires_root_main(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "x.py").write_text("pass\n")
            with self.assertRaisesRegex(ValueError, "main.py"):
                scan_source(root)

    def test_rejects_network_client_and_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self._good(root)
            (root / "bad.py").write_text("import requests\nrequests.get('https://x')\n")
            with self.assertRaisesRegex(ValueError, "network"):
                scan_source(root)
            (root / "bad.py").write_text("API_KEY = 'super-secret-value'\n")
            with self.assertRaisesRegex(ValueError, "secret"):
                scan_source(root)

    def test_size_ceiling_and_hidden_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self._good(root)
            with self.assertRaisesRegex(ValueError, "size"):
                scan_source(root, max_bytes=1)
            (root / ".env").write_text("x")
            with self.assertRaisesRegex(ValueError, "hidden"):
                scan_source(root)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "src"; root.mkdir(); self._good(root)
            target = Path(td) / "outside.txt"; target.write_text("x")
            link = root / "weights.bin"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "symlink"):
                scan_source(root)


if __name__ == "__main__":
    unittest.main()
