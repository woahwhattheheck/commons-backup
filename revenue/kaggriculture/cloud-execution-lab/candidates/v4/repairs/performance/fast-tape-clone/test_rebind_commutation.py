import unittest
from pathlib import Path
import tempfile

import verify_rebind_commutation as v


class RebindCommutationTests(unittest.TestCase):
    def test_live_current_edge(self):
        report = v.verify()
        self.assertEqual(report["current_runtime_git_blob"], v.CURRENT_BLOB)
        self.assertEqual(report["fast_tape_output_git_blob"], v.COMBINED_BLOB)
        self.assertEqual(report["fast_tape_output_sha256"], v.COMBINED_SHA256)
        self.assertTrue(report["rebind_fixed_point"])
        self.assertFalse(report["full_diamond_checked"])
        self.assertFalse(report["decision_authority"])
        self.assertFalse(report["runtime_promoted"])
        self.assertFalse(report["feature_enabled"])

    def test_landed_transformer_identities(self):
        self.assertEqual(v.git_blob(v.PORT_TRANSFORMER.read_bytes()), v.PORT_TRANSFORMER_BLOB)
        self.assertEqual(v.git_blob(v.REBIND_TRANSFORMER.read_bytes()), v.REBIND_TRANSFORMER_BLOB)

    def test_wrong_current_runtime_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "titan_runtime.py"
            p.write_bytes(v.CURRENT_RUNTIME.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                v.verify(p)

    def test_wrong_baseline_refuses_before_claiming_diamond(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "baseline.py"
            p.write_bytes(b"not the canonical b952 runtime\n")
            with self.assertRaises(ValueError):
                v.verify(baseline_runtime=p)

    def test_exact_hash_constants(self):
        for value in (
            v.BASELINE_BLOB, v.CURRENT_BLOB, v.LEGACY_FAST_BLOB, v.COMBINED_BLOB,
            v.PORT_TRANSFORMER_BLOB, v.REBIND_TRANSFORMER_BLOB,
        ):
            self.assertRegex(value, r"^[0-9a-f]{40}$")
        self.assertRegex(v.COMBINED_SHA256, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
