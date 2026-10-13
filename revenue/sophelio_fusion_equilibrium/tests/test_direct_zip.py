from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from toolkit import Prediction, compile_bundle  # noqa: E402


class DirectUploadContractTests(unittest.TestCase):
    def test_exact_two_npz_root_members(self):
        def pred(t: int) -> Prediction:
            return Prediction(
                np.zeros((t, 65, 65), dtype=np.float32),
                np.zeros(t, dtype=np.float32),
                np.zeros(t, dtype=np.float32),
            )
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            compile_bundle(out, [pred(2)], [2], [pred(3)], [3])
            with zipfile.ZipFile(out / "submission.zip", "r") as zf:
                self.assertEqual(
                    zf.namelist(),
                    ["diii_d_public_test.npz", "mast_public_test.npz"],
                )
                self.assertNotIn("manifest.json", zf.namelist())


if __name__ == "__main__":
    unittest.main(verbosity=2)
