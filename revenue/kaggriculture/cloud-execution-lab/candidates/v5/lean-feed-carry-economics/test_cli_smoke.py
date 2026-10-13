from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import feed_carry_oracle as oracle
from test_feed_carry_oracle import document


class CliSmokeTests(unittest.TestCase):
    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "evidence.json"
            output = root / "out"
            source.write_text(json.dumps(document()), encoding="utf-8")
            self.assertEqual(
                oracle.main([str(source), "--out", str(output)]),
                0,
            )
            summary = json.loads(
                (output / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                summary["promotion"]["candidate_conclusion"],
                "PROMOTE_RESEARCH_CANDIDATE",
            )
            self.assertEqual(
                summary["promotion"]["conclusion"],
                "SOURCE_MODEL_BLOCKED",
            )
            self.assertFalse(summary["promotion"]["authority_verified"])
            self.assertEqual(summary["census"], [])
            self.assertEqual(summary["paired_deltas"], [])
            self.assertEqual(summary["runs"], [])
            self.assertFalse(summary["authority"]["promotion_authorized"])
            self.assertTrue((output / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
