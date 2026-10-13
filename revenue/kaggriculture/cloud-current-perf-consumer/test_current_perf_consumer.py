# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import tempfile
import unittest

import compose_current as c


class CurrentPerfConsumerTests(unittest.TestCase):
    def test_git_blob_identity(self):
        self.assertEqual(c.git_blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_replace_once_rejects_ambiguous_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.py"
            path.write_text("x\nx\n")
            with self.assertRaises(ValueError):
                c._replace_once(path, "x", "y")

    def test_current_constants_are_successor_bound(self):
        self.assertEqual(c.CURRENT_ARCHIVE, "499989ab907331d4c0c990af2ab3703e6731dc83078964aca8563ea5a069e48e")
        self.assertEqual(c.CURRENT_RUNTIME_FILES, 83)
        self.assertEqual(c.TARGET_BLOBS["revenue/kaggriculture/cloud-execution-lab/build_integrated.py"],
                         "8ca5fcae2f49a14f1dc166ed8c1ca391a350e081")

    def test_real_checkout_plan_when_source_matches(self):
        repo = Path(__file__).resolve().parents[3]
        pointer = repo / c.POINTER
        if not pointer.exists():
            self.skipTest("not running inside Commons checkout")
        current = json.loads(pointer.read_text())
        if current.get("sha256") != c.CURRENT_ARCHIVE:
            self.skipTest("CURRENT advanced; composer correctly requires a rebase")
        patch, receipt = c.render_plan(repo)
        expected = set(c.TARGET_BLOBS)
        for rel in expected:
            self.assertIn(f"a/{rel}", patch)
            self.assertIn(f"b/{rel}", patch)
        self.assertIn("seller_snapshot import seller_public_observation", patch)
        self.assertIn("observed_clone import detached_json_value", patch)
        self.assertIn("plant_suffix import immutable_plant_suffixes", patch)
        self.assertIn("local_trace_lines", patch)
        self.assertIn("mapping['seller_snapshot.py']", patch)
        self.assertEqual(receipt["expected_runtime_files_after_canonical_build"], 86)
        self.assertFalse(receipt["canonical_mutated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
