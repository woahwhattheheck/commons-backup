from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from kaggle.package import build_bundle, notebook_object, scan_python, source_manifest
from kaggle.profile import run_profile
from kaggle.readiness import RuntimeLimits, evaluate_readiness


class PackagingTests(unittest.TestCase):
    def source_tree(self, root: Path):
        (root / "sage.py").write_text("def main():\n    return 1\n", encoding="utf-8")
        (root / "benchmark.py").write_text("print('ok')\n", encoding="utf-8")

    def test_manifest_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "src"; root.mkdir(); self.source_tree(root)
            self.assertEqual(source_manifest(root), source_manifest(root))
            self.assertEqual(source_manifest(root)["network_or_secret_findings"], [])

    def test_network_import_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.py"; path.write_text("import requests\n")
            self.assertIn("NETWORK_IMPORT:requests", scan_python(path))

    def test_secret_literal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.py"; path.write_text("api_key = '1234567890SECRET'\n")
            self.assertIn("SECRET_PATTERN", scan_python(path))

    def test_bundle_and_notebook_are_stable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "src"; root.mkdir(); self.source_tree(root)
            out1 = Path(td) / "out1"; out2 = Path(td) / "out2"
            m1 = build_bundle(root, out1); m2 = build_bundle(root, out2)
            self.assertEqual(m1, m2)
            self.assertEqual((out1 / "offline_submission.ipynb").read_bytes(), (out2 / "offline_submission.ipynb").read_bytes())
            self.assertEqual(json.loads((out1 / "source_manifest.json").read_text())["manifest_sha256"], m1["manifest_sha256"])

    def test_output_inside_source_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.source_tree(root)
            with self.assertRaises(ValueError):
                build_bundle(root, root / "bundle")

    def test_profile_success(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = run_profile([sys.executable, "-c", "print('ok')"], cwd=Path(td), timeout_seconds=5)
            self.assertEqual(receipt.returncode, 0)
            self.assertFalse(receipt.timed_out)
            self.assertGreaterEqual(receipt.wall_seconds, 0)

    def test_readiness_blocks_unknown_memory(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = run_profile([sys.executable, "-c", "pass"], cwd=Path(td), timeout_seconds=5)
            manifest = {"manifest_sha256": "x", "network_or_secret_findings": []}
            report = evaluate_readiness(manifest=manifest, profile=receipt, limits=RuntimeLimits(32400, None))
            self.assertEqual(report["state"], "BLOCKED")
            self.assertIn("DECLARED_MEMORY_LIMIT_UNKNOWN", report["blockers"])

    def test_readiness_can_be_green_with_explicit_limits(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = run_profile([sys.executable, "-c", "pass"], cwd=Path(td), timeout_seconds=5)
            manifest = {"manifest_sha256": "x", "network_or_secret_findings": []}
            report = evaluate_readiness(manifest=manifest, profile=receipt,
                                        limits=RuntimeLimits(max(10.0, receipt.wall_seconds * 10), max(1024.0, receipt.peak_rss_mib * 10)))
            self.assertEqual(report["state"], "READY_FOR_ACCOUNT_SIDE_SUBMISSION_STEPS")
            self.assertFalse(report["authority"]["kaggle_submit"])


if __name__ == "__main__":
    unittest.main()
