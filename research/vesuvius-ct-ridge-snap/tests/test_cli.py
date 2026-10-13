from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import sha256_file, verify_bundle_bytes, verify_receipt  # noqa: E402


class CliTests(unittest.TestCase):
    def test_cli_end_to_end_and_repeatable_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            shape = (15, 15, 15)
            labels = np.zeros(shape, dtype=np.uint8)
            labels[6, 3:12, 3:12] = 1
            z = np.arange(shape[0], dtype=np.float32)[:, None, None]
            ct = np.broadcast_to(np.exp(-0.5 * ((z - 8.0) / 0.65) ** 2), shape).copy().astype(np.float32)
            np.save(work / "ct.npy", ct, allow_pickle=False)
            np.save(work / "labels.npy", labels, allow_pickle=False)
            manifest = {
                "format": "vesuvius-ct-ridge-snap/v1",
                "ct": {"kind": "npy", "path": "ct.npy", "sha256": sha256_file(work / "ct.npy")},
                "labels": {"kind": "npy", "path": "labels.npy", "sha256": sha256_file(work / "labels.npy")},
                "train_regions": [[[0, 4], [0, 4], [0, 4]]],
                "eval_regions": [[[10, 15], [10, 15], [10, 15]]],
            }
            (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            bundles = []
            for i in (1, 2):
                out = work / f"out{i}"
                cp = subprocess.run(
                    [sys.executable, str(ROOT / "run.py"), str(work / "manifest.json"), "--output", str(out)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                status = json.loads(cp.stdout)
                self.assertEqual(status["decision"], "REVIEW")
                receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
                self.assertTrue(verify_receipt(receipt))
                verify_bundle_bytes((out / "vesuvius-review-bundle.zip").read_bytes())
                self.assertFalse(receipt["raw_dataset059_execution_claim"])
                self.assertFalse(receipt["topology_preserved_claim"])
                bundles.append((out / "vesuvius-review-bundle.zip").read_bytes())
            self.assertEqual(bundles[0], bundles[1])


if __name__ == "__main__":
    unittest.main()
